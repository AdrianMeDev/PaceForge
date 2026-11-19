"""Connecting, re-checking and removing a user's Intervals.icu connection.

Every function acts on the connection of the user it is given and on nothing else. The stored key
is decrypted only where it is needed to call Intervals.icu; reading the status or deleting the
connection never touches it, so they keep working even if the instance key was lost.
"""

from collections.abc import Callable

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from accounts.models import User
from core.encryption import DecryptionError
from integrations.intervals import IntervalsClient, InvalidKeyError
from integrations.models import ProviderConnection

PROVIDER = ProviderConnection.Provider.INTERVALS_ICU


class NotConnectedError(Exception):
    """The user has no Intervals.icu connection."""


def _own(user: User) -> QuerySet[ProviderConnection]:
    # The key stays encrypted (not even loaded) unless a caller asks for it.
    return ProviderConnection.objects.for_user(user).filter(provider=PROVIDER).defer("api_key")


def get_connection(user: User) -> ProviderConnection | None:
    return _own(user).first()


def connect(user: User, api_key: str) -> ProviderConnection:
    """Check ``api_key`` with Intervals.icu, then store it (replacing an earlier one).

    Raises the errors of ``IntervalsClient``; nothing is stored or changed when it does. The
    earlier key is never read, so a connection whose key can no longer be decrypted (the instance
    key was lost) can still be replaced.
    """
    athlete = IntervalsClient(api_key).get_athlete()
    for attempt in (1, 2):
        try:
            with transaction.atomic():
                connection = _own(user).select_for_update().first() or ProviderConnection(
                    owner=user, provider=PROVIDER
                )
                now = timezone.now()
                connection.api_key = api_key
                connection.athlete_id = athlete.id
                connection.status = ProviderConnection.Status.CONNECTED
                connection.connected_at = now
                connection.last_checked_at = now
                connection.last_sync_error = ""
                connection.save()
                return connection
        except IntegrityError:
            # A second request created the row first; the next round updates that one.
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def check(user: User) -> ProviderConnection:
    """Ask Intervals.icu whether the stored key still works and record the answer.

    A refused or unreadable key marks the connection ``invalid`` (it is kept, so the user sees
    that it needs attention). If Intervals.icu cannot be reached, the error is raised and the
    stored state stays as it was.
    """
    connection = _own(user).first()
    if connection is None:
        raise NotConnectedError
    try:
        client = IntervalsClient(connection.api_key)
        client.get_athlete()
    except DecryptionError, InvalidKeyError:
        _record(connection, ProviderConnection.Status.INVALID)
    else:
        _record(connection, ProviderConnection.Status.CONNECTED)
    return connection


def with_client[T](user: User, call: Callable[[IntervalsClient], T]) -> T:
    """Run ``call`` with a client that uses the user's own stored key, and return its result.

    Raises ``NotConnectedError`` if there is no connection. A key that Intervals.icu refuses, or
    that can no longer be decrypted, marks the connection ``invalid`` (as ``check`` does) and
    raises ``InvalidKeyError``. If Intervals.icu cannot be reached, the error is raised and the
    stored state stays as it was.
    """
    connection = _own(user).first()
    if connection is None:
        raise NotConnectedError
    try:
        return call(IntervalsClient(connection.api_key))
    except DecryptionError, InvalidKeyError:
        _record(connection, ProviderConnection.Status.INVALID)
        raise InvalidKeyError("The stored key is not usable.") from None


def disconnect(user: User) -> None:
    """Remove the connection and with it the key. Removing nothing is fine."""
    _own(user).delete()


def record_sync_result(user: User, *, error: str = "") -> None:
    """Record a sync's fixed error code, or its success time and clear an earlier error.

    A failure keeps the last successful sync time. This never needs to decrypt the stored key.
    """
    if error not in ProviderConnection.SyncError.values:
        raise ValueError("Unknown sync error code.")
    updates: dict[str, object] = {"last_sync_error": error}
    if not error:
        updates["last_sync_at"] = timezone.now()
    if not _own(user).update(**updates):
        raise NotConnectedError


def _record(connection: ProviderConnection, status: ProviderConnection.Status) -> None:
    connection.status = status
    connection.last_checked_at = timezone.now()
    fields = ["status", "last_checked_at"]
    if status == ProviderConnection.Status.CONNECTED:
        connection.last_sync_error = ""
        fields.append("last_sync_error")
    connection.save(update_fields=fields)
