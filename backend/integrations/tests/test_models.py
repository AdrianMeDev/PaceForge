import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.forms.models import model_to_dict
from django.utils import timezone

from accounts.models import User
from core.encryption import PREFIX
from integrations.models import ProviderConnection

pytestmark = pytest.mark.django_db

KEY = "k3y-0123456789-abcdefghij"


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def connect(owner: User, key: str = KEY, athlete_id: str = "i100") -> ProviderConnection:
    return ProviderConnection.objects.create(
        owner=owner,
        provider=ProviderConnection.Provider.INTERVALS_ICU,
        api_key=key,
        athlete_id=athlete_id,
    )


def stored_key(connection_id: int) -> str:
    table = ProviderConnection._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT api_key FROM {table} WHERE id = %s", [connection_id])
        return cursor.fetchone()[0]


class TestOwnership:
    def test_a_user_has_one_connection_per_provider(self, alice: User) -> None:
        connect(alice)

        with pytest.raises(IntegrityError), transaction.atomic():
            connect(alice, key="another-key")

        assert ProviderConnection.objects.filter(owner=alice).count() == 1

    def test_every_user_may_connect_the_same_provider(self, alice: User, bob: User) -> None:
        connect(alice, athlete_id="i1")
        connect(bob, athlete_id="i2")

        assert ProviderConnection.objects.count() == 2

    def test_for_user_shows_only_the_own_connection(self, alice: User, bob: User) -> None:
        alices = connect(alice, athlete_id="i1")
        bobs = connect(bob, athlete_id="i2")

        assert list(ProviderConnection.objects.for_user(alice)) == [alices]
        assert list(ProviderConnection.objects.for_user(bob)) == [bobs]

    def test_anonymous_users_see_nothing(self, alice: User) -> None:
        connect(alice)

        assert not ProviderConnection.objects.for_user(AnonymousUser()).exists()

    def test_deleting_the_user_deletes_the_connection_and_its_key(self, alice: User) -> None:
        connection_id = connect(alice).pk

        alice.delete()

        assert not ProviderConnection.objects.filter(pk=connection_id).exists()


class TestTheKey:
    def test_it_is_ciphertext_in_the_table_and_plaintext_in_the_model(self, alice: User) -> None:
        created = connect(alice)

        raw = stored_key(created.pk)

        assert raw.startswith(PREFIX)
        assert KEY not in raw
        assert ProviderConnection.objects.get(pk=created.pk).api_key == KEY

    def test_replacing_it_replaces_the_ciphertext(self, alice: User) -> None:
        created = connect(alice)
        before = stored_key(created.pk)

        created.api_key = "a-new-key-value"
        created.save()

        assert stored_key(created.pk) != before
        assert ProviderConnection.objects.get(pk=created.pk).api_key == "a-new-key-value"

    def test_it_is_not_part_of_the_text_forms_of_the_object(self, alice: User) -> None:
        created = connect(alice)

        assert KEY not in str(created)
        assert KEY not in repr(created)

    def test_it_is_not_part_of_a_form_style_dictionary(self, alice: User) -> None:
        created = connect(alice)

        data = model_to_dict(created)

        assert "api_key" not in data
        assert KEY not in str(data)


class TestFields:
    def test_a_new_connection_is_connected_and_timestamped(self, alice: User) -> None:
        created = connect(alice)

        assert created.status == ProviderConnection.Status.CONNECTED
        assert created.connected_at is not None
        assert created.last_checked_at is not None
        assert created.last_sync_at is None
        assert created.last_sync_error == ""

    @pytest.mark.parametrize("error", ProviderConnection.SyncError.values)
    def test_sync_state_is_kept(self, alice: User, error: str) -> None:
        created = connect(alice)
        synced_at = timezone.now()
        created.last_sync_at = synced_at
        created.last_sync_error = error
        created.full_clean()
        created.save()

        created.refresh_from_db()
        assert created.last_sync_at == synced_at
        assert created.last_sync_error == error

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("provider", "garmin"),
            ("status", "broken"),
            ("athlete_id", ""),
            ("last_sync_error", "raw provider response"),
        ],
    )
    def test_unknown_values_are_not_valid(self, alice: User, field: str, value: str) -> None:
        created = ProviderConnection(
            owner=alice, provider="intervals_icu", api_key=KEY, athlete_id="i1"
        )
        setattr(created, field, value)

        with pytest.raises(ValidationError) as raised:
            created.full_clean()

        assert field in raised.value.message_dict

    def test_the_text_names_the_provider_and_the_owner_but_not_the_athlete(
        self, alice: User
    ) -> None:
        created = connect(alice, athlete_id="i424242")

        assert "Intervals.icu" in str(created)
        assert str(alice.pk) in str(created)
        assert "i424242" not in str(created)
