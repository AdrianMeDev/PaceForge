"""Read-only hints about inputs that differ from the confirmed season's original baseline.

Only the confirmed version counts. Neither reading a hint nor making a draft acknowledges a
change. Capacity is compared on the dates kept in the plan, never against a shifted skeleton.
"""

from datetime import timedelta
from enum import StrEnum
from typing import TypedDict

from accounts.models import User
from availability.capacity import weekly_capacities
from goals.services import today_of

from .models import SeasonPlanVersion
from .snapshots import SNAPSHOT_VERSION, collect_inputs
from .storage import skeleton_from_data

TIME_CHANGE_PERCENT = 20
TIME_CHANGE_MINUTES = 60


class Reason(StrEnum):
    BASELINE_UNKNOWN = "baseline_unknown"
    GOALS_CHANGED = "goals_changed"
    FTP_CHANGED = "ftp_changed"
    BEST_TIMES_CHANGED = "best_times_changed"
    TRAINING_TIME_CHANGED = "training_time_changed"


class Reassessment(TypedDict):
    confirmed_plan_id: str | None
    reasons: list[str]
    deviation_weeks: list[str]


def reassess(user: User) -> Reassessment:
    """Compare today's inputs with what the user's confirmed plan was drafted from.

    Unknown or unsupported snapshots need a new baseline, not invented historical inputs.
    Reasons have a fixed order and contain no user text or input values.
    """
    result: Reassessment = {"confirmed_plan_id": None, "reasons": [], "deviation_weeks": []}
    plan = (
        SeasonPlanVersion.objects.for_user(user)
        .filter(status=SeasonPlanVersion.Status.CONFIRMED)
        .first()
    )
    if plan is None:
        return result
    result["confirmed_plan_id"] = str(plan.pk)
    baseline = plan.input_snapshot
    if (
        not isinstance(baseline, dict)
        or baseline.get("version") != SNAPSHOT_VERSION
        or not {"goals", "ftp", "best_times", "typical_weekly_minutes"} <= baseline.keys()
    ):
        result["reasons"].append(Reason.BASELINE_UNKNOWN.value)
        return result

    current = collect_inputs(user)
    for field, reason in (
        ("goals", Reason.GOALS_CHANGED),
        ("ftp", Reason.FTP_CHANGED),
        ("best_times", Reason.BEST_TIMES_CHANGED),
    ):
        if baseline[field] != current[field]:
            result["reasons"].append(reason.value)
    if _large_time_change(
        baseline["typical_weekly_minutes"], current["typical_weekly_minutes"]
    ) or _capacity_changed(user, plan):
        result["reasons"].append(Reason.TRAINING_TIME_CHANGED.value)
    return result


def _large_time_change(before: int | None, now: int | None) -> bool:
    # Unspecified typical minutes count as zero for this comparison. From zero, the absolute
    # threshold alone applies. Integer multiplication keeps the percentage boundary exact.
    old, new = before or 0, now or 0
    difference = abs(new - old)
    return difference >= TIME_CHANGE_MINUTES and difference * 100 >= old * TIME_CHANGE_PERCENT


def _capacity_changed(user: User, plan: SeasonPlanVersion) -> bool:
    today = today_of(user)
    monday = today - timedelta(days=today.weekday())
    remaining = tuple(
        week for week in skeleton_from_data(plan.skeleton).weeks if week.week_start >= monday
    )
    if not remaining:
        return False
    first = remaining[0].week_start
    count = (remaining[-1].week_start - first).days // 7 + 1
    capacities = weekly_capacities(user, first, count)
    return any(
        _large_time_change(week.capacity_minutes, capacities[(week.week_start - first).days // 7])
        for week in remaining
    )
