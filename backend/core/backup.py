"""Create and prune encrypted database backups.

``create_backup`` streams ``pg_dump`` straight into ``encrypt_stream``: the plaintext dump only
lives in a pipe, never on disk. The encrypted data goes to a ``0600`` temporary file next to the
target and is moved into place with an atomic rename, so a backup is either complete or absent.
The database password reaches ``pg_dump`` through the ``PGPASSWORD`` environment variable only.

``restore_backup`` is the reverse: it streams ``decrypt_stream`` straight into ``pg_restore`` and
refuses to touch a database that already has tables unless the operator allows it.
"""

import contextlib
import os
import re
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, BinaryIO, cast

import psycopg
from django.conf import settings

from core.backup_crypto import decrypt_stream, encrypt_stream, parse_backup_keys

PG_DUMP = "pg_dump"
PG_RESTORE = "pg_restore"
BACKUP_SUFFIX = ".pgdump.enc"
_NAME_TIME_FORMAT = "%Y%m%d-%H%M%SZ"
_NAME_PATTERN = re.compile(r"paceforge-(\d{8}-\d{6}Z)" + re.escape(BACKUP_SUFFIX))
_MAX_ERROR_TEXT = 500


class BackupError(Exception):
    """A backup cannot be made. The message never contains keys, passwords or dump content."""


def load_backup_keys(key_file: Path | None = None) -> list[str]:
    """Return the backup keys from ``key_file`` or the settings, checked and kept apart.

    A key file holds one or more keys separated by commas or line breaks. No backup key may also
    be an instance key (``ENCRYPTION_KEYS``): that would let one leaked secret open both.
    """
    if key_file is not None:
        try:
            text = key_file.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            raise BackupError("The key file cannot be read.") from None
        keys = [key.strip() for key in re.split(r"[,\r\n]", text) if key.strip()]
    else:
        keys = list(settings.BACKUP_ENCRYPTION_KEYS)
    if not keys:
        raise BackupError(
            "No backup key found: set BACKUP_ENCRYPTION_KEY or pass a key file with --key-file."
        )
    parse_backup_keys(keys)
    if set(keys) & set(settings.ENCRYPTION_KEYS):
        raise BackupError("A backup key must differ from ENCRYPTION_KEY.")
    return keys


def backup_filename(moment: datetime) -> str:
    return f"paceforge-{moment.astimezone(UTC).strftime(_NAME_TIME_FORMAT)}{BACKUP_SUFFIX}"


def _pg_command(
    program: str, options: list[str], database: Mapping[str, Any]
) -> tuple[list[str], dict[str, str]]:
    """Build a ``pg_*`` command line for ``database``; the password only goes into the env."""
    command = [program, *options, "--no-password"]
    if database.get("HOST"):
        command += ["-h", str(database["HOST"])]
    if database.get("PORT"):
        command += ["-p", str(database["PORT"])]
    if database.get("USER"):
        command += ["-U", str(database["USER"])]
    command += ["-d", str(database["NAME"])]
    env = dict(os.environ)
    env.pop("PGPASSWORD", None)
    if database.get("PASSWORD"):
        env["PGPASSWORD"] = str(database["PASSWORD"])
    return command, env


def _pg_dump_command() -> tuple[list[str], dict[str, str]]:
    return _pg_command(PG_DUMP, ["-Fc"], settings.DATABASES["default"])


def _stderr_text(stderr: IO[bytes]) -> str:
    stderr.seek(0)
    return stderr.read(_MAX_ERROR_TEXT).decode("utf-8", errors="replace").strip()


def create_backup(output_dir: Path, keys: Sequence[str], *, now: datetime | None = None) -> Path:
    """Dump the database into an encrypted file in ``output_dir`` and return its path."""
    moment = now or datetime.now(UTC)
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = output_dir / backup_filename(moment)
    command, env = _pg_dump_command()

    descriptor, temp_name = tempfile.mkstemp(prefix=".paceforge-", suffix=".tmp", dir=output_dir)
    temp_path = Path(temp_name)
    try:
        os.fchmod(descriptor, 0o600)
        with (
            os.fdopen(descriptor, "wb") as destination,
            tempfile.TemporaryFile() as stderr,
        ):
            try:
                process = subprocess.Popen(  # noqa: S603 - fixed argument list, no shell
                    command, stdout=subprocess.PIPE, stderr=stderr, env=env
                )
            except OSError:
                raise BackupError("pg_dump could not be started.") from None
            assert process.stdout is not None
            try:
                with process.stdout:
                    encrypt_stream(cast(BinaryIO, process.stdout), destination, list(keys))
            except BaseException:
                process.kill()
                process.wait()
                raise
            if process.wait() != 0:
                detail = _stderr_text(stderr)
                raise BackupError(
                    f"pg_dump failed with exit code {process.returncode}"
                    + (f": {detail}" if detail else ".")
                )
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temp_path, target)
    except BaseException:
        with contextlib.suppress(OSError):
            temp_path.unlink()
        raise
    return target


def database_is_empty(database: Mapping[str, Any]) -> bool:
    """Return whether the ``public`` schema of ``database`` has no tables."""
    try:
        with (
            psycopg.connect(
                host=database.get("HOST") or None,
                port=database.get("PORT") or None,
                user=database.get("USER") or None,
                password=database.get("PASSWORD") or None,
                dbname=str(database["NAME"]),
                connect_timeout=10,
            ) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public')")
            row = cursor.fetchone()
    except psycopg.Error:
        raise BackupError("The target database cannot be reached.") from None
    return row is None or not row[0]


class _FirstChunkChecked(Exception):
    """Raised by ``_FirstWrite`` once the first chunk decrypted."""


class _FirstWrite:
    def write(self, data: bytes) -> int:
        raise _FirstChunkChecked


def _check_backup(path: Path, keys: Sequence[str]) -> None:
    """Make sure the file is a backup that one of ``keys`` opens, before anything is restored."""
    try:
        with path.open("rb") as source:
            try:
                decrypt_stream(source, cast(BinaryIO, _FirstWrite()), list(keys))
            except _FirstChunkChecked:
                pass
    except FileNotFoundError:
        raise BackupError("The backup file does not exist.") from None
    except OSError:
        raise BackupError("The backup file cannot be read.") from None


def restore_backup(
    path: Path,
    keys: Sequence[str],
    database: Mapping[str, Any] | None = None,
    *,
    allow_non_empty: bool = False,
) -> None:
    """Decrypt ``path`` straight into ``pg_restore`` for ``database`` (default: the configured one).

    A database with tables is refused unless ``allow_non_empty`` is set; then existing objects are
    dropped first. Everything runs in one transaction, so a failed restore changes nothing.
    """
    target = settings.DATABASES["default"] if database is None else database
    _check_backup(path, keys)
    if not allow_non_empty and not database_is_empty(target):
        raise BackupError(
            "The target database is not empty. Restore into an empty database or pass "
            "--allow-non-empty to replace its contents."
        )
    options = ["--no-owner", "--no-privileges", "--exit-on-error", "--single-transaction"]
    if allow_non_empty:
        options += ["--clean", "--if-exists"]
    command, env = _pg_command(PG_RESTORE, options, target)

    with tempfile.TemporaryFile() as stderr, path.open("rb") as source:
        try:
            process = subprocess.Popen(  # noqa: S603 - fixed argument list, no shell
                command, stdin=subprocess.PIPE, stderr=stderr, env=env
            )
        except OSError:
            raise BackupError("pg_restore could not be started.") from None
        assert process.stdin is not None
        try:
            try:
                decrypt_stream(source, cast(BinaryIO, process.stdin), list(keys))
                process.stdin.close()
            except BrokenPipeError:
                pass  # pg_restore stopped reading; its exit code and message follow below
        except BaseException:
            # Kill before closing the pipe: pg_restore must never see a clean end of a damaged
            # stream, or it could commit a partial restore.
            process.kill()
            process.wait()
            with contextlib.suppress(OSError):
                process.stdin.close()
            raise
        with contextlib.suppress(OSError):
            process.stdin.close()
        if process.wait() != 0:
            detail = _stderr_text(stderr)
            raise BackupError(
                f"pg_restore failed with exit code {process.returncode}"
                + (f": {detail}" if detail else ".")
            )


def _backup_time(path: Path) -> datetime | None:
    match = _NAME_PATTERN.fullmatch(path.name)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), _NAME_TIME_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def prune_backups(
    output_dir: Path, keep_daily: int, keep_weekly: int, *, protect: Path | None = None
) -> int:
    """Delete expired backups and return how many were removed.

    Keeps the newest backup of each of the latest ``keep_daily`` UTC days and of each of the
    latest ``keep_weekly`` ISO weeks (days and weeks that have a backup). Files that are not
    PaceForge backups and the ``protect`` file are never touched.
    """
    found: list[tuple[datetime, Path]] = []
    for path in output_dir.iterdir():
        moment = _backup_time(path)
        if moment is not None and path.is_file() and not path.is_symlink():
            found.append((moment, path))
    found.sort(key=lambda item: item[0], reverse=True)

    keep: set[Path] = {protect} if protect is not None else set()
    days: set[object] = set()
    weeks: set[object] = set()
    for moment, path in found:  # newest first: the first file of a bucket is its newest
        day = moment.date()
        week = moment.isocalendar()[:2]
        if day not in days and len(days) < keep_daily:
            days.add(day)
            keep.add(path)
        if week not in weeks and len(weeks) < keep_weekly:
            weeks.add(week)
            keep.add(path)

    removed = 0
    for _, path in found:
        if path in keep:
            continue
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
            removed += 1
    return removed
