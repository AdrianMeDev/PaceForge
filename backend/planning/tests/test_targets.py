import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from athletes.models import ThresholdValue
from athletes.zones import heart_rate_zones, pace_zones, power_zones
from planning.schema import ZONE_COUNT, Sport, ZoneSystem
from planning.targets import Target, Targets

from .conftest import make_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


def hold(owner: User, sport: str, metric: str, value: float) -> None:
    ThresholdValue.objects.create(
        owner=owner,
        sport=sport,
        metric=metric,
        value=value,
        source=ThresholdValue.Source.MANUAL,
        basis="test",
    )


class TestPower:
    def test_closed_ranges_for_an_ftp_of_250(self, alice: User) -> None:
        hold(alice, "ride", "ftp", 250)
        targets = Targets(alice)

        def power(zone: int) -> Target | None:
            return targets.target(Sport.CYCLING, ZoneSystem.POWER, zone)

        # The open sides close at 40 % and 200 % of the FTP.
        assert power(1) == Target(100, 138, "W")
        assert power(2) == Target(138, 188, "W")
        assert power(7) == Target(375, 500, "W")

    def test_every_zone_is_a_closed_range_in_order(self, alice: User) -> None:
        hold(alice, "ride", "ftp", 250)
        targets = Targets(alice)

        for zone in range(1, ZONE_COUNT["power"] + 1):
            target = targets.target(Sport.CYCLING, ZoneSystem.POWER, zone)
            assert target is not None
            assert target.low < target.high

    def test_without_an_ftp_there_is_no_target(self, alice: User) -> None:
        hold(alice, "ride", "lthr", 160)

        assert Targets(alice).target(Sport.CYCLING, ZoneSystem.POWER, 2) is None


class TestHeartRate:
    def test_from_the_lactate_threshold(self, alice: User) -> None:
        hold(alice, "run", "lthr", 170)
        targets = Targets(alice)

        # 85, 90, 95 and 100 percent of 170; the open sides close at 65 and 105 percent.
        assert targets.target(Sport.RUNNING, ZoneSystem.HEART_RATE, 1) == Target(111, 145, "bpm")
        assert targets.target(Sport.RUNNING, ZoneSystem.HEART_RATE, 5) == Target(170, 179, "bpm")

    def test_from_the_maximum_if_there_is_no_lactate_threshold(self, alice: User) -> None:
        hold(alice, "ride", "max_hr", 190)

        # 60 percent of 190, and the open side closed at 50 percent.
        assert Targets(alice).target(Sport.CYCLING, ZoneSystem.HEART_RATE, 1) == Target(
            95, 114, "bpm"
        )
        assert Targets(alice).target(Sport.CYCLING, ZoneSystem.HEART_RATE, 5) == Target(
            171, 190, "bpm"
        )

    def test_the_sports_do_not_share_thresholds(self, alice: User) -> None:
        hold(alice, "ride", "lthr", 160)

        assert Targets(alice).target(Sport.RUNNING, ZoneSystem.HEART_RATE, 2) is None


class TestPace:
    def test_the_fast_end_comes_first(self, alice: User) -> None:
        hold(alice, "run", "threshold_pace", 300)
        targets = Targets(alice)

        def pace(zone: int) -> Target | None:
            return targets.target(Sport.RUNNING, ZoneSystem.PACE, zone)

        # Zone 1 is the slowest: from 129 % to the closing 150 % of the threshold pace.
        assert pace(1) == Target(387, 450, "s/km")
        # Zone 5 is the fastest: from the closing 85 % up to 99 %.
        assert pace(5) == Target(255, 297, "s/km")

    def test_every_zone_is_a_closed_range_in_order(self, alice: User) -> None:
        hold(alice, "run", "threshold_pace", 300)

        for zone in range(1, ZONE_COUNT["pace"] + 1):
            target = Targets(alice).target(Sport.RUNNING, ZoneSystem.PACE, zone)
            assert target is not None
            assert target.low < target.high

    def test_cycling_has_no_pace(self, alice: User) -> None:
        hold(alice, "run", "threshold_pace", 300)

        assert Targets(alice).target(Sport.CYCLING, ZoneSystem.PACE, 2) is None


class TestAgreementWithTheZones:
    def test_closed_sides_leave_the_closed_bounds_as_they_are(self, alice: User) -> None:
        hold(alice, "ride", "ftp", 250)
        hold(alice, "run", "threshold_pace", 300)
        hold(alice, "run", "lthr", 170)
        targets = Targets(alice)
        sets = {
            (Sport.CYCLING, ZoneSystem.POWER): power_zones(250),
            (Sport.RUNNING, ZoneSystem.PACE): pace_zones(300),
            (Sport.RUNNING, ZoneSystem.HEART_RATE): heart_rate_zones(lthr=170),
        }

        for (sport, system), zone_set in sets.items():
            assert zone_set is not None
            for zone in zone_set.zones:
                target = targets.target(sport, system, zone.number)
                assert target is not None
                if zone.lower is not None:
                    assert target.low == zone.lower
                if zone.upper is not None:
                    assert target.high == zone.upper
                assert target.unit == zone.unit


class TestNoTarget:
    def test_swimming_and_strength_have_no_zones(self, alice: User) -> None:
        hold(alice, "ride", "ftp", 250)
        targets = Targets(alice)

        for sport in (Sport.SWIMMING, Sport.STRENGTH):
            for system in ZoneSystem:
                assert targets.target(sport, system, 1) is None

    def test_a_zone_that_does_not_exist(self, alice: User) -> None:
        hold(alice, "ride", "ftp", 250)

        assert Targets(alice).target(Sport.CYCLING, ZoneSystem.POWER, 8) is None
        assert Targets(alice).target(Sport.CYCLING, ZoneSystem.POWER, 0) is None

    def test_a_user_with_nothing(self, alice: User) -> None:
        assert Targets(alice).target(Sport.CYCLING, ZoneSystem.POWER, 1) is None

    def test_the_thresholds_of_other_users_do_not_count(self, alice: User) -> None:
        bob = make_user("bob@example.com")
        hold(bob, "ride", "ftp", 300)

        assert Targets(alice).target(Sport.CYCLING, ZoneSystem.POWER, 2) is None


def test_the_thresholds_are_loaded_once(alice: User) -> None:
    # two queries: the stored thresholds and the best times, whatever the number of zones asked for
    hold(alice, "ride", "ftp", 250)
    hold(alice, "ride", "lthr", 160)
    hold(alice, "run", "threshold_pace", 300)

    with CaptureQueriesContext(connection) as queries:
        targets = Targets(alice)
        for zone in range(1, 6):
            targets.target(Sport.CYCLING, ZoneSystem.POWER, zone)
            targets.target(Sport.RUNNING, ZoneSystem.PACE, zone)

    assert len(queries) == 2
