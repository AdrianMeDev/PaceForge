"""The shape of what the season API answers: built by hand from the skeleton, nothing else."""

from datetime import date
from typing import TYPE_CHECKING, Any

from rest_framework import serializers

from planning.serializers import report_data
from planning.validation import Report

from .schema import to_json
from .storage import skeleton_data

if TYPE_CHECKING:
    from .done import WeekTotals
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
    plan: SeasonPlanVersion,
    loaded: StoredSeason,
    report: Report | None,
    planned_load: dict[date, dict[str, int]],
    done: dict[date, WeekTotals] | None = None,
) -> dict[str, Any]:
    """One version with its weeks and the skeleton it was made for. A draft comes with what the
    checks say about it (``report`` is ``None`` for a plan that was decided on: the checks are
    about what can still be done). The text of the coach (the rationale, the reasons and the
    details) is in it as text and nothing else. ``done`` holds minutes and load for confirmed
    weeks that have begun; other weeks have ``done: null`` and ``done_load: null``."""
    data = to_json(loaded.plan)
    done = done or {}
    return {
        "id": str(plan.pk),
        "version": plan.version,
        "status": plan.status,
        "reason": plan.reason,
        "request": plan.request,
        "rationale": data["rationale"],
        "parent": str(plan.parent_id) if plan.parent_id else None,
        "created_at": _time(plan.created_at),
        "confirmed_at": _time(plan.confirmed_at),
        "skeleton": skeleton_data(loaded.context.skeleton),
        "weeks": [
            {
                **week,
                "total_minutes": built.total,
                "planned_load": planned_load[built.week_start],
                "total_planned_load": sum(planned_load[built.week_start].values()),
                "done": _done(done[built.week_start]["minutes"], "minutes")
                if built.week_start in done
                else None,
                "done_load": _done(done[built.week_start]["load"], "load")
                if built.week_start in done
                else None,
            }
            for week, built in zip(data["weeks"], loaded.plan.weeks, strict=True)
        ],
        "report": None if report is None else report_data(report),
    }


def _done(entries: list[tuple[str, int]], field: str) -> list[dict[str, Any]]:
    return [{"sport": sport, field: amount} for sport, amount in entries]


_TIME = serializers.DateTimeField()


def _time(value: Any) -> Any:
    return None if value is None else _TIME.to_representation(value)
