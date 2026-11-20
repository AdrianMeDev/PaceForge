from io import StringIO
from typing import Any

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from core.management.commands import run_backups


class StopLoop(Exception):
    pass


@pytest.fixture(autouse=True)
def no_database_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    # The loop closes stale connections between rounds; these tests run without a database.
    monkeypatch.setattr(run_backups, "close_old_connections", lambda: None)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def fake_call_command(name: str, *args: Any, **kwargs: Any) -> None:
        seen.append(name)
        kwargs["stdout"].write("paceforge-x.pgdump.enc  10 bytes  pruned 0")

    monkeypatch.setattr(run_backups, "call_command", fake_call_command)
    return seen


def test_once_makes_one_backup_and_does_not_sleep(
    calls: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_sleep(seconds: float) -> None:
        raise AssertionError("must not sleep with --once")

    monkeypatch.setattr(run_backups.time, "sleep", no_sleep)
    out = StringIO()
    call_command("run_backups", "--once", stdout=out)
    assert calls == ["backup_db"]
    assert "pgdump.enc" in out.getvalue()


@override_settings(BACKUP_INTERVAL_HOURS=3)
def test_loop_sleeps_the_configured_interval(
    calls: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise StopLoop

    monkeypatch.setattr(run_backups.time, "sleep", fake_sleep)
    with pytest.raises(StopLoop):
        call_command("run_backups", stdout=StringIO())
    assert sleeps == [3 * 3600, 3 * 3600]
    assert calls == ["backup_db", "backup_db"]


@pytest.mark.parametrize("args", [[], ["--once"]])
@pytest.mark.parametrize("interval", [0, -1, 169, 1.5, True])
def test_invalid_interval_fails_before_the_first_round(
    calls: list[str],
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
    interval: Any,
    args: list[str],
) -> None:
    def no_sleep(seconds: float) -> None:
        raise AssertionError("must not sleep with an invalid interval")

    monkeypatch.setattr(run_backups.time, "sleep", no_sleep)
    settings.BACKUP_INTERVAL_HOURS = interval
    with pytest.raises(CommandError, match="BACKUP_INTERVAL_HOURS must be a whole number"):
        call_command("run_backups", *args, stdout=StringIO())
    assert calls == []


@pytest.mark.parametrize("interval", [1, 168])
def test_interval_limits_are_valid(
    calls: list[str], monkeypatch: pytest.MonkeyPatch, settings: Any, interval: int
) -> None:
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        raise StopLoop

    monkeypatch.setattr(run_backups.time, "sleep", fake_sleep)
    settings.BACKUP_INTERVAL_HOURS = interval
    with pytest.raises(StopLoop):
        call_command("run_backups", stdout=StringIO())
    assert calls == ["backup_db"]
    assert sleeps == [interval * 3600]


def test_once_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(name: str, *args: Any, **kwargs: Any) -> None:
        raise CommandError("pg_dump failed")

    monkeypatch.setattr(run_backups, "call_command", failing)
    with pytest.raises(CommandError, match="pg_dump failed"):
        call_command("run_backups", "--once", stdout=StringIO())


def test_loop_survives_a_failed_round(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(name: str, *args: Any, **kwargs: Any) -> None:
        raise CommandError("pg_dump failed")

    def stop(seconds: float) -> None:
        raise StopLoop

    monkeypatch.setattr(run_backups, "call_command", failing)
    monkeypatch.setattr(run_backups.time, "sleep", stop)
    err = StringIO()
    with pytest.raises(StopLoop):
        call_command("run_backups", stdout=StringIO(), stderr=err)
    assert "Backup failed: pg_dump failed" in err.getvalue()
