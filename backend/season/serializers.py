"""The shape of what the season API answers: built by hand from the skeleton, nothing else."""

from datetime import date
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
    plan: SeasonPlanVersion,
    loaded: StoredSeason,
    report: Report | None,
    done: dict[date, list[tuple[str, int]]] | None = None,
) -> dict[str, Any]:
    """One version with its weeks and the skeleton it was made for. A draft comes with what the
    checks say about it (``report`` is ``None`` for a plan that was decided on: the checks are
    about what can still be done). The text of the coach (the rationale, the reasons and the
    details) is in it as text and nothing else. ``done`` holds the minutes the athlete trained in
    the weeks that have begun (``season.done``); a week that is not in it has ``done: null``."""
    data = to_json(loaded.plan)
    done = done or {}
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
            {
                **week,
                "total_minutes": built.total,
                "done": _done(done.get(built.week_start)),
            }
            for week, built in zip(data["weeks"], loaded.plan.weeks, strict=True)
        ],
        "report": None if report is None else report_data(report),
    }


def _done(entries: list[tuple[str, int]] | None) -> list[dict[str, Any]] | None:
    if entries is None:
        return None
    return [{"sport": sport, "minutes": minutes} for sport, minutes in entries]


_TIME = serializers.DateTimeField()


def _time(value: Any) -> Any:
    return None if value is None else _TIME.to_representation(value)
