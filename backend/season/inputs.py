"""What the skeleton of a user starts from, read from the database in a fixed number of queries.

The pure skeleton (``season.skeleton``) knows nothing of users: this module reads today in the
time zone of the athlete, their active races, what the weeks offer, the reference week and the
intensity level, and builds the skeleton from them.
"""

from datetime import timedelta
from fractions import Fraction

from accounts.models import User
from availability.capacity import weekly_capacities
from availability.intensity import DEFAULT_LEVEL
from availability.models import AvailabilitySettings
from goals.models import Goal
from goals.services import time_zone_of, today_of
from planning.context import recent_activities, recent_weekly_minutes
from planning.rules import TYPICAL_VOLUME_PERCENT

from .skeleton import MAX_WEEKS, Race, Skeleton, SkeletonInputs, build_skeleton


def skeleton_for(user: User) -> Skeleton:
    """The skeleton of the season of ``user``, from the Monday of the current week on."""
    today = today_of(user)
    first_monday = today - timedelta(days=today.weekday())
    zone = time_zone_of(user)
    recent = recent_weekly_minutes(recent_activities(user, first_monday, zone), zone, first_monday)
    settings = (
        AvailabilitySettings.objects.for_user(user)
        .values_list("typical_weekly_minutes", "intensity_level")
        .first()
    )
    typical, level = settings if settings is not None else (None, DEFAULT_LEVEL.value)
    return build_skeleton(
        SkeletonInputs(
            first_monday=first_monday,
            capacities=weekly_capacities(user, first_monday, MAX_WEEKS),
            races=races_of(user),
            reference_minutes=reference_minutes(recent, typical),
            level=level,
        )
    )


def races_of(user: User) -> tuple[Race, ...]:
    """The active races with a date, by date. Goals of another kind have no day to work towards."""
    rows = (
        Goal.objects.for_user(user)
        .filter(status=Goal.Status.ACTIVE, kind=Goal.Kind.RACE, target_date__isnull=False)
        .order_by("target_date", "created_at", "id")
        .values_list("target_date", "priority", "discipline", "distance_m", "title")
    )
    return tuple(
        Race(day, priority, discipline or None, distance, title)
        for day, priority, discipline, distance, title in rows
        if day is not None
    )


def reference_minutes(recent_weeks: tuple[int, ...], typical: int | None) -> int | None:
    """The reference week of the athlete: the higher of the average of the recent weeks and their
    normal week (``TYPICAL_VOLUME_PERCENT`` of it), as the rules take it. ``None`` without either.
    """
    options: list[Fraction] = []
    if recent_weeks and sum(recent_weeks) > 0:
        options.append(Fraction(sum(recent_weeks), len(recent_weeks)))
    if typical:
        options.append(Fraction(typical * TYPICAL_VOLUME_PERCENT, 100))
    if not options:
        return None
    return int(max(options) + Fraction(1, 2))
