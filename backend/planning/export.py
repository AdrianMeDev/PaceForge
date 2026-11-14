"""A planned workout as an event of the Intervals.icu calendar.

Pure: no database and no network. The description is written in the workout syntax of
Intervals.icu, which parses it into steps (``- 10m 120-165w``), repeat blocks (``Work 4x`` followed
by the steps) and a planned load. What the syntax makes of a line:

- a line that starts with ``-`` is a step, a line that ends in ``<n>x`` starts a repeat block, any
  other line is a heading or a comment, and a blank line ends a block;
- targets are absolute: ``120-165w``, ``145-152bpm`` and ``5:12-5:41/km Pace``.

The text of the coach (``notes``) must never become a step or a repeat block, so it is written as
one line that starts with a word and does not end in ``<n>x``. Titles go into the name of the event,
which is not parsed.

How a segment is written: a segment done several times in a row (``repeat``) is one block, so the
steps add up to the same time as in PaceForge. Time of day only gives an order in PaceForge; the
event needs a start time, so the three times of day have fixed start times.
"""

import re
from datetime import time
from typing import Any

from .schema import Segment, SegmentKind, Slot, Sport, Workout, ZoneSystem
from .targets import Target, Targets

# The type of the event in Intervals.icu for each sport.
EVENT_TYPE = {
    Sport.RUNNING: "Run",
    Sport.CYCLING: "Ride",
    Sport.SWIMMING: "Swim",
    Sport.STRENGTH: "WeightTraining",
}

# When the three times of day start; a workout without one is an all-day event.
START = {Slot.MORNING: time(7), Slot.AFTERNOON: time(12), Slot.EVENING: time(18)}

HEADINGS = {
    SegmentKind.WARMUP: "Warmup",
    SegmentKind.STEADY: "Steady",
    SegmentKind.WORK: "Work",
    SegmentKind.RECOVERY: "Recovery",
    SegmentKind.COOLDOWN: "Cooldown",
}

ZONE_NAMES = {
    ZoneSystem.POWER: "Power",
    ZoneSystem.HEART_RATE: "Heart rate",
    ZoneSystem.PACE: "Pace",
}

_ENDS_IN_REPEAT = re.compile(r"\d\s*x$", re.IGNORECASE)


def to_event(workout: Workout, external_id: str, targets: Targets) -> dict[str, Any]:
    """The event for ``workout``, ready to send to ``/athlete/0/events/bulk?upsert=true``."""
    when = START.get(workout.slot) if workout.slot else None
    clock = when or time(0)
    event: dict[str, Any] = {
        "category": "WORKOUT",
        "type": EVENT_TYPE[workout.sport],
        "start_date_local": f"{workout.day.isoformat()}T{clock.isoformat(timespec='seconds')}",
        "name": workout.title,
        "external_id": external_id,
        "description": description(workout, targets),
    }
    if workout.sport is Sport.STRENGTH:
        # Strength has no steps to add up, so the duration is given as it is.
        event["moving_time"] = workout.duration_minutes * 60
    return event


def description(workout: Workout, targets: Targets) -> str:
    blocks: list[str] = []
    if workout.notes:
        blocks.append(_line("Note: ", workout.notes))
    if workout.sport is Sport.STRENGTH:
        blocks.append(f"Strength session, {workout.duration_minutes} min.")
    elif workout.segments:
        blocks.extend(_segment(workout.sport, segment, targets) for segment in workout.segments)
    else:
        blocks.append(
            _steps(
                workout.sport,
                workout.zone_system,
                workout.zone,
                workout.duration_minutes * 60,
                1,
                None,
                targets,
            )
        )
    if workout.stretching_minutes:
        blocks.append(f"Stretching: {workout.stretching_minutes} min after the workout.")
    return "\n\n".join(blocks)


def _segment(sport: Sport, segment: Segment, targets: Targets) -> str:
    return _steps(
        sport,
        segment.zone_system,
        segment.zone,
        segment.seconds,
        segment.repeat,
        HEADINGS[segment.kind],
        targets,
    )


def _steps(
    sport: Sport,
    system: ZoneSystem | None,
    zone: int | None,
    seconds: int,
    repeat: int,
    heading: str | None,
    targets: Targets,
) -> str:
    """One block: a heading (with ``<n>x`` for a repeat) and one step."""
    found = None if system is None or zone is None else targets.target(sport, system, zone)
    lines = []
    # A zone without numbers (no threshold known) stays in the text, so it is not lost.
    named = f"{ZONE_NAMES[system]} zone {zone}" if system and zone and found is None else None
    title = " ".join(part for part in (heading, named) if part)
    if repeat > 1:
        lines.append(f"{title or 'Repeat'} {repeat}x".strip())
    elif title:
        lines.append(title)
    step = f"- {_duration(seconds)}"
    if found is not None:
        step += f" {_target(found)}"
    lines.append(step)
    return "\n".join(lines)


def _target(target: Target) -> str:
    if target.unit == "s/km":
        return f"{_pace(target.low)}-{_pace(target.high)}/km Pace"
    return f"{target.low}-{target.high}{'w' if target.unit == 'W' else target.unit}"


def _pace(seconds_per_km: int) -> str:
    return f"{seconds_per_km // 60}:{seconds_per_km % 60:02d}"


def _duration(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return "".join(
        f"{amount}{unit}" for amount, unit in ((hours, "h"), (minutes, "m"), (secs, "s")) if amount
    )


def _line(prefix: str, text: str) -> str:
    """Free text as a single comment line: the lines of ``text`` are joined (so none can start with
    ``-``) and the prefix is a word, so Intervals.icu never reads it as a step. A text that ends in
    ``4x`` would start a repeat block, so it gets a full stop."""
    line = prefix + " ".join(text.split())
    return line + "." if _ENDS_IN_REPEAT.search(line) else line
