import random
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from accounts.models import User
from activities.models import Activity
from athletes import estimates
from athletes.estimates import (
    BASIS,
    estimate_max_heart_rate,
    refresh_estimates,
    refresh_estimates_safely,
)
from athletes.models import ThresholdValue
from athletes.thresholds import candidates, effective

from .conftest import make_user

pytestmark = pytest.mark.django_db

START = datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
Sport = Activity.Sport


def estimate(*values: float) -> int | None:
    return estimate_max_heart_rate(values, minimum=30, maximum=250)


class TestTheRule:
    def test_three_activities_with_two_that_agree(self) -> None:
        assert estimate(182, 184, 171) == 184

    def test_a_single_false_peak_without_a_partner_is_ignored(self) -> None:
        assert estimate(200, 184, 182, 171) == 184

    @pytest.mark.parametrize("values", [(), (190,), (190, 190), (190, 189)])
    def test_fewer_than_three_activities_give_no_estimate(self, values: tuple[float, ...]) -> None:
        assert estimate(*values) is None

    def test_three_activities_that_do_not_agree_give_no_estimate(self) -> None:
        assert estimate(190, 180, 170) is None

    @pytest.mark.parametrize(("distance", "expected"), [(0, 190), (1, 190), (3, 190), (4, None)])
    def test_the_second_activity_must_be_within_three_beats(
        self, distance: int, expected: int | None
    ) -> None:
        assert estimate(190, 190 - distance, 150) == expected

    def test_the_same_value_three_times_is_believed(self) -> None:
        assert estimate(190, 190, 190) == 190

    def test_the_highest_confirmed_value_wins_over_a_lower_pair(self) -> None:
        assert estimate(190, 188, 170, 169) == 190

    def test_two_peaks_that_agree_with_each_other_are_believed(self) -> None:
        """The rule cannot tell two matching false peaks from the truth; the basis says so."""
        assert estimate(210, 209, 180, 170) == 210

    @pytest.mark.parametrize(
        ("values", "expected"),
        [
            ((260, 259, 185, 184, 183), 185),  # above what a person reaches
            ((20, 21, 190, 189, 188), 190),  # below it
            ((260, 259, 258), None),
            ((0, 0, 0), None),
        ],
    )
    def test_implausible_values_are_ignored(
        self, values: tuple[float, ...], expected: int | None
    ) -> None:
        assert estimate(*values) == expected

    def test_the_order_of_the_values_does_not_matter(self) -> None:
        values = [200, 190, 188, 171, 150, 149]
        for seed in range(10):
            shuffled = values[:]
            random.Random(seed).shuffle(shuffled)
            assert estimate(*shuffled) == 190

    def test_the_result_is_a_whole_number(self) -> None:
        result = estimate(184.6, 183.9, 160)

        assert result == 185 and isinstance(result, int)

    def test_the_limits_are_those_given_and_include_their_ends(self) -> None:
        values = [100, 99, 98]

        assert estimate_max_heart_rate(values, minimum=30, maximum=100) == 100
        assert estimate_max_heart_rate(values, minimum=30, maximum=99) is None  # only two left
        assert estimate_max_heart_rate(values, minimum=98, maximum=250) == 100
        assert estimate_max_heart_rate(values, minimum=99, maximum=250) is None  # only two left


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


_counter = iter(range(1, 10_000))


def activity(owner: User, heart_rate: int | None, sport: str = Sport.RUNNING) -> Activity:
    n = next(_counter)
    return Activity.objects.create(
        owner=owner,
        source=Activity.Source.FIT_FILE,
        source_hash=f"{n:064x}",
        sport=sport,
        start_time=START + timedelta(hours=n),
        max_heart_rate=heart_rate,
    )


def estimated(owner: User) -> dict[str, float]:
    return {
        row.sport: row.value
        for row in ThresholdValue.objects.filter(
            owner=owner, metric="max_hr", source=ThresholdValue.Source.ESTIMATED
        )
    }


class TestRefreshing:
    def test_three_runs_give_an_estimate_with_the_basis(self, alice: User) -> None:
        for heart_rate in (182, 184, 171):
            activity(alice, heart_rate)

        refresh_estimates(alice)

        assert estimated(alice) == {"run": 184}
        row = ThresholdValue.objects.get()
        assert (row.source, row.metric, row.basis) == ("estimated", "max_hr", BASIS)

    def test_the_estimate_counts_when_nothing_else_does(self, alice: User) -> None:
        for heart_rate in (182, 184, 171):
            activity(alice, heart_rate)

        refresh_estimates(alice)

        found = effective(alice, "run", "max_hr")
        assert found is not None and (found.value, found.source) == (184, "estimated")

    def test_running_and_cycling_are_kept_apart(self, alice: User) -> None:
        for heart_rate in (184, 183, 170):
            activity(alice, heart_rate, Sport.RUNNING)
        for heart_rate in (176, 175, 160):
            activity(alice, heart_rate, Sport.CYCLING)

        refresh_estimates(alice)

        assert estimated(alice) == {"run": 184, "ride": 176}

    def test_runs_and_rides_are_not_added_up(self, alice: User) -> None:
        for heart_rate in (184, 183):
            activity(alice, heart_rate, Sport.RUNNING)
        activity(alice, 160, Sport.CYCLING)

        refresh_estimates(alice)

        assert estimated(alice) == {}  # two runs and one ride: three in all, but not three of one

    @pytest.mark.parametrize("sport", [Sport.SWIMMING, Sport.STRENGTH, Sport.OTHER])
    def test_other_sports_are_ignored(self, alice: User, sport: str) -> None:
        for heart_rate in (200, 199, 198):
            activity(alice, heart_rate, sport)

        refresh_estimates(alice)

        assert estimated(alice) == {}

    def test_activities_without_a_heart_rate_do_not_count(self, alice: User) -> None:
        for heart_rate in (184, 183, None, None, None):
            activity(alice, heart_rate)

        refresh_estimates(alice)

        assert estimated(alice) == {}

    def test_the_activities_of_another_user_never_count(self, alice: User, bob: User) -> None:
        for heart_rate in (190, 189, 188):
            activity(bob, heart_rate)
        for heart_rate in (180, 179):
            activity(alice, heart_rate)

        refresh_estimates(alice)

        assert estimated(alice) == {}
        assert estimated(bob) == {}  # bob has not been refreshed

    def test_refreshing_one_user_does_not_touch_the_estimates_of_another(
        self, alice: User, bob: User
    ) -> None:
        for heart_rate in (190, 189, 188):
            activity(bob, heart_rate)
        refresh_estimates(bob)

        refresh_estimates(alice)  # alice has no activities at all

        assert estimated(bob) == {"run": 190}

    def test_deleting_the_activity_that_held_the_estimate_lowers_it(self, alice: User) -> None:
        peak = activity(alice, 190)
        for heart_rate in (189, 175, 174):
            activity(alice, heart_rate)
        refresh_estimates(alice)
        assert estimated(alice) == {"run": 190}

        peak.delete()
        refresh_estimates(alice)

        assert estimated(alice) == {"run": 175}

    def test_deleting_one_of_the_last_three_removes_the_estimate(self, alice: User) -> None:
        keep = [activity(alice, heart_rate) for heart_rate in (184, 183)]
        gone = activity(alice, 150)
        refresh_estimates(alice)
        assert estimated(alice) == {"run": 184}

        gone.delete()
        refresh_estimates(alice)

        assert estimated(alice) == {}
        assert len(keep) == 2 and ThresholdValue.objects.count() == 0

    def test_a_changed_estimate_is_updated_in_place(self, alice: User) -> None:
        for heart_rate in (180, 179, 160):
            activity(alice, heart_rate)
        refresh_estimates(alice)
        row = ThresholdValue.objects.get()

        activity(alice, 186)
        activity(alice, 185)
        refresh_estimates(alice)

        assert estimated(alice) == {"run": 186}
        assert ThresholdValue.objects.get().pk == row.pk

    def test_an_unchanged_estimate_keeps_the_time_of_its_last_change(self, alice: User) -> None:
        for heart_rate in (184, 183, 160):
            activity(alice, heart_rate)
        refresh_estimates(alice)
        before = ThresholdValue.objects.get().updated_at

        refresh_estimates(alice)

        assert ThresholdValue.objects.get().updated_at == before

    def test_nothing_is_written_for_a_user_without_activities(self, alice: User) -> None:
        refresh_estimates(alice)

        assert not ThresholdValue.objects.exists()


class TestOtherSourcesAndMetrics:
    def prepare(self, alice: User) -> None:
        for heart_rate in (184, 183, 160):
            activity(alice, heart_rate)

    def test_a_typed_value_stays_effective_and_the_estimate_is_a_candidate(
        self, alice: User
    ) -> None:
        self.prepare(alice)
        ThresholdValue.objects.create(
            owner=alice, sport="run", metric="max_hr", source="manual", value=175
        )

        refresh_estimates(alice)

        assert effective(alice, "run", "max_hr").value == 175  # type: ignore[union-attr]
        assert [(c.source, c.value) for c in candidates(alice, "run", "max_hr")] == [
            ("manual", 175),
            ("estimated", 184),
        ]

    def test_a_value_from_intervals_stays_effective(self, alice: User) -> None:
        self.prepare(alice)
        ThresholdValue.objects.create(
            owner=alice, sport="run", metric="max_hr", source="intervals", value=188
        )

        refresh_estimates(alice)

        assert effective(alice, "run", "max_hr").source == "intervals"  # type: ignore[union-attr]

    def test_other_rows_are_not_touched_even_when_the_estimate_goes_away(self, alice: User) -> None:
        # The estimate that has to go is created first, so that a lookup which also finds the
        # other rows would pick one of them instead of it.
        stale = ThresholdValue.objects.create(
            owner=alice, sport="run", metric="max_hr", source="estimated", value=190, basis="old"
        )
        manual = ThresholdValue.objects.create(
            owner=alice, sport="run", metric="max_hr", source="manual", value=175
        )
        intervals = ThresholdValue.objects.create(
            owner=alice, sport="run", metric="max_hr", source="intervals", value=188
        )
        other_metric = ThresholdValue.objects.create(
            owner=alice, sport="run", metric="lthr", source="intervals", value=165, basis="x"
        )
        kept = (manual, intervals, other_metric)
        before = {row.pk: (row.value, row.basis, row.updated_at) for row in kept}

        refresh_estimates(alice)  # no activities: the old estimate must go

        assert not ThresholdValue.objects.filter(pk=stale.pk).exists()
        after = {
            row.pk: (row.value, row.basis, row.updated_at)
            for row in ThresholdValue.objects.filter(pk__in=before)
        }
        assert after == before

    def test_an_estimate_with_an_old_basis_text_gets_the_current_one(self, alice: User) -> None:
        for heart_rate in (184, 183, 160):
            activity(alice, heart_rate)
        ThresholdValue.objects.create(
            owner=alice, sport="run", metric="max_hr", source="estimated", value=184, basis="old"
        )

        refresh_estimates(alice)

        assert ThresholdValue.objects.get().basis == BASIS

    def test_a_failure_while_writing_leaves_all_estimates_as_they_were(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for heart_rate in (184, 183, 160):
            activity(alice, heart_rate, Sport.RUNNING)
        for heart_rate in (176, 175, 150):
            activity(alice, heart_rate, Sport.CYCLING)
        original = ThresholdValue.objects.update_or_create
        calls = {"n": 0}

        def failing(*args: Any, **kwargs: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("disk full")
            return original(*args, **kwargs)

        monkeypatch.setattr(ThresholdValue.objects, "update_or_create", failing)

        with pytest.raises(RuntimeError):
            refresh_estimates(alice)

        assert estimated(alice) == {}  # not even the first one stays


class TestSafely:
    def test_a_failure_is_logged_and_does_not_escape(
        self, alice: User, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        def fail(user: User) -> None:
            raise RuntimeError("database gone")

        monkeypatch.setattr(estimates, "refresh_estimates", fail)

        refresh_estimates_safely(alice)

        assert "Could not refresh the estimated thresholds" in caplog.text
        assert str(alice.pk) in caplog.text

    def test_it_does_the_work_when_all_is_well(self, alice: User) -> None:
        for heart_rate in (184, 183, 160):
            activity(alice, heart_rate)

        refresh_estimates_safely(alice)

        assert estimated(alice) == {"run": 184}


def test_the_basis_is_a_fixed_text_without_values() -> None:
    assert not any(character.isdigit() for character in BASIS)
