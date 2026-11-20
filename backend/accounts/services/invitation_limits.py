import hashlib
import math
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.managers import clean_email
from accounts.models import InvitationEmailCounter, User

# Counters whose window started this long ago are deleted after the next reservation.
_PURGE_AFTER = timedelta(days=1)


class InvitationLimitError(Exception):
    """An invitation email limit is reached; try again in ``retry_after`` seconds."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"Invitation email limit reached, retry in {retry_after} seconds")
        self.retry_after = retry_after


def _key(scope: str, identity: str) -> str:
    return hashlib.sha256(f"{scope}:{identity}".encode()).hexdigest()


def reserve_invitation_email(*, sender: User, recipient: str) -> None:
    """Count one invitation email against the sender and the recipient, or refuse.

    Nothing is counted when either limit is full. Raises ``InvitationLimitError``.
    """
    limits = settings.INVITATION_EMAIL_LIMITS
    keys = {
        _key("sender", str(sender.pk)): limits["sender"],
        _key("recipient", clean_email(recipient)): limits["recipient"],
    }
    now = timezone.now()
    # A concurrent purge can delete a long-expired counter before it is locked. The next attempt
    # creates it again with a fresh window, which no purge deletes, so one retry per counter is
    # enough.
    for _ in range(len(keys) + 1):
        if _count(keys, now):
            break
    else:
        raise RuntimeError("Invitation email counters were deleted during every attempt")
    _purge_expired(now)


def _count(keys: dict[str, dict[str, int]], now: datetime) -> bool:
    """Count one email against every key; return False when a counter vanished before its lock."""
    with transaction.atomic():
        InvitationEmailCounter.objects.bulk_create(
            [InvitationEmailCounter(key=key, window_start=now) for key in keys],
            ignore_conflicts=True,
        )
        counters = list(
            InvitationEmailCounter.objects.select_for_update().filter(key__in=keys).order_by("key")
        )
        if len(counters) < len(keys):
            # Roll back to release the locks, so the retry cannot deadlock with another reservation.
            transaction.set_rollback(True)
            return False
        retry_after = 0
        for counter in counters:
            rule = keys[counter.key]
            window = timedelta(seconds=rule["window_seconds"])
            if counter.window_start + window <= now:
                counter.window_start = now
                counter.count = 0
            if counter.count >= rule["limit"]:
                remaining = (counter.window_start + window - now).total_seconds()
                retry_after = max(retry_after, math.ceil(remaining))
        if retry_after:
            # Expired windows are reset in memory only; the reset is saved with the next count.
            raise InvitationLimitError(retry_after)
        for counter in counters:
            counter.count += 1
        InvitationEmailCounter.objects.bulk_update(counters, ["window_start", "count"])
    return True


def _purge_expired(now: datetime) -> None:
    """Delete long-expired counters, skipping any that a running reservation has locked.

    The purge never waits for a lock, so it cannot deadlock with a reservation.
    """
    with transaction.atomic():
        expired = InvitationEmailCounter.objects.select_for_update(skip_locked=True).filter(
            window_start__lt=now - _PURGE_AFTER
        )
        InvitationEmailCounter.objects.filter(pk__in=expired.values("pk")).delete()
