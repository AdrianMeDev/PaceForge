import base64
import io
import os
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from django.core.management import CommandError, call_command

from core import backup
from core.backup import BackupError, restore_backup
from core.backup_crypto import encrypt_stream

DUMP = b"PGDMP-stub-" + b"y" * 5000


def new_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def write_stub(path: Path, body: str) -> Path:
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o700)
    return path


@pytest.fixture
def key() -> str:
    return new_key()


@pytest.fixture
def backup_file(tmp_path: Path, key: str) -> Path:
    path = tmp_path / "paceforge-20260304-050607Z.pgdump.enc"
    with path.open("wb") as destination:
        encrypt_stream(io.BytesIO(DUMP), destination, [key])
    return path


@pytest.fixture
def stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A pg_restore that records PGPASSWORD, its arguments and stdin."""
    record = tmp_path / "record.txt"
    received = tmp_path / "received.bin"
    script = write_stub(
        tmp_path / "pg_restore_stub",
        f'echo "$PGPASSWORD" > "{record}"\necho "$@" >> "{record}"\ncat > "{received}"',
    )
    monkeypatch.setattr(backup, "PG_RESTORE", str(script))
    return record


class Emptiness:
    """Stands in for ``database_is_empty`` and records the databases it was asked about."""

    def __init__(self) -> None:
        self.empty = True
        self.seen: list[dict[str, Any]] = []

    def __call__(self, database: Any) -> bool:
        self.seen.append(dict(database))
        return self.empty


@pytest.fixture
def emptiness(monkeypatch: pytest.MonkeyPatch) -> Emptiness:
    fake = Emptiness()
    monkeypatch.setattr(backup, "database_is_empty", fake)
    return fake


def run(*args: str) -> str:
    out = StringIO()
    call_command("restore_db", *args, stdout=out)
    return out.getvalue()


def test_restore_into_empty_database_streams_decrypted_dump(
    stub: Path,
    emptiness: Emptiness,
    backup_file: Path,
    key: str,
    tmp_path: Path,
    settings: Any,
) -> None:
    password = "p@ss:w/rd?a#b%c&d+e=f"
    settings.DATABASES = {
        **settings.DATABASES,
        "default": {**settings.DATABASES["default"], "PASSWORD": password},
    }
    run(str(backup_file), "--key-file", _key_file(tmp_path, key))

    lines = stub.read_text().splitlines()
    options = lines[1].split()
    assert (tmp_path / "received.bin").read_bytes() == DUMP
    assert lines[0] == password
    assert "--single-transaction" in options
    assert "--exit-on-error" in options
    assert "--no-owner" in options
    assert "--no-privileges" in options
    assert "--clean" not in options
    assert password not in lines[1]


def _key_file(tmp_path: Path, key: str) -> str:
    path = tmp_path / "backup.key"
    path.write_text(key)
    return str(path)


def test_restore_refuses_non_empty_database(
    stub: Path, emptiness: Emptiness, backup_file: Path, key: str, tmp_path: Path
) -> None:
    emptiness.empty = False

    with pytest.raises(CommandError, match="not empty"):
        run(str(backup_file), "--key-file", _key_file(tmp_path, key))

    assert not stub.exists()


def test_allow_non_empty_cleans_existing_objects(
    stub: Path, emptiness: Emptiness, backup_file: Path, key: str, tmp_path: Path
) -> None:
    emptiness.empty = False

    run(str(backup_file), "--key-file", _key_file(tmp_path, key), "--allow-non-empty")

    options = stub.read_text().splitlines()[1].split()
    assert "--clean" in options
    assert "--if-exists" in options
    assert (tmp_path / "received.bin").read_bytes() == DUMP


def test_wrong_key_fails_before_pg_restore_starts(
    stub: Path, emptiness: Emptiness, backup_file: Path, tmp_path: Path
) -> None:
    other = new_key()

    with pytest.raises(CommandError, match="damaged") as error:
        run(str(backup_file), "--key-file", _key_file(tmp_path, other))

    assert other not in str(error.value)
    assert not stub.exists()


def test_missing_key_is_reported(
    stub: Path,
    emptiness: Emptiness,
    backup_file: Path,
    settings: Any,
) -> None:
    settings.BACKUP_ENCRYPTION_KEYS = []

    with pytest.raises(CommandError, match="No backup key"):
        run(str(backup_file))

    assert not stub.exists()


def test_missing_file_is_reported(
    stub: Path, emptiness: Emptiness, key: str, tmp_path: Path
) -> None:
    with pytest.raises(CommandError, match="does not exist"):
        run(str(tmp_path / "nope.pgdump.enc"), "--key-file", _key_file(tmp_path, key))


def test_corrupted_file_is_rejected_without_restoring(
    stub: Path, emptiness: Emptiness, backup_file: Path, key: str, tmp_path: Path
) -> None:
    data = bytearray(backup_file.read_bytes())
    data[-1] ^= 0xFF
    backup_file.write_bytes(bytes(data))

    with pytest.raises(CommandError, match="damaged"):
        run(str(backup_file), "--key-file", _key_file(tmp_path, key))


def test_not_a_backup_file_is_rejected(
    stub: Path, emptiness: Emptiness, key: str, tmp_path: Path
) -> None:
    junk = tmp_path / "junk.enc"
    junk.write_bytes(b"not a backup at all, just text")

    with pytest.raises(CommandError, match="not a PaceForge backup"):
        run(str(junk), "--key-file", _key_file(tmp_path, key))

    assert not stub.exists()


def test_pg_restore_error_is_propagated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    emptiness: Emptiness,
    backup_file: Path,
    key: str,
) -> None:
    script = write_stub(tmp_path / "failing", "echo 'boom' >&2\nexit 3")
    monkeypatch.setattr(backup, "PG_RESTORE", str(script))

    with pytest.raises(CommandError, match="exit code 3: boom"):
        run(str(backup_file), "--key-file", _key_file(tmp_path, key))


def test_database_url_is_parsed_and_password_stays_out_of_arguments(
    stub: Path, emptiness: Emptiness, backup_file: Path, key: str, tmp_path: Path
) -> None:
    run(
        str(backup_file),
        "--key-file",
        _key_file(tmp_path, key),
        "--database-url",
        "postgres://restorer:s3cret%40pw@db.example:5433/target",
    )

    lines = stub.read_text().splitlines()
    assert lines[0] == "s3cret@pw"
    assert "s3cret" not in lines[1]
    assert lines[1].split()[-8:] == [
        "-h",
        "db.example",
        "-p",
        "5433",
        "-U",
        "restorer",
        "-d",
        "target",
    ]
    assert emptiness.seen[0]["NAME"] == "target"
    assert emptiness.seen[0]["HOST"] == "db.example"


@pytest.mark.parametrize("empty_url", ["", "   "])
def test_empty_database_url_is_rejected_without_touching_default_db(
    stub: Path,
    emptiness: Emptiness,
    backup_file: Path,
    key: str,
    tmp_path: Path,
    empty_url: str,
) -> None:
    with pytest.raises(CommandError, match="must not be empty"):
        run(
            str(backup_file),
            "--key-file",
            _key_file(tmp_path, key),
            "--database-url",
            empty_url,
            "--allow-non-empty",
        )

    assert not stub.exists()
    assert emptiness.seen == []


def test_database_url_without_a_name_is_rejected(
    stub: Path, emptiness: Emptiness, backup_file: Path, key: str, tmp_path: Path
) -> None:
    with pytest.raises(CommandError, match="must name a database"):
        run(
            str(backup_file),
            "--key-file",
            _key_file(tmp_path, key),
            "--database-url",
            "postgres://user:pw@host:5432/",
        )


def test_restore_backup_reports_unreachable_pg_restore(
    monkeypatch: pytest.MonkeyPatch,
    emptiness: Emptiness,
    backup_file: Path,
    key: str,
) -> None:
    monkeypatch.setattr(backup, "PG_RESTORE", "/nonexistent/pg_restore")

    with pytest.raises(BackupError, match="could not be started"):
        restore_backup(backup_file, [key])
