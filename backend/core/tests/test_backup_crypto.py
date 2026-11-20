import base64
import io
import os
import runpy
from typing import Any

import environ
import pytest
from cryptography.fernet import Fernet
from django.core.checks import run_checks
from django.core.exceptions import ImproperlyConfigured

from config import settings as config_settings
from core.backup_crypto import (
    HEADER_SIZE,
    MAGIC,
    TAG_SIZE,
    BackupCryptoError,
    decrypt_stream,
    encrypt_stream,
    parse_backup_keys,
)

CHUNK = 64


def new_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def encrypt(data: bytes, key: str, chunk_size: int = CHUNK) -> bytes:
    out = io.BytesIO()
    encrypt_stream(io.BytesIO(data), out, [key], chunk_size=chunk_size)
    return out.getvalue()


def decrypt(blob: bytes, *keys: str) -> bytes:
    out = io.BytesIO()
    decrypt_stream(io.BytesIO(blob), out, list(keys))
    return out.getvalue()


class TestRoundTrip:
    @pytest.mark.parametrize("size", [0, 1, CHUNK - 1, CHUNK, CHUNK + 1, 3 * CHUNK, 5 * CHUNK + 7])
    def test_round_trip(self, size: int) -> None:
        key = new_key()
        data = os.urandom(size)
        assert decrypt(encrypt(data, key), key) == data

    def test_default_chunk_size(self) -> None:
        key = new_key()
        data = os.urandom(2 * 1024 * 1024 + 5)
        out = io.BytesIO()
        encrypt_stream(io.BytesIO(data), out, [key])
        assert decrypt(out.getvalue(), key) == data

    def test_reads_from_a_stream_that_returns_short_reads(self) -> None:
        class Trickle(io.RawIOBase):
            def __init__(self, data: bytes) -> None:
                self.buffer = io.BytesIO(data)

            def readable(self) -> bool:
                return True

            def readinto(self, target: Any) -> int:
                chunk = self.buffer.read(min(len(target), 5))
                target[: len(chunk)] = chunk
                return len(chunk)

        key = new_key()
        data = os.urandom(300)
        out = io.BytesIO()
        encrypt_stream(Trickle(data), out, [key], chunk_size=CHUNK)  # type: ignore[arg-type]
        assert decrypt(out.getvalue(), key) == data

    def test_output_is_versioned_and_random(self) -> None:
        key = new_key()
        first, second = encrypt(b"same", key), encrypt(b"same", key)
        assert first.startswith(MAGIC) and MAGIC == b"PFBK\x01"
        assert first != second
        assert b"same" not in first


class TestKeys:
    def test_rotation(self) -> None:
        old, new = new_key(), new_key()
        blob = encrypt(b"data", old)
        assert decrypt(blob, new, old) == b"data"

    def test_new_key_encrypts(self) -> None:
        old, new = new_key(), new_key()
        out = io.BytesIO()
        encrypt_stream(io.BytesIO(b"data"), out, [new, old])
        assert decrypt(out.getvalue(), new) == b"data"
        with pytest.raises(BackupCryptoError):
            decrypt(out.getvalue(), old)

    def test_wrong_key(self) -> None:
        blob = encrypt(b"x" * 200, new_key())
        with pytest.raises(BackupCryptoError):
            decrypt(blob, new_key())

    def test_no_keys(self, settings: Any) -> None:
        settings.BACKUP_ENCRYPTION_KEYS = []
        with pytest.raises(BackupCryptoError, match="not configured"):
            encrypt_stream(io.BytesIO(b"x"), io.BytesIO())
        with pytest.raises(BackupCryptoError, match="not configured"):
            decrypt_stream(io.BytesIO(b"x"), io.BytesIO())

    def test_keys_default_to_settings(self, settings: Any) -> None:
        key = new_key()
        settings.BACKUP_ENCRYPTION_KEYS = [key]
        out, plain = io.BytesIO(), io.BytesIO()
        encrypt_stream(io.BytesIO(b"data"), out)
        decrypt_stream(io.BytesIO(out.getvalue()), plain)
        assert plain.getvalue() == b"data"

    @pytest.mark.parametrize("bad", ["", "short", "!" * 44, "A" * 43, "A" * 45])
    def test_parse_rejects_malformed_keys(self, bad: str) -> None:
        with pytest.raises(BackupCryptoError, match="Key 2 of BACKUP_ENCRYPTION_KEY"):
            parse_backup_keys([new_key(), bad])

    def test_parse_accepts_fernet_keys(self) -> None:
        assert len(parse_backup_keys([Fernet.generate_key().decode()])[0]) == 32


class TestTamperingAndDamage:
    key = new_key()
    data = os.urandom(5 * CHUNK + 10)

    def blob(self) -> bytes:
        return encrypt(self.data, self.key)

    def test_flipped_byte_anywhere(self) -> None:
        blob = self.blob()
        for position in range(0, len(blob), 7):
            damaged = bytearray(blob)
            damaged[position] ^= 1
            with pytest.raises(BackupCryptoError):
                decrypt(bytes(damaged), self.key)

    def test_truncated_at_every_length(self) -> None:
        blob = self.blob()
        for length in range(len(blob)):
            with pytest.raises(BackupCryptoError):
                decrypt(blob[:length], self.key)

    def test_truncated_at_chunk_boundary(self) -> None:
        blob = self.blob()
        with pytest.raises(BackupCryptoError):
            decrypt(blob[: HEADER_SIZE + 2 * (CHUNK + TAG_SIZE)], self.key)

    def test_trailing_data(self) -> None:
        blob = self.blob()
        for extra in (b"\x00", os.urandom(CHUNK + TAG_SIZE), blob[HEADER_SIZE:]):
            with pytest.raises(BackupCryptoError):
                decrypt(blob + extra, self.key)

    def test_trailing_data_after_exact_multiple(self) -> None:
        blob = encrypt(b"x" * (2 * CHUNK), self.key)
        with pytest.raises(BackupCryptoError):
            decrypt(blob + b"\x00" * TAG_SIZE, self.key)

    def test_reordered_chunks(self) -> None:
        blob = self.blob()
        frame = CHUNK + TAG_SIZE
        body = blob[HEADER_SIZE:]
        swapped = body[frame : 2 * frame] + body[:frame] + body[2 * frame :]
        with pytest.raises(BackupCryptoError):
            decrypt(blob[:HEADER_SIZE] + swapped, self.key)

    def test_not_a_backup(self) -> None:
        for blob in (b"", b"PFBK", b"plain text, no header at all"):
            with pytest.raises(BackupCryptoError, match="not a PaceForge backup"):
                decrypt(blob, self.key)

    def test_unknown_version(self) -> None:
        blob = bytearray(self.blob())
        blob[4] = 2
        with pytest.raises(BackupCryptoError, match="not a PaceForge backup"):
            decrypt(bytes(blob), self.key)

    def test_errors_do_not_leak(self) -> None:
        other = new_key()
        blob = encrypt(b"top-secret-payload" * 20, self.key)
        for keys, data in ((other, blob), (self.key, blob[:-3]), (self.key, blob + b"x")):
            with pytest.raises(BackupCryptoError) as caught:
                decrypt(data, keys)
            text = str(caught.value)
            assert self.key not in text and other not in text and "top-secret" not in text

    def test_bad_key_error_does_not_leak(self) -> None:
        bad = "secret-looking-but-malformed"
        with pytest.raises(BackupCryptoError) as caught:
            parse_backup_keys([bad])
        assert bad not in str(caught.value)


class TestSettings:
    @pytest.fixture
    def read_settings(self, monkeypatch: pytest.MonkeyPatch) -> Any:
        for name in (
            "BACKUP_ENCRYPTION_KEY",
            "BACKUP_DIR",
            "BACKUP_INTERVAL_HOURS",
            "BACKUP_KEEP_DAILY",
            "BACKUP_KEEP_WEEKLY",
        ):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setattr(environ.Env, "read_env", classmethod(lambda cls, *a, **k: None))

        def read(**env: str) -> dict[str, Any]:
            for name, value in env.items():
                monkeypatch.setenv(name, value)
            return runpy.run_path(config_settings.__file__)

        return read

    def test_defaults(self, read_settings: Any) -> None:
        values = read_settings()
        assert values["BACKUP_ENCRYPTION_KEYS"] == []
        assert values["BACKUP_INTERVAL_HOURS"] == 24
        assert values["BACKUP_KEEP_DAILY"] == 7
        assert values["BACKUP_KEEP_WEEKLY"] == 4
        assert values["BACKUP_DIR"].name == "backups"

    def test_custom_values(self, read_settings: Any, tmp_path: Any) -> None:
        a, b = new_key(), new_key()
        values = read_settings(
            BACKUP_ENCRYPTION_KEY=f" {a} , {b},",
            BACKUP_DIR=str(tmp_path),
            BACKUP_INTERVAL_HOURS="168",
            BACKUP_KEEP_DAILY="365",
            BACKUP_KEEP_WEEKLY="0",
        )
        assert values["BACKUP_ENCRYPTION_KEYS"] == [a, b]
        assert values["BACKUP_DIR"] == tmp_path
        assert values["BACKUP_KEEP_WEEKLY"] == 0

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("BACKUP_INTERVAL_HOURS", "0"),
            ("BACKUP_INTERVAL_HOURS", "-1"),
            ("BACKUP_INTERVAL_HOURS", "169"),
            ("BACKUP_KEEP_DAILY", "0"),
            ("BACKUP_KEEP_DAILY", "366"),
            ("BACKUP_KEEP_WEEKLY", "-1"),
            ("BACKUP_KEEP_WEEKLY", "105"),
        ],
    )
    def test_out_of_range(self, read_settings: Any, name: str, value: str) -> None:
        with pytest.raises(ImproperlyConfigured, match=name):
            read_settings(**{name: value})


class TestSystemChecks:
    def ids(self) -> list[str]:
        return [message.id for message in run_checks() if message.id]

    def test_optional(self, settings: Any) -> None:
        settings.BACKUP_ENCRYPTION_KEYS = []
        assert "core.E006" not in self.ids()
        assert "core.E007" not in self.ids()

    def test_valid_keys(self, settings: Any) -> None:
        settings.BACKUP_ENCRYPTION_KEYS = [new_key(), new_key()]
        assert not {"core.E006", "core.E007"} & set(self.ids())

    def test_malformed_key(self, settings: Any) -> None:
        settings.BACKUP_ENCRYPTION_KEYS = [new_key(), "not-a-key"]
        messages = [m for m in run_checks() if m.id == "core.E006"]
        assert len(messages) == 1
        assert "Key 2" in messages[0].msg and "not-a-key" not in messages[0].msg

    def test_reused_instance_key(self, settings: Any) -> None:
        instance = Fernet.generate_key().decode()
        settings.ENCRYPTION_KEYS = [instance]
        settings.BACKUP_ENCRYPTION_KEYS = [new_key(), instance]
        messages = [m for m in run_checks() if m.id == "core.E007"]
        assert len(messages) == 1
        assert instance not in messages[0].msg

    def test_reused_old_instance_key(self, settings: Any) -> None:
        old = Fernet.generate_key().decode()
        settings.ENCRYPTION_KEYS = [Fernet.generate_key().decode(), old]
        settings.BACKUP_ENCRYPTION_KEYS = [old]
        assert "core.E007" in self.ids()
