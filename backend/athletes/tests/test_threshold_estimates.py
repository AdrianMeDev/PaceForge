from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from accounts.models import User
from activities.models import Activity
from athletes.estimates import (
    FTP_BASIS,
    PACE_BASIS,
    RIDE_LTHR_BASIS,
    RUN_LTHR_BASIS,
    refresh_estimates,
)
from athletes.models import ThresholdValue
from athletes.thresholds import effective

from .conftest import make_user

pytestmark = pytest.mark.django_db

_counter = iter(range(1, 100_000))


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def efforts(
    power: float | None = None, speed: float | None = None, heart_rate: float | None = 160
) -> dict[str, Any]:
    stored: dict[str, Any] = {"power": {}, "speed": {}}
    if power is not None:
        stored["power"]["1200"] = {"value": power, "heart_rate": heart_rate}
    if speed is not None:
        stored["speed"]["1800"] = {"value": speed, "heart_rate": heart_rate}
    return stored


def activity(owner: User, sport: str, best: Any, days_ago: float = 5) -> Activity:
    n = next(_counter)
    return Activity.objects.create(
        owner=owner,
        source=Activity.Source.FIT_FILE,
        source_hash=f"{n:064x}",
        sport=sport,
        start_time=timezone.now() - timedelta(days=days_ago, seconds=n),
        best_efforts=best,
    )


def estimated(owner: User) -> dict[tuple[str, str], tuple[float, str]]:
    return {
        (row.sport, row.metric): (row.value, row.basis)
        for row in ThresholdValue.objects.filter(owner=owner, source="estimated")
    }


class TestCycling:
    def test_ftp_is_95_percent_of_the_best_20_minutes(self, alice: User) -> None:
        activity(alice, "cycling", efforts(power=260, heart_rate=170))

        refresh_estimates(alice)

        assert estimated(alice)[("ride", "ftp")] == (247.0, FTP_BASIS)  # 260 × 0.95

    def test_lthr_is_95_percent_of_the_heart_rate_during_it(self, alice: User) -> None:
        activity(alice, "cycling", efforts(power=260, heart_rate=170))

        refresh_estimates(alice)

        assert estimated(alice)[("ride", "lthr")] == (162.0, RIDE_LTHR_BASIS)  # 170 × 0.95 = 161.5

    def test_the_best_ride_counts(self, alice: User) -> None:
        activity(alice, "cycling", efforts(power=200, heart_rate=150))
        activity(alice, "cycling", efforts(power=300, heart_rate=172))
        activity(alice, "cycling", efforts(power=250, heart_rate=180))

        refresh_estimates(alice)

        assert estimated(alice)[("ride", "ftp")][0] == 285  # 300 × 0.95
        assert estimated(alice)[("ride", "lthr")][0] == 163  # 172 × 0.95 = 163.4

    def test_no_heart_rate_means_no_lthr_but_an_ftp(self, alice: User) -> None:
        activity(alice, "cycling", efforts(power=260, heart_rate=None))

        refresh_estimates(alice)

        assert ("ride", "ftp") in estimated(alice)
        assert ("ride", "lthr") not in estimated(alice)

    def test_running_power_never_becomes_an_ftp(self, alice: User) -> None:
        activity(alice, "running", efforts(power=340, speed=3.4))

        refresh_estimates(alice)

        assert ("ride", "ftp") not in estimated(alice)


class TestRunning:
    def test_the_pace_is_the_best_30_minutes(self, alice: User) -> None:
        activity(alice, "running", efforts(speed=10 / 3, heart_rate=165))

        refresh_estimates(alice)

        assert estimated(alice)[("run", "threshold_pace")] == (300.0, PACE_BASIS)
        assert estimated(alice)[("run", "lthr")] == (165.0, RUN_LTHR_BASIS)

    def test_the_fastest_run_counts(self, alice: User) -> None:
        activity(alice, "running", efforts(speed=3.0, heart_rate=150))
        activity(alice, "running", efforts(speed=3.5, heart_rate=168))

        refresh_estimates(alice)

        assert estimated(alice)[("run", "threshold_pace")][0] == 286  # 1000 / 3.5 = 285.7
        assert estimated(alice)[("run", "lthr")][0] == 168

    def test_ride_speed_never_becomes_a_running_pace(self, alice: User) -> None:
        activity(alice, "cycling", efforts(speed=9.0))

        refresh_estimates(alice)

        assert ("run", "threshold_pace") not in estimated(alice)

    def test_other_sports_do_not_count(self, alice: User) -> None:
        activity(alice, "swimming", efforts(power=300, speed=1.5))
        activity(alice, "other", efforts(power=300, speed=4))

        refresh_estimates(alice)

        assert estimated(alice) == {}


class TestWhatCounts:
    def test_activities_older_than_90_days_do_not_count(self, alice: User) -> None:
        activity(alice, "cycling", efforts(power=400), days_ago=91)
        activity(alice, "cycling", efforts(power=200), days_ago=89)

        refresh_estimates(alice)

        assert estimated(alice)[("ride", "ftp")][0] == 190

    def test_an_estimate_goes_away_when_its_activity_becomes_too_old(self, alice: User) -> None:
        ride = activity(alice, "cycling", efforts(power=260))
        refresh_estimates(alice)
        assert ("ride", "ftp") in estimated(alice)

        Activity.objects.filter(pk=ride.pk).update(start_time=timezone.now() - timedelta(days=100))
        refresh_estimates(alice)

        assert ("ride", "ftp") not in estimated(alice)

    def test_deleting_the_best_ride_lowers_the_estimate(self, alice: User) -> None:
        best = activity(alice, "cycling", efforts(power=300))
        activity(alice, "cycling", efforts(power=200))
        refresh_estimates(alice)

        best.delete()
        refresh_estimates(alice)

        assert estimated(alice)[("ride", "ftp")][0] == 190

    @pytest.mark.parametrize(
        "stored",
        [
            None,
            {},
            {"power": {}},
            {"power": {"1200": {}}},
            {"power": {"1200": {"value": "x"}}},
            {"power": {"1200": {"value": -5, "heart_rate": 150}}},
            {"power": []},
            [],
            "text",
        ],
    )
    def test_missing_or_odd_efforts_count_as_none(self, alice: User, stored: Any) -> None:
        activity(alice, "cycling", stored)

        refresh_estimates(alice)

        assert estimated(alice) == {}

    def test_an_odd_heart_rate_only_costs_the_lthr(self, alice: User) -> None:
        activity(alice, "cycling", {"power": {"1200": {"value": 260, "heart_rate": "fast"}}})

        refresh_estimates(alice)

        assert set(estimated(alice)) == {("ride", "ftp")}

    @pytest.mark.parametrize(
        ("sport", "best", "key"),
        [
            ("cycling", efforts(power=5000), ("ride", "ftp")),  # 4750 W: more than a person
            ("cycling", efforts(power=20), ("ride", "ftp")),  # 19 W
            ("running", efforts(speed=0.5), ("run", "threshold_pace")),  # 2000 s/km
            ("running", efforts(speed=12), ("run", "threshold_pace")),  # 83 s/km
            ("running", efforts(speed=3, heart_rate=260), ("run", "lthr")),
        ],
    )
    def test_a_value_outside_the_ranges_is_not_stored(
        self, alice: User, sport: str, best: Any, key: tuple[str, str]
    ) -> None:
        activity(alice, sport, best)

        refresh_estimates(alice)

        assert key not in estimated(alice)

    def test_the_activities_of_another_user_never_count(self, alice: User, bob: User) -> None:
        activity(bob, "cycling", efforts(power=300))

        refresh_estimates(alice)

        assert estimated(alice) == {}


class TestTogetherWithTheOtherSources:
    def test_a_typed_or_intervals_value_still_counts(self, alice: User) -> None:
        activity(alice, "cycling", efforts(power=260))
        ThresholdValue.objects.create(
            owner=alice, sport="ride", metric="ftp", source="manual", value=280
        )
        ThresholdValue.objects.create(
            owner=alice, sport="run", metric="lthr", source="intervals", value=170
        )
        activity(alice, "running", efforts(speed=3, heart_rate=160))

        refresh_estimates(alice)

        assert effective(alice, "ride", "ftp").source == "manual"  # type: ignore[union-attr]
        assert effective(alice, "run", "lthr").source == "intervals"  # type: ignore[union-attr]
        assert effective(alice, "run", "threshold_pace").source == "estimated"  # type: ignore[union-attr]

    def test_the_maximum_heart_rate_estimate_works_as_before(self, alice: User) -> None:
        for heart_rate in (184, 183, 160):
            n = next(_counter)
            Activity.objects.create(
                owner=alice,
                source="fit_file",
                source_hash=f"{n:064x}",
                sport="running",
                start_time=timezone.now() - timedelta(days=200, seconds=n),  # older than 90 days
                max_heart_rate=heart_rate,
            )

        refresh_estimates(alice)

        assert estimated(alice)[("run", "max_hr")][0] == 184

    def test_an_unchanged_estimate_keeps_the_time_of_its_last_change(self, alice: User) -> None:
        activity(alice, "cycling", efforts(power=260))
        refresh_estimates(alice)
        before = ThresholdValue.objects.get(metric="ftp").updated_at

        refresh_estimates(alice)

        assert ThresholdValue.objects.get(metric="ftp").updated_at == before

    def test_a_stale_estimate_of_any_metric_is_removed(self, alice: User) -> None:
        ThresholdValue.objects.create(
            owner=alice, sport="run", metric="lthr", source="estimated", value=165, basis="old"
        )

        refresh_estimates(alice)

        assert estimated(alice) == {}

    def test_every_basis_says_it_is_a_lower_bound_and_names_the_period(self) -> None:
        for basis in (FTP_BASIS, RIDE_LTHR_BASIS, PACE_BASIS, RUN_LTHR_BASIS):
            assert basis.startswith("At least")
            assert "90 days" in basis
            assert len(basis) <= 200
