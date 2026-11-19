"""The whole dashboard: the current week (``dashboard.summary``) and what surrounds it: where the
week is in the season, the main goal, the minutes of the last weeks, the latest activities and the
use of the coach.

Every function acts on the data of the user it is given and on nothing else. The number of queries
does not depend on how much data there is, and not on whether there is a main goal either: the form
of the athlete is read always, also when no goal needs it.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from accounts.models import User
from activities.models import Activity
from coach.services import UsageSummary, usage_summary
from goals.assessing import facts_of, form_of
from goals.models import Goal
from goals.realism import Assessment, Form, assess
from goals.services import time_zone_of, today_of
from season.done import done_minutes
from season.skeleton import Phase
from season.weeks import confirmed_week
from wellness.summary import WellnessSummary, wellness_summary

from .setup import SetupStep, setup_of
from .summary import WeekGlance, week_glance

# The weeks of the chart: the current one and the ones before it.
CHART_WEEKS = 8
RECENT_ACTIVITIES = 3


@dataclass(frozen=True)
class SeasonGlance:
    """The week in the confirmed season plan: its phase, whether it is a recovery week and the
    minutes the skeleton aims for."""

    phase: Phase
    recovery: bool
    target_minutes: int


@dataclass(frozen=True)
class MainGoal:
    """The active main goal. ``title`` is the athlete's own text. ``weeks_left`` are the whole weeks
    to the date (``None``: no date, or it has passed); ``assessment`` is the judgement."""

    id: UUID
    title: str
    kind: str
    target_date: date | None
    weeks_left: int | None
    assessment: Assessment


@dataclass(frozen=True)
class WeekMinutes:
    """The minutes done in a week as ``(sport, minutes)``, only the sports with some."""

    week_start: date
    sports: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class RecentActivity:
    """An activity on the local day it was done; ``minutes`` is ``None`` without a duration."""

    id: UUID
    day: date
    sport: str
    minutes: int | None


@dataclass(frozen=True)
class Dashboard:
    week: WeekGlance
    season: SeasonGlance | None
    main_goal: MainGoal | None
    weeks: tuple[WeekMinutes, ...]
    recent: tuple[RecentActivity, ...]
    usage: UsageSummary
    setup: tuple[SetupStep, ...]
    wellness: WellnessSummary | None


def dashboard_of(user: User) -> Dashboard:
    week = week_glance(user)
    today = today_of(user)
    form = form_of(user)
    mondays = [week.week_start - timedelta(weeks=n) for n in range(CHART_WEEKS - 1, -1, -1)]
    done = done_minutes(user, mondays)
    return Dashboard(
        week=week,
        season=_season(user, week.week_start),
        main_goal=_main_goal(user, form, today),
        weeks=tuple(WeekMinutes(monday, tuple(done[monday])) for monday in mondays),
        recent=_recent(user),
        usage=usage_summary(user),
        setup=setup_of(user),
        wellness=_wellness(user, today),
    )


def _season(user: User, monday: date) -> SeasonGlance | None:
    found = confirmed_week(user, monday)
    if found is None:
        return None
    return SeasonGlance(found.phase, found.recovery, found.target_minutes)


def _main_goal(user: User, form: Form, today: date) -> MainGoal | None:
    goal = (
        Goal.objects.for_user(user)
        .filter(priority=Goal.Priority.MAIN, status=Goal.Status.ACTIVE)
        .first()
    )
    if goal is None:
        return None
    days = None if goal.target_date is None else (goal.target_date - today).days
    return MainGoal(
        id=goal.pk,
        title=goal.title,
        kind=goal.kind,
        target_date=goal.target_date,
        weeks_left=None if days is None or days < 0 else days // 7,
        assessment=assess(facts_of(goal), form, today),
    )


def _recent(user: User) -> tuple[RecentActivity, ...]:
    zone = time_zone_of(user)
    rows = (
        Activity.objects.for_user(user)
        .order_by("-start_time", "-id")
        .values_list("id", "start_time", "sport", "timer_seconds", "elapsed_seconds")[
            :RECENT_ACTIVITIES
        ]
    )
    return tuple(
        RecentActivity(
            id=pk,
            day=start.astimezone(zone).date(),
            sport=sport,
            minutes=_minutes(timer if timer is not None else elapsed),
        )
        for pk, start, sport, timer, elapsed in rows
    )


def _minutes(seconds: float | None) -> int | None:
    """Whole minutes, half up (as ``season.done`` counts them)."""
    return None if seconds is None else int(seconds / 60 + 0.5)


def _wellness(user: User, today: date) -> WellnessSummary | None:
    """The recent wellness summary, or ``None`` when no metric has enough recent readings."""
    summary = wellness_summary(user, today)
    if all(
        metric.recent is None
        for metric in (summary.sleep, summary.hrv, summary.resting_hr, summary.weight)
    ):
        return None
    return summary
