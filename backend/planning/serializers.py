"""The shape of what the planning API answers.

The answers are built by hand from stored values and the fixed texts of the checks: nothing the
coach wrote outside the plan itself, no error text of a provider, no ids of other users.
"""

from typing import Any

from rest_framework import serializers

from .models import WeeklyPlan
from .push import ExportState, PushResult
from .rules import Finding
from .schema import Sport, WeekPlan, Workout, ZoneSystem, workout_to_json
from .targets import Targets
from .validation import Report

_TIME = serializers.DateTimeField()


def _time(value: Any) -> Any:
    return None if value is None else _TIME.to_representation(value)


def summary_data(plan: WeeklyPlan, workout_count: int) -> dict[str, Any]:
    """One version of a week, for the list."""
    return {
        "id": str(plan.pk),
        "version": plan.version,
        "status": plan.status,
        "reason": plan.reason,
        "workout_count": workout_count,
        "created_at": _time(plan.created_at),
        "confirmed_at": _time(plan.confirmed_at),
    }


def plan_data(
    plan: WeeklyPlan,
    week_plan: WeekPlan,
    report: Report | None,
    targets: Targets,
    export: ExportState | None = None,
) -> dict[str, Any]:
    """One plan with its workouts and, for a draft, what the checks say about it. Every zone
    comes with its target range as it is *now* (from the thresholds of the user), or ``None``."""
    return {
        "id": str(plan.pk),
        "week_start": plan.week_start.isoformat(),
        "version": plan.version,
        "status": plan.status,
        "reason": plan.reason,
        "rationale": week_plan.rationale,
        "parent": str(plan.parent_id) if plan.parent_id else None,
        "created_at": _time(plan.created_at),
        "confirmed_at": _time(plan.confirmed_at),
        "workouts": [
            {**workout_data(workout, targets), "export": _export(export, index)}
            for index, workout in enumerate(week_plan.workouts)
        ],
        "report": None if report is None else report_data(report),
        "export": None if export is None else _summary(export),
    }


def _export(export: ExportState | None, index: int) -> dict[str, Any] | None:
    """What is known about the event of one workout; ``None`` for a plan that is not sent."""
    if export is None:
        return None
    state = export.workouts[index]
    return {
        "status": state.status,
        "error_code": state.error_code,
        "pushed_at": _time(state.pushed_at),
    }


def _summary(export: ExportState) -> dict[str, int]:
    count = [state.status for state in export.workouts]
    return {
        "synced": count.count("synced"),
        "failed": count.count("failed"),
        "not_sent": count.count("not_sent"),
        # Events of an older version of the week that are still in the calendar.
        "older": export.older,
    }


def push_data(result: PushResult) -> dict[str, Any]:
    return {
        "ok": True,
        "synced": result.synced,
        "failed": result.failed,
        "removed": result.removed,
        "left_behind": result.left_behind,
    }


def push_problem_data(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "problem": code, "message": message}


def workout_data(workout: Workout, targets: Targets) -> dict[str, Any]:
    """The workout in the format of the plan, with ``target`` on it and on each segment."""
    data = workout_to_json(workout)
    data["target"] = _target(targets, workout.sport, workout.zone_system, workout.zone)
    for segment, shown in zip(workout.segments, data["segments"], strict=True):
        shown["target"] = _target(targets, workout.sport, segment.zone_system, segment.zone)
    return data


def _target(
    targets: Targets, sport: Sport, system: ZoneSystem | None, zone: int | None
) -> dict[str, Any] | None:
    if system is None or zone is None:
        return None
    found = targets.target(sport, system, zone)
    return None if found is None else {"low": found.low, "high": found.high, "unit": found.unit}


def report_data(report: Report) -> dict[str, Any]:
    return {
        "valid": report.valid,
        "findings": [finding_data(finding) for finding in report.findings],
    }


def finding_data(finding: Finding) -> dict[str, str]:
    return {
        "severity": finding.severity.value,
        "code": finding.code,
        "message": finding.message,
        "path": finding.path,
    }
