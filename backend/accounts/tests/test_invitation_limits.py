from datetime import timedelta
from threading import Barrier, Event, Thread

import pytest
from django.db import connection, transaction
from django.test import override_settings
from django.utils import timezone

from accounts.models import InvitationEmailCounter, User
from accounts.services import invitation_limits
from accounts.services.invitation_limits import InvitationLimitError, reserve_invitation_email

LIMITS = {
    "sender": {"limit": 3, "window_seconds": 60},
    "recipient": {"limit": 2, "window_seconds": 3600},
}

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _limits():
    with override_settings(INVITATION_EMAIL_LIMITS=LIMITS):
        yield


def make_admin(name: str) -> User:
    return User.objects.create_user(email=f"{name}@admin.test", password="x", is_staff=True)


def counts() -> list[int]:
    return sorted(InvitationEmailCounter.objects.values_list("count", flat=True))


def test_sender_limit():
    admin = make_admin("a")
    for i in range(3):
        reserve_invitation_email(sender=admin, recipient=f"user{i}@example.com")
    with pytest.raises(InvitationLimitError) as exc:
        reserve_invitation_email(sender=admin, recipient="other@example.com")
    assert 0 < exc.value.retry_after <= 60
    # Another administrator is not affected.
    reserve_invitation_email(sender=make_admin("b"), recipient="other@example.com")


def test_recipient_limit_spans_administrators():
    first, second = make_admin("a"), make_admin("b")
    reserve_invitation_email(sender=first, recipient="ann@example.com")
    reserve_invitation_email(sender=second, recipient="ann@example.com")
    with pytest.raises(InvitationLimitError) as exc:
        reserve_invitation_email(sender=first, recipient="ann@example.com")
    assert 0 < exc.value.retry_after <= 3600


def test_recipient_case_and_spaces_share_a_counter():
    admin = make_admin("a")
    reserve_invitation_email(sender=admin, recipient=" Ann@Example.com ")
    reserve_invitation_email(sender=admin, recipient="ann@example.com")
    with pytest.raises(InvitationLimitError):
        reserve_invitation_email(sender=admin, recipient="ANN@example.com")


def test_new_window_after_expiry(monkeypatch):
    admin = make_admin("a")
    start = timezone.now()
    monkeypatch.setattr(invitation_limits.timezone, "now", lambda: start)
    for _ in range(2):
        reserve_invitation_email(sender=admin, recipient="ann@example.com")
    with pytest.raises(InvitationLimitError):
        reserve_invitation_email(sender=admin, recipient="ann@example.com")
    monkeypatch.setattr(invitation_limits.timezone, "now", lambda: start + timedelta(seconds=3601))
    reserve_invitation_email(sender=admin, recipient="ann@example.com")
    assert counts() == [1, 1]


def test_refusal_counts_nothing():
    admin = make_admin("a")
    for _ in range(2):
        reserve_invitation_email(sender=admin, recipient="ann@example.com")
    before = counts()
    with pytest.raises(InvitationLimitError):
        reserve_invitation_email(sender=admin, recipient="ann@example.com")
    assert counts() == before
    # The sender counter stayed at 2, so a different recipient still goes through.
    reserve_invitation_email(sender=admin, recipient="bob@example.com")


def test_counters_do_not_contain_the_address():
    admin = make_admin("a")
    reserve_invitation_email(sender=admin, recipient="ann@example.com")
    for counter in InvitationEmailCounter.objects.all():
        assert len(counter.key) == 64
        assert "ann" not in counter.key
        assert "example" not in str(counter.__dict__)


def test_long_expired_counters_are_deleted():
    admin = make_admin("a")
    old = InvitationEmailCounter.objects.create(
        key="0" * 64, window_start=timezone.now() - timedelta(days=3), count=1
    )
    reserve_invitation_email(sender=admin, recipient="ann@example.com")
    assert not InvitationEmailCounter.objects.filter(pk=old.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_counter_purged_before_its_lock_is_created_again(monkeypatch):
    admin = make_admin("a")
    reserve_invitation_email(sender=admin, recipient="ann@example.com")
    InvitationEmailCounter.objects.update(window_start=timezone.now() - timedelta(days=2))
    manager = InvitationEmailCounter.objects
    bulk_create = manager.bulk_create
    purged = Event()

    def purge_from_another_worker() -> None:
        try:
            cutoff = timezone.now() - timedelta(days=1)
            InvitationEmailCounter.objects.filter(window_start__lt=cutoff).delete()
        finally:
            connection.close()

    def bulk_create_then_purge(*args, **kwargs):
        created = bulk_create(*args, **kwargs)
        if not purged.is_set():
            # Another worker deletes both long-expired counters before this reservation locks them.
            worker = Thread(target=purge_from_another_worker)
            worker.start()
            worker.join()
            purged.set()
        return created

    monkeypatch.setattr(manager, "bulk_create", bulk_create_then_purge)
    reserve_invitation_email(sender=admin, recipient="ann@example.com")
    assert purged.is_set()
    assert counts() == [1, 1]


@pytest.mark.django_db(transaction=True)
def test_purge_does_not_wait_for_a_locked_counter():
    old = InvitationEmailCounter.objects.create(
        key="0" * 64, window_start=timezone.now() - timedelta(days=3), count=1
    )
    locked, done = Event(), Event()
    released_in_time = []

    def hold_lock() -> None:
        try:
            with transaction.atomic():
                InvitationEmailCounter.objects.select_for_update().get(pk=old.pk)
                locked.set()
                released_in_time.append(done.wait(timeout=5))
        finally:
            connection.close()

    holder = Thread(target=hold_lock)
    holder.start()
    assert locked.wait(timeout=5)
    reserve_invitation_email(sender=make_admin("a"), recipient="ann@example.com")
    done.set()
    holder.join()
    assert released_in_time == [True]
    assert InvitationEmailCounter.objects.filter(pk=old.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_reservations_let_exactly_one_through():
    from concurrent.futures import ThreadPoolExecutor

    admin = make_admin("a")
    for i in range(2):
        reserve_invitation_email(sender=admin, recipient=f"user{i}@example.com")
    barrier = Barrier(2)

    def attempt(recipient: str) -> bool:
        try:
            barrier.wait(timeout=10)
            reserve_invitation_email(sender=admin, recipient=recipient)
            return True
        except InvitationLimitError:
            return False
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["x@example.com", "y@example.com"]))
    assert sorted(results) == [False, True]
