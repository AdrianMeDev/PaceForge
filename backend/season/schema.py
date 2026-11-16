"""The format of a filled season, and the one strict parser that reads it.

The coach answers with one object: a reason for the whole season and, for every week of the
skeleton, the minutes of each sport, a focus, up to three key sessions and a reason. The parser
accepts exactly this format, reports *every* problem at once by its path
(``weeks[2].key_sessions[0].minutes``) and never repeats a value of the input in a message, as the
parser of the week plan (``planning.schema``) does: it is built on the same reader.

Whether the weeks are the weeks of the skeleton and whether the minutes follow it is a matter of
the checks (``season.rules``), not of the format.

```
{
  "rationale": "Why the season looks like this",     # optional
  "weeks": [
    {
      "week_start": "2026-11-16",                      # a Monday
      "minutes": {"running": 180, "strength": 45},     # per sport; a sport left out has none
      "focus": "endurance",
      "key_sessions": [                                # optional, at most 3
        {"sport": "running", "kind": "long", "minutes": 90, "detail": "steady, 20 km"}
      ],
      "reason": "Build the base; one long run, strength twice."
    }
  ]
}
```

This module is pure: no database, no Django.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

# The reader of the week plan is shared on purpose: the same rules for text, numbers and choices,
# the same messages. Its building blocks are private to ``planning.schema`` and used here.
from planning.schema import _MISSING, _NAME, PlanFormatError, Problem, Sport, _Reader

from .skeleton import MAX_WEEKS

RATIONALE_MAX = 1000
REASON_MAX = 300
DETAIL_MAX = 60
MAX_KEY_SESSIONS = 3
# The most of one sport in a week: all of its minutes.
WEEK_MINUTES_MAX = 7 * 24 * 60
KEY_SESSION_MINUTES_MAX = 24 * 60

__all__ = [
    "DETAIL_MAX",
    "Focus",
    "KEY_SESSION_MINUTES_MAX",
    "KeySession",
    "MAX_KEY_SESSIONS",
    "PlanFormatError",
    "PlanWeek",
    "Problem",
    "REASON_MAX",
    "RATIONALE_MAX",
    "SeasonPlan",
    "SessionKind",
    "WEEK_MINUTES_MAX",
    "parse_season_plan",
    "to_json",
]


class Focus(StrEnum):
    """What a week is about."""

    RECOVERY = "recovery"
    ENDURANCE = "endurance"
    TEMPO = "tempo"
    THRESHOLD = "threshold"
    VO2MAX = "vo2max"
    RACE_SPECIFIC = "race_specific"


class SessionKind(StrEnum):
    """What a key session is."""

    LONG = "long"
    TEMPO = "tempo"
    THRESHOLD = "threshold"
    VO2MAX = "vo2max"
    RACE_PACE = "race_pace"
    STRENGTH = "strength"
    RACE = "race"


@dataclass(frozen=True)
class KeySession:
    """One of the sessions a week stands on: the sport, what it is, how long, and a few words of
    the coach ("3 x 10 min") that are only ever shown as text."""

    sport: Sport
    kind: SessionKind
    minutes: int
    detail: str = ""


@dataclass(frozen=True)
class PlanWeek:
    week_start: date
    # The minutes of the sports the coach gave, in the order of ``Sport``.
    minutes: tuple[tuple[Sport, int], ...]
    focus: Focus
    reason: str
    key_sessions: tuple[KeySession, ...] = ()

    @property
    def total(self) -> int:
        """All the minutes of the week."""
        return sum(amount for _, amount in self.minutes)


@dataclass(frozen=True)
class SeasonPlan:
    weeks: tuple[PlanWeek, ...] = ()
    rationale: str = ""


def parse_season_plan(data: object) -> SeasonPlan:
    """The plan in ``data``, or a ``PlanFormatError`` with all problems."""
    reader = _SeasonReader()
    plan = reader.read(data)
    if reader.problems or plan is None:
        raise PlanFormatError(tuple(reader.problems))
    return plan


def to_json(plan: SeasonPlan) -> dict[str, Any]:
    """The plan in the format above, with every field written out. ``parse_season_plan`` reads it
    back into an equal plan."""
    return {
        "rationale": plan.rationale,
        "weeks": [
            {
                "week_start": week.week_start.isoformat(),
                "minutes": {sport.value: amount for sport, amount in week.minutes},
                "focus": week.focus.value,
                "key_sessions": [
                    {
                        "sport": session.sport.value,
                        "kind": session.kind.value,
                        "minutes": session.minutes,
                        "detail": session.detail,
                    }
                    for session in week.key_sessions
                ],
                "reason": week.reason,
            }
            for week in plan.weeks
        ],
    }


class _SeasonReader(_Reader):
    def read(self, data: object) -> SeasonPlan | None:
        item = self._object(data, "", {"weeks"}, {"rationale"})
        if item is None:
            return None
        rationale = self._text(item.get("rationale", ""), "rationale", RATIONALE_MAX, True, True)
        weeks = self._list(item.get("weeks", _MISSING), "weeks", MAX_WEEKS)
        parsed = [self._week(raw, f"weeks[{index}]") for index, raw in enumerate(weeks or [])]
        if rationale is None or weeks is None:
            return None
        return SeasonPlan(tuple(week for week in parsed if week is not None), rationale)

    def _week(self, data: object, path: str) -> PlanWeek | None:
        item = self._object(
            data, path, {"week_start", "minutes", "focus", "reason"}, {"key_sessions"}
        )
        if item is None:
            return None
        start = self._monday(item.get("week_start", _MISSING), f"{path}.week_start")
        minutes = self._minutes(item.get("minutes", _MISSING), f"{path}.minutes")
        focus = self._choice(item.get("focus", _MISSING), Focus, f"{path}.focus")
        reason = self._text(
            item.get("reason", _MISSING), f"{path}.reason", REASON_MAX, False, False
        )
        raw_sessions = self._list(
            item.get("key_sessions", []), f"{path}.key_sessions", MAX_KEY_SESSIONS
        )
        sessions = [
            self._session(raw, f"{path}.key_sessions[{index}]")
            for index, raw in enumerate(raw_sessions or [])
        ]
        if (
            start is None
            or minutes is None
            or focus is None
            or reason is None
            or raw_sessions is None
            or any(session is None for session in sessions)
        ):
            return None
        return PlanWeek(
            week_start=start,
            minutes=minutes,
            focus=focus,
            reason=reason,
            key_sessions=tuple(s for s in sessions if s is not None),
        )

    def _session(self, data: object, path: str) -> KeySession | None:
        item = self._object(data, path, {"sport", "kind", "minutes"}, {"detail"})
        if item is None:
            return None
        sport = self._choice(item.get("sport", _MISSING), Sport, f"{path}.sport")
        kind = self._choice(item.get("kind", _MISSING), SessionKind, f"{path}.kind")
        minutes = self._integer(
            item.get("minutes", _MISSING), f"{path}.minutes", 1, KEY_SESSION_MINUTES_MAX
        )
        detail = self._text(item.get("detail", ""), f"{path}.detail", DETAIL_MAX, True, False)
        if sport is None or kind is None or minutes is None or detail is None:
            return None
        return KeySession(sport, kind, minutes, detail)

    def _minutes(self, value: object, path: str) -> tuple[tuple[Sport, int], ...] | None:
        """The minutes of each sport: an object with a whole number for any of the sports."""
        if value is _MISSING:
            return None
        if not isinstance(value, dict):
            self.fail(path, "Must be an object.")
            return None
        found: dict[Sport, int] = {}
        usable = True
        for key, amount in value.items():
            if not isinstance(key, str) or key not in Sport:
                shown = key if isinstance(key, str) and _NAME.fullmatch(key) else "?"
                self.fail(f"{path}.{shown}", "Unknown sport.")
                usable = False
                continue
            number = self._integer(amount, f"{path}.{key}", 0, WEEK_MINUTES_MAX)
            if number is None:
                usable = False
            else:
                found[Sport(key)] = number
        if not usable:
            return None
        return tuple((sport, found[sport]) for sport in Sport if sport in found)
