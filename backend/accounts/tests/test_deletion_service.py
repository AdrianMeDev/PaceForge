import http.client
from datetime import date, timedelta
from typing import Any

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from django.contrib.sessions.models import Session
from django.test import Client
from django.utils import timezone

from accounts.models import User, UserInvitation
from accounts.services.deletion import (
    ConfirmationMismatchError,
    InvalidMfaCodeError,
    InvalidPasswordError,
    LastAdminError,
    MfaRequiredError,
    delete_account,
    verify_mfa_code,
)
from activities.models import Activity, ActivityFile
from chat.models import ChatMessage
from core.models import OwnedModel
from planning.models import PlannedWorkout, WeeklyPlan, WorkoutExport
from reviews.models import WorkoutReview
from season.models import SeasonPlanVersion

from .conftest import enable_totp, totp_code
from .test_export_service import make_user, populate

pytestmark = pytest.mark.django_db

PASSWORD = "export-test-password"


def owned_models() -> list[type[OwnedModel]]:
    return [m for m in OwnedModel.__subclasses__() if not m._meta.abstract]


def count_rows(user: User) -> int:
    return sum(m.objects.filter(owner=user).count() for m in owned_models())


def delete(user: User, **overrides: Any) -> None:
    arguments = {"password": PASSWORD, "confirmation": user.email, **overrides}
    delete_account(user, **arguments)


def sign_in(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Records every attempt to open an outbound HTTP connection and refuses it."""
    attempts: list[str] = []

    def refuse(self: http.client.HTTPConnection) -> None:
        attempts.append(self.host)
        raise AssertionError("no outbound request is allowed")

    monkeypatch.setattr(http.client.HTTPConnection, "connect", refuse)
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", refuse)
    return attempts


def test_a_member_is_deleted() -> None:
    user = make_user("member@example.com")

    delete(user)

    assert not User.objects.filter(email="member@example.com").exists()


def test_the_confirmation_ignores_case_and_surrounding_space() -> None:
    user = make_user("member@example.com")

    delete(user, confirmation="  Member@Example.com ")

    assert not User.objects.filter(pk=user.pk).exists()


def test_a_wrong_confirmation_is_refused() -> None:
    user = make_user("member@example.com")

    with pytest.raises(ConfirmationMismatchError):
        delete(user, confirmation="other@example.com")

    assert User.objects.filter(pk=user.pk).exists()


def test_a_wrong_password_is_refused() -> None:
    user = make_user("member@example.com")

    with pytest.raises(InvalidPasswordError):
        delete(user, password="wrong")

    assert User.objects.filter(pk=user.pk).exists()


def test_an_authenticator_code_allows_the_deletion() -> None:
    user = make_user("member@example.com")
    factor = enable_totp(user)

    delete(user, mfa_code=f" {totp_code(factor.secret)} ")

    assert not User.objects.filter(pk=user.pk).exists()


def test_a_recovery_code_allows_the_deletion() -> None:
    user = make_user("member@example.com")
    factor = enable_totp(user)

    delete(user, mfa_code=factor.recovery_codes[0])

    assert not User.objects.filter(pk=user.pk).exists()


def test_a_missing_code_is_refused_when_mfa_is_on() -> None:
    user = make_user("member@example.com")
    enable_totp(user)

    with pytest.raises(MfaRequiredError):
        delete(user)

    assert User.objects.filter(pk=user.pk).exists()


@pytest.mark.parametrize("code", ["000000", "not a code", "   "])
def test_a_wrong_code_is_refused_when_mfa_is_on(code: str) -> None:
    user = make_user("member@example.com")
    enable_totp(user)

    with pytest.raises((InvalidMfaCodeError, MfaRequiredError)):
        delete(user, mfa_code=code)

    assert User.objects.filter(pk=user.pk).exists()


def test_a_used_recovery_code_does_not_work_again() -> None:
    user = make_user("member@example.com")
    factor = enable_totp(user)
    code = factor.recovery_codes[0]

    assert verify_mfa_code(user, code)
    assert not verify_mfa_code(user, code)


def test_the_last_administrator_is_kept() -> None:
    admin = User.objects.create_superuser("admin@example.com", PASSWORD)
    User.objects.create_user("inactive@example.com", PASSWORD, is_staff=True, is_active=False)

    with pytest.raises(LastAdminError):
        delete(admin)

    assert User.objects.filter(pk=admin.pk).exists()


def test_an_administrator_can_go_when_another_active_one_remains() -> None:
    admin = User.objects.create_superuser("admin@example.com", PASSWORD)
    other = User.objects.create_superuser("second@example.com", PASSWORD)

    delete(admin)

    assert not User.objects.filter(pk=admin.pk).exists()
    assert User.objects.filter(pk=other.pk).exists()


def test_a_refused_deletion_leaves_the_data_and_sessions() -> None:
    admin = User.objects.create_superuser("admin@example.com", PASSWORD)
    populate(admin, "admin")
    sign_in(admin)
    rows = count_rows(admin)

    with pytest.raises(LastAdminError):
        delete(admin)

    assert count_rows(admin) == rows > 0
    assert Session.objects.count() == 1


def test_a_refused_deletion_does_not_consume_the_recovery_code() -> None:
    admin = User.objects.create_superuser("admin@example.com", PASSWORD)
    factor = enable_totp(admin)
    code = factor.recovery_codes[0]

    with pytest.raises(LastAdminError):
        delete(admin, mfa_code=code)

    User.objects.create_superuser("second@example.com", PASSWORD)
    delete(admin, mfa_code=code)

    assert not User.objects.filter(pk=admin.pk).exists()


def test_everything_of_the_user_is_deleted_and_nothing_of_others(no_network: list[str]) -> None:
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    factors = {}
    for user, tag in ((alice, "alice"), (bob, "bob")):
        populate(user, tag)
        EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
        factors[tag] = enable_totp(user)
        sign_in(user)
    bob_rows = count_rows(bob)
    assert count_rows(alice) == bob_rows > 0

    delete(alice, mfa_code=totp_code(factors["alice"].secret))

    assert not User.objects.filter(pk=alice.pk).exists()
    for model in owned_models():
        assert not model.objects.filter(owner_id=alice.pk).exists(), model
    assert not EmailAddress.objects.filter(user_id=alice.pk).exists()
    assert not Authenticator.objects.filter(user_id=alice.pk).exists()
    assert ActivityFile.objects.count() == 1
    assert count_rows(bob) == bob_rows
    assert EmailAddress.objects.filter(user=bob).count() == 1
    assert Authenticator.objects.filter(user=bob).count() == 2
    assert Session.objects.count() == 1
    assert Session.objects.get().get_decoded()["_auth_user_id"] == str(bob.pk)
    assert no_network == []


def test_expired_sessions_of_others_are_left_alone() -> None:
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    sign_in(alice)
    sign_in(bob)
    Session.objects.filter(session_key=sign_in(bob).session.session_key).update(
        expire_date=timezone.now() - timedelta(days=1)
    )

    delete(alice)

    assert Session.objects.count() == 2


def test_invitations_of_the_user_go_and_the_ones_to_others_stay() -> None:
    admin = User.objects.create_superuser("admin@example.com", PASSWORD)
    member = make_user("member@example.com")
    expires = timezone.now() + timedelta(days=7)
    UserInvitation.objects.create(
        email="member@example.com", token_hash="a" * 64, invited_by=admin, expires_at=expires
    )
    UserInvitation.objects.create(
        email="joined@example.com",
        token_hash="b" * 64,
        invited_by=admin,
        used_by=member,
        used_at=timezone.now(),
        expires_at=expires,
    )
    UserInvitation.objects.create(
        email="friend@example.com", token_hash="c" * 64, invited_by=member, expires_at=expires
    )
    UserInvitation.objects.create(
        email="other@example.com", token_hash="d" * 64, invited_by=admin, expires_at=expires
    )

    delete(member)

    assert sorted(UserInvitation.objects.values_list("email", flat=True)) == [
        "friend@example.com",
        "other@example.com",
    ]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("status", ["confirmed", "superseded", "discarded"])
def test_authenticated_deletion_removes_historical_workouts_and_exports(
    no_network: list[str],
    status: str,
) -> None:
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    for user, tag in ((alice, "alice"), (bob, "bob")):
        populate(user, tag)
        plan = WeeklyPlan.objects.get(owner=user)
        workout = plan.workouts.get()
        WorkoutExport.objects.create(
            owner=user,
            week_start=plan.week_start,
            workout=workout,
            external_id=tag,
            status="synced",
            event_id=1,
        )
        plan.status = status
        plan.confirmed_at = timezone.now() if status != "discarded" else None
        plan.save(update_fields=["status", "confirmed_at"])
    bob_rows = count_rows(bob)
    sign_in(alice)
    sign_in(bob)

    delete(alice)

    assert not User.objects.filter(pk=alice.pk).exists()
    for model in owned_models():
        assert not model.objects.filter(owner_id=alice.pk).exists(), model
    assert count_rows(bob) == bob_rows
    assert WeeklyPlan.objects.get(owner=bob).workouts.count() == 1
    assert WorkoutExport.objects.get(owner=bob).workout_id is not None
    assert Session.objects.get().get_decoded()["_auth_user_id"] == str(bob.pk)
    assert no_network == []


@pytest.mark.django_db(transaction=True)
def test_deletion_removes_guarded_season_history_and_linked_records(
    no_network: list[str],
) -> None:
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    now = timezone.now()
    for user, tag in ((alice, "alice"), (bob, "bob")):
        populate(user, tag)

        season_v1 = SeasonPlanVersion.objects.get(owner=user)
        season_v1.status = SeasonPlanVersion.Status.CONFIRMED
        season_v1.confirmed_at = now - timedelta(days=1)
        season_v1.save(update_fields=["status", "confirmed_at"])

        season_v2 = SeasonPlanVersion.objects.create(
            owner=user,
            version=2,
            parent=season_v1,
            request=f"Season v2 {tag}",
        )
        season_v1.status = SeasonPlanVersion.Status.SUPERSEDED
        season_v1.save(update_fields=["status"])
        season_v2.status = SeasonPlanVersion.Status.CONFIRMED
        season_v2.confirmed_at = now
        season_v2.save(update_fields=["status", "confirmed_at"])

        plan_one = WeeklyPlan.objects.get(owner=user)
        plan_one.status = WeeklyPlan.Status.CONFIRMED
        plan_one.confirmed_at = now
        plan_one.save(update_fields=["status", "confirmed_at"])

        plan_two = WeeklyPlan.objects.create(
            owner=user,
            week_start=date(2026, 3, 9),
            note=f"Week 2 {tag}",
        )
        workout_two = PlannedWorkout.objects.create(
            owner=user,
            plan=plan_two,
            day=date(2026, 3, 10),
            sport="cycling",
            title=f"Workout 2 {tag}",
            goal="tempo",
            duration_minutes=60,
        )
        plan_two.status = WeeklyPlan.Status.CONFIRMED
        plan_two.confirmed_at = now
        plan_two.save(update_fields=["status", "confirmed_at"])
        second_activity = Activity.objects.get(owner=user, source="intervals_icu")
        WorkoutReview.objects.create(
            owner=user,
            workout=workout_two,
            activity=second_activity,
            status=WorkoutReview.Status.DONE,
        )

        ChatMessage.objects.create(
            owner=user,
            role=ChatMessage.Role.COACH,
            text=f"Season message {tag}",
            season_plan=season_v2,
        )

    bob_rows = count_rows(bob)

    delete(alice)

    assert not User.objects.filter(pk=alice.pk).exists()
    for model in owned_models():
        assert not model.objects.filter(owner_id=alice.pk).exists(), model
    assert count_rows(bob) == bob_rows
    bob_v1 = SeasonPlanVersion.objects.get(owner=bob, version=1)
    bob_v2 = SeasonPlanVersion.objects.get(owner=bob, version=2)
    assert bob_v1.status == SeasonPlanVersion.Status.SUPERSEDED
    assert bob_v2.status == SeasonPlanVersion.Status.CONFIRMED
    assert bob_v2.parent_id == bob_v1.pk
    assert WeeklyPlan.objects.filter(owner=bob, status=WeeklyPlan.Status.CONFIRMED).count() == 2
    assert WorkoutReview.objects.filter(owner=bob, activity__isnull=False).count() == 2
    assert ChatMessage.objects.filter(owner=bob, plan__isnull=False).count() == 1
    assert ChatMessage.objects.filter(owner=bob, season_plan__isnull=False).count() == 1
    assert no_network == []
