import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from django.core.checks import Error
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command

from core.checks import check_encryption_keys
from core.encryption import PREFIX, DecryptionError, decrypt, encrypt

SECRET = "JBSWY3DPEHPK3PXP-s3cr3t"


def new_key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def key(settings: Any) -> str:
    value = new_key()
    settings.ENCRYPTION_KEYS = [value]
    return value


class TestRoundTrip:
    @pytest.mark.parametrize(
        "text",
        ["", "hello", SECRET, "ünïcödé ✓ 日本語 🔐", "line\nbreak\ttab", "x" * 20_000, PREFIX],
    )
    def test_text_comes_back_unchanged(self, key: str, text: str) -> None:
        assert decrypt(encrypt(text)) == text

    def test_the_stored_value_is_marked_and_hides_the_text(self, key: str) -> None:
        stored = encrypt(SECRET)

        assert stored.startswith(PREFIX)
        assert SECRET not in stored

    def test_every_encryption_gives_a_different_value(self, key: str) -> None:
        assert encrypt(SECRET) != encrypt(SECRET)


class TestRejectedValues:
    def test_a_modified_value_is_rejected(self, key: str) -> None:
        stored = encrypt(SECRET)
        middle = len(stored) // 2
        flipped = "A" if stored[middle] != "A" else "B"

        with pytest.raises(DecryptionError):
            decrypt(stored[:middle] + flipped + stored[middle + 1 :])

    def test_a_truncated_value_is_rejected(self, key: str) -> None:
        with pytest.raises(DecryptionError):
            decrypt(encrypt(SECRET)[:-8])

    @pytest.mark.parametrize(
        "stored",
        ["", SECRET, PREFIX, PREFIX + "not-a-token", PREFIX + "ünï✓", "enc:v2:abc"],
    )
    def test_values_that_are_not_ciphertext_are_rejected(self, key: str, stored: str) -> None:
        with pytest.raises(DecryptionError):
            decrypt(stored)

    def test_a_token_without_the_marker_is_not_accepted(self, key: str) -> None:
        bare = encrypt(SECRET)[len(PREFIX) :]

        with pytest.raises(DecryptionError):
            decrypt(bare)

    def test_another_key_cannot_read_it(self, key: str, settings: Any) -> None:
        stored = encrypt(SECRET)
        settings.ENCRYPTION_KEYS = [new_key()]

        with pytest.raises(DecryptionError):
            decrypt(stored)

    def test_the_error_reveals_neither_the_text_nor_the_keys(self, key: str, settings: Any) -> None:
        stored = encrypt(SECRET)
        other = new_key()
        settings.ENCRYPTION_KEYS = [other]

        with pytest.raises(DecryptionError) as raised:
            decrypt(stored)

        shown = f"{raised.value} {raised.value!r} {raised.value.__cause__!r}"
        assert SECRET not in shown
        assert key not in shown
        assert other not in shown
        assert stored not in shown


class TestKeyRotation:
    def test_old_values_stay_readable_after_a_new_key_is_put_in_front(
        self, key: str, settings: Any
    ) -> None:
        old_value = encrypt(SECRET)
        new = new_key()
        settings.ENCRYPTION_KEYS = [new, key]

        assert decrypt(old_value) == SECRET

    def test_new_values_are_made_with_the_first_key_only(self, key: str, settings: Any) -> None:
        new = new_key()
        settings.ENCRYPTION_KEYS = [new, key]
        stored = encrypt(SECRET)

        settings.ENCRYPTION_KEYS = [new]
        assert decrypt(stored) == SECRET
        settings.ENCRYPTION_KEYS = [key]
        with pytest.raises(DecryptionError):
            decrypt(stored)

    def test_dropping_the_old_key_makes_old_values_unreadable(
        self, key: str, settings: Any
    ) -> None:
        old_value = encrypt(SECRET)
        settings.ENCRYPTION_KEYS = [new_key()]

        with pytest.raises(DecryptionError):
            decrypt(old_value)


def test_nothing_is_encrypted_without_a_key(settings: Any) -> None:
    settings.ENCRYPTION_KEYS = []

    with pytest.raises(ImproperlyConfigured, match="ENCRYPTION_KEY"):
        encrypt(SECRET)
    with pytest.raises(ImproperlyConfigured, match="ENCRYPTION_KEY"):
        decrypt(PREFIX + "abc")


class TestSystemCheck:
    def test_a_valid_key_passes(self, settings: Any) -> None:
        settings.ENCRYPTION_KEYS = [new_key()]

        assert check_encryption_keys(None) == []

    def test_several_valid_keys_pass(self, settings: Any) -> None:
        settings.ENCRYPTION_KEYS = [new_key(), new_key()]

        assert check_encryption_keys(None) == []

    def test_an_empty_setting_is_reported(self, settings: Any) -> None:
        settings.ENCRYPTION_KEYS = []

        [error] = check_encryption_keys(None)

        assert isinstance(error, Error)
        assert error.id == "core.E001"
        assert "ENCRYPTION_KEY" in error.msg
        assert "Fernet.generate_key" in error.msg

    @pytest.mark.parametrize(
        "bad",
        ["short", "not base64 !!!", "A" * 44, "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"],
    )
    def test_a_malformed_key_is_reported_without_showing_it(self, settings: Any, bad: str) -> None:
        settings.ENCRYPTION_KEYS = [bad]

        [error] = check_encryption_keys(None)

        assert error.id == "core.E002"
        assert bad not in error.msg

    def test_the_position_of_the_bad_key_is_named(self, settings: Any) -> None:
        settings.ENCRYPTION_KEYS = [new_key(), "broken", new_key()]

        [error] = check_encryption_keys(None)

        assert "Key 2 " in error.msg

    def test_the_check_is_part_of_manage_py_check(self, settings: Any) -> None:
        call_command("check")  # passes with the test key

        settings.ENCRYPTION_KEYS = ["broken"]
        with pytest.raises(Exception, match="core.E002"):
            call_command("check")


# Importing the settings reads the real `.env` of the repository, which may hold a key; these tests
# are about the environment they pass in.
NO_DOTENV = "import environ; environ.Env.read_env = lambda *a, **k: None; "


def import_settings(statement: str, **env: str) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if k != "ENCRYPTION_KEY"}
    return subprocess.run(
        [sys.executable, "-c", NO_DOTENV + statement],
        env=base | {"DJANGO_SECRET_KEY": "x", "DATABASE_URL": "sqlite:///unused.db"} | env,
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
    )


class TestConfiguration:
    def test_django_does_not_start_without_the_variable(self) -> None:
        result = import_settings("import config.settings")

        assert result.returncode != 0
        assert "ENCRYPTION_KEY" in result.stderr

    def test_keys_are_split_at_commas_and_trimmed(self) -> None:
        first, second = new_key(), new_key()

        result = import_settings(
            "import config.settings as s; print(s.ENCRYPTION_KEYS)",
            ENCRYPTION_KEY=f" {first} , {second} ,",
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str([first, second])

    def test_a_single_key_imports(self) -> None:
        key = new_key()

        result = import_settings(
            "import config.settings as s; print(s.ENCRYPTION_KEYS)", ENCRYPTION_KEY=key
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str([key])

    @pytest.mark.parametrize("value", ["", " ", " , ", ",\t,"])
    def test_a_variable_without_any_key_is_refused(self, value: str) -> None:
        result = import_settings("import config.settings", ENCRYPTION_KEY=value)

        assert result.returncode != 0
        assert "ImproperlyConfigured" in result.stderr
        assert "ENCRYPTION_KEY" in result.stderr
