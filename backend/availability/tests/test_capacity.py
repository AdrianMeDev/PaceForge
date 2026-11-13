from datetime import date, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from availability.capacity import WeekCapacity, minutes_in_week, minutes_on, week_capacity
from availability.models import AvailabilitySettings, UnavailablePeriod, WeekdayMinutes

pytestmark = pytest.mark.django_db

MONDAY = date(2027, 7, 12)
assert MONDAY.weekday() == 0
WEDNESDAY = MONDAY + timedelta(days=2)
SUNDAY = MONDAY + timedelta(days=6)
NEXT_MONDAY = MONDAY + timedelta(days=7)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def declare(user: User, *minutes: int) -> None:
    """Minutes per weekday from Monday on; fewer than seven values leave the rest undeclared."""
    for weekday, value in enumerate(minutes):
        WeekdayMinutes.objects.create(owner=user, weekday=weekday, minutes=value)


def away(user: User, start: date, end: date | None = None, kind: str = "vacation") -> None:
    UnavailablePeriod.objects.create(owner=user, kind=kind, start_date=start, end_date=end or start)


def budget(user: User, minutes: int | None) -> None:
    AvailabilitySettings.objects.create(owner=user, weekly_budget_minutes=minutes)


class TestADay:
    def test_nothing_declared_offers_no_time(self, alice: User) -> None:
        assert minutes_on(alice, MONDAY) == 0

    def test_a_day_offers_the_minutes_of_its_weekday(self, alice: User) -> None:
        declare(alice, 60, 0, 90, 0, 0, 120, 180)

        assert [minutes_on(alice, MONDAY + timedelta(days=i)) for i in range(7)] == [
            60,
            0,
            90,
            0,
            0,
            120,
            180,
        ]

    def test_it_is_the_weekday_that_counts_in_any_week(self, alice: User) -> None:
        declare(alice, 60)

        assert minutes_on(alice, MONDAY) == 60
        assert minutes_on(alice, NEXT_MONDAY) == 60
        assert minutes_on(alice, date(2030, 1, 7)) == 60
        assert minutes_on(alice, NEXT_MONDAY + timedelta(days=1)) == 0

    def test_an_undeclared_weekday_offers_nothing(self, alice: User) -> None:
        declare(alice, 60)

        assert minutes_on(alice, WEDNESDAY) == 0

    def test_a_day_inside_a_period_offers_nothing(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        away(alice, MONDAY + timedelta(days=1), MONDAY + timedelta(days=3))

        assert minutes_on(alice, MONDAY) == 60
        assert minutes_on(alice, MONDAY + timedelta(days=1)) == 0
        assert minutes_on(alice, MONDAY + timedelta(days=2)) == 0
        assert minutes_on(alice, MONDAY + timedelta(days=3)) == 0
        assert minutes_on(alice, MONDAY + timedelta(days=4)) == 60

    def test_both_ends_of_a_period_belong_to_it(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        away(alice, WEDNESDAY, WEDNESDAY)

        assert minutes_on(alice, WEDNESDAY) == 0
        assert minutes_on(alice, WEDNESDAY - timedelta(days=1)) == 60
        assert minutes_on(alice, WEDNESDAY + timedelta(days=1)) == 60

    def test_overlapping_periods_offer_nothing_either(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        away(alice, MONDAY, WEDNESDAY)
        away(alice, WEDNESDAY, SUNDAY, kind="illness")

        assert [minutes_on(alice, MONDAY + timedelta(days=i)) for i in range(7)] == [0] * 7

    def test_a_period_that_starts_long_before_still_covers_the_day(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        away(alice, MONDAY - timedelta(days=100), MONDAY + timedelta(days=100))

        assert minutes_on(alice, MONDAY) == 0

    def test_the_weekly_budget_does_not_cap_a_day(self, alice: User) -> None:
        declare(alice, 300)
        budget(alice, 60)

        assert minutes_on(alice, MONDAY) == 300

    def test_other_users_rows_are_ignored(self, alice: User, bob: User) -> None:
        declare(bob, 120, 120, 120, 120, 120, 120, 120)
        away(bob, MONDAY, SUNDAY)
        declare(alice, 45)

        assert minutes_on(alice, MONDAY) == 45
        assert minutes_on(alice, WEDNESDAY) == 0
        assert minutes_on(bob, MONDAY) == 0

    def test_it_takes_two_queries(self, alice: User) -> None:
        declare(alice, 60)

        with CaptureQueriesContext(connection) as queries:
            minutes_on(alice, MONDAY)

        assert len(queries) == 2


class TestAWeek:
    def test_nothing_declared_offers_no_time(self, alice: User) -> None:
        assert minutes_in_week(alice, MONDAY) == 0

    def test_the_days_are_added_up(self, alice: User) -> None:
        declare(alice, 60, 0, 90, 0, 0, 120, 180)

        assert minutes_in_week(alice, MONDAY) == 450
        assert minutes_in_week(alice, NEXT_MONDAY) == 450

    def test_a_budget_below_the_sum_caps_the_week(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        budget(alice, 300)

        assert minutes_in_week(alice, MONDAY) == 300

    def test_a_budget_equal_to_the_sum_changes_nothing(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        budget(alice, 420)

        assert minutes_in_week(alice, MONDAY) == 420

    def test_a_budget_above_the_sum_changes_nothing(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        budget(alice, 1000)

        assert minutes_in_week(alice, MONDAY) == 420

    def test_a_budget_of_zero_offers_nothing(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        budget(alice, 0)

        assert minutes_in_week(alice, MONDAY) == 0

    def test_a_settings_row_without_a_budget_does_not_cap(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        budget(alice, None)

        assert minutes_in_week(alice, MONDAY) == 420

    def test_a_budget_without_weekdays_offers_nothing(self, alice: User) -> None:
        budget(alice, 600)

        assert minutes_in_week(alice, MONDAY) == 0

    def test_a_period_takes_its_days_out_before_the_cap(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        away(alice, MONDAY, MONDAY + timedelta(days=2))
        budget(alice, 200)

        # four days of 60 minutes are left (240), the cap brings it to 200
        assert minutes_in_week(alice, MONDAY) == 200

    def test_a_period_can_bring_the_week_below_the_budget(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        away(alice, MONDAY, MONDAY + timedelta(days=4))
        budget(alice, 300)

        assert minutes_in_week(alice, MONDAY) == 120

    def test_a_period_covering_part_of_the_week_counts_only_that_part(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        away(alice, SUNDAY - timedelta(days=1), SUNDAY + timedelta(days=20))

        assert minutes_in_week(alice, MONDAY) == 300
        assert minutes_in_week(alice, NEXT_MONDAY) == 0

    def test_a_period_before_or_after_the_week_does_not_count(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        away(alice, MONDAY - timedelta(days=10), MONDAY - timedelta(days=1))
        away(alice, NEXT_MONDAY, NEXT_MONDAY + timedelta(days=3))

        assert minutes_in_week(alice, MONDAY) == 420

    def test_overlapping_periods_are_not_counted_twice(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        away(alice, MONDAY, WEDNESDAY)
        away(alice, WEDNESDAY - timedelta(days=1), WEDNESDAY + timedelta(days=1))

        assert minutes_in_week(alice, MONDAY) == 180

    def test_a_week_in_a_period_offers_nothing(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        away(alice, MONDAY, SUNDAY)

        assert minutes_in_week(alice, MONDAY) == 0

    @pytest.mark.parametrize("offset", [1, 2, 3, 4, 5, 6])
    def test_a_day_that_is_not_a_monday_is_refused(self, alice: User, offset: int) -> None:
        with pytest.raises(ValueError, match="not a Monday"):
            minutes_in_week(alice, MONDAY + timedelta(days=offset))

    def test_other_users_rows_are_ignored(self, alice: User, bob: User) -> None:
        declare(bob, 120, 120, 120, 120, 120, 120, 120)
        budget(bob, 100)
        away(bob, MONDAY, SUNDAY)
        declare(alice, 60, 60)
        budget(alice, 1000)

        assert minutes_in_week(alice, MONDAY) == 120

    def test_it_takes_three_queries(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        away(alice, MONDAY, WEDNESDAY)
        budget(alice, 200)

        with CaptureQueriesContext(connection) as queries:
            minutes_in_week(alice, MONDAY)

        assert len(queries) == 3


class TestTheWholeWeek:
    def test_nothing_declared_offers_nothing(self, alice: User) -> None:
        assert week_capacity(alice, MONDAY) == WeekCapacity((0,) * 7, (None,) * 7, None, 0)

    def test_the_days_the_budget_and_the_total(self, alice: User) -> None:
        declare(alice, 60, 0, 90, 0, 0, 120, 180)
        budget(alice, 400)

        assert week_capacity(alice, MONDAY) == WeekCapacity(
            (60, 0, 90, 0, 0, 120, 180), (None,) * 7, 400, 400
        )

    def test_a_budget_above_the_sum_is_shown_but_does_not_raise_the_total(
        self, alice: User
    ) -> None:
        declare(alice, 60, 60)
        budget(alice, 1000)

        result = week_capacity(alice, MONDAY)

        assert (result.budget, result.total) == (1000, 120)

    def test_a_day_inside_a_period_offers_nothing_and_names_it(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        away(alice, MONDAY + timedelta(days=1), MONDAY + timedelta(days=2), kind="illness")
        away(alice, SUNDAY, SUNDAY + timedelta(days=9))

        result = week_capacity(alice, MONDAY)

        assert result.minutes == (60, 0, 0, 60, 60, 60, 0)
        assert result.absences == (None, "illness", "illness", None, None, None, "vacation")
        assert result.total == 240

    @pytest.mark.parametrize(
        ("kinds", "named"),
        [
            (["vacation", "illness"], "illness"),
            (["other", "vacation"], "vacation"),
            (["other", "illness", "vacation"], "illness"),
            (["other"], "other"),
            (["vacation", "vacation"], "vacation"),
        ],
    )
    def test_where_absences_overlap_the_one_that_says_most_is_named(
        self, alice: User, kinds: list[str], named: str
    ) -> None:
        for kind in kinds:
            away(alice, MONDAY, MONDAY, kind=kind)

        assert week_capacity(alice, MONDAY).absences[0] == named

    def test_a_period_ending_before_or_starting_after_the_week_is_ignored(
        self, alice: User
    ) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        away(alice, MONDAY - timedelta(days=5), MONDAY - timedelta(days=1))
        away(alice, NEXT_MONDAY, NEXT_MONDAY + timedelta(days=3))

        assert week_capacity(alice, MONDAY).absences == (None,) * 7

    @pytest.mark.parametrize("offset", [1, 2, 3, 4, 5, 6])
    def test_a_day_that_is_not_a_monday_is_refused(self, alice: User, offset: int) -> None:
        with pytest.raises(ValueError, match="not a Monday"):
            week_capacity(alice, MONDAY + timedelta(days=offset))

    def test_other_users_rows_are_ignored(self, alice: User, bob: User) -> None:
        declare(bob, 120, 120, 120, 120, 120, 120, 120)
        budget(bob, 100)
        away(bob, MONDAY, SUNDAY)

        assert week_capacity(alice, MONDAY) == WeekCapacity((0,) * 7, (None,) * 7, None, 0)

    def test_it_takes_three_queries_however_full_the_week(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        for day in range(7):
            away(alice, MONDAY + timedelta(days=day))
        budget(alice, 200)

        with CaptureQueriesContext(connection) as queries:
            week_capacity(alice, MONDAY)

        assert len(queries) == 3

    def test_the_total_is_what_minutes_in_week_says(self, alice: User) -> None:
        declare(alice, 60, 60, 60, 60, 60, 60, 60)
        away(alice, MONDAY, MONDAY + timedelta(days=1))
        budget(alice, 250)

        assert minutes_in_week(alice, MONDAY) == week_capacity(alice, MONDAY).total == 250
