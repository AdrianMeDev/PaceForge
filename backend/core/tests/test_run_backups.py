from io import StringIO
from typing import Any

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from core.management.commands import run_backups


class StopLoop(Exception):
    pass


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
