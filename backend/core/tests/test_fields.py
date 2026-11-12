from typing import Any

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import FieldError
from django.db import connection

from core.encryption import PREFIX, DecryptionError, encrypt
from core.fields import EncryptedTextField
from core.tests.sample.models import Credential

pytestmark = pytest.mark.django_db

SECRET = "sk-test-0123456789-abcdef"


def stored(pk: int) -> str | None:
    """The value in the table, read around the ORM."""
    table = connection.ops.quote_name(Credential._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT secret FROM {table} WHERE id = %s", [pk])
        return cursor.fetchone()[0]


def raw_insert(value: str | None) -> int:
    table = connection.ops.quote_name(Credential._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {table} (label, secret) VALUES ('raw', %s) RETURNING id", [value]
        )
        return cursor.fetchone()[0]


class TestStorage:
    def test_the_table_holds_ciphertext_and_the_orm_gives_the_plaintext_back(self) -> None:
        pk = Credential.objects.create(secret=SECRET).pk

        raw = stored(pk)

        assert raw is not None and raw.startswith(PREFIX)
        assert SECRET not in raw
        assert Credential.objects.get(pk=pk).secret == SECRET

    @pytest.mark.parametrize("text", ["", " ", "ünï ✓ 日本語", "x" * 10_000, "line\nbreak"])
    def test_any_text_round_trips(self, text: str) -> None:
        pk = Credential.objects.create(secret=text).pk

        assert Credential.objects.get(pk=pk).secret == text

    def test_none_stays_null(self) -> None:
        pk = Credential.objects.create(secret=None).pk

        assert stored(pk) is None
        assert Credential.objects.get(pk=pk).secret is None

    def test_saving_a_new_value_replaces_the_ciphertext(self) -> None:
        credential = Credential.objects.create(secret=SECRET)
        before = stored(credential.pk)

        credential.secret = "another-value"
        credential.save()

        assert stored(credential.pk) != before
        assert Credential.objects.get(pk=credential.pk).secret == "another-value"

    def test_saving_the_same_value_again_gives_new_ciphertext(self) -> None:
        credential = Credential.objects.create(secret=SECRET)
        before = stored(credential.pk)

        credential.save()

        assert stored(credential.pk) != before
        assert Credential.objects.get(pk=credential.pk).secret == SECRET

    def test_a_value_can_be_cleared(self) -> None:
        credential = Credential.objects.create(secret=SECRET)

        credential.secret = None
        credential.save()

        assert stored(credential.pk) is None

    def test_it_is_encrypted_only_once(self) -> None:
        credential = Credential.objects.create(secret=SECRET)
        credential.save()
        credential.refresh_from_db()
        credential.save()

        assert Credential.objects.get(pk=credential.pk).secret == SECRET

    def test_update_and_bulk_create_encrypt_too(self) -> None:
        credential = Credential.objects.create(secret=None)
        Credential.objects.filter(pk=credential.pk).update(secret=SECRET)
        [created] = Credential.objects.bulk_create([Credential(secret="bulk-" + SECRET)])

        for pk in (credential.pk, created.pk):
            raw = stored(pk)
            assert raw is not None and raw.startswith(PREFIX)
            assert SECRET not in raw
        assert Credential.objects.get(pk=credential.pk).secret == SECRET

    def test_other_ways_of_reading_decrypt_as_well(self) -> None:
        pk = Credential.objects.create(secret=SECRET).pk

        assert list(Credential.objects.filter(pk=pk).values_list("secret", flat=True)) == [SECRET]
        assert Credential.objects.filter(pk=pk).values("secret").get() == {"secret": SECRET}
        credential = Credential.objects.defer("secret").get(pk=pk)
        credential.refresh_from_db(fields=["secret"])
        assert credential.secret == SECRET

    def test_the_text_is_not_part_of_the_default_representation(self) -> None:
        credential = Credential.objects.create(label="key", secret=SECRET)

        assert SECRET not in f"{credential} {credential!r}"


class TestLookups:
    @pytest.mark.parametrize(
        "lookup",
        ["secret", "secret__exact", "secret__contains", "secret__startswith", "secret__in"],
    )
    def test_the_value_cannot_be_searched(self, lookup: str) -> None:
        Credential.objects.create(secret=SECRET)
        argument: Any = [SECRET] if lookup.endswith("__in") else SECRET

        with pytest.raises(FieldError, match="cannot be searched"):
            list(Credential.objects.filter(**{lookup: argument}))

    def test_isnull_works_in_both_directions(self) -> None:
        with_value = Credential.objects.create(secret=SECRET)
        without = Credential.objects.create(secret=None)

        assert list(Credential.objects.filter(secret__isnull=True)) == [without]
        assert list(Credential.objects.filter(secret__isnull=False)) == [with_value]


class TestWhatCannotBeRead:
    def test_a_value_encrypted_with_another_key_is_not_returned(self, settings: Any) -> None:
        pk = Credential.objects.create(secret=SECRET).pk
        settings.ENCRYPTION_KEYS = [Fernet.generate_key().decode()]

        with pytest.raises(DecryptionError):
            Credential.objects.get(pk=pk)

    def test_the_old_key_still_works_behind_a_new_one(self, settings: Any) -> None:
        pk = Credential.objects.create(secret=SECRET).pk
        settings.ENCRYPTION_KEYS = [Fernet.generate_key().decode(), *settings.ENCRYPTION_KEYS]

        assert Credential.objects.get(pk=pk).secret == SECRET

    def test_a_clear_text_value_in_the_table_is_not_accepted(self) -> None:
        pk = raw_insert(SECRET)

        with pytest.raises(DecryptionError):
            Credential.objects.get(pk=pk)

    def test_a_damaged_value_is_not_accepted(self) -> None:
        pk = raw_insert(encrypt(SECRET)[:-6])

        with pytest.raises(DecryptionError):
            Credential.objects.get(pk=pk)

    def test_the_error_does_not_show_the_stored_text(self) -> None:
        pk = raw_insert(PREFIX + "not-a-token-" + SECRET)

        with pytest.raises(DecryptionError) as raised:
            Credential.objects.get(pk=pk)

        assert SECRET not in str(raised.value)


def test_the_field_is_described_by_its_import_path_in_migrations() -> None:
    _, path, _, _ = EncryptedTextField(null=True).deconstruct()

    assert path == "core.fields.EncryptedTextField"
