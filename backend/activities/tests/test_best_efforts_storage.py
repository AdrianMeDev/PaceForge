import logging
from io import StringIO
from typing import Any

import pytest
from django.core.management import CommandError, call_command

from accounts.models import User
from activities import services
from activities.efforts import BestEfforts, Effort, as_json
from activities.models import Activity, ActivityFile
from activities.services import import_activity

from .fit_builder import activity_file
from .tcx_builder import tcx_document, trackpoint_document

pytestmark = pytest.mark.django_db

SamplesType = list[tuple[int, int | None, int | None, int | None]]


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def hard_ride(minutes: int = 21, power: int = 250, start_day: int = 0) -> bytes:
    from datetime import UTC, datetime, timedelta

    samples: SamplesType = [(s, power, s * 900, 155) for s in range(minutes * 60)]
    return activity_file(
        samples=samples, start=datetime(2026, 11, 1, 6, tzinfo=UTC) + timedelta(days=start_day)
    )


def stored(activity: Activity) -> dict[str, Any]:
    value = Activity.objects.get(pk=activity.pk).best_efforts
    assert value is not None
    return dict(value)


def backfill(*args: str) -> str:
    out = StringIO()
    call_command("backfill_best_efforts", *args, stdout=out)
    return out.getvalue()


class TestTheStoredForm:
    def test_windows_become_text_keys_and_numbers_are_rounded(self) -> None:
        found = BestEfforts(
            power={1200: Effort(250.04, 155.06), 5: Effort(400.0, None)},
            speed={1800: Effort(10 / 3, 160.0)},
        )

        assert as_json(found) == {
            "power": {
                "5": {"value": 400.0, "heart_rate": None},
                "1200": {"value": 250.0, "heart_rate": 155.1},
            },
            "speed": {"1800": {"value": 3.3333, "heart_rate": 160.0}},
        }

    def test_nothing_found_is_two_empty_parts(self) -> None:
        assert as_json(BestEfforts()) == {"power": {}, "speed": {}}


class TestOnImport:
    def test_a_fit_file_stores_its_efforts(self, alice: User) -> None:
        activity = import_activity(alice, hard_ride())

        found = stored(activity)
        assert found["power"]["1200"] == {"value": 250.0, "heart_rate": 155.0}
        assert found["speed"]["1200"]["value"] == pytest.approx(9)

    def test_a_tcx_file_stores_its_efforts(self, alice: User) -> None:
        points: list[tuple[float, float | None, int | None, int | None]] = [
            (s, s * 3.0, 160, None) for s in range(400)
        ]
        activity = import_activity(alice, trackpoint_document(points))

        found = stored(activity)
        assert found["speed"]["300"] == {"value": 3.0, "heart_rate": 160.0}
        assert found["power"] == {}

    def test_a_file_without_a_usable_series_still_imports(self, alice: User) -> None:
        activity = import_activity(alice, activity_file(records=3, with_record_times=False))

        assert Activity.objects.get(pk=activity.pk).best_efforts == {}

    def test_a_series_the_reader_refuses_counts_as_none(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from activities.parsing import InvalidFileError

        def refuse(data: bytes) -> Any:
            raise InvalidFileError("The FIT file is damaged or incomplete.")

        monkeypatch.setattr(services, "parse_series", refuse)

        activity = import_activity(alice, tcx_document())

        assert Activity.objects.get(pk=activity.pk).best_efforts == {}

    def test_an_unexpected_failure_is_logged_and_the_import_succeeds(
        self, alice: User, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        def explode(data: bytes) -> Any:
            raise RuntimeError("a bug")

        monkeypatch.setattr(services, "parse_series", explode)
        caplog.set_level(logging.ERROR)

        activity = import_activity(alice, tcx_document())

        assert Activity.objects.get(pk=activity.pk).best_efforts is None
        assert ActivityFile.objects.filter(pk=activity.pk).exists()
        assert "Could not compute the best efforts" in caplog.text

    def test_a_refused_import_does_not_compute_anything(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[bytes] = []
        import_activity(alice, hard_ride())
        monkeypatch.setattr(services, "best_efforts_of", lambda data: calls.append(data))

        with pytest.raises(services.DuplicateActivityError):
            import_activity(alice, hard_ride())

        assert calls == []


class TestBackfill:
    def missing(self, owner: User, data: bytes) -> Activity:
        activity = import_activity(owner, data)
        Activity.objects.filter(pk=activity.pk).update(best_efforts=None)
        return activity

    def test_it_fills_what_is_missing_from_the_stored_file(self, alice: User) -> None:
        activity = self.missing(alice, hard_ride())

        output = backfill()

        assert stored(activity)["power"]["1200"]["value"] == 250
        assert output.strip() == (
            "Computed 1, no usable series in 0, failed 0, without a stored file 0."
        )

    def test_it_skips_what_is_already_there(self, alice: User) -> None:
        done = import_activity(alice, hard_ride())
        Activity.objects.filter(pk=done.pk).update(best_efforts={"power": {}, "speed": {"x": 1}})

        output = backfill()

        assert Activity.objects.get(pk=done.pk).best_efforts == {"power": {}, "speed": {"x": 1}}
        assert output.startswith("Computed 0,")

    def test_it_can_run_twice(self, alice: User) -> None:
        self.missing(alice, hard_ride())

        backfill()
        output = backfill()

        assert output.startswith("Computed 0, no usable series in 0, failed 0")

    def test_files_without_a_series_are_counted_and_not_tried_again(self, alice: User) -> None:
        activity = self.missing(alice, activity_file(records=3, with_record_times=False))

        assert "no usable series in 1" in backfill()
        assert Activity.objects.get(pk=activity.pk).best_efforts == {}
        assert "no usable series in 0" in backfill()

    def test_a_failure_is_counted_and_tried_again_next_time(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        activity = self.missing(alice, hard_ride())

        def explode(data: bytes) -> Any:
            raise RuntimeError("a bug")

        monkeypatch.setattr(services, "parse_series", explode)
        assert backfill().strip() == (
            "Computed 0, no usable series in 0, failed 1, without a stored file 0."
        )
        assert Activity.objects.get(pk=activity.pk).best_efforts is None
        monkeypatch.undo()
        assert backfill().startswith("Computed 1,")

    def test_an_activity_without_a_stored_file_is_counted(self, alice: User) -> None:
        activity = self.missing(alice, hard_ride())
        ActivityFile.objects.filter(pk=activity.pk).delete()

        assert "without a stored file 1" in backfill()

    def test_email_limits_it_to_one_account(self, alice: User, bob: User) -> None:
        mine = self.missing(alice, hard_ride())
        theirs = self.missing(bob, hard_ride())

        output = backfill("--email", "ALICE@example.com ")

        assert Activity.objects.get(pk=mine.pk).best_efforts is not None
        assert Activity.objects.get(pk=theirs.pk).best_efforts is None
        assert output.startswith("Computed 1,")

    def test_an_unknown_account_is_an_error(self) -> None:
        with pytest.raises(CommandError, match="no account"):
            backfill("--email", "nobody@example.com")

    def test_without_email_every_account_is_filled(self, alice: User, bob: User) -> None:
        self.missing(alice, hard_ride())
        self.missing(bob, hard_ride(start_day=1))

        assert backfill().startswith("Computed 2,")
        assert not Activity.objects.filter(best_efforts__isnull=True).exists()

    def test_it_prints_counts_only(self, alice: User) -> None:
        self.missing(alice, hard_ride())

        output = backfill()

        assert "alice" not in output
        assert "250" not in output


def test_the_answers_of_the_api_do_not_include_the_efforts() -> None:
    from activities.serializers import ActivityDetailSerializer, ActivitySerializer

    assert "best_efforts" not in ActivitySerializer.Meta.fields
    assert "best_efforts" not in ActivityDetailSerializer.Meta.fields
