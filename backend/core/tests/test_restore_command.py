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


PASSWORD = "p@ss:w/rd?a#b%c&d+e=f"
RESTORE_OPTIONS = ["--no-owner", "--no-privileges", "--exit-on-error", "--single-transaction"]
CLEAN_OPTIONS = ["--clean", "--if-exists"]
CONNECTION = ["--no-password", "-h", "db.example", "-p", "5433", "-U", "dumper", "-d", "paceforge"]


def recorded_args(record: Path) -> list[str]:
    return record.read_text().splitlines()


def recorded_password(record: Path) -> str:
    return (record.parent / "password.txt").read_text().removesuffix("\n")


SECRET_MARKERS = (
    "ENCRYPTION_KEY",
    "BACKUP_ENCRYPTION_KEY",
    "DJANGO_SECRET_KEY",
    "DATABASE_URL",
    "POSTGRES_PASSWORD",
    "UNRELATED_SETTING",
)


def recorded_environment(record: Path) -> dict[str, str]:
    lines = (record.parent / "env.txt").read_text().splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line)


@pytest.fixture
def database(settings: Any) -> dict[str, str]:
    target = {
        "HOST": "db.example",
        "PORT": "5433",
        "USER": "dumper",
        "NAME": "paceforge",
        "PASSWORD": PASSWORD,
    }
    settings.DATABASES = {
        **settings.DATABASES,
        "default": {**settings.DATABASES["default"], **target},
    }
    return target


@pytest.fixture
def stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A pg_restore that records its arguments (one per line), PGPASSWORD and stdin."""
    record = tmp_path / "args.txt"
    password = tmp_path / "password.txt"
    received = tmp_path / "received.bin"
    script = write_stub(
        tmp_path / "pg_restore_stub",
        f'printf "%s\\n" "$PGPASSWORD" > "{password}"\n'
        f'printf "%s\\n" "$@" > "{record}"\n'
        f'env > "{tmp_path / "env.txt"}"\n'
        f'cat > "{received}"',
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
    database: dict[str, str],
) -> None:
    run(str(backup_file), "--key-file", _key_file(tmp_path, key))

    args = recorded_args(stub)
    assert (tmp_path / "received.bin").read_bytes() == DUMP
    assert recorded_password(stub) == PASSWORD
    assert args == [*RESTORE_OPTIONS, *CONNECTION]
    assert all(PASSWORD not in arg for arg in args)


def test_restore_gives_pg_restore_only_the_libpq_environment(
    stub: Path,
    emptiness: Emptiness,
    backup_file: Path,
    key: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
) -> None:
    settings.DATABASES = {
        **settings.DATABASES,
        "default": {**settings.DATABASES["default"], "PASSWORD": ""},
    }
    for name in SECRET_MARKERS:
        monkeypatch.setenv(name, f"marker-{name}")
    monkeypatch.setenv("PGPASSWORD", "inherited-password")
    monkeypatch.setenv("PGSSLMODE", "require")

    run(str(backup_file), "--key-file", _key_file(tmp_path, key))

    child = recorded_environment(stub)
    assert not any(name in child for name in SECRET_MARKERS)
    assert not any("marker-" in value for value in child.values())
    assert "PGPASSWORD" not in child
    assert child["PATH"] == os.environ["PATH"]
    assert child["PGSSLMODE"] == "require"


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
    stub: Path,
    emptiness: Emptiness,
    backup_file: Path,
    key: str,
    tmp_path: Path,
    database: dict[str, str],
) -> None:
    emptiness.empty = False

    run(str(backup_file), "--key-file", _key_file(tmp_path, key), "--allow-non-empty")

    assert recorded_args(stub) == [*RESTORE_OPTIONS, *CLEAN_OPTIONS, *CONNECTION]
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


def _password_file(tmp_path: Path, content: str = "s3cret@pw\n") -> str:
    path = tmp_path / "target.password"
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_database_url_is_parsed_and_password_stays_out_of_arguments(
    stub: Path, emptiness: Emptiness, backup_file: Path, key: str, tmp_path: Path
) -> None:
    run(
        str(backup_file),
        "--key-file",
        _key_file(tmp_path, key),
        "--database-url",
        "postgres://restorer@db.example:5433/target",
        "--password-file",
        _password_file(tmp_path, "s3cret@pw\r\n"),
    )

    args = recorded_args(stub)
    assert recorded_password(stub) == "s3cret@pw"
    assert args == [
        *RESTORE_OPTIONS,
        "--no-password",
        "-h",
        "db.example",
        "-p",
        "5433",
        "-U",
        "restorer",
        "-d",
        "target",
    ]
    assert all("s3cret" not in arg for arg in args)
    assert emptiness.seen[0]["NAME"] == "target"
    assert emptiness.seen[0]["HOST"] == "db.example"
    assert emptiness.seen[0]["PASSWORD"] == "s3cret@pw"


def test_database_url_with_a_password_is_refused_before_anything_runs(
    stub: Path, emptiness: Emptiness, backup_file: Path, key: str, tmp_path: Path
) -> None:
    with pytest.raises(CommandError, match="must not contain a password") as error:
        run(
            str(backup_file),
            "--key-file",
            _key_file(tmp_path, key),
            "--database-url",
            "postgres://restorer:s3cret%40pw@db.example:5433/target",
        )

    assert "s3cret" not in str(error.value)
    assert emptiness.seen == []
    assert not stub.exists()


def test_password_file_needs_a_database_url(
    stub: Path, emptiness: Emptiness, backup_file: Path, key: str, tmp_path: Path
) -> None:
    with pytest.raises(CommandError, match="needs --database-url"):
        run(
            str(backup_file),
            "--key-file",
            _key_file(tmp_path, key),
            "--password-file",
            _password_file(tmp_path),
        )

    assert emptiness.seen == []
    assert not stub.exists()


def test_missing_password_file_is_reported(
    stub: Path, emptiness: Emptiness, backup_file: Path, key: str, tmp_path: Path
) -> None:
    with pytest.raises(CommandError, match="cannot be read"):
        run(
            str(backup_file),
            "--key-file",
            _key_file(tmp_path, key),
            "--database-url",
            "postgres://restorer@db.example:5433/target",
            "--password-file",
            str(tmp_path / "nope.password"),
        )

    assert emptiness.seen == []
    assert not stub.exists()


@pytest.mark.parametrize("content", ["", "\n", "\r\n"])
def test_empty_password_file_is_refused(
    stub: Path, emptiness: Emptiness, backup_file: Path, key: str, tmp_path: Path, content: str
) -> None:
    with pytest.raises(CommandError, match="is empty"):
        run(
            str(backup_file),
            "--key-file",
            _key_file(tmp_path, key),
            "--database-url",
            "postgres://restorer@db.example:5433/target",
            "--password-file",
            _password_file(tmp_path, content),
        )

    assert emptiness.seen == []
    assert not stub.exists()


def test_unreadable_password_file_does_not_show_its_content(
    stub: Path, emptiness: Emptiness, backup_file: Path, key: str, tmp_path: Path
) -> None:
    path = tmp_path / "binary.password"
    path.write_bytes(b"\xff\xfesecret-bytes")

    with pytest.raises(CommandError, match="cannot be read") as error:
        run(
            str(backup_file),
            "--key-file",
            _key_file(tmp_path, key),
            "--database-url",
            "postgres://restorer@db.example:5433/target",
            "--password-file",
            str(path),
        )

    assert "secret" not in str(error.value)
    assert emptiness.seen == []


def test_help_shows_no_password_in_the_example() -> None:
    from django.core.management import load_command_class

    help_text = load_command_class("core", "restore_db").create_parser("manage.py", "restore_db")
    text = help_text.format_help()

    assert ":password@" not in text
    assert "--password-file" in text


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
            "postgres://user@host:5432/",
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
