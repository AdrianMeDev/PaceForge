"""The format of a training week, and the one strict parser that reads it.

A week plan arrives as JSON (the coach's answer, later perhaps an API request). Nothing is taken on
trust: the parser accepts exactly the format below, reports *every* problem at once by its path
(``workouts[2].segments[0].seconds``) and never repeats a value of the input in a message, so that
an answer of the model cannot smuggle text into logs or pages through an error. Only fields that
are a key of the format are named, and only if they look like a name.

This module is pure: no database, no Django. The limits here are the single source for the models.

```
{
  "week_start": "2027-07-12",                  # a Monday
  "rationale": "Why this week looks like this",   # optional
  "workouts": [
    {
      "day": "2027-07-13", "sport": "cycling", "title": "Endurance ride", "goal": "endurance",
      "duration_minutes": 90,
      "zone_system": "power", "zone": 2,           # optional pair: the target of the whole session
      "notes": "",                                  # optional
      "slot": "morning",                            # optional: morning, afternoon or evening
      "stretching_minutes": 10,                     # optional: added to the session, no session
      "segments": [                                 # optional: the interval structure
        {"kind": "warmup", "seconds": 600, "zone_system": "power", "zone": 1},
        {"kind": "work", "seconds": 300, "repeat": 4, "zone_system": "power", "zone": 4}
      ]
    }
  ]
}
```
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

TITLE_MAX = 100
NOTES_MAX = 500
RATIONALE_MAX = 1000
DURATION_MAX = 1440  # minutes: a day
MAX_WORKOUTS = 28
MAX_SEGMENTS = 40
SEGMENT_SECONDS_MAX = 86_400
REPEAT_MAX = 50
STRETCHING_MAX = 60  # minutes of stretching added to one workout
# Zones per zone system: the seven power levels, five heart rate zones, five pace zones. The zones
# themselves are those of ``athletes.zones`` (a test keeps the two in step).
ZONE_COUNT = {"power": 7, "heart_rate": 5, "pace": 5}


class Sport(StrEnum):
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"
    STRENGTH = "strength"


class Goal(StrEnum):
    RECOVERY = "recovery"
    ENDURANCE = "endurance"
    TEMPO = "tempo"
    THRESHOLD = "threshold"
    VO2MAX = "vo2max"
    STRENGTH = "strength"
    OTHER = "other"


class ZoneSystem(StrEnum):
    POWER = "power"
    HEART_RATE = "heart_rate"
    PACE = "pace"


class Slot(StrEnum):
    """When on the day a workout is done. Only the order is meant: a morning workout comes before
    an afternoon one, there is no clock time."""

    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


class SegmentKind(StrEnum):
    WARMUP = "warmup"
    STEADY = "steady"
    WORK = "work"
    RECOVERY = "recovery"
    COOLDOWN = "cooldown"


@dataclass(frozen=True)
class Segment:
    """One part of a workout, done ``repeat`` times in a row."""

    kind: SegmentKind
    seconds: int
    repeat: int = 1
    zone_system: ZoneSystem | None = None
    zone: int | None = None


@dataclass(frozen=True)
class Workout:
    day: date
    sport: Sport
    title: str
    goal: Goal
    duration_minutes: int
    segments: tuple[Segment, ...] = ()
    # The target of the whole session; both are set or both are ``None``.
    zone_system: ZoneSystem | None = None
    zone: int | None = None
    notes: str = ""
    # When on the day; ``None``: not said.
    slot: Slot | None = None
    # Stretching added to this workout, in minutes (0: none). It is never a workout of its own and
    # does not count as training time.
    stretching_minutes: int = 0


@dataclass(frozen=True)
class WeekPlan:
    week_start: date
    workouts: tuple[Workout, ...] = ()
    rationale: str = ""


@dataclass(frozen=True)
class Problem:
    """What is wrong and where. ``path`` is empty for the plan as a whole."""

    path: str
    message: str


class PlanFormatError(Exception):
    """The input is not a week plan. ``problems`` has every problem found."""

    def __init__(self, problems: tuple[Problem, ...]) -> None:
        super().__init__(f"The plan has {len(problems)} problem(s).")
        self.problems = problems


# A required field that is not there. It has been reported once by ``_object``; the checks of its
# value stay silent so that one mistake is one problem.
_MISSING: Any = object()
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_NAME = re.compile(r"[A-Za-z0-9_]{1,40}")
# Line and paragraph separators and the controls that reorder text on screen, written as escapes
# on purpose: these characters are invisible in an editor.
_FORBIDDEN = frozenset(
    "\u2028\u2029"  # line and paragraph separator
    "\u202a\u202b\u202c\u202d\u202e"  # embedding and override of the direction of text
    "\u2066\u2067\u2068\u2069"  # isolates
)


def parse_week_plan(data: object) -> WeekPlan:
    """The plan in ``data``, or a ``PlanFormatError`` with all problems."""
    reader = _Reader()
    plan = reader.plan(data)
    if reader.problems or plan is None:
        raise PlanFormatError(tuple(reader.problems))
    return plan


def to_json(plan: WeekPlan) -> dict[str, Any]:
    """The plan in the format above, with every field written out. ``parse_week_plan`` reads it
    back into an equal plan."""
    return {
        "week_start": plan.week_start.isoformat(),
        "rationale": plan.rationale,
        "workouts": [workout_to_json(workout) for workout in plan.workouts],
    }


def workout_to_json(workout: Workout) -> dict[str, Any]:
    """One workout in the format above, with every field written out."""
    return {
        "day": workout.day.isoformat(),
        "sport": workout.sport.value,
        "title": workout.title,
        "goal": workout.goal.value,
        "duration_minutes": workout.duration_minutes,
        "zone_system": workout.zone_system.value if workout.zone_system else None,
        "zone": workout.zone,
        "notes": workout.notes,
        "slot": workout.slot.value if workout.slot else None,
        "stretching_minutes": workout.stretching_minutes,
        "segments": [
            {
                "kind": segment.kind.value,
                "seconds": segment.seconds,
                "repeat": segment.repeat,
                "zone_system": segment.zone_system.value if segment.zone_system else None,
                "zone": segment.zone,
            }
            for segment in workout.segments
        ],
    }


class _Reader:
    def __init__(self) -> None:
        self.problems: list[Problem] = []

    def fail(self, path: str, message: str) -> None:
        self.problems.append(Problem(path, message))

    # --- the plan

    def plan(self, data: object) -> WeekPlan | None:
        item = self._object(data, "", {"week_start", "workouts"}, {"rationale"})
        if item is None:
            return None
        week_start = self._monday(item.get("week_start", _MISSING), "week_start")
        rationale = self._text(item.get("rationale", ""), "rationale", RATIONALE_MAX, True, True)
        workouts = self._list(item.get("workouts", _MISSING), "workouts", MAX_WORKOUTS)
        parsed = [
            self._workout(raw, f"workouts[{index}]") for index, raw in enumerate(workouts or [])
        ]
        if week_start is None or rationale is None or workouts is None:
            return None
        return WeekPlan(week_start, tuple(w for w in parsed if w is not None), rationale)

    def _workout(self, data: object, path: str) -> Workout | None:
        item = self._object(
            data,
            path,
            {"day", "sport", "title", "goal", "duration_minutes"},
            {"zone_system", "zone", "notes", "segments", "slot", "stretching_minutes"},
        )
        if item is None:
            return None
        day = self._day(item.get("day", _MISSING), f"{path}.day")
        sport = self._choice(item.get("sport", _MISSING), Sport, f"{path}.sport")
        title = self._text(item.get("title", _MISSING), f"{path}.title", TITLE_MAX, False, False)
        goal = self._choice(item.get("goal", _MISSING), Goal, f"{path}.goal")
        minutes = self._integer(
            item.get("duration_minutes", _MISSING), f"{path}.duration_minutes", 1, DURATION_MAX
        )
        notes = self._text(item.get("notes", ""), f"{path}.notes", NOTES_MAX, True, True)
        raw_slot = item.get("slot")
        slot = None if raw_slot is None else self._choice(raw_slot, Slot, f"{path}.slot")
        stretching = self._integer(
            item.get("stretching_minutes", 0), f"{path}.stretching_minutes", 0, STRETCHING_MAX
        )
        system, zone, zone_ok = self._zone(item, path)
        raw_segments = self._list(item.get("segments", []), f"{path}.segments", MAX_SEGMENTS)
        segments = [
            self._segment(raw, f"{path}.segments[{index}]")
            for index, raw in enumerate(raw_segments or [])
        ]
        if (
            day is None
            or sport is None
            or title is None
            or goal is None
            or minutes is None
            or notes is None
            or (raw_slot is not None and slot is None)
            or stretching is None
            or not zone_ok
            or raw_segments is None
            or any(segment is None for segment in segments)
        ):
            return None
        return Workout(
            day=day,
            sport=sport,
            title=title,
            goal=goal,
            duration_minutes=minutes,
            segments=tuple(s for s in segments if s is not None),
            zone_system=system,
            zone=zone,
            notes=notes,
            slot=slot,
            stretching_minutes=stretching,
        )

    def _segment(self, data: object, path: str) -> Segment | None:
        item = self._object(data, path, {"kind", "seconds"}, {"repeat", "zone_system", "zone"})
        if item is None:
            return None
        kind = self._choice(item.get("kind", _MISSING), SegmentKind, f"{path}.kind")
        seconds = self._integer(
            item.get("seconds", _MISSING), f"{path}.seconds", 1, SEGMENT_SECONDS_MAX
        )
        repeat = self._integer(item.get("repeat", 1), f"{path}.repeat", 1, REPEAT_MAX)
        system, zone, zone_ok = self._zone(item, path)
        if kind is None or seconds is None or repeat is None or not zone_ok:
            return None
        return Segment(kind, seconds, repeat, system, zone)

    def _zone(self, item: dict[str, Any], path: str) -> tuple[ZoneSystem | None, int | None, bool]:
        """The zone system and zone of a workout or segment: both or neither, and the zone must
        exist in its system."""
        raw_system, raw_zone = item.get("zone_system"), item.get("zone")
        if raw_system is None and raw_zone is None:
            return None, None, True
        if raw_system is None or raw_zone is None:
            self.fail(f"{path}.zone_system", "A zone system and a zone go together.")
            return None, None, False
        system = self._choice(raw_system, ZoneSystem, f"{path}.zone_system")
        if system is None:
            self._integer(raw_zone, f"{path}.zone", 1, max(ZONE_COUNT.values()))
            return None, None, False
        zone = self._integer(raw_zone, f"{path}.zone", 1, ZONE_COUNT[system.value])
        return system, zone, zone is not None

    # --- the building blocks

    def _object(
        self, value: object, path: str, required: set[str], optional: set[str]
    ) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            self.fail(path, "Must be an object.")
            return None
        for name in sorted(required - value.keys()):
            self.fail(_join(path, name), "Is required.")
        for key in value:
            if key not in required and key not in optional:
                shown = key if isinstance(key, str) and _NAME.fullmatch(key) else "?"
                self.fail(_join(path, shown), "Unknown field.")
        return value

    def _list(self, value: object, path: str, limit: int) -> list[Any] | None:
        if value is _MISSING:
            return None
        if not isinstance(value, list):
            self.fail(path, "Must be a list.")
            return None
        if len(value) > limit:
            self.fail(path, f"Must have at most {limit} entries.")
            return None
        return value

    def _text(
        self, value: object, path: str, limit: int, blank: bool, multiline: bool
    ) -> str | None:
        if value is _MISSING:
            return None
        if not isinstance(value, str):
            self.fail(path, "Must be text.")
            return None
        text = value.strip()
        if not text and not blank:
            self.fail(path, "Must not be empty.")
            return None
        if len(text) > limit:
            self.fail(path, f"Must have at most {limit} characters.")
            return None
        if any(_forbidden(char, multiline) for char in text):
            self.fail(path, "Must not contain control characters.")
            return None
        return text

    def _integer(self, value: object, path: str, low: int, high: int) -> int | None:
        if value is _MISSING:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            self.fail(path, "Must be a whole number.")
            return None
        if not low <= value <= high:
            self.fail(path, f"Must be between {low} and {high}.")
            return None
        return value

    def _choice[E: StrEnum](self, value: object, options: type[E], path: str) -> E | None:
        if value is _MISSING:
            return None
        try:
            if isinstance(value, str):
                return options(value)
        except ValueError:
            pass
        names = ", ".join(option.value for option in options)
        self.fail(path, f"Must be one of: {names}.")
        return None

    def _day(self, value: object, path: str) -> date | None:
        if value is _MISSING:
            return None
        if not isinstance(value, str) or not _DATE.fullmatch(value):
            self.fail(path, "Must be a date like 2027-07-12.")
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            self.fail(path, "Must be a date like 2027-07-12.")
            return None

    def _monday(self, value: object, path: str) -> date | None:
        day = self._day(value, path)
        if day is not None and day.weekday() != 0:
            self.fail(path, "A week starts on a Monday.")
            return None
        return day


def _join(path: str, name: str) -> str:
    return f"{path}.{name}" if path else name


def _forbidden(char: str, multiline: bool) -> bool:
    if char in _FORBIDDEN:
        return True
    if char == "\n" and multiline:
        return False
    return unicodedata.category(char) == "Cc"


# The order of the times of day within a day; a workout without a time comes after those with one.
_SLOT_ORDER = {Slot.MORNING: 0, Slot.AFTERNOON: 1, Slot.EVENING: 2}


def order_key(workout: Workout) -> tuple[date, int]:
    """Where a workout stands in the week: by day, then by time of day (workouts without one last).
    Sorting is stable, so workouts with the same key keep the order they were given in."""
    rank = _SLOT_ORDER[workout.slot] if workout.slot else len(_SLOT_ORDER)
    return workout.day, rank
