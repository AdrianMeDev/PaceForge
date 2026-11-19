"""The facts a week plan is checked against: what the user can do, have and did.

``build_context`` collects them from the database for one user and one week; the checks themselves
(``planning.rules``) are pure functions on a plan and this context. Nothing is invented: a fact the
user has not given is simply not there (no time declared means no time, no threshold means no zone
system, no activities means no reference volume).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from accounts.models import User
from activities.models import Activity
from athletes import best_times
from athletes.facts import body_and_training
from athletes.thresholds import all_candidates
from availability.capacity import week_capacity
from availability.fixed_sessions import fixed_sessions
from availability.intensity import DEFAULT_LEVEL, LEVEL_LIMITS, Limits
from availability.limitations import current_limitations
from availability.preferences import sport_preferences
from goals.services import time_zone_of
from season.weeks import SeasonWeekFacts, confirmed_week

from .schema import Slot, Sport, ZoneSystem

# How many weeks before the plan's week make up the reference volume.
RECENT_WEEKS = 4


@dataclass(frozen=True)
class ActiveLimitation:
    """A current injury or limitation: where it is (from a fixed list) and the sports it affects,
    none meaning no particular sport."""

    body_part: str
    sports: frozenset[Sport]


@dataclass(frozen=True)
class SportFacts:
    """What the athlete said about one sport: its role (``None``: none) and the least and the most
    sessions a week they want of it (``None``: no wish)."""

    sport: Sport
    role: str | None
    sessions_min: int | None
    sessions_max: int | None


@dataclass(frozen=True)
class FixedFacts:
    """A session that happens every week: the weekday (Monday is 0), the sport, how long it lasts
    and the part of the day (``None``: none named)."""

    weekday: int
    sport: Sport
    minutes: int
    slot: Slot | None


@dataclass(frozen=True)
class AthleteFacts:
    """What the athlete said about their body and their training, ``None`` or empty for what they
    did not say. The age is the year of the week to plan minus the birth year (it can be one too
    high before the birthday); the birth year itself is not kept."""

    age: int | None = None
    sex: str | None = None
    weight_kg: float | None = None
    resting_hr: int | None = None
    training_years: tuple[tuple[Sport, int], ...] = ()
    strength_experience: str | None = None
    strength_equipment: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanContext:
    week_start: date
    # What each day offers, Monday first; 0 inside an absence. The weekly budget is not in here.
    minutes: tuple[int, ...]
    # The kind of absence that covers each day, else ``None``.
    absences: tuple[str | None, ...]
    # The weekly budget (``None``: none) and what the week offers in all, budget applied.
    weekly_budget: int | None
    weekly_minutes: int
    # The (sport, zone system) pairs the athlete has a threshold for.
    zone_systems: frozenset[tuple[Sport, ZoneSystem]]
    # Minutes done in each of the up to ``RECENT_WEEKS`` weeks before this one that have data,
    # the latest week first. Empty: there is no reference.
    recent_weeks: tuple[int, ...]
    # What the athlete calls a normal week, in minutes (``None``: not said). The progression rule
    # takes it as the reference when it is higher than the recent weeks.
    typical_weekly_minutes: int | None = None
    # The sports the athlete wants in a plan (all of them if none was chosen) and whether
    # stretching may be added to sessions.
    sports: frozenset[Sport] = frozenset(Sport)
    stretching: bool = False
    # The limits of the rules that follow from the athlete's intensity level and own values.
    limits: Limits = LEVEL_LIMITS[DEFAULT_LEVEL]
    # Per day, Monday first: whether two workouts are allowed, and the parts of the day that are
    # open. Without a choice two are allowed and every part of the day is open.
    double_days: tuple[bool, ...] = (True,) * 7
    time_windows: tuple[frozenset[Slot], ...] = (frozenset(Slot),) * 7
    # The current limitations, the newest first. Healed ones are not in here.
    limitations: tuple[ActiveLimitation, ...] = ()
    # The athlete's free text about their limitations, only if they let it go to the coach.
    limitations_text: str | None = None
    # The wishes for a week, ``None`` where there is none: on how many days to train at most, the
    # least to train in a week (minutes), and for each sport with a long day the place of that day
    # in the week (Monday is 0).
    training_days: int | None = None
    min_weekly_minutes: int | None = None
    long_days: tuple[tuple[Sport, int], ...] = ()
    # What the athlete said about their sports (only the sports they said something about, in the
    # order of the format) and what strength training is for (``None``: not said).
    sport_preferences: tuple[SportFacts, ...] = ()
    strength_focus: str | None = None
    # The athlete's body and training data.
    athlete: AthleteFacts = AthleteFacts()
    # The sessions that happen every week, by weekday and part of the day.
    fixed_sessions: tuple[FixedFacts, ...] = ()
    # The athlete's best times, in the order of the distances, with their VDOT. The one that counts
    # for the threshold pace is found with ``best_times.counting``.
    best_times: tuple[best_times.Entry, ...] = ()
    # What the confirmed season plan says about this week; ``None``: there is no confirmed plan,
    # or the week is not in it.
    season_week: SeasonWeekFacts | None = None
    # Running minutes for the same weeks, including zero when a week has no timed run.
    recent_run_weeks: tuple[int, ...] = ()

    def offset(self, day: date) -> int | None:
        """The place of ``day`` in the week (Monday is 0), ``None`` if it lies outside."""
        offset = (day - self.week_start).days
        return offset if 0 <= offset < 7 else None


def build_context(user: User, monday: date) -> PlanContext:
    """The context of the week that starts on ``monday``: the same few queries however full the
    data."""
    capacity = week_capacity(user, monday)  # raises ValueError unless it is a Monday
    body = body_and_training(user)
    races = best_times.entries(user)
    held = set(all_candidates(user, races))
    zone = time_zone_of(user)
    activities = recent_activities(user, monday, zone)
    return PlanContext(
        week_start=monday,
        minutes=capacity.minutes,
        absences=capacity.absences,
        weekly_budget=capacity.budget,
        weekly_minutes=capacity.total,
        zone_systems=usable_zone_systems(held),
        recent_weeks=recent_weekly_minutes(activities, zone, monday),
        recent_run_weeks=recent_weekly_minutes(
            activities, zone, monday, sport=Activity.Sport.RUNNING
        ),
        typical_weekly_minutes=capacity.typical_weekly_minutes,
        sports=frozenset(Sport(sport) for sport in capacity.sports),
        stretching=capacity.stretching,
        limits=capacity.limits,
        double_days=capacity.double_days,
        time_windows=tuple(
            frozenset(Slot(slot) for slot in window) for window in capacity.time_windows
        ),
        limitations_text=capacity.shared_limitations_text,
        strength_focus=capacity.strength_focus,
        best_times=tuple(races),
        athlete=AthleteFacts(
            age=None if body.birth_year is None else max(monday.year - body.birth_year, 0),
            sex=body.sex,
            weight_kg=body.weight_kg,
            resting_hr=body.resting_hr,
            training_years=tuple((Sport(sport), years) for sport, years in body.training_years),
            strength_experience=body.strength_experience,
            strength_equipment=body.strength_equipment,
        ),
        sport_preferences=tuple(
            SportFacts(Sport(sport), role, low, high)
            for sport, role, low, high in sport_preferences(user)
        ),
        fixed_sessions=tuple(
            FixedFacts(weekday, Sport(sport), minutes, Slot(slot) if slot else None)
            for weekday, sport, minutes, slot in fixed_sessions(user)
        ),
        training_days=capacity.training_days,
        min_weekly_minutes=capacity.min_weekly_minutes,
        long_days=tuple(
            (sport, day)
            for sport, day in (
                (Sport.RUNNING, capacity.long_run_day),
                (Sport.CYCLING, capacity.long_ride_day),
            )
            if day is not None
        ),
        limitations=tuple(
            ActiveLimitation(body_part, frozenset(Sport(sport) for sport in sports))
            for body_part, sports in current_limitations(user)
        ),
        season_week=confirmed_week(user, monday),
    )


def usable_zone_systems(held: Iterable[tuple[str, str]]) -> frozenset[tuple[Sport, ZoneSystem]]:
    """The zone systems that can be used for a sport, given the thresholds the athlete has
    (``(sport group, metric)`` pairs such as ``("ride", "ftp")``). Power needs the FTP, pace the
    threshold pace and heart rate the lactate threshold or the maximum heart rate. Swimming and
    strength have no zones."""
    held = set(held)
    systems: set[tuple[Sport, ZoneSystem]] = set()
    if ("ride", "ftp") in held:
        systems.add((Sport.CYCLING, ZoneSystem.POWER))
    if ("ride", "lthr") in held or ("ride", "max_hr") in held:
        systems.add((Sport.CYCLING, ZoneSystem.HEART_RATE))
    if ("run", "threshold_pace") in held:
        systems.add((Sport.RUNNING, ZoneSystem.PACE))
    if ("run", "lthr") in held or ("run", "max_hr") in held:
        systems.add((Sport.RUNNING, ZoneSystem.HEART_RATE))
    return frozenset(systems)


def recent_weekly_minutes(
    activities: Iterable[tuple[datetime, float | None, float | None, str]],
    zone: tzinfo,
    monday: date,
    weeks: int = RECENT_WEEKS,
    sport: str | None = None,
) -> tuple[int, ...]:
    """The minutes done in each of the ``weeks`` weeks before ``monday``, the latest first.

    ``activities`` are ``(start, timer seconds, elapsed seconds, sport)``. A week is a calendar week
    (Monday to Sunday) in ``zone``, so an activity just after midnight belongs to the day the
    athlete lived it. The timer time counts, the elapsed time stands in for it, and an activity
    with neither has no duration and does not count at all. A week without any activity that has
    a duration is left out. With a sport filter, other timed activities still establish a week,
    but contribute zero minutes.
    """
    first = monday - timedelta(weeks=weeks)
    seconds_by_week: dict[date, float] = {}
    for start, timer, elapsed, activity_sport in activities:
        duration = timer if timer is not None else elapsed
        if duration is None:
            continue
        day = start.astimezone(zone).date()
        if not first <= day < monday:
            continue
        week = day - timedelta(days=day.weekday())
        seconds_by_week.setdefault(week, 0.0)
        if sport is None or activity_sport == sport:
            seconds_by_week[week] += duration
    return tuple(
        int(seconds_by_week[week] / 60 + 0.5) for week in sorted(seconds_by_week, reverse=True)
    )


def recent_activities(
    user: User, monday: date, zone: tzinfo
) -> list[tuple[datetime, float | None, float | None, str]]:
    """The user's activities of the weeks before ``monday``, with one query."""
    since = _local_midnight(monday - timedelta(weeks=RECENT_WEEKS), zone)
    until = _local_midnight(monday, zone)
    return list(
        Activity.objects.for_user(user)
        .filter(start_time__gte=since, start_time__lt=until)
        .values_list("start_time", "timer_seconds", "elapsed_seconds", "sport")
    )


def _local_midnight(day: date, zone: tzinfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)
