import base64
import io
import os
import stat
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from django.core.management import CommandError, call_command

from core import backup
from core.backup import (
    BackupError,
    backup_filename,
    create_backup,
    load_backup_keys,
    prune_backups,
)
from core.backup_crypto import BackupCryptoError, decrypt_stream

DUMP = b"PGDMP-stub-" + b"x" * 5000


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
def stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A pg_dump that records its arguments and PGPASSWORD, then writes a fixed dump."""
    record = tmp_path / "record.txt"
    dump = tmp_path / "dump.bin"
    dump.write_bytes(DUMP)
    script = write_stub(
        tmp_path / "pg_dump_stub",
        f'echo "$PGPASSWORD" > "{record}"\necho "$@" >> "{record}"\ncat "{dump}"',
    )
    monkeypatch.setattr(backup, "PG_DUMP", str(script))
    return record


@pytest.fixture
def out(tmp_path: Path) -> Path:
    return tmp_path / "backups"


def decrypt(path: Path, key: str) -> bytes:
    result = io.BytesIO()
    with path.open("rb") as source:
        decrypt_stream(source, result, [key])
    return result.getvalue()


def touch_backup(directory: Path, stamp: str) -> Path:
    path = directory / f"paceforge-{stamp}Z.pgdump.enc"
    path.write_bytes(b"x")
    return path


def test_create_backup_writes_encrypted_0600_file(stub: Path, out: Path, key: str) -> None:
    moment = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
    path = create_backup(out, [key], now=moment)

    assert path == out / "paceforge-20260304-050607Z.pgdump.enc"
    assert backup_filename(moment) == path.name
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert DUMP not in path.read_bytes()
    assert decrypt(path, key) == DUMP
    assert [p.name for p in out.iterdir()] == [path.name]


def test_create_backup_passes_password_by_environment_only(
    stub: Path, out: Path, key: str, settings: Any
) -> None:
    password = "p@ss:w/rd?a#b%c&d+e=f"
    settings.DATABASES = {
        **settings.DATABASES,
        "default": {**settings.DATABASES["default"], "PASSWORD": password},
    }
    create_backup(out, [key])
    lines = stub.read_text().splitlines()

    assert lines[0] == password
    assert "-Fc" in lines[1].split()
    assert password not in lines[1]


def test_create_backup_cleans_up_when_pg_dump_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, out: Path, key: str
) -> None:
    script = write_stub(tmp_path / "failing", "echo partial\necho 'boom' >&2\nexit 3")
    monkeypatch.setattr(backup, "PG_DUMP", str(script))

    with pytest.raises(BackupError, match="exit code 3: boom"):
        create_backup(out, [key])

    assert list(out.iterdir()) == []


def test_failed_backup_keeps_the_previous_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub: Path, out: Path, key: str
) -> None:
    moment = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
    path = create_backup(out, [key], now=moment)
    before = path.read_bytes()
    script = write_stub(tmp_path / "failing", "exit 1")
    monkeypatch.setattr(backup, "PG_DUMP", str(script))

    with pytest.raises(BackupError):
        create_backup(out, [key], now=moment)

    assert path.read_bytes() == before
    assert [p.name for p in out.iterdir()] == [path.name]


def test_create_backup_cleans_up_when_pg_dump_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, out: Path, key: str
) -> None:
    monkeypatch.setattr(backup, "PG_DUMP", str(tmp_path / "missing"))

    with pytest.raises(BackupError, match="could not be started"):
        create_backup(out, [key])

    assert list(out.iterdir()) == []


def test_create_backup_cleans_up_on_a_bad_key(stub: Path, out: Path) -> None:
    with pytest.raises(BackupCryptoError):
        create_backup(out, ["not-a-key"])

    assert list(out.iterdir()) == []


def test_load_backup_keys_from_settings(settings: Any, key: str) -> None:
    settings.BACKUP_ENCRYPTION_KEYS = [key]
    assert load_backup_keys() == [key]


def test_load_backup_keys_from_file(tmp_path: Path, key: str) -> None:
    other = new_key()
    key_file = tmp_path / "backup.key"
    key_file.write_text(f"{key}\n{other},\n")

    assert load_backup_keys(key_file) == [key, other]


def test_load_backup_keys_rejects_missing_unreadable_and_invalid(
    tmp_path: Path, settings: Any
) -> None:
    settings.BACKUP_ENCRYPTION_KEYS = []
    with pytest.raises(BackupError, match="No backup key"):
        load_backup_keys()
    with pytest.raises(BackupError, match="cannot be read"):
        load_backup_keys(tmp_path / "missing")
    bad = tmp_path / "bad.key"
    bad.write_text("secret-not-a-key")
    with pytest.raises(BackupCryptoError) as error:
        load_backup_keys(bad)
    assert "secret-not-a-key" not in str(error.value)


def test_load_backup_keys_rejects_the_instance_key(tmp_path: Path) -> None:
    instance_key = backup.settings.ENCRYPTION_KEYS[0]
    key_file = tmp_path / "backup.key"
    key_file.write_text(f"{new_key()},{instance_key}")

    with pytest.raises(BackupError, match="must differ from ENCRYPTION_KEY"):
        load_backup_keys(key_file)


def test_prune_keeps_newest_per_day_and_week(tmp_path: Path) -> None:
    # 2026-03-02 is a Monday (ISO week 10); 2026-03-09 starts week 11.
    old_week = touch_backup(tmp_path, "20260302-010000")
    old_week_late = touch_backup(tmp_path, "20260304-230000")
    old_week_early = touch_backup(tmp_path, "20260304-010000")
    this_week = touch_backup(tmp_path, "20260309-010000")
    today_early = touch_backup(tmp_path, "20260310-010000")
    today_late = touch_backup(tmp_path, "20260310-230000")

    removed = prune_backups(tmp_path, keep_daily=2, keep_weekly=2)

    # Days kept: 10th (late) and 9th. Weeks kept: week 11 (late on the 10th) and week 10 (the
    # newest of that week, 4th late).
    assert removed == 3
    remaining = {p.name for p in tmp_path.iterdir()}
    assert remaining == {today_late.name, this_week.name, old_week_late.name}
    assert not any(p.exists() for p in (old_week, old_week_early, today_early))


def test_prune_without_weekly_retention(tmp_path: Path) -> None:
    touch_backup(tmp_path, "20260301-010000")
    keep = touch_backup(tmp_path, "20260310-010000")

    assert prune_backups(tmp_path, keep_daily=1, keep_weekly=0) == 1
    assert [p.name for p in tmp_path.iterdir()] == [keep.name]


def test_prune_ignores_unrelated_files_and_never_deletes_the_protected_one(
    tmp_path: Path,
) -> None:
    unrelated = [
        tmp_path / "notes.txt",
        tmp_path / "paceforge-20200101-010000Z.pgdump",
        tmp_path / "paceforge-2020.pgdump.enc",
        tmp_path / "paceforge-20201301-010000Z.pgdump.enc",
        tmp_path / ".paceforge-abc.tmp",
    ]
    for path in unrelated:
        path.write_bytes(b"x")
    (tmp_path / "paceforge-20200102-010000Z.pgdump.enc").mkdir()
    protected = touch_backup(tmp_path, "20200101-010000")
    touch_backup(tmp_path, "20260310-010000")

    assert prune_backups(tmp_path, 1, 0, protect=protected) == 0
    assert protected.exists()
    assert all(path.exists() for path in unrelated)


def test_backup_db_creates_and_prunes_and_prints_only_a_summary(
    stub: Path, out: Path, key: str, tmp_path: Path
) -> None:
    old = out
    old.mkdir()
    expired = touch_backup(old, "20200101-010000")
    key_file = tmp_path / "backup.key"
    key_file.write_text(key)
    stdout = StringIO()

    call_command(
        "backup_db",
        output_dir=out,
        key_file=key_file,
        keep_daily=1,
        keep_weekly=0,
        stdout=stdout,
    )

    created = [p for p in out.iterdir() if p != expired]
    assert not expired.exists()
    assert len(created) == 1
    assert decrypt(created[0], key) == DUMP
    text = stdout.getvalue().strip()
    assert text.split()[0] == created[0].name
    assert text.endswith("pruned 1")
    assert key not in text
    assert str(out) not in text


def test_backup_db_no_prune_keeps_old_backups(
    stub: Path, out: Path, key: str, tmp_path: Path
) -> None:
    out.mkdir()
    expired = touch_backup(out, "20200101-010000")
    key_file = tmp_path / "backup.key"
    key_file.write_text(key)

    call_command(
        "backup_db",
        output_dir=out,
        key_file=key_file,
        keep_daily=1,
        keep_weekly=0,
        no_prune=True,
        stdout=StringIO(),
    )

    assert expired.exists()


def test_backup_db_does_not_prune_after_a_failed_dump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, out: Path, key: str
) -> None:
    out.mkdir()
    expired = touch_backup(out, "20200101-010000")
    key_file = tmp_path / "backup.key"
    key_file.write_text(key)
    monkeypatch.setattr(backup, "PG_DUMP", str(write_stub(tmp_path / "failing", "exit 2")))

    with pytest.raises(CommandError, match="pg_dump failed"):
        call_command(
            "backup_db",
            output_dir=out,
            key_file=key_file,
            keep_daily=1,
            keep_weekly=0,
            stdout=StringIO(),
        )

    assert expired.exists()


def test_backup_db_reports_key_problems_and_bad_options(out: Path, tmp_path: Path) -> None:
    with pytest.raises(CommandError, match="cannot be read"):
        call_command("backup_db", output_dir=out, key_file=tmp_path / "missing")
    with pytest.raises(CommandError, match="--keep-daily"):
        call_command("backup_db", output_dir=out, keep_daily=0)
