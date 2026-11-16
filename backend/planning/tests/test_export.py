from datetime import date
from typing import Any

import pytest

from accounts.models import User
from athletes.models import ThresholdValue
from planning.export import EVENT_TYPE, START, to_event
from planning.schema import (
    Exercise,
    ExerciseEquipment,
    ExerciseRegion,
    Goal,
    Segment,
    SegmentKind,
    Slot,
    Sport,
    Workout,
    ZoneSystem,
)
from planning.targets import Targets

from .conftest import make_user

pytestmark = pytest.mark.django_db

DAY = date(2027, 7, 19)
ID = "paceforge-0190c0de-0000-7000-8000-000000000001"


@pytest.fixture
def targets() -> Targets:
    user: User = make_user("alice@example.com")
    for sport, metric, value in (
        ("ride", "ftp", 250),
        ("ride", "lthr", 160),
        ("run", "threshold_pace", 300),
        ("run", "lthr", 170),
    ):
        ThresholdValue.objects.create(
            owner=user, sport=sport, metric=metric, value=value, source="manual", basis="test"
        )
    return Targets(user)


def workout(**fields: object) -> Workout:
    values: dict[str, Any] = {
        "day": DAY,
        "sport": Sport.CYCLING,
        "title": "Endurance ride",
        "goal": Goal.ENDURANCE,
        "duration_minutes": 60,
    }
    values.update(fields)
    return Workout(**values)


class TestTheEvent:
    def test_the_fields_of_a_workout_event(self, targets: Targets) -> None:
        event = to_event(
            workout(zone_system=ZoneSystem.POWER, zone=2, slot=Slot.MORNING), ID, targets
        )

        assert event == {
            "category": "WORKOUT",
            "type": "Ride",
            "start_date_local": "2027-07-19T07:00:00",
            "name": "Endurance ride",
            "external_id": ID,
            "description": "- 1h 138-188w",
        }

    @pytest.mark.parametrize(
        ("slot", "start"),
        [
            (Slot.MORNING, "07:00:00"),
            (Slot.AFTERNOON, "12:00:00"),
            (Slot.EVENING, "18:00:00"),
            (None, "00:00:00"),
        ],
    )
    def test_the_time_of_day_gives_the_start_time(
        self, targets: Targets, slot: Slot | None, start: str
    ) -> None:
        event = to_event(workout(slot=slot), ID, targets)

        assert event["start_date_local"] == f"2027-07-19T{start}"

    def test_every_time_of_day_has_a_start_time_in_order(self) -> None:
        assert set(START) == set(Slot)
        assert START[Slot.MORNING] < START[Slot.AFTERNOON] < START[Slot.EVENING]

    @pytest.mark.parametrize(
        ("sport", "kind"),
        [
            (Sport.RUNNING, "Run"),
            (Sport.CYCLING, "Ride"),
            (Sport.SWIMMING, "Swim"),
            (Sport.STRENGTH, "WeightTraining"),
        ],
    )
    def test_the_type_follows_the_sport(self, targets: Targets, sport: Sport, kind: str) -> None:
        assert to_event(workout(sport=sport), ID, targets)["type"] == kind
        assert set(EVENT_TYPE) == set(Sport)

    def test_the_title_is_the_name_and_not_part_of_the_description(self, targets: Targets) -> None:
        event = to_event(workout(title="Sunday long ride"), ID, targets)

        assert event["name"] == "Sunday long ride"
        assert "Sunday" not in event["description"]


class TestTheSteps:
    def test_an_interval_workout_has_a_block_per_segment(self, targets: Targets) -> None:
        segments = (
            Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 1),
            Segment(SegmentKind.WORK, 300, 4, ZoneSystem.POWER, 5),
            Segment(SegmentKind.RECOVERY, 180, 4, ZoneSystem.POWER, 1),
            Segment(SegmentKind.COOLDOWN, 600, 1, ZoneSystem.POWER, 1),
        )

        event = to_event(workout(segments=segments, duration_minutes=62), ID, targets)

        assert event["description"] == (
            "Warmup\n- 10m 100-138w\n\n"
            "Work 4x\n- 5m 263-300w\n\n"
            "Recovery 4x\n- 3m 100-138w\n\n"
            "Cooldown\n- 10m 100-138w"
        )

    def test_a_workout_with_a_zone_and_no_segments_is_one_step(self, targets: Targets) -> None:
        event = to_event(
            workout(sport=Sport.RUNNING, zone_system=ZoneSystem.HEART_RATE, zone=2), ID, targets
        )

        assert event["description"] == "- 1h 145-153bpm"

    def test_pace_is_written_per_kilometre_with_the_faster_end_first(
        self, targets: Targets
    ) -> None:
        event = to_event(
            workout(
                sport=Sport.RUNNING,
                duration_minutes=30,
                zone_system=ZoneSystem.PACE,
                zone=3,
            ),
            ID,
            targets,
        )

        assert event["description"] == "- 30m 5:18-5:42/km Pace"

    def test_a_workout_without_a_zone_is_a_step_without_a_target(self, targets: Targets) -> None:
        assert to_event(workout(duration_minutes=45), ID, targets)["description"] == "- 45m"

    def test_a_zone_without_a_threshold_stays_in_the_text(self, targets: Targets) -> None:
        # The athlete has no FTP for running and no swim zones: nothing to compute.
        event = to_event(
            workout(sport=Sport.RUNNING, zone_system=ZoneSystem.POWER, zone=3), ID, targets
        )

        assert event["description"] == "Power zone 3\n- 1h"

    def test_a_repeat_of_a_zone_without_numbers_keeps_the_repeat(self, targets: Targets) -> None:
        segment = Segment(SegmentKind.WORK, 120, 3, ZoneSystem.POWER, 4)
        event = to_event(workout(sport=Sport.SWIMMING, segments=(segment,)), ID, targets)

        assert event["description"] == "Work Power zone 4 3x\n- 2m"

    def test_the_steps_add_up_to_the_time_of_the_segments(self, targets: Targets) -> None:
        segment = Segment(SegmentKind.WORK, 90, 2)

        assert to_event(workout(segments=(segment,)), ID, targets)["description"] == (
            "Work 2x\n- 1m30s"
        )

    @pytest.mark.parametrize(
        ("seconds", "text"),
        [(30, "30s"), (60, "1m"), (90, "1m30s"), (3600, "1h"), (5400, "1h30m"), (3661, "1h1m1s")],
    )
    def test_durations(self, targets: Targets, seconds: int, text: str) -> None:
        segment = Segment(SegmentKind.STEADY, seconds)

        assert to_event(workout(segments=(segment,)), ID, targets)["description"] == (
            f"Steady\n- {text}"
        )


class TestStrengthAndStretching:
    def test_strength_is_text_with_a_duration(self, targets: Targets) -> None:
        event = to_event(
            workout(sport=Sport.STRENGTH, goal=Goal.STRENGTH, duration_minutes=45), ID, targets
        )

        assert event["description"] == "Strength session, 45 min."
        assert event["moving_time"] == 2700
        assert "- " not in event["description"]

    def test_other_sports_have_no_moving_time_of_their_own(self, targets: Targets) -> None:
        assert "moving_time" not in to_event(workout(), ID, targets)

    def test_stretching_is_a_line_after_the_workout(self, targets: Targets) -> None:
        event = to_event(workout(stretching_minutes=10, duration_minutes=30), ID, targets)

        assert event["description"] == "- 30m\n\nStretching: 10 min after the workout."

    def test_no_stretching_says_nothing(self, targets: Targets) -> None:
        assert "Stretching" not in to_event(workout(), ID, targets)["description"]


def move(name: str = "Goblet squat", **fields: object) -> Exercise:
    values: dict[str, Any] = {
        "name": name,
        "region": ExerciseRegion.LEGS,
        "equipment": ExerciseEquipment.DUMBBELLS,
        "sets": 3,
        "reps": 10,
    }
    values.update(fields)
    return Exercise(**values)


def lifting(*exercises: Exercise, **fields: object) -> Workout:
    return workout(
        sport=Sport.STRENGTH,
        goal=Goal.STRENGTH,
        duration_minutes=45,
        exercises=exercises,
        **fields,
    )


class TestExercises:
    def test_every_exercise_is_a_numbered_line_after_the_duration(self, targets: Targets) -> None:
        event = to_event(
            lifting(
                move(rpe=7, rest_seconds=90),
                move("Plank", reps=None, seconds=45),
                move("Push-up", sets=4, reps=12, rest_seconds=60),
            ),
            ID,
            targets,
        )

        assert event["description"] == (
            "Strength session, 45 min.\n\n"
            "Exercises:\n"
            "1. Goblet squat: 3 sets of 10, RPE 7, rest 1:30\n"
            "2. Plank: 3 sets of 45 s\n"
            "3. Push-up: 4 sets of 12, rest 1:00"
        )
        assert event["moving_time"] == 2700

    def test_a_workout_without_exercises_is_as_before(self, targets: Targets) -> None:
        event = to_event(lifting(), ID, targets)

        assert event["description"] == "Strength session, 45 min."

    def test_the_notes_come_first_and_stretching_last(self, targets: Targets) -> None:
        event = to_event(lifting(move(), notes="Go slow", stretching_minutes=10), ID, targets)

        lines = event["description"].split("\n\n")
        assert lines[0] == "Note: Go slow"
        assert lines[1] == "Strength session, 45 min."
        assert lines[2].startswith("Exercises:")
        assert lines[3] == "Stretching: 10 min after the workout."

    @pytest.mark.parametrize(
        "name",
        ["- 5m 300w", "Squat 4x", "Squat 3 X", "\n- 10m", "a\n- b", "  - dash first", "5m 300w"],
    )
    def test_a_name_never_becomes_a_step_or_a_repeat(self, targets: Targets, name: str) -> None:
        event = to_event(lifting(move(name)), ID, targets)

        lines = event["description"].splitlines()
        exercise_lines = [line for line in lines if line[:1].isdigit() and ". " in line[:4]]
        assert len(exercise_lines) == 1
        assert not any(line.startswith("-") for line in lines)
        assert not exercise_lines[0].rstrip().lower().endswith(("1x", "2x", "3x", "4x", "5x"))

    def test_the_name_is_one_line_with_single_spaces(self, targets: Targets) -> None:
        event = to_event(lifting(move("Goblet   squat\nwide")), ID, targets)

        assert "1. Goblet squat wide: 3 sets of 10" in event["description"]

    def test_no_exercise_makes_the_event_a_step_workout(self, targets: Targets) -> None:
        event = to_event(lifting(move()), ID, targets)

        assert not any(line.startswith("-") for line in event["description"].splitlines())


class TestFreeText:
    def test_notes_come_first_as_one_line(self, targets: Targets) -> None:
        event = to_event(workout(notes="Keep it easy\nand relaxed"), ID, targets)

        assert event["description"] == "Note: Keep it easy and relaxed\n\n- 1h"

    @pytest.mark.parametrize(
        "notes",
        [
            "- 5m 300w",
            "5m 300w",
            "\n- 10m 100w",
            "easy\n- 10m 100w\nnow",
            "Main set 4x",
            "do it 4x",
            "do it 4 X",
            "  - dash first",
        ],
    )
    def test_notes_never_become_steps_or_repeats(self, targets: Targets, notes: str) -> None:
        event = to_event(workout(notes=notes), ID, targets)

        lines = event["description"].splitlines()
        # The note is the first line, it is a comment, and the only step is the real one.
        assert lines[0].startswith("Note: ")
        assert not lines[0].startswith("-")
        assert not lines[0].rstrip().lower().endswith(("1x", "2x", "3x", "4x", "5x"))
        assert [line for line in lines if line.startswith("-")] == ["- 1h"]
        assert lines[1] == ""

    def test_the_text_of_the_notes_is_kept(self, targets: Targets) -> None:
        event = to_event(workout(notes="Legs feel heavy – stay in zone 2"), ID, targets)

        assert "Legs feel heavy – stay in zone 2" in event["description"]

    def test_no_notes_no_note_line(self, targets: Targets) -> None:
        assert "Note" not in to_event(workout(notes=""), ID, targets)["description"]
