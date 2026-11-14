"""The shape of what the planning API answers.

The answers are built by hand from stored values and the fixed texts of the checks: nothing the
coach wrote outside the plan itself, no error text of a provider, no ids of other users.
"""

from typing import Any

from rest_framework import serializers

from .models import WeeklyPlan
from .rules import Finding
from .schema import WeekPlan, workout_to_json
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


def plan_data(plan: WeeklyPlan, week_plan: WeekPlan, report: Report | None) -> dict[str, Any]:
    """One plan with its workouts and, for a draft, what the checks say about it."""
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
        "workouts": [workout_to_json(workout) for workout in week_plan.workouts],
        "report": None if report is None else report_data(report),
    }


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
