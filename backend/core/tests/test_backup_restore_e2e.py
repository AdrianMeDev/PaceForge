"""End to end: a real encrypted ``pg_dump`` is restored into an empty PostgreSQL database.

The test needs ``pg_dump`` and ``pg_restore`` of PostgreSQL 17. It uses the ones on the ``PATH``
(CI installs ``postgresql-client-17``) and otherwise runs them inside the ``db`` container of
``compose.dev.yaml``, which is the server the tests use anyway.
"""

import base64
import os
import re
import shutil
import stat
import subprocess
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote

import psycopg
import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db.models import Model
from psycopg import sql

from coach.models import AIProviderConfiguration
from core import backup
from core.encryption import PREFIX, DecryptionError, decrypt
from integrations.models import ProviderConnection
from planning.models import PlannedWorkout, WeeklyPlan

PG_MAJOR = "17"
COMPOSE_FILE = Path(__file__).resolve().parents[3] / "compose.dev.yaml"

CONNECTION_KEY = "intervals-secret-key-0123456789"
AI_KEY = "sk-ai-secret-key-9876543210"
EMAIL = "restore-athlete@example.com"
WORKOUT_TITLE = "Restore check threshold intervals"


def _native_tool(name: str) -> str | None:
    candidates = [shutil.which(name), f"/usr/lib/postgresql/{PG_MAJOR}/bin/{name}"]
    for candidate in candidates:
        if candidate is None or not Path(candidate).is_file():
            continue
        try:
            result = subprocess.run(  # noqa: S603 - fixed argument list, no shell
                [candidate, "--version"], capture_output=True, text=True, timeout=30, check=False
            )
        except OSError, subprocess.SubprocessError:
            continue
        if re.search(rf"\) {PG_MAJOR}(\.|$)", result.stdout.strip()):
            return candidate
    return None


def _compose_wrapper(directory: Path, name: str) -> str | None:
    """A script that runs ``name`` in the ``db`` container, with stdin and PGPASSWORD passed on."""
    docker = shutil.which("docker")
    if docker is None or not COMPOSE_FILE.is_file():
        return None
    script = directory / name
    command = f'exec "{docker}" compose -f "{COMPOSE_FILE}" exec -T -e PGPASSWORD db {name} "$@"'
    script.write_text(f"#!/bin/sh\n{command}\n")
    script.chmod(0o700)
    return str(script)


@pytest.fixture
def pg_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tools: dict[str, str] = {}
    wrappers = tmp_path / "wrappers"
    wrappers.mkdir()
    for name in ("pg_dump", "pg_restore"):
        found = _native_tool(name) or _compose_wrapper(wrappers, name)
        if found is None:
            pytest.skip(f"{name} {PG_MAJOR} is not installed and the compose db is not usable.")
        tools[name] = found
    monkeypatch.setattr(backup, "PG_DUMP", tools["pg_dump"])
    monkeypatch.setattr(backup, "PG_RESTORE", tools["pg_restore"])


def _connect(name: str, **options: Any) -> psycopg.Connection[Any]:
    database = backup.settings.DATABASES["default"]
    return psycopg.connect(
        host=database.get("HOST") or None,
        port=database.get("PORT") or None,
        user=database.get("USER") or None,
        password=database.get("PASSWORD") or None,
        dbname=name,
        **options,
    )


def _database_url(name: str) -> str:
    database = backup.settings.DATABASES["default"]
    return (
        f"postgres://{quote(str(database['USER']), safe='')}:"
        f"{quote(str(database['PASSWORD']), safe='')}@{database['HOST']}:{database['PORT']}/{name}"
    )


@contextmanager
def empty_database() -> Iterator[str]:
    """Create a fresh, empty database next to the test one and always drop it again."""
    name = f"paceforge_restore_{uuid.uuid4().hex[:12]}"
    with _connect(str(backup.settings.DATABASES["default"]["NAME"]), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield name
        finally:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )


def _scalar(name: str, query: sql.SQL | sql.Composed | str, *params: Any) -> Any:
    with _connect(name) as connection:
        row = connection.execute(query, params).fetchone()
    assert row is not None
    return row[0]


def _table_count(name: str) -> int:
    return int(_scalar(name, "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"))


def _rows(name: str, model: Any) -> int:
    query = sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(model._meta.db_table))
    with _connect(name) as connection:
        row = connection.execute(query).fetchone()
    assert row is not None
    return int(row[0])


def _raw_key(name: str, model: Any) -> str:
    query = sql.SQL("SELECT api_key FROM {}").format(sql.Identifier(model._meta.db_table))
    with _connect(name) as connection:
        row = connection.execute(query).fetchone()
    assert row is not None
    return str(row[0])


@pytest.mark.django_db(transaction=True)
def test_encrypted_backup_restores_into_empty_database(
    pg_tools: None, tmp_path: Path, settings: Any
) -> None:
    backup_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    settings.BACKUP_ENCRYPTION_KEYS = [backup_key]
    instance_keys = list(settings.ENCRYPTION_KEYS)

    user = get_user_model().objects.create_user(email=EMAIL, password="x" * 20)
    ProviderConnection.objects.create(
        owner=user, provider="intervals_icu", api_key=CONNECTION_KEY, athlete_id="i1"
    )
    AIProviderConfiguration.objects.create(
        owner=user, provider="anthropic", model="claude-sonnet-5-5", api_key=AI_KEY
    )
    plan = WeeklyPlan.objects.create(owner=user, week_start=date(2026, 3, 2))
    PlannedWorkout.objects.create(
        owner=user,
        plan=plan,
        day=date(2026, 3, 3),
        sport="running",
        title=WORKOUT_TITLE,
        goal="threshold",
        duration_minutes=60,
    )
    expected: dict[type[Model], int] = {
        model: model.objects.count()
        for model in (
            get_user_model(),
            ProviderConnection,
            AIProviderConfiguration,
            WeeklyPlan,
            PlannedWorkout,
        )
    }

    # Backup: encrypted, private and free of plaintext and of the instance key.
    out = tmp_path / "backups"
    call_command("backup_db", "--output-dir", str(out), "--no-prune")
    (archive,) = out.glob(f"*{backup.BACKUP_SUFFIX}")
    assert stat.S_IMODE(archive.stat().st_mode) == 0o600
    content = archive.read_bytes()
    assert not content.startswith(b"PGDMP")
    forbidden = [CONNECTION_KEY, AI_KEY, EMAIL, WORKOUT_TITLE, PREFIX, backup_key]
    forbidden += instance_keys
    for secret in forbidden:
        assert secret.encode() not in content

    with empty_database() as target:
        url = _database_url(target)

        # A wrong backup key fails and leaves the database empty.
        settings.BACKUP_ENCRYPTION_KEYS = [base64.urlsafe_b64encode(os.urandom(32)).decode()]
        with pytest.raises(CommandError):
            call_command("restore_db", str(archive), "--database-url", url)
        assert _table_count(target) == 0

        # The right key restores everything.
        settings.BACKUP_ENCRYPTION_KEYS = [backup_key]
        call_command("restore_db", str(archive), "--database-url", url)
        for model, count in expected.items():
            assert _rows(target, model) == count
        assert (
            _scalar(
                target,
                sql.SQL("SELECT title FROM {}").format(
                    sql.Identifier(PlannedWorkout._meta.db_table)
                ),
            )
            == WORKOUT_TITLE
        )

        # The secrets are still ciphertext; only the original instance key opens them.
        secrets = {ProviderConnection: CONNECTION_KEY, AIProviderConfiguration: AI_KEY}
        other_key = Fernet.generate_key().decode()
        for model, plaintext in secrets.items():
            raw = _raw_key(target, model)
            assert raw.startswith(PREFIX)
            assert plaintext not in raw
            assert decrypt(raw) == plaintext
            settings.ENCRYPTION_KEYS = [other_key]
            with pytest.raises(DecryptionError):
                decrypt(raw)
            settings.ENCRYPTION_KEYS = instance_keys

        # A second restore into the now filled database is refused and changes nothing.
        tables = _table_count(target)
        with pytest.raises(CommandError, match="not empty"):
            call_command("restore_db", str(archive), "--database-url", url)
        assert _table_count(target) == tables
        for model, count in expected.items():
            assert _rows(target, model) == count
