from datetime import date, timedelta
from typing import Any

import pytest

from accounts.models import User
from wellness.models import DailyWellness
from wellness.summary import (
    BASELINE_DAYS,
    BASELINE_MIN_READINGS,
    RECENT_DAYS,
    RECENT_MIN_READINGS,
    MetricSummary,
    WellnessSummary,
    wellness_data,
    wellness_summary,
)

pytestmark = pytest.mark.django_db

TODAY = date(2027, 7, 19)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def recent_days() -> list[date]:
    """The RECENT_DAYS days ending on TODAY, oldest first."""
    return [TODAY - timedelta(days=i) for i in range(RECENT_DAYS - 1, -1, -1)]


def baseline_days() -> list[date]:
    """The BASELINE_DAYS days just before the recent window, oldest first."""
    return [
        TODAY - timedelta(days=RECENT_DAYS + BASELINE_DAYS - 1 - i) for i in range(BASELINE_DAYS)
    ]


def fill(user: User, days: list[date], field: str, value: float | int | None) -> None:
    """Set one metric on the user's row for each day (creating the row when needed)."""
    for day in days:
        row, _ = DailyWellness.objects.get_or_create(owner=user, day=day)
        setattr(row, field, value)
        row.save(update_fields=[field])


def fill_constant(user: User, recent: float | int, baseline: float | int, field: str) -> None:
    """Every recent day one reading and every baseline day one reading."""
    fill(user, recent_days(), field, recent)
    fill(user, baseline_days(), field, baseline)


def summary_for(
    user: User,
    *,
    recent: float | int | None = None,
    baseline: float | int | None = None,
    field: str = "sleep_minutes",
) -> WellnessSummary:
    if recent is not None:
        fill(user, recent_days(), field, recent)
    if baseline is not None:
        fill(user, baseline_days(), field, baseline)
    return wellness_summary(user, TODAY)


def metric(summary: WellnessSummary, field: str) -> MetricSummary:
    # The dataclass attributes are the short names (``sleep``, ``weight_kg`` becomes ``weight``).
    attribute = field.replace("_minutes", "").replace("_kg", "")
    return getattr(summary, attribute)


class TestWindows:
    def test_no_rows_means_no_data_and_no_warning(self, alice: User) -> None:
        summary = wellness_summary(alice, TODAY)
        assert summary.sleep == MetricSummary(None, None, None)
        assert summary.warning is False
        assert summary.warning_signals == ()

    def test_sparse_data_is_not_reported(self, alice: User) -> None:
        # Below the minimum readings in both windows: no means reported.
        fill(alice, recent_days()[: RECENT_MIN_READINGS - 1], "hrv", 60)
        fill(alice, baseline_days()[: BASELINE_MIN_READINGS - 1], "hrv", 60)
        summary = wellness_summary(alice, TODAY)
        assert summary.hrv == MetricSummary(None, None, None)

    def test_days_with_none_metric_are_not_readings(self, alice: User) -> None:
        fill(alice, recent_days(), "hrv", None)
        fill(alice, baseline_days(), "hrv", None)
        summary = wellness_summary(alice, TODAY)
        assert summary.hrv == MetricSummary(None, None, None)

    def test_values_outside_the_windows_are_ignored(self, alice: User) -> None:
        fill_constant(alice, 480, 500, "sleep_minutes")
        too_old = baseline_days()[0] - timedelta(days=1)
        DailyWellness.objects.create(owner=alice, day=too_old, sleep_minutes=1)
        future = TODAY + timedelta(days=1)
        DailyWellness.objects.create(owner=alice, day=future, sleep_minutes=1)
        summary = wellness_summary(alice, TODAY)
        assert summary.sleep.recent == 480
        assert summary.sleep.baseline == 500


class TestTrends:
    def test_recent_above_baseline_is_up(self, alice: User) -> None:
        summary = summary_for(alice, recent=500, baseline=480)
        assert metric(summary, "sleep_minutes") == MetricSummary(500, 480, "up")

    def test_recent_below_baseline_is_down(self, alice: User) -> None:
        summary = summary_for(alice, recent=420, baseline=480)
        assert metric(summary, "sleep_minutes") == MetricSummary(420, 480, "down")

    def test_equal_means_are_flat(self, alice: User) -> None:
        summary = summary_for(alice, recent=480, baseline=480)
        assert metric(summary, "sleep_minutes") == MetricSummary(480, 480, "flat")

    def test_averages_are_computed_not_copied(self, alice: User) -> None:
        # Recent: 5 days of 480 and 2 days of 620 -> mean 520.
        fill(alice, recent_days()[:5], "sleep_minutes", 480)
        fill(alice, recent_days()[5:], "sleep_minutes", 620)
        fill(alice, baseline_days(), "sleep_minutes", 500)
        summary = wellness_summary(alice, TODAY)
        assert summary.sleep.recent == 520
        assert summary.sleep.baseline == 500
        assert summary.sleep.trend == "up"


class TestWarnings:
    def test_low_sleep_just_at_the_10_percent_boundary(self, alice: User) -> None:
        # baseline 500 -> 10% below is 450; exactly 450 warns.
        summary = summary_for(alice, recent=450, baseline=500)
        assert summary.warning is True
        assert summary.warning_signals == ("low_sleep",)

    def test_low_sleep_just_above_the_boundary_does_not_warn(self, alice: User) -> None:
        summary = summary_for(alice, recent=451, baseline=500)
        assert summary.warning is False

    def test_low_hrv_warns(self, alice: User) -> None:
        # baseline 100 -> 10% below is 90; 90 warns, 91 does not.
        assert summary_for(alice, recent=90, baseline=100, field="hrv").warning is True
        assert summary_for(alice, recent=91, baseline=100, field="hrv").warning is False

    def test_high_resting_hr_warns_at_4_bpm_above(self, alice: User) -> None:
        # 4 bpm above warns; 3 above does not.
        warned = summary_for(alice, recent=54, baseline=50, field="resting_hr")
        assert warned.warning is True
        assert warned.warning_signals == ("high_resting_hr",)
        assert summary_for(alice, recent=53, baseline=50, field="resting_hr").warning is False

    def test_weight_does_not_warn(self, alice: User) -> None:
        summary = summary_for(alice, recent=90, baseline=70, field="weight_kg")
        assert summary.weight.trend == "up"
        assert summary.warning is False

    def test_several_signals_are_all_named(self, alice: User) -> None:
        fill_constant(alice, 450, 500, "sleep_minutes")
        fill_constant(alice, 90, 100, "hrv")
        fill_constant(alice, 54, 50, "resting_hr")
        summary = wellness_summary(alice, TODAY)
        assert summary.warning is True
        assert summary.warning_signals == ("low_sleep", "low_hrv", "high_resting_hr")

    def test_no_warning_when_baseline_missing(self, alice: User) -> None:
        fill(alice, recent_days(), "sleep_minutes", 450)
        summary = wellness_summary(alice, TODAY)
        assert summary.warning is False


class TestSingleQuery:
    def test_one_query_regardless_of_row_count(
        self, alice: User, django_assert_max_num_queries: Any
    ) -> None:
        for i in range(BASELINE_DAYS + RECENT_DAYS):
            DailyWellness.objects.create(
                owner=alice, day=TODAY - timedelta(days=i), sleep_minutes=480
            )
        with django_assert_max_num_queries(1):
            wellness_summary(alice, TODAY)


class TestIsolation:
    def test_one_users_wellness_never_reaches_another(self, alice: User, bob: User) -> None:
        fill_constant(alice, 450, 500, "sleep_minutes")
        fill_constant(bob, 480, 500, "sleep_minutes")

        alices = wellness_summary(alice, TODAY)
        bobs = wellness_summary(bob, TODAY)

        assert alices.warning is True
        assert bobs.warning is False
        assert bobs.sleep.recent == 480


class TestWellnessData:
    def test_none_in_none_out(self) -> None:
        assert wellness_data(None) is None

    def test_a_full_summary_serializes(self, alice: User) -> None:
        fill_constant(alice, 450, 500, "sleep_minutes")
        fill_constant(alice, 54, 50, "resting_hr")
        data = wellness_data(wellness_summary(alice, TODAY))
        assert data is not None
        assert data["warning"] is True
        assert data["warning_signals"] == ["low_sleep", "high_resting_hr"]
        assert data["sleep"] == {"recent": 450, "baseline": 500, "trend": "down"}
        assert data["resting_hr"] == {"recent": 54, "baseline": 50, "trend": "up"}
