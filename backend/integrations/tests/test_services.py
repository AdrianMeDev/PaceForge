from datetime import timedelta
from typing import Any

import pytest
from cryptography.fernet import Fernet
from django.utils import timezone

from accounts.models import User
from integrations.models import ProviderConnection
from integrations.services import NotConnectedError, record_sync_result

pytestmark = pytest.mark.django_db


def connection(owner: User) -> ProviderConnection:
    return ProviderConnection.objects.create(
        owner=owner,
        provider=ProviderConnection.Provider.INTERVALS_ICU,
        api_key="test-only-key",
        athlete_id="i100",
        last_sync_at=timezone.now() - timedelta(days=1),
        last_sync_error="unavailable",
    )


class TestRecordSyncResult:
    def test_success_moves_the_timestamp_and_clears_the_error(self, alice: User) -> None:
        stored = connection(alice)
        before = timezone.now()

        record_sync_result(alice)

        stored.refresh_from_db()
        assert stored.last_sync_at is not None
        assert before <= stored.last_sync_at <= timezone.now()
        assert stored.last_sync_error == ""

    @pytest.mark.parametrize("error", ["invalid_key", "unavailable", "unexpected"])
    def test_failure_keeps_the_last_success_time(self, alice: User, error: str) -> None:
        stored = connection(alice)
        last_success = stored.last_sync_at

        record_sync_result(alice, error=error)

        stored.refresh_from_db()
        assert stored.last_sync_at == last_success
        assert stored.last_sync_error == error

    def test_failure_before_the_first_success_keeps_a_null_time(self, alice: User) -> None:
        stored = connection(alice)
        stored.last_sync_at = None
        stored.save(update_fields=["last_sync_at"])

        record_sync_result(alice, error="unexpected")

        stored.refresh_from_db()
        assert stored.last_sync_at is None
        assert stored.last_sync_error == "unexpected"

    @pytest.mark.parametrize("error", ["", "invalid_key", "unavailable", "unexpected"])
    def test_only_the_own_sync_fields_change(
        self, alice: User, bob: User, settings: Any, error: str
    ) -> None:
        mine = connection(alice)
        theirs = connection(bob)
        own_fields = ("status", "connected_at", "last_checked_at", "athlete_id")
        before = ProviderConnection.objects.filter(pk=mine.pk).values(*own_fields).get()
        other_before = ProviderConnection.objects.filter(pk=theirs.pk).values().get()
        settings.ENCRYPTION_KEYS = [Fernet.generate_key().decode()]

        record_sync_result(alice, error=error)

        assert ProviderConnection.objects.filter(pk=mine.pk).values(*own_fields).get() == before
        # Read without the key: recording sync status also works after the instance key is lost.
        other_after = ProviderConnection.objects.filter(pk=theirs.pk).defer("api_key").get()
        assert other_after.last_sync_at == other_before["last_sync_at"]
        assert other_after.last_sync_error == other_before["last_sync_error"]
        assert other_after.last_checked_at == other_before["last_checked_at"]

    def test_unknown_error_text_is_refused_without_changing_state(self, alice: User) -> None:
        stored = connection(alice)
        before = ProviderConnection.objects.filter(pk=stored.pk).values().get()

        with pytest.raises(ValueError, match="Unknown sync error code"):
            record_sync_result(alice, error="raw provider response")

        assert ProviderConnection.objects.filter(pk=stored.pk).values().get() == before

    def test_no_connection_raises_and_cannot_change_another_users(
        self, alice: User, bob: User
    ) -> None:
        stored = connection(bob)
        before = ProviderConnection.objects.filter(pk=stored.pk).values().get()

        with pytest.raises(NotConnectedError):
            record_sync_result(alice)

        assert ProviderConnection.objects.filter(pk=stored.pk).values().get() == before
