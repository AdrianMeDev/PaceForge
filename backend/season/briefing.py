"""What the coach is told when it fills a season: the skeleton and a few facts of the athlete.

A fixed set of keys, built from the skeleton and from the briefing of the week plan
(``planning.briefing``), so the athlete's sports, facts, best times and limitations are told in
the same words and under the same privacy rules as there. Never told: the name, the e-mail
address, ids, notes, the activities, the free text about limitations. The titles of the races are
the athlete's own text: they are cut and sent as data, which the system prompt says is never
instructions.

The same data gives the same briefing. The number of queries does not depend on how much data
there is.
"""

import json
from datetime import date
from typing import Any

from accounts.models import User
from planning import briefing as week_briefing

from .skeleton import Race, Skeleton
from .storage import skeleton_data

# At most this many races are told, the earliest first; the rest is only counted.
MAX_RACES_TOLD = 20
# The title of a race is cut here (the model allows 100); it is the athlete's own text.
RACE_TITLE_TOLD_MAX = 60
# The most the JSON of a briefing may take, measured in UTF-8 bytes with every free-text character
# as a six-byte escape (a control character), the worst a character can cost.
MAX_BYTES = 24_000

# What is taken over from the briefing of the week plan, word for word.
TAKEN_FROM_THE_WEEK = (
    "sports",
    "sport_preferences",
    "strength_focus",
    "athlete",
    "best_times",
    "vdot",
    "limits",
    "limitations",
    "limitations_not_shown",
    "typical_weekly_minutes",
    "recent_weeks_minutes",
    "weekly_budget_minutes",
)


def build_briefing(user: User, today: date, skeleton: Skeleton) -> dict[str, Any]:
    """The briefing for filling ``skeleton``, as JSON-compatible data. ``today`` is the day it is
    for the athlete; the first week of the skeleton is the week it lies in."""
    first = skeleton.weeks[0].week_start if skeleton.weeks else today
    week = week_briefing.build_briefing(user, first)
    shown = _races(skeleton)
    return {
        "today": today.isoformat(),
        "rolling": skeleton.rolling,
        "truncated": skeleton.truncated,
        "peak_minutes": skeleton.peak_minutes,
        "weeks": [_week(week) for week in skeleton_data(skeleton)["weeks"]],
        "races": [_race(race) for race in shown[:MAX_RACES_TOLD]],
        "races_not_shown": max(len(shown) - MAX_RACES_TOLD, 0),
        **{name: week[name] for name in TAKEN_FROM_THE_WEEK},
    }


def to_json(briefing: dict[str, Any]) -> str:
    """The briefing as text: sorted keys and no spaces, so the same briefing is the same text."""
    return json.dumps(briefing, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _week(week: dict[str, Any]) -> dict[str, Any]:
    """A week of the skeleton as it is told: the races only by their day (their titles are in
    ``races``, once)."""
    return {
        "week_start": week["week_start"],
        "phase": week["phase"],
        "recovery": week["recovery"],
        "target_minutes": week["target_minutes"],
        "capacity_minutes": week["capacity_minutes"],
        "race_dates": [race["date"] for race in week["races"]],
    }


def _races(skeleton: Skeleton) -> list[Race]:
    """Every race of the skeleton's weeks, by day."""
    return sorted((race for week in skeleton.weeks for race in week.races), key=lambda r: r.day)


def _race(race: Race) -> dict[str, Any]:
    return {
        "date": race.day.isoformat(),
        "priority": race.priority,
        "discipline": race.discipline,
        "distance_m": race.distance_m,
        "title": race.title[:RACE_TITLE_TOLD_MAX],
    }
