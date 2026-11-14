import hashlib
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from django.db import IntegrityError

from accounts.models import User
from activities import services
from activities.models import Activity, ActivityFile
from activities.parsing import InvalidFileError, UnsupportedFileError
from activities.services import DuplicateActivityError, FileTooLargeError, import_activity

from .fit_builder import activity_file
from .tcx_builder import tcx_document

pytestmark = pytest.mark.django_db

START = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)
BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def counts() -> tuple[int, int]:
    return Activity.objects.count(), ActivityFile.objects.count()


class TestImport:
    def test_a_fit_file_creates_one_activity_and_one_file(self, alice: User) -> None:
        data = activity_file()

        activity = import_activity(alice, data)

        assert counts() == (1, 1)
        stored = Activity.objects.get(pk=activity.pk)
        assert stored.owner == alice
        assert stored.source == Activity.Source.FIT_FILE
        assert stored.source_hash == hashlib.sha256(data).hexdigest()
        assert stored.sport == Activity.Sport.RUNNING
        assert stored.start_time == START
        assert stored.elapsed_seconds == pytest.approx(3904.59)
        assert stored.timer_seconds == pytest.approx(3900.0)
        assert stored.distance_m == pytest.approx(12766.23)
        assert (stored.avg_heart_rate, stored.max_heart_rate) == (155, 169)
        assert stored.avg_power_w == 325
        assert stored.calories == 1133
        assert stored.manufacturer == "garmin"
        assert len(stored.laps) == 1
        assert stored.laps[0]["start_time"] == START.isoformat()
        assert stored.laps[0]["distance_m"] == pytest.approx(6383.0)
        assert (stored.laps[0]["avg_heart_rate"], stored.laps[0]["max_heart_rate"]) == (150, 165)

    def test_a_tcx_file_creates_one_activity_and_one_file(self, alice: User) -> None:
        data = tcx_document(sport="Biking")

        activity = import_activity(alice, data)

        assert counts() == (1, 1)
        stored = Activity.objects.get(pk=activity.pk)
        assert stored.source == Activity.Source.TCX_FILE
        assert stored.sport == Activity.Sport.CYCLING
        assert stored.start_time == START
        assert stored.distance_m == pytest.approx(7000.0)
        assert stored.manufacturer == "Test Watch"
        assert [lap["distance_m"] for lap in stored.laps] == [2000, 4000, 1000]
        assert stored.laps[1]["start_time"] == "2026-11-12T06:40:00+00:00"

    @pytest.mark.parametrize("make", [activity_file, tcx_document])
    def test_the_stored_file_is_identical_after_decompressing(self, alice: User, make: Any) -> None:
        data = make()

        activity = import_activity(alice, data)

        file = ActivityFile.objects.get(pk=activity.pk)
        assert file.read() == data
        assert file.original_size == len(data)

    def test_values_the_file_does_not_report_stay_empty(self, alice: User) -> None:
        activity = import_activity(alice, tcx_document(laps=[{"start": START}]))

        stored = Activity.objects.get(pk=activity.pk)
        assert stored.distance_m is None
        assert stored.avg_heart_rate is None
        assert stored.total_ascent_m is None
        assert stored.laps[0]["distance_m"] is None


class TestDuplicates:
    @pytest.mark.parametrize("make", [activity_file, tcx_document])
    def test_the_same_file_twice_is_refused_with_the_existing_id(
        self, alice: User, make: Any
    ) -> None:
        first = import_activity(alice, make())

        with pytest.raises(DuplicateActivityError) as raised:
            import_activity(alice, make())

        assert raised.value.existing_id == first.pk
        assert counts() == (1, 1)

    def test_the_same_run_as_fit_and_as_tcx_is_refused(self, alice: User) -> None:
        first = import_activity(alice, activity_file())

        with pytest.raises(DuplicateActivityError) as raised:
            import_activity(alice, tcx_document())

        assert raised.value.existing_id == first.pk
        assert counts() == (1, 1)

    def test_a_file_that_starts_a_few_minutes_later_with_the_same_length_is_refused(
        self, alice: User
    ) -> None:
        first = import_activity(alice, activity_file())

        with pytest.raises(DuplicateActivityError) as raised:
            import_activity(alice, activity_file(start=START + timedelta(minutes=4)))

        assert raised.value.existing_id == first.pk
        assert counts() == (1, 1)

    def test_a_file_that_starts_later_than_the_tolerance_is_another_activity(
        self, alice: User
    ) -> None:
        import_activity(alice, activity_file())

        import_activity(alice, activity_file(start=START + timedelta(minutes=11)))

        assert counts() == (2, 2)

    def test_a_session_entered_by_hand_is_the_duplicate_of_its_file(self, alice: User) -> None:
        by_hand = Activity.objects.create(
            owner=alice,
            source=Activity.Source.MANUAL,
            sport=Activity.Sport.RUNNING,
            start_time=START + timedelta(minutes=3),
            timer_seconds=65 * 60,
        )

        with pytest.raises(DuplicateActivityError) as raised:
            import_activity(alice, activity_file())

        assert raised.value.existing_id == by_hand.pk
        assert counts() == (1, 0)

    def test_the_same_start_in_another_sport_is_another_activity(self, alice: User) -> None:
        import_activity(alice, activity_file())

        import_activity(alice, tcx_document(sport="Biking"))

        assert counts() == (2, 2)

    def test_another_user_may_import_the_same_file(self, alice: User, bob: User) -> None:
        data = activity_file()
        first = import_activity(alice, data)

        second = import_activity(bob, data)

        assert second.pk != first.pk
        assert second.owner == bob
        assert counts() == (2, 2)

    def test_a_duplicate_of_someone_else_is_not_reported(self, alice: User, bob: User) -> None:
        """The error must not reveal another user's activity id."""
        import_activity(alice, activity_file())

        import_activity(bob, tcx_document())  # same start and sport, but another user

        assert Activity.objects.filter(owner=bob).count() == 1

    def test_an_insert_that_loses_a_race_is_reported_as_a_duplicate(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both checks pass, then the database refuses the insert: it must still be a duplicate."""
        data = activity_file()
        first = import_activity(alice, data)
        calls = iter([None, first])
        monkeypatch.setattr(services, "_find_duplicate", lambda *args: next(calls))

        with pytest.raises(DuplicateActivityError) as raised:
            import_activity(alice, data)

        assert raised.value.existing_id == first.pk
        assert counts() == (1, 1)

    def test_an_integrity_error_that_is_no_duplicate_is_not_hidden(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(services.Activity.objects, "create", _raise(IntegrityError("other")))

        with pytest.raises(IntegrityError):
            import_activity(alice, activity_file())

        assert counts() == (0, 0)


class TestNothingIsStoredOnFailure:
    @pytest.mark.parametrize(
        ("data", "error"),
        [
            (b"", UnsupportedFileError),
            (b"just some text", UnsupportedFileError),
            (activity_file()[:-30], InvalidFileError),
            (tcx_document(prolog='<?xml version="1.0"?><!DOCTYPE x>'), InvalidFileError),
            (tcx_document()[:-40], InvalidFileError),
        ],
    )
    def test_a_parser_error_stores_nothing(self, alice: User, data: bytes, error: type) -> None:
        with pytest.raises(error):
            import_activity(alice, data)

        assert counts() == (0, 0)

    def test_a_failure_while_saving_the_file_leaves_no_activity(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ActivityFile, "save", _raise(RuntimeError("disk full")))

        with pytest.raises(RuntimeError):
            import_activity(alice, activity_file())

        assert counts() == (0, 0)

    def test_a_failure_while_saving_the_activity_leaves_no_file(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Activity, "save", _raise(RuntimeError("disk full")))

        with pytest.raises(RuntimeError):
            import_activity(alice, activity_file())

        assert counts() == (0, 0)


class TestSizeLimit:
    def test_a_file_over_the_limit_is_refused_before_parsing(
        self, alice: User, settings: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data = activity_file()
        settings.ACTIVITY_UPLOAD_MAX_BYTES = len(data) - 1
        monkeypatch.setattr(services, "parse_activity_file", _raise(AssertionError("parsed")))

        with pytest.raises(FileTooLargeError):
            import_activity(alice, data)

        assert counts() == (0, 0)

    def test_a_file_exactly_at_the_limit_is_accepted(self, alice: User, settings: Any) -> None:
        data = activity_file()
        settings.ACTIVITY_UPLOAD_MAX_BYTES = len(data)

        import_activity(alice, data)

        assert counts() == (1, 1)

    def test_the_default_limit_is_25_mb(self, settings: Any) -> None:
        assert settings.ACTIVITY_UPLOAD_MAX_BYTES == 25 * 1024 * 1024

    def test_errors_contain_nothing_from_the_file(self, alice: User, settings: Any) -> None:
        settings.ACTIVITY_UPLOAD_MAX_BYTES = 10

        with pytest.raises(FileTooLargeError) as raised:
            import_activity(alice, b"secret-track-data" * 3)

        assert "secret" not in str(raised.value)


class TestSetting:
    @pytest.mark.parametrize("value", ["0", "-5", "lots", "1.5", ""])  # "" is not a number either
    def test_an_invalid_limit_fails_at_startup(self, value: str) -> None:
        result = _import_settings(ACTIVITY_UPLOAD_MAX_BYTES=value)

        assert result.returncode != 0

    def test_a_positive_limit_is_read_from_the_environment(self) -> None:
        result = _import_settings(
            ACTIVITY_UPLOAD_MAX_BYTES="1234",
            check="print(config.settings.ACTIVITY_UPLOAD_MAX_BYTES)",
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "1234"

    def test_zero_is_explained(self) -> None:
        result = _import_settings(ACTIVITY_UPLOAD_MAX_BYTES="0")

        assert "ACTIVITY_UPLOAD_MAX_BYTES must be a positive integer" in result.stderr


def _raise(error: BaseException) -> Any:
    def fail(*args: Any, **kwargs: Any) -> Any:
        raise error

    return fail


def _import_settings(check: str = "pass", **env: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ | {
        "DJANGO_SECRET_KEY": "x",
        "DATABASE_URL": "sqlite:///unused.db",
        "ENCRYPTION_KEY": "srPGFiK_-1uuYQrhJix9QxALddGxwSw-I5bllic4QsY=",
    }
    environment.pop("ACTIVITY_UPLOAD_MAX_BYTES", None)
    return subprocess.run(
        [sys.executable, "-c", f"import config.settings; {check}"],
        env=environment | env,
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
