import secrets
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import environ
import psycopg
import pytest
from django.db import connection
from django.db.utils import ConnectionHandler
from psycopg import sql

from config.database import database_from_env
from core.backup import _pg_command, database_is_empty

COMPOSE_PROD = Path(__file__).resolve().parents[2] / "compose.prod.yaml"
# Every character that breaks a password inside a URL.
URL_RESERVED = "@:/?#%&+="


@pytest.mark.django_db
def test_tests_run_against_postgresql() -> None:
    assert connection.vendor == "postgresql"

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)


@pytest.fixture
def reserved_role() -> Iterator[tuple[str, str]]:
    """A temporary login role whose password holds URL-reserved characters."""
    admin = connection.settings_dict
    name = f"pf_role_{secrets.token_hex(6)}"
    password = f"{URL_RESERVED}{secrets.token_urlsafe(12)}{URL_RESERVED}"
    with psycopg.connect(
        host=admin["HOST"] or None,
        port=admin["PORT"] or None,
        user=admin["USER"],
        password=admin["PASSWORD"] or None,
        dbname=admin["NAME"],
        autocommit=True,
    ) as admin_connection:
        admin_connection.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(name), sql.Literal(password)
            )
        )
        try:
            yield name, password
        finally:
            admin_connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))


@pytest.mark.django_db
def test_role_with_url_reserved_password_connects_everywhere(
    reserved_role: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    role, password = reserved_role
    admin = connection.settings_dict
    env = environ.Env()
    monkeypatch.setattr(
        env,
        "ENVIRON",
        {
            "DATABASE_URL": "",
            "POSTGRES_HOST": admin["HOST"] or "localhost",
            "POSTGRES_PORT": str(admin["PORT"] or 5432),
            "POSTGRES_USER": role,
            "POSTGRES_PASSWORD": password,
            "POSTGRES_DB": admin["NAME"],
        },
    )

    database = database_from_env(env)

    assert database["PASSWORD"] == password

    with psycopg.connect(
        host=database["HOST"],
        port=database["PORT"],
        user=database["USER"],
        password=database["PASSWORD"],
        dbname=database["NAME"],
    ) as direct:
        assert direct.execute("SELECT current_user").fetchone() == (role,)

    handler = ConnectionHandler({"default": database})
    try:
        with handler["default"].cursor() as cursor:
            cursor.execute("SELECT current_user")
            assert cursor.fetchone() == (role,)
    finally:
        handler.close_all()

    # The test database holds the Django tables, so it is not empty; reaching it is the point.
    assert database_is_empty(database) is False

    command, command_env = _pg_command("psql", ["-tA", "-c", "SELECT current_user"], database)
    assert command_env["PGPASSWORD"] == password
    assert password not in " ".join(command)
    if shutil.which(command[0]):
        result = subprocess.run(
            command, env=command_env, check=True, capture_output=True, text=True, timeout=30
        )
        assert result.stdout.strip() == role


def test_compose_prod_defines_the_database_environment_once() -> None:
    if not COMPOSE_PROD.exists():
        pytest.skip("compose.prod.yaml is not part of this checkout")
    text = COMPOSE_PROD.read_text()

    assert "DATABASE_URL: postgres" not in text
    assert "://" not in "".join(line for line in text.splitlines() if "POSTGRES_PASSWORD" in line)
    assert text.count("POSTGRES_HOST:") == 1
    assert text.count("DATABASE_URL:") == 1
    # backend, scheduler and backup each merge the shared block.
    assert text.count("<<: *backend-environment") == 3
