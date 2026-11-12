import importlib
import json
from collections.abc import Iterator
from http import HTTPStatus
from io import StringIO
from typing import Any

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.adapter import get_adapter
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from cryptography.fernet import Fernet
from django.apps import apps as current_apps
from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from accounts.mfa_adapter import MFAAdapter
from accounts.models import User
from core.encryption import PREFIX, DecryptionError, decrypt, encrypt

from .conftest import PASSWORD, AuthApi, enable_totp, totp_code

TOTP_URL = "/account/authenticators/totp"
LEGACY_SECRET = "JBSWY3DPEHPK3PXP"
LEGACY_SEED = "ab12" * 20
EMAIL = "legacy@example.com"

migration = importlib.import_module("accounts.migrations.0003_encrypt_mfa_secrets")


def stored() -> dict[str, dict[str, Any]]:
    """What the database table holds, read around the ORM and the adapter."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT type, data FROM mfa_authenticator")
        rows = cursor.fetchall()
    return {t: (json.loads(d) if isinstance(d, str) else d) for t, d in rows}


def raw_text() -> str:
    return json.dumps(stored())


class TestTheAdapter:
    def test_it_is_the_adapter_allauth_uses(self) -> None:
        assert isinstance(get_adapter(), MFAAdapter)

    def test_it_encrypts_with_the_instance_key(self) -> None:
        adapter = MFAAdapter()

        value = adapter.encrypt(LEGACY_SECRET)

        assert value.startswith(PREFIX)
        assert LEGACY_SECRET not in value
        assert adapter.decrypt(value) == LEGACY_SECRET


@pytest.mark.django_db
class TestNewAuthenticators:
    def test_the_authenticator_app_is_stored_encrypted(self, verified_user: User) -> None:
        factor = enable_totp(verified_user)

        secret = stored()["totp"]["secret"]

        assert secret.startswith(PREFIX)
        assert factor.secret not in raw_text()
        assert decrypt(secret) == factor.secret

    def test_the_recovery_code_seed_is_stored_encrypted(self, verified_user: User) -> None:
        enable_totp(verified_user)

        data = stored()["recovery_codes"]

        assert data["seed"].startswith(PREFIX)
        assert decrypt(data["seed"]) not in raw_text()
        assert data["used_mask"] == 0

    def test_setting_it_up_through_the_api_stores_it_encrypted(
        self, api: AuthApi, verified_user: User
    ) -> None:
        api.login(verified_user.email)
        secret = api.request("GET", TOTP_URL).json()["meta"]["secret"]
        api.reauthenticate()

        response = api.request("POST", TOTP_URL, {"code": totp_code(secret)})

        assert response.status_code == HTTPStatus.OK
        assert secret not in raw_text()
        assert stored()["totp"]["secret"].startswith(PREFIX)

    def test_signing_in_with_the_authenticator_app_still_works(
        self, api: AuthApi, verified_user: User
    ) -> None:
        factor = enable_totp(verified_user)

        response = api.login_with_totp(verified_user.email, factor.secret)

        assert response.status_code == HTTPStatus.OK
        assert api.is_authenticated

    def test_signing_in_with_a_recovery_code_still_works(
        self, api: AuthApi, verified_user: User
    ) -> None:
        factor = enable_totp(verified_user)
        api.login(verified_user.email)

        response = api.authenticate_mfa(factor.recovery_codes[0])

        assert response.status_code == HTTPStatus.OK
        assert api.is_authenticated

    def test_a_used_recovery_code_is_still_refused(self, api: AuthApi, verified_user: User) -> None:
        factor = enable_totp(verified_user)
        api.login(verified_user.email)
        api.authenticate_mfa(factor.recovery_codes[0])
        second = AuthApi()
        second.login(verified_user.email)

        response = second.authenticate_mfa(factor.recovery_codes[0])

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert not second.is_authenticated


@pytest.mark.django_db
class TestAnotherKey:
    def test_the_data_cannot_be_used_but_reset_mfa_still_clears_it(
        self, api: AuthApi, verified_user: User, settings: Any
    ) -> None:
        factor = enable_totp(verified_user)
        settings.ENCRYPTION_KEYS = [Fernet.generate_key().decode()]
        api.login(verified_user.email)

        with pytest.raises(DecryptionError):
            api.authenticate_mfa(totp_code(factor.secret))
        call_command("reset_mfa", email=verified_user.email, stdout=StringIO())

        assert Authenticator.objects.filter(user=verified_user).count() == 0
        assert AuthApi().login(verified_user.email).status_code == HTTPStatus.OK

    def test_the_old_key_still_works_when_it_follows_a_new_one(
        self, api: AuthApi, verified_user: User, settings: Any
    ) -> None:
        factor = enable_totp(verified_user)
        old = settings.ENCRYPTION_KEYS[0]
        settings.ENCRYPTION_KEYS = [Fernet.generate_key().decode(), old]

        response = api.login_with_totp(verified_user.email, factor.secret)

        assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
class TestEncryptingExistingData:
    def make_user(self, apps: Any, email: str = EMAIL) -> Any:
        user_model = apps.get_model("accounts", "User")
        user = user_model.objects.create(email=email, password=make_password(PASSWORD))
        # The historical state of a migration only holds the apps on its dependency path, so the
        # address is created with the current model; the table is the same.
        EmailAddress.objects.create(user_id=user.pk, email=email, primary=True, verified=True)
        return user

    def add(self, apps: Any, user: Any, type_: str, data: dict[str, Any]) -> None:
        apps.get_model("mfa", "Authenticator").objects.create(user=user, type=type_, data=data)

    def legacy_rows(self, apps: Any) -> Any:
        user = self.make_user(apps)
        self.add(apps, user, "totp", {"secret": LEGACY_SECRET})
        self.add(apps, user, "recovery_codes", {"seed": LEGACY_SEED, "used_mask": 5})
        return user

    def run(self, function: Any) -> None:
        function(current_apps, None)

    def test_clear_text_values_are_encrypted_and_everything_else_is_kept(self) -> None:
        user = self.legacy_rows(current_apps)

        self.run(migration.encrypt_secrets)

        rows = stored()
        assert decrypt(rows["totp"]["secret"]) == LEGACY_SECRET
        assert decrypt(rows["recovery_codes"]["seed"]) == LEGACY_SEED
        assert rows["recovery_codes"]["used_mask"] == 5
        assert LEGACY_SECRET not in raw_text()
        assert LEGACY_SEED not in raw_text()
        assert Authenticator.objects.filter(user_id=user.pk).count() == 2

    def test_running_it_twice_changes_nothing_the_second_time(self) -> None:
        self.legacy_rows(current_apps)
        self.run(migration.encrypt_secrets)
        before = stored()

        self.run(migration.encrypt_secrets)

        assert stored() == before

    def test_values_that_are_encrypted_already_are_not_encrypted_again(self) -> None:
        user = self.make_user(current_apps)
        already = encrypt(LEGACY_SECRET)
        self.add(current_apps, user, "totp", {"secret": already})

        self.run(migration.encrypt_secrets)

        assert stored()["totp"]["secret"] == already

    def test_migrated_recovery_codes_are_encrypted_one_by_one(self) -> None:
        user = self.make_user(current_apps)
        self.add(current_apps, user, "recovery_codes", {"migrated_codes": ["11112222", "33334444"]})

        self.run(migration.encrypt_secrets)

        codes = stored()["recovery_codes"]["migrated_codes"]
        assert [decrypt(c) for c in codes] == ["11112222", "33334444"]
        assert "11112222" not in raw_text()

    def test_other_authenticator_types_and_unknown_fields_are_left_alone(self) -> None:
        user = self.make_user(current_apps)
        self.add(current_apps, user, "webauthn", {"secret": "not-ours", "name": "key"})
        self.add(current_apps, user, "totp", {"secret": LEGACY_SECRET, "note": "plain"})

        self.run(migration.encrypt_secrets)

        rows = Authenticator.objects.filter(user_id=user.pk)
        assert rows.get(type="webauthn").data == {"secret": "not-ours", "name": "key"}
        assert rows.get(type="totp").data["note"] == "plain"

    def test_reversing_restores_the_clear_text(self) -> None:
        self.legacy_rows(current_apps)
        self.run(migration.encrypt_secrets)

        self.run(migration.decrypt_secrets)

        rows = stored()
        assert rows["totp"] == {"secret": LEGACY_SECRET}
        assert rows["recovery_codes"] == {"seed": LEGACY_SEED, "used_mask": 5}


BEFORE = [("accounts", "0002_userinvitation"), ("mfa", "0003_authenticator_type_uniq")]


@pytest.fixture
def before_the_migration(transactional_db: None) -> Iterator[Any]:
    """The schema and models as they were before the encryption migration."""
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    yield executor.loader.project_state(BEFORE).apps
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


def migrate_forward() -> None:
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


class TestTheMigrationItself:
    helper = TestEncryptingExistingData()

    def test_an_existing_account_signs_in_with_its_old_authenticator_after_migrating(
        self, before_the_migration: Any
    ) -> None:
        self.helper.legacy_rows(before_the_migration)
        assert LEGACY_SECRET in raw_text()

        migrate_forward()

        assert LEGACY_SECRET not in raw_text()
        assert stored()["totp"]["secret"].startswith(PREFIX)
        api = AuthApi()
        assert api.login_with_totp(EMAIL, LEGACY_SECRET).status_code == HTTPStatus.OK
        other = AuthApi()
        other.login(EMAIL)
        codes = RecoveryCodes(Authenticator.objects.get(type="recovery_codes")).get_unused_codes()
        assert other.authenticate_mfa(codes[0]).status_code == HTTPStatus.OK

    def test_it_can_be_reversed_through_the_migration_framework(
        self, before_the_migration: Any
    ) -> None:
        self.helper.legacy_rows(before_the_migration)
        migrate_forward()

        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)

        assert stored()["totp"] == {"secret": LEGACY_SECRET}
        assert stored()["recovery_codes"]["seed"] == LEGACY_SEED

    def test_the_email_address_of_the_legacy_account_survives(
        self, before_the_migration: Any
    ) -> None:
        self.helper.legacy_rows(before_the_migration)

        migrate_forward()

        assert EmailAddress.objects.get(email=EMAIL).verified
