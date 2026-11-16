"""What the confirmed season plan says about one week.

The week plan asks here for the week it is about. Only the **confirmed** plan of the user counts,
and the week must lie in the skeleton that plan was made for. A plan that cannot be read (it should
not happen: it was parsed when it was stored) counts as no season week, so planning a week never
fails because of it. One query, however long the season is.

This module imports neither ``season.services`` nor ``season.rules`` (they reach into
``planning.validation``, and the week plan reads this module while it is built).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from accounts.models import User
from planning.schema import PlanFormatError, Sport

from .models import SeasonPlanVersion
from .schema import Focus, KeySession, parse_season_plan
from .skeleton import Phase, Race
from .storage import skeleton_from_data


@dataclass(frozen=True)
class SeasonWeekFacts:
    """One week of the confirmed season: what the skeleton says (phase, recovery, the minutes it
    aims for and the week offers, the races) and what the coach filled in (minutes per sport, the
    focus, the key sessions and the reason, which is the coach's own text)."""

    week_start: date
    phase: Phase
    recovery: bool
    target_minutes: int
    capacity_minutes: int
    races: tuple[Race, ...]
    # The minutes of the sports the coach gave, in the order of ``Sport``.
    minutes: tuple[tuple[Sport, int], ...]
    focus: Focus
    key_sessions: tuple[KeySession, ...]
    reason: str

    @property
    def total_minutes(self) -> int:
        return sum(amount for _, amount in self.minutes)


def confirmed_weeks(user: User, mondays: Iterable[date]) -> dict[date, SeasonWeekFacts]:
    """The weeks that start on ``mondays`` that are in the confirmed season plan of ``user``. A
    Monday that is not in it is not in the answer, and neither is any if there is no confirmed
    plan or it cannot be read. One query, however many weeks are asked for."""
    stored = SeasonPlanVersion.objects.for_user(user).filter(status="confirmed").first()
    if stored is None:
        return {}
    try:
        plan = parse_season_plan({"rationale": stored.rationale, "weeks": stored.weeks})
        skeleton = skeleton_from_data(stored.skeleton)
    except PlanFormatError, ValueError, KeyError, TypeError:
        return {}
    frames = {week.week_start: week for week in skeleton.weeks}
    filled = {week.week_start: week for week in plan.weeks}
    found: dict[date, SeasonWeekFacts] = {}
    for monday in mondays:
        frame, fill = frames.get(monday), filled.get(monday)
        if frame is None or fill is None:
            continue
        found[monday] = SeasonWeekFacts(
            week_start=monday,
            phase=frame.phase,
            recovery=frame.recovery,
            target_minutes=frame.target_minutes,
            capacity_minutes=frame.capacity_minutes,
            races=frame.races,
            minutes=fill.minutes,
            focus=fill.focus,
            key_sessions=fill.key_sessions,
            reason=fill.reason,
        )
    return found


def confirmed_week(user: User, monday: date) -> SeasonWeekFacts | None:
    """The week that starts on ``monday`` in the confirmed season plan of ``user``, or ``None``: no
    confirmed plan, the week is not in it, or the plan cannot be read."""
    return confirmed_weeks(user, [monday]).get(monday)
