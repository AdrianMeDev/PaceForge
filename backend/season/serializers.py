"""The shape of what the season API answers: built by hand from the skeleton, nothing else."""

from typing import TYPE_CHECKING, Any

from rest_framework import serializers

from planning.serializers import report_data
from planning.validation import Report

from .schema import to_json
from .storage import skeleton_data

if TYPE_CHECKING:
    from .models import SeasonPlanVersion
    from .services import StoredSeason


def plan_summary(plan: SeasonPlanVersion) -> dict[str, Any]:
    """One version of the season plan, for the list."""
    return {
        "id": str(plan.pk),
        "version": plan.version,
        "status": plan.status,
        "reason": plan.reason,
        "week_count": len(plan.weeks),
        "created_at": _time(plan.created_at),
        "confirmed_at": _time(plan.confirmed_at),
    }


def plan_detail(
    plan: SeasonPlanVersion, loaded: StoredSeason, report: Report | None
) -> dict[str, Any]:
    """One version with its weeks and the skeleton it was made for. A draft comes with what the
    checks say about it (``report`` is ``None`` for a plan that was decided on: the checks are
    about what can still be done). The text of the coach (the rationale, the reasons and the
    details) is in it as text and nothing else."""
    data = to_json(loaded.plan)
    return {
        "id": str(plan.pk),
        "version": plan.version,
        "status": plan.status,
        "reason": plan.reason,
        "rationale": data["rationale"],
        "parent": str(plan.parent_id) if plan.parent_id else None,
        "created_at": _time(plan.created_at),
        "confirmed_at": _time(plan.confirmed_at),
        "skeleton": skeleton_data(loaded.context.skeleton),
        "weeks": [
            {**week, "total_minutes": built.total}
            for week, built in zip(data["weeks"], loaded.plan.weeks, strict=True)
        ],
        "report": None if report is None else report_data(report),
    }


_TIME = serializers.DateTimeField()


def _time(value: Any) -> Any:
    return None if value is None else _TIME.to_representation(value)
