"""Stable inputs belonging to a season version, without notes or bookkeeping timestamps.

Dates of goals and best times are inputs. Their creation and update times are not. Only active
goals count; best times are kept without a moving age window. FTP is the effective number, so a
change to a source that does not count leaves the inputs unchanged. Collection only reads data.
"""

from typing import Any

from accounts.models import User
from athletes.models import BestTime, ThresholdValue
from athletes.thresholds import effective
from availability.models import AvailabilitySettings
from goals.models import Goal

SNAPSHOT_VERSION = 1


def collect_inputs(user: User) -> dict[str, Any]:
    """JSON-compatible inputs of this user in a fixed order, with explicit unknown values."""
    goals = Goal.objects.for_user(user).filter(status=Goal.Status.ACTIVE).order_by("id")
    best_times = BestTime.objects.for_user(user).order_by("distance")
    ftp = effective(user, ThresholdValue.Sport.RIDE, ThresholdValue.Metric.FTP)
    typical = (
        AvailabilitySettings.objects.for_user(user)
        .values_list("typical_weekly_minutes", flat=True)
        .first()
    )
    return {
        "version": SNAPSHOT_VERSION,
        "goals": [
            {
                "id": str(goal.pk),
                "kind": goal.kind,
                "title": goal.title,
                "priority": goal.priority,
                "target_date": None if goal.target_date is None else goal.target_date.isoformat(),
                "discipline": goal.discipline,
                "distance_m": goal.distance_m,
                "target_time_seconds": goal.target_time_seconds,
                "metric": goal.metric,
                "target_value": goal.target_value,
            }
            for goal in goals
        ],
        "ftp": None if ftp is None else ftp.value,
        "best_times": [
            {"distance": best.distance, "seconds": best.seconds, "date": best.date.isoformat()}
            for best in best_times
        ],
        "typical_weekly_minutes": typical,
    }
