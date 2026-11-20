import ast
import copy
import json
from dataclasses import FrozenInstanceError
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from planning import schema
from planning.schema import (
    Exercise,
    ExerciseEquipment,
    ExerciseRegion,
    Goal,
    PlanFormatError,
    Problem,
    Segment,
    SegmentKind,
    Slot,
    Sport,
    WeekPlan,
    Workout,
    ZoneSystem,
    order_key,
    parse_week_plan,
    to_json,
)

MONDAY = date(2027, 7, 12)
assert MONDAY.weekday() == 0


def segment(**fields: Any) -> dict[str, Any]:
    return {"kind": "work", "seconds": 300, **fields}


def workout(**fields: Any) -> dict[str, Any]:
    return {
        "day": "2027-07-13",
        "sport": "cycling",
        "title": "Endurance ride",
        "goal": "endurance",
        "duration_minutes": 90,
        **fields,
    }


def exercise(**fields: Any) -> dict[str, Any]:
    return {
        "name": "Goblet squat",
        "region": "legs",
        "equipment": "dumbbells",
        "sets": 3,
        "reps": 10,
        **fields,
    }


def with_exercise(**fields: Any) -> dict[str, Any]:
    return plan(
        workouts=[workout(sport="strength", goal="strength", exercises=[exercise(**fields)])]
    )


def plan(**fields: Any) -> dict[str, Any]:
    return {"week_start": "2027-07-12", "workouts": [workout()], **fields}


def problems_of(data: object) -> list[Problem]:
    with pytest.raises(PlanFormatError) as raised:
        parse_week_plan(data)
    return list(raised.value.problems)


def paths_of(data: object) -> list[str]:
    return [problem.path for problem in problems_of(data)]


def with_workout(**fields: Any) -> dict[str, Any]:
    return plan(workouts=[workout(**fields)])


def with_segment(**fields: Any) -> dict[str, Any]:
    return with_workout(segments=[segment(**fields)])


class TestAValidPlan:
    def test_the_smallest_plan_has_defaults(self) -> None:
        result = parse_week_plan({"week_start": "2027-07-12", "workouts": []})

        assert result == WeekPlan(MONDAY, (), "")

    def test_a_week_without_workouts_is_a_valid_rest_week(self) -> None:
        assert parse_week_plan(plan(workouts=[])).workouts == ()

    def test_a_workout_gets_its_defaults(self) -> None:
        (result,) = parse_week_plan(plan()).workouts

        assert result == Workout(
            day=MONDAY + timedelta(days=1),
            sport=Sport.CYCLING,
            title="Endurance ride",
            goal=Goal.ENDURANCE,
            duration_minutes=90,
        )
        assert (result.segments, result.zone_system, result.zone, result.notes) == (
            (),
            None,
            None,
            "",
        )

    def test_a_full_plan_is_read_completely(self) -> None:
        data = plan(
            rationale="Build the base.\nKeep it easy.",
            workouts=[
                workout(
                    zone_system="power",
                    zone=2,
                    notes="Stay relaxed",
                    segments=[
                        segment(kind="warmup", seconds=600, zone_system="power", zone=1),
                        segment(repeat=4, zone_system="power", zone=4),
                        segment(kind="recovery", seconds=120),
                    ],
                ),
                workout(
                    day="2027-07-15", sport="running", goal="tempo", zone_system="pace", zone=3
                ),
            ],
        )

        result = parse_week_plan(data)

        assert result.rationale == "Build the base.\nKeep it easy."
        first, second = result.workouts
        assert (first.zone_system, first.zone, first.notes) == (ZoneSystem.POWER, 2, "Stay relaxed")
        assert first.segments == (
            Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 1),
            Segment(SegmentKind.WORK, 300, 4, ZoneSystem.POWER, 4),
            Segment(SegmentKind.RECOVERY, 120, 1, None, None),
        )
        assert (second.sport, second.zone_system, second.zone) == (
            Sport.RUNNING,
            ZoneSystem.PACE,
            3,
        )

    def test_the_order_of_the_workouts_is_kept(self) -> None:
        days = ["2027-07-15", "2027-07-13", "2027-07-13", "2027-07-18"]

        result = parse_week_plan(plan(workouts=[workout(day=day) for day in days]))

        assert [w.day.isoformat() for w in result.workouts] == days

    def test_explicit_nulls_for_the_optional_pairs_are_the_same_as_leaving_them_out(self) -> None:
        a = parse_week_plan(plan(workouts=[workout(zone_system=None, zone=None)]))
        b = parse_week_plan(plan())

        assert a == b

    def test_text_is_trimmed(self) -> None:
        result = parse_week_plan(
            plan(rationale="  why  ", workouts=[workout(title="  Ride  ", notes="  n  ")])
        )

        assert result.rationale == "why"
        assert (result.workouts[0].title, result.workouts[0].notes) == ("Ride", "n")

    def test_the_result_cannot_be_changed(self) -> None:
        result = parse_week_plan(plan())

        with pytest.raises(FrozenInstanceError):
            result.week_start = MONDAY  # type: ignore[misc]
        assert isinstance(result.workouts, tuple)
        assert isinstance(result.workouts[0].segments, tuple)

    def test_the_input_is_not_changed(self) -> None:
        data = plan(workouts=[workout(segments=[segment()])])
        before = copy.deepcopy(data)

        parse_week_plan(data)

        assert data == before

    def test_emoji_and_umlauts_are_fine(self) -> None:
        result = parse_week_plan(plan(workouts=[workout(title="Läufer 🏃‍♂️ Übung")]))

        assert result.workouts[0].title == "Läufer 🏃‍♂️ Übung"


class TestTheWayBack:
    def test_a_plan_survives_the_round_trip(self) -> None:
        original = parse_week_plan(
            plan(
                rationale="Why",
                workouts=[
                    workout(
                        zone_system="heart_rate",
                        zone=2,
                        notes="Note",
                        segments=[segment(repeat=3, zone_system="heart_rate", zone=4)],
                    ),
                    workout(day="2027-07-14", sport="strength", goal="strength"),
                ],
            )
        )

        assert parse_week_plan(to_json(original)) == original

    def test_the_json_is_plain_data(self) -> None:
        original = parse_week_plan(plan(workouts=[workout(segments=[segment()])]))

        text = json.dumps(to_json(original))

        assert json.loads(text) == to_json(original)

    def test_every_field_is_written_out(self) -> None:
        original = parse_week_plan(plan(workouts=[workout(segments=[segment()])]))

        assert to_json(original) == {
            "week_start": "2027-07-12",
            "rationale": "",
            "workouts": [
                {
                    "day": "2027-07-13",
                    "sport": "cycling",
                    "title": "Endurance ride",
                    "goal": "endurance",
                    "duration_minutes": 90,
                    "zone_system": None,
                    "zone": None,
                    "notes": "",
                    "slot": None,
                    "stretching_minutes": 0,
                    "segments": [
                        {
                            "kind": "work",
                            "seconds": 300,
                            "repeat": 1,
                            "zone_system": None,
                            "zone": None,
                        }
                    ],
                    "exercises": [],
                }
            ],
        }


class TestThePlanAsAWhole:
    @pytest.mark.parametrize("data", [[], "plan", 5, None, True, 1.5])
    def test_something_that_is_no_object_is_refused(self, data: object) -> None:
        assert problems_of(data) == [Problem("", "Must be an object.")]

    @pytest.mark.parametrize("missing", ["week_start", "workouts"])
    def test_a_missing_field_is_named(self, missing: str) -> None:
        data = plan()
        del data[missing]

        assert problems_of(data) == [Problem(missing, "Is required.")]

    def test_an_unknown_field_is_refused(self) -> None:
        assert problems_of(plan(colour="red")) == [Problem("", "Unknown field.")]

    @pytest.mark.parametrize(
        "value", [5, None, ["2027-07-12"], True, "", "2027-7-12", "20270712", "12.07.2027"]
    )
    def test_a_week_start_that_is_no_date_is_refused(self, value: object) -> None:
        assert problems_of(plan(week_start=value)) == [
            Problem("week_start", "Must be a date like 2027-07-12.")
        ]

    @pytest.mark.parametrize(
        "value",
        [
            "2027-02-30",
            "2027-13-01",
            "2027-00-10",
            "2027-07-12T00:00:00",
            " 2027-07-12",
            "2027-07-12 ",
        ],
    )
    def test_dates_that_do_not_exist_or_carry_more_are_refused(self, value: str) -> None:
        assert paths_of(plan(week_start=value)) == ["week_start"]

    @pytest.mark.parametrize("offset", [1, 2, 3, 4, 5, 6])
    def test_a_week_starts_on_a_monday(self, offset: int) -> None:
        day = (MONDAY + timedelta(days=offset)).isoformat()

        assert problems_of(plan(week_start=day)) == [
            Problem("week_start", "A week starts on a Monday.")
        ]

    def test_any_monday_is_fine(self) -> None:
        assert parse_week_plan(plan(week_start="2028-02-28")).week_start == date(2028, 2, 28)

    def test_the_rationale_is_text_of_at_most_1000_characters(self) -> None:
        assert parse_week_plan(plan(rationale="r" * 1000)).rationale == "r" * 1000
        assert problems_of(plan(rationale="r" * 1001)) == [
            Problem("rationale", "Must have at most 1000 characters.")
        ]
        assert problems_of(plan(rationale=5)) == [Problem("rationale", "Must be text.")]
        assert problems_of(plan(rationale=None)) == [Problem("rationale", "Must be text.")]

    def test_the_rationale_may_have_line_breaks_but_no_other_controls(self) -> None:
        assert parse_week_plan(plan(rationale="a\nb")).rationale == "a\nb"
        bad_values = [
            "a\x00b",
            "a\rb",
            "a\tb",
            "a\x1bb",
            "a\x7fb",
            "a\u2028b",
            "a\u2029b",
            "a\u061cb",
            "a\u200eb",
            "a\u200fb",
            "a\u202ab",
            "a\u202bb",
            "a\u202cb",
            "a\u202db",
            "a\u202eb",
            "a\u2066b",
            "a\u2067b",
            "a\u2068b",
            "a\u2069b",
        ]
        for bad in bad_values:
            assert paths_of(plan(rationale=bad)) == ["rationale"], repr(bad)

    @pytest.mark.parametrize("value", [None, {}, "x", 5, {"0": {}}])
    def test_workouts_must_be_a_list(self, value: object) -> None:
        assert problems_of(plan(workouts=value)) == [Problem("workouts", "Must be a list.")]

    def test_a_week_holds_at_most_28_workouts(self) -> None:
        assert len(parse_week_plan(plan(workouts=[workout()] * 28)).workouts) == 28
        assert problems_of(plan(workouts=[workout()] * 29)) == [
            Problem("workouts", "Must have at most 28 entries.")
        ]

    def test_a_list_that_is_too_long_is_not_read_entry_by_entry(self) -> None:
        # twenty-nine broken entries give one problem, not twenty-nine
        assert len(problems_of(plan(workouts=[{}] * 29))) == 1


class TestAWorkout:
    @pytest.mark.parametrize("value", [None, [], "x", 5])
    def test_a_workout_must_be_an_object(self, value: object) -> None:
        assert problems_of(plan(workouts=[value])) == [Problem("workouts[0]", "Must be an object.")]

    @pytest.mark.parametrize("missing", ["day", "sport", "title", "goal", "duration_minutes"])
    def test_a_missing_field_is_named(self, missing: str) -> None:
        data = workout()
        del data[missing]

        assert problems_of(plan(workouts=[data])) == [
            Problem(f"workouts[0].{missing}", "Is required.")
        ]

    def test_an_unknown_field_is_refused(self) -> None:
        assert problems_of(with_workout(colour="red")) == [Problem("workouts[0]", "Unknown field.")]

    @pytest.mark.parametrize("sport", ["running", "cycling", "swimming", "strength"])
    def test_every_sport_is_known(self, sport: str) -> None:
        assert parse_week_plan(with_workout(sport=sport)).workouts[0].sport == sport

    @pytest.mark.parametrize(
        "sport", ["Running", "rowing", "", " running", 5, None, ["running"], True]
    )
    def test_another_sport_is_refused(self, sport: object) -> None:
        assert problems_of(with_workout(sport=sport)) == [
            Problem("workouts[0].sport", "Must be one of: running, cycling, swimming, strength.")
        ]

    @pytest.mark.parametrize(
        "goal", ["recovery", "endurance", "tempo", "threshold", "vo2max", "strength", "other"]
    )
    def test_every_goal_is_known(self, goal: str) -> None:
        assert parse_week_plan(with_workout(goal=goal)).workouts[0].goal == goal

    @pytest.mark.parametrize("goal", ["fun", "VO2MAX", "", 5, None])
    def test_another_goal_is_refused(self, goal: object) -> None:
        assert paths_of(with_workout(goal=goal)) == ["workouts[0].goal"]

    def test_the_limit_counts_the_trimmed_text(self) -> None:
        padded = "  " + "t" * 100 + "  "

        assert parse_week_plan(with_workout(title=padded)).workouts[0].title == "t" * 100
        assert (
            parse_week_plan(with_workout(notes=padded.replace("t", "n"))).workouts[0].notes
            == "n" * 100
        )

    def test_a_title_has_one_line_of_at_most_100_characters(self) -> None:
        assert parse_week_plan(with_workout(title="t" * 100)).workouts[0].title == "t" * 100
        assert problems_of(with_workout(title="t" * 101)) == [
            Problem("workouts[0].title", "Must have at most 100 characters.")
        ]

    @pytest.mark.parametrize("title", ["", "   ", "\n"])
    def test_a_title_cannot_be_empty(self, title: str) -> None:
        assert problems_of(with_workout(title=title)) == [
            Problem("workouts[0].title", "Must not be empty.")
        ]

    @pytest.mark.parametrize("title", [5, None, ["x"], True])
    def test_a_title_is_text(self, title: object) -> None:
        assert problems_of(with_workout(title=title)) == [
            Problem("workouts[0].title", "Must be text.")
        ]

    @pytest.mark.parametrize(
        "title",
        [
            "a\nb",
            "a\tb",
            "a\x00b",
            "a\u2028b",
            "a\u2029b",
            "a\u061cb",
            "a\u200eb",
            "a\u200fb",
            "a\u202ab",
            "a\u202bb",
            "a\u202cb",
            "a\u202db",
            "a\u202eb",
            "a\u2066b",
            "a\u2067b",
            "a\u2068b",
            "a\u2069b",
        ],
    )
    def test_a_title_has_no_line_breaks_or_controls(self, title: str) -> None:
        assert problems_of(with_workout(title=title)) == [
            Problem("workouts[0].title", "Must not contain control characters.")
        ]

    def test_notes_may_have_line_breaks_and_500_characters(self) -> None:
        assert parse_week_plan(with_workout(notes="a\nb")).workouts[0].notes == "a\nb"
        assert parse_week_plan(with_workout(notes="n" * 500)).workouts[0].notes == "n" * 500
        assert paths_of(with_workout(notes="n" * 501)) == ["workouts[0].notes"]
        assert paths_of(with_workout(notes=5)) == ["workouts[0].notes"]
        bad_notes = [
            "a\x00b",
            "a\u2028b",
            "a\u2029b",
            "a\u061cb",
            "a\u200eb",
            "a\u200fb",
            "a\u202ab",
            "a\u202bb",
            "a\u202cb",
            "a\u202db",
            "a\u202eb",
            "a\u2066b",
            "a\u2067b",
            "a\u2068b",
            "a\u2069b",
        ]
        for bad in bad_notes:
            assert problems_of(with_workout(notes=bad)) == [
                Problem("workouts[0].notes", "Must not contain control characters.")
            ], repr(bad)

    @pytest.mark.parametrize("day", ["2027-07-13", "2027-07-12", "2027-07-18", "2027-12-31"])
    def test_a_day_is_any_date(self, day: str) -> None:
        # whether it lies in the week is a matter of the checks, not of the format
        assert parse_week_plan(with_workout(day=day)).workouts[0].day == date.fromisoformat(day)

    @pytest.mark.parametrize("day", ["2027-02-30", "13.07.2027", "", 5, None, "2027-07-13T10:00"])
    def test_a_day_that_is_no_date_is_refused(self, day: object) -> None:
        assert problems_of(with_workout(day=day)) == [
            Problem("workouts[0].day", "Must be a date like 2027-07-12.")
        ]

    @pytest.mark.parametrize("minutes", [1, 90, 1440])
    def test_a_duration_between_a_minute_and_a_day_is_valid(self, minutes: int) -> None:
        assert (
            parse_week_plan(with_workout(duration_minutes=minutes)).workouts[0].duration_minutes
            == minutes
        )

    @pytest.mark.parametrize("minutes", [0, 1441, -1, 10**9])
    def test_a_duration_out_of_range_is_refused(self, minutes: int) -> None:
        assert problems_of(with_workout(duration_minutes=minutes)) == [
            Problem("workouts[0].duration_minutes", "Must be between 1 and 1440.")
        ]

    @pytest.mark.parametrize("minutes", ["90", 90.0, 90.5, True, None, [90], float("nan")])
    def test_a_duration_must_be_a_whole_number(self, minutes: object) -> None:
        assert problems_of(with_workout(duration_minutes=minutes)) == [
            Problem("workouts[0].duration_minutes", "Must be a whole number.")
        ]


class TestTheZone:
    @pytest.mark.parametrize(
        ("system", "zone"),
        [
            ("power", 1),
            ("power", 7),
            ("heart_rate", 1),
            ("heart_rate", 5),
            ("pace", 1),
            ("pace", 5),
        ],
    )
    def test_a_zone_that_exists_is_accepted(self, system: str, zone: int) -> None:
        result = parse_week_plan(with_workout(zone_system=system, zone=zone)).workouts[0]

        assert (result.zone_system, result.zone) == (system, zone)

    @pytest.mark.parametrize(
        ("system", "zone", "high"),
        [("power", 8, 7), ("power", 0, 7), ("heart_rate", 6, 5), ("pace", 6, 5), ("pace", -1, 5)],
    )
    def test_a_zone_that_does_not_exist_is_refused(self, system: str, zone: int, high: int) -> None:
        assert problems_of(with_workout(zone_system=system, zone=zone)) == [
            Problem("workouts[0].zone", f"Must be between 1 and {high}.")
        ]

    @pytest.mark.parametrize(
        "data", [{"zone_system": "power"}, {"zone": 3}, {"zone_system": "power", "zone": None}]
    )
    def test_a_system_and_a_zone_go_together(self, data: dict[str, Any]) -> None:
        assert problems_of(with_workout(**data)) == [
            Problem("workouts[0].zone_system", "A zone system and a zone go together.")
        ]

    def test_an_unknown_system_is_refused_and_its_zone_checked_loosely(self) -> None:
        assert paths_of(with_workout(zone_system="rpe", zone=3)) == ["workouts[0].zone_system"]
        assert paths_of(with_workout(zone_system="rpe", zone=99)) == [
            "workouts[0].zone_system",
            "workouts[0].zone",
        ]

    @pytest.mark.parametrize("zone", ["2", 2.0, True, [2], {}])
    def test_a_zone_must_be_a_whole_number(self, zone: object) -> None:
        assert problems_of(with_workout(zone_system="power", zone=zone)) == [
            Problem("workouts[0].zone", "Must be a whole number.")
        ]

    @pytest.mark.parametrize("system", [5, ["power"], True, "Power", ""])
    def test_a_system_must_be_one_of_the_known_texts(self, system: object) -> None:
        assert "workouts[0].zone_system" in paths_of(with_workout(zone_system=system, zone=2))


class TestTheTimeOfDay:
    def slot_of(self, **fields: Any) -> Slot | None:
        (result,) = parse_week_plan(with_workout(**fields)).workouts
        return result.slot

    def test_a_workout_has_no_time_of_day_unless_it_is_given(self) -> None:
        assert self.slot_of() is None

    @pytest.mark.parametrize("slot", ["morning", "afternoon", "evening"])
    def test_every_time_of_day_is_known(self, slot: str) -> None:
        assert self.slot_of(slot=slot) == Slot(slot)

    def test_an_explicit_null_is_the_same_as_leaving_it_out(self) -> None:
        assert self.slot_of(slot=None) is None

    @pytest.mark.parametrize(
        "slot", ["noon", "Morning", "MORNING", " morning", "", "night", 1, True, ["morning"], {}]
    )
    def test_any_other_time_of_day_is_refused(self, slot: object) -> None:
        problems = problems_of(with_workout(slot=slot))

        assert [(p.path, p.message) for p in problems] == [
            ("workouts[0].slot", "Must be one of: morning, afternoon, evening.")
        ]

    def test_two_workouts_of_one_day_may_have_two_times(self) -> None:
        result = parse_week_plan(
            plan(workouts=[workout(slot="morning"), workout(slot="evening", sport="running")])
        )

        assert [w.slot for w in result.workouts] == [Slot.MORNING, Slot.EVENING]


class TestStretching:
    def minutes_of(self, **fields: Any) -> int:
        (result,) = parse_week_plan(with_workout(**fields)).workouts
        return result.stretching_minutes

    def test_there_is_none_unless_it_is_given(self) -> None:
        assert self.minutes_of() == 0

    @pytest.mark.parametrize("minutes", [0, 1, 10, 59, 60])
    def test_up_to_an_hour_is_fine(self, minutes: int) -> None:
        assert self.minutes_of(stretching_minutes=minutes) == minutes

    @pytest.mark.parametrize("minutes", [-1, 61, 100, 10**9])
    def test_other_lengths_are_refused(self, minutes: int) -> None:
        problems = problems_of(with_workout(stretching_minutes=minutes))

        assert [(p.path, p.message) for p in problems] == [
            ("workouts[0].stretching_minutes", "Must be between 0 and 60.")
        ]

    @pytest.mark.parametrize("minutes", ["10", 10.0, 7.5, True, False, None, [10], {}])
    def test_a_length_must_be_a_whole_number(self, minutes: object) -> None:
        assert paths_of(with_workout(stretching_minutes=minutes)) == [
            "workouts[0].stretching_minutes"
        ]

    def test_it_is_no_workout_and_makes_none(self) -> None:
        result = parse_week_plan(with_workout(stretching_minutes=20))

        assert len(result.workouts) == 1
        assert result.workouts[0].duration_minutes == 90

    def test_it_comes_back_through_the_round_trip(self) -> None:
        original = parse_week_plan(
            plan(
                workouts=[
                    workout(slot="morning", stretching_minutes=15),
                    workout(slot="evening", sport="running"),
                ]
            )
        )

        assert parse_week_plan(to_json(original)) == original
        assert [w["slot"] for w in to_json(original)["workouts"]] == ["morning", "evening"]
        assert [w["stretching_minutes"] for w in to_json(original)["workouts"]] == [15, 0]

    def test_both_problems_are_named_at_once(self) -> None:
        assert paths_of(with_workout(slot="noon", stretching_minutes=99, sport="golf")) == [
            "workouts[0].sport",
            "workouts[0].slot",
            "workouts[0].stretching_minutes",
        ]

    def test_nothing_of_the_input_is_repeated(self) -> None:
        marker = "SECRETMARKER"

        text = repr(problems_of(with_workout(slot=marker, stretching_minutes=marker)))

        assert marker not in text


class TestTheOrderOfAWeek:
    def key_of(self, day: int, slot: Slot | None) -> tuple[date, int]:
        return order_key(
            Workout(
                day=MONDAY + timedelta(days=day),
                sport=Sport.RUNNING,
                title="t",
                goal=Goal.ENDURANCE,
                duration_minutes=30,
                slot=slot,
            )
        )

    def test_the_day_counts_first(self) -> None:
        assert self.key_of(0, Slot.EVENING) < self.key_of(1, Slot.MORNING)
        assert self.key_of(0, None) < self.key_of(1, Slot.MORNING)

    def test_within_a_day_morning_comes_before_afternoon_before_evening(self) -> None:
        keys = [self.key_of(2, slot) for slot in (Slot.MORNING, Slot.AFTERNOON, Slot.EVENING)]

        assert keys == sorted(keys)
        assert len(set(keys)) == 3

    def test_a_workout_without_a_time_comes_after_those_with_one(self) -> None:
        assert self.key_of(2, Slot.EVENING) < self.key_of(2, None)

    def test_the_same_time_is_the_same_place(self) -> None:
        assert self.key_of(2, Slot.AFTERNOON) == self.key_of(2, Slot.AFTERNOON)
        assert self.key_of(2, None) == self.key_of(2, None)


class TestTheSegments:
    def test_a_segment_has_its_defaults(self) -> None:
        (result,) = parse_week_plan(with_segment()).workouts[0].segments

        assert result == Segment(SegmentKind.WORK, 300, 1, None, None)

    @pytest.mark.parametrize("kind", ["warmup", "steady", "work", "recovery", "cooldown"])
    def test_every_kind_is_known(self, kind: str) -> None:
        assert parse_week_plan(with_segment(kind=kind)).workouts[0].segments[0].kind == kind

    @pytest.mark.parametrize("kind", ["rest", "Work", "", 5, None])
    def test_another_kind_is_refused(self, kind: object) -> None:
        assert problems_of(with_segment(kind=kind)) == [
            Problem(
                "workouts[0].segments[0].kind",
                "Must be one of: warmup, steady, work, recovery, cooldown.",
            )
        ]

    @pytest.mark.parametrize("seconds", [1, 600, 86400])
    def test_the_length_of_a_segment_may_be_a_second_to_a_day(self, seconds: int) -> None:
        assert (
            parse_week_plan(with_segment(seconds=seconds)).workouts[0].segments[0].seconds
            == seconds
        )

    @pytest.mark.parametrize("seconds", [0, -5, 86401])
    def test_other_lengths_are_refused(self, seconds: int) -> None:
        assert problems_of(with_segment(seconds=seconds)) == [
            Problem("workouts[0].segments[0].seconds", "Must be between 1 and 86400.")
        ]

    @pytest.mark.parametrize("seconds", ["300", 300.0, True, None, [300]])
    def test_a_length_must_be_a_whole_number(self, seconds: object) -> None:
        assert problems_of(with_segment(seconds=seconds)) == [
            Problem("workouts[0].segments[0].seconds", "Must be a whole number.")
        ]

    @pytest.mark.parametrize("repeat", [1, 4, 50])
    def test_a_segment_may_be_repeated_up_to_50_times(self, repeat: int) -> None:
        assert parse_week_plan(with_segment(repeat=repeat)).workouts[0].segments[0].repeat == repeat

    @pytest.mark.parametrize("repeat", [0, 51, -1])
    def test_other_repeats_are_refused(self, repeat: int) -> None:
        assert problems_of(with_segment(repeat=repeat)) == [
            Problem("workouts[0].segments[0].repeat", "Must be between 1 and 50.")
        ]

    @pytest.mark.parametrize("repeat", ["2", 2.0, True, None])
    def test_a_repeat_must_be_a_whole_number(self, repeat: object) -> None:
        assert paths_of(with_segment(repeat=repeat)) == ["workouts[0].segments[0].repeat"]

    @pytest.mark.parametrize("missing", ["kind", "seconds"])
    def test_a_missing_field_is_named(self, missing: str) -> None:
        data = segment()
        del data[missing]

        assert problems_of(with_workout(segments=[data])) == [
            Problem(f"workouts[0].segments[0].{missing}", "Is required.")
        ]

    def test_an_unknown_field_is_refused(self) -> None:
        assert problems_of(with_segment(colour="red")) == [
            Problem("workouts[0].segments[0]", "Unknown field.")
        ]

    @pytest.mark.parametrize("value", [None, [], "x", 5])
    def test_a_segment_must_be_an_object(self, value: object) -> None:
        assert problems_of(with_workout(segments=[value])) == [
            Problem("workouts[0].segments[0]", "Must be an object.")
        ]

    @pytest.mark.parametrize("value", [None, {}, "x", 5])
    def test_segments_must_be_a_list(self, value: object) -> None:
        assert problems_of(with_workout(segments=value)) == [
            Problem("workouts[0].segments", "Must be a list.")
        ]

    def test_a_workout_holds_at_most_40_segments(self) -> None:
        assert (
            len(parse_week_plan(with_workout(segments=[segment()] * 40)).workouts[0].segments) == 40
        )
        assert problems_of(with_workout(segments=[segment()] * 41)) == [
            Problem("workouts[0].segments", "Must have at most 40 entries.")
        ]

    def test_a_segment_has_its_own_zone_with_the_same_rules(self) -> None:
        ok = parse_week_plan(with_segment(zone_system="pace", zone=5)).workouts[0].segments[0]
        assert (ok.zone_system, ok.zone) == (ZoneSystem.PACE, 5)
        assert problems_of(with_segment(zone_system="pace", zone=6)) == [
            Problem("workouts[0].segments[0].zone", "Must be between 1 and 5.")
        ]
        assert problems_of(with_segment(zone_system="power")) == [
            Problem("workouts[0].segments[0].zone_system", "A zone system and a zone go together.")
        ]


class TestTheExercises:
    def first(self, **fields: Any) -> Exercise:
        return parse_week_plan(with_exercise(**fields)).workouts[0].exercises[0]

    def test_a_workout_has_none_by_default(self) -> None:
        assert parse_week_plan(plan()).workouts[0].exercises == ()

    def test_an_exercise_has_its_defaults(self) -> None:
        assert self.first() == Exercise(
            "Goblet squat",
            ExerciseRegion.LEGS,
            ExerciseEquipment.DUMBBELLS,
            3,
            reps=10,
        )

    def test_a_full_exercise_is_read_and_written_back(self) -> None:
        data = with_exercise(rpe=7, rest_seconds=90)

        written = to_json(parse_week_plan(data))["workouts"][0]["exercises"]

        assert written == [
            {
                "name": "Goblet squat",
                "region": "legs",
                "equipment": "dumbbells",
                "sets": 3,
                "reps": 10,
                "seconds": None,
                "rpe": 7,
                "rest_seconds": 90,
            }
        ]
        assert parse_week_plan(to_json(parse_week_plan(data))) == parse_week_plan(data)

    def test_a_hold_is_read_with_seconds(self) -> None:
        found = self.first(name="Plank", reps=None, seconds=45)

        assert (found.reps, found.seconds) == (None, 45)

    def test_the_order_is_kept(self) -> None:
        data = plan(
            workouts=[
                workout(
                    sport="strength",
                    exercises=[exercise(name="First"), exercise(name="Second")],
                )
            ]
        )

        names = [e.name for e in parse_week_plan(data).workouts[0].exercises]

        assert names == ["First", "Second"]

    def test_the_name_is_trimmed(self) -> None:
        assert self.first(name="  Plank  ").name == "Plank"

    @pytest.mark.parametrize("region", ["legs", "core", "upper_body", "full_body"])
    def test_every_region_is_known(self, region: str) -> None:
        assert self.first(region=region).region == region

    @pytest.mark.parametrize("equipment", ["gym", "dumbbells", "bodyweight"])
    def test_every_equipment_is_known(self, equipment: str) -> None:
        assert self.first(equipment=equipment).equipment == equipment

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("region", "arms", "Must be one of: legs, core, upper_body, full_body."),
            ("region", None, "Must be one of: legs, core, upper_body, full_body."),
            ("equipment", "barbell", "Must be one of: gym, dumbbells, bodyweight."),
            ("name", "", "Must not be empty."),
            ("name", "   ", "Must not be empty."),
            ("name", "x" * 61, "Must have at most 60 characters."),
            ("name", "a\nb", "Must not contain control characters."),
            ("name", 5, "Must be text."),
            ("sets", 0, "Must be between 1 and 10."),
            ("sets", 11, "Must be between 1 and 10."),
            ("sets", 3.0, "Must be a whole number."),
            ("sets", "3", "Must be a whole number."),
            ("sets", True, "Must be a whole number."),
            ("reps", 0, "Must be between 1 and 100."),
            ("reps", 101, "Must be between 1 and 100."),
            ("reps", "10", "Must be a whole number."),
            ("rpe", 0, "Must be between 1 and 10."),
            ("rpe", 11, "Must be between 1 and 10."),
            ("rest_seconds", -1, "Must be between 0 and 600."),
            ("rest_seconds", 601, "Must be between 0 and 600."),
        ],
    )
    def test_a_field_that_is_not_usable_is_named(
        self, field: str, value: object, message: str
    ) -> None:
        assert problems_of(with_exercise(**{field: value})) == [
            Problem(f"workouts[0].exercises[0].{field}", message)
        ]

    @pytest.mark.parametrize("seconds", [4, 601, 0])
    def test_a_hold_outside_its_range_is_named(self, seconds: int) -> None:
        assert problems_of(with_exercise(reps=None, seconds=seconds)) == [
            Problem("workouts[0].exercises[0].seconds", "Must be between 5 and 600.")
        ]

    @pytest.mark.parametrize(
        "fields", [{"reps": None}, {"reps": 10, "seconds": 45}, {"reps": None, "seconds": None}]
    )
    def test_exactly_one_of_reps_and_seconds_is_needed(self, fields: dict[str, Any]) -> None:
        assert problems_of(with_exercise(**fields)) == [
            Problem(
                "workouts[0].exercises[0].reps",
                "Give either reps or seconds, not both and not neither.",
            )
        ]

    @pytest.mark.parametrize("missing", ["name", "region", "equipment", "sets"])
    def test_a_required_field_is_named(self, missing: str) -> None:
        data = with_exercise()
        del data["workouts"][0]["exercises"][0][missing]

        assert problems_of(data) == [Problem(f"workouts[0].exercises[0].{missing}", "Is required.")]

    def test_an_unknown_field_is_reported_at_its_parent(self) -> None:
        assert paths_of(with_exercise(weight_kg=20)) == ["workouts[0].exercises[0]"]

    def test_at_most_fifteen_exercises(self) -> None:
        many = plan(workouts=[workout(sport="strength", exercises=[exercise()] * 16)])

        assert problems_of(many) == [
            Problem("workouts[0].exercises", "Must have at most 15 entries.")
        ]
        full = plan(workouts=[workout(sport="strength", exercises=[exercise()] * 15)])
        assert len(parse_week_plan(full).workouts[0].exercises) == 15

    def test_the_exercises_must_be_a_list(self) -> None:
        assert problems_of(plan(workouts=[workout(exercises="squat")])) == [
            Problem("workouts[0].exercises", "Must be a list.")
        ]

    def test_every_problem_of_every_exercise_is_named_at_once(self) -> None:
        data = plan(
            workouts=[
                workout(
                    sport="strength",
                    exercises=[exercise(sets=0), exercise(), exercise(region="x", rpe=99)],
                )
            ]
        )

        assert paths_of(data) == [
            "workouts[0].exercises[0].sets",
            "workouts[0].exercises[2].region",
            "workouts[0].exercises[2].rpe",
        ]

    def test_the_sport_is_not_checked_here(self) -> None:
        # exercises on a run are a matter of the checks, not of the format
        data = plan(workouts=[workout(sport="running", exercises=[exercise()])])

        assert len(parse_week_plan(data).workouts[0].exercises) == 1


class TestEveryProblemAtOnce:
    def test_problems_in_several_places_are_all_reported_by_path(self) -> None:
        data = {
            "week_start": "2027-07-13",
            "workouts": [
                workout(sport="rowing", duration_minutes=0),
                workout(title="", segments=[segment(seconds="x"), segment(kind="rest")]),
                5,
            ],
        }

        assert paths_of(data) == [
            "week_start",
            "workouts[0].sport",
            "workouts[0].duration_minutes",
            "workouts[1].title",
            "workouts[1].segments[0].seconds",
            "workouts[1].segments[1].kind",
            "workouts[2]",
        ]

    def test_a_missing_field_and_a_wrong_one_are_both_named(self) -> None:
        data = workout(sport=5)
        del data["goal"]

        assert sorted(paths_of(plan(workouts=[data]))) == ["workouts[0].goal", "workouts[0].sport"]

    def test_the_error_says_how_many(self) -> None:
        with pytest.raises(PlanFormatError) as raised:
            parse_week_plan({"week_start": 5, "workouts": 5})

        assert str(raised.value) == "The plan has 2 problem(s)."
        assert len(raised.value.problems) == 2


class TestNothingOfTheInputIsRepeated:
    MARKER = "SECRET-MARKER-9f3"

    def everything(self, data: object) -> str:
        with pytest.raises(PlanFormatError) as raised:
            parse_week_plan(data)
        parts = [str(raised.value), repr(raised.value)]
        for problem in raised.value.problems:
            parts += [problem.path, problem.message]
        return " ".join(parts)

    @pytest.mark.parametrize(
        "data",
        [
            plan(week_start=MARKER),
            plan(rationale={"x": MARKER}),
            with_workout(sport=MARKER),
            with_workout(goal=MARKER),
            with_workout(day=MARKER),
            with_workout(title=MARKER[:6] + "\n" + MARKER[6:]),
            with_workout(notes=[MARKER]),
            with_workout(zone_system=MARKER, zone=MARKER),
            with_segment(kind=MARKER),
            with_exercise(name=MARKER[:6] + "\n" + MARKER[6:]),
            with_exercise(region=MARKER),
            with_exercise(equipment=MARKER),
            with_exercise(sets=MARKER),
            with_exercise(**{MARKER: 1}),
            with_segment(seconds=MARKER),
            plan(**{MARKER: 1}),
            with_workout(**{MARKER: 1}),
            with_segment(**{MARKER: 1}),
            {MARKER: MARKER},
        ],
    )
    def test_no_message_path_or_text_holds_a_value_of_the_input(self, data: object) -> None:
        assert self.MARKER not in self.everything(data)

    @pytest.mark.parametrize(
        "key",
        [
            "SECRETMARKER",
            "colour_2",
            "x" * 40,
            "a b",
            "x" * 41,
            "é",
            "a.b",
            "a[0]",
            "",
            "<script>",
            5,
        ],
    )
    @pytest.mark.parametrize("level", ["plan", "workout", "segment", "exercise"])
    def test_unknown_keys_are_reported_once_at_the_trusted_parent(
        self, key: Any, level: str
    ) -> None:
        data = with_exercise()
        data["workouts"][0]["segments"] = [segment()]
        targets = {
            "plan": (data, ""),
            "workout": (data["workouts"][0], "workouts[0]"),
            "segment": (data["workouts"][0]["segments"][0], "workouts[0].segments[0]"),
            "exercise": (data["workouts"][0]["exercises"][0], "workouts[0].exercises[0]"),
        }
        target, path = targets[level]
        target.update({key: 1, "ANOTHER_UNKNOWN_KEY": 2})

        assert problems_of(data) == [Problem(path, "Unknown field.")]
        if isinstance(key, str) and key:
            assert key not in self.everything(data)
        assert "ANOTHER_UNKNOWN_KEY" not in self.everything(data)


class TestTheLimits:
    def test_the_limits_are_written_out_on_purpose(self) -> None:
        # The other tests read the constants and would follow a change.
        assert (schema.TITLE_MAX, schema.NOTES_MAX, schema.RATIONALE_MAX) == (100, 500, 1000)
        assert (schema.DURATION_MAX, schema.MAX_WORKOUTS, schema.MAX_SEGMENTS) == (1440, 28, 40)
        assert (schema.SEGMENT_SECONDS_MAX, schema.REPEAT_MAX) == (86_400, 50)
        assert schema.STRETCHING_MAX == 60
        assert (schema.MAX_EXERCISES, schema.EXERCISE_NAME_MAX) == (15, 60)
        assert (schema.SETS_MAX, schema.REPS_MAX, schema.RPE_MAX) == (10, 100, 10)
        assert (schema.HOLD_SECONDS_MIN, schema.HOLD_SECONDS_MAX) == (5, 600)
        assert schema.REST_SECONDS_MAX == 600
        assert schema.ZONE_COUNT == {"power": 7, "heart_rate": 5, "pace": 5}

    def test_the_models_use_the_same_limits(self) -> None:
        from planning import models

        assert (models.TITLE_MAX, models.NOTES_MAX, models.RATIONALE_MAX) == (100, 500, 1000)
        assert models.ZONE_COUNT is schema.ZONE_COUNT

    def test_the_source_has_no_invisible_characters(self) -> None:
        # The forbidden characters are written as escapes; a literal one would be invisible.
        source = Path(schema.__file__).read_text()

        assert source.isascii()

    def test_the_test_file_has_no_literal_forbidden_characters(self) -> None:
        source = Path(__file__).read_text(encoding="utf-8")

        assert not any(char in source for char in schema._FORBIDDEN)

    def test_the_module_needs_no_django(self) -> None:
        source = Path(schema.__file__).read_text()
        imported = {
            node.module.split(".")[0]
            if isinstance(node, ast.ImportFrom) and node.module
            else alias.name.split(".")[0]
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Import | ast.ImportFrom)
            for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(name="")])
        }

        assert "django" not in imported
        assert "planning" not in imported


class TestWhateverIsSent:
    JUNK: list[Any] = [
        None, True, False, 0, -1, 1, 7, 90, 10**30, 1.5, float("nan"), float("inf"), "", " ", "x",
        "2027-07-12", "2027-07-13", "running", "power", "work", "\n", "a\x00b", "é" * 3, "x" * 2000,
        [], {}, [None], [[]], {"a": 1}, {"kind": "work", "seconds": 5}, [{"day": 1}],
    ]  # fmt: skip

    def mutated(self, rng: Any, data: Any) -> Any:
        """A copy of ``data`` in which one random place holds junk or is gone."""
        copy_ = copy.deepcopy(data)
        places: list[tuple[Any, Any]] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for key in list(node):
                    places.append((node, key))
                    walk(node[key])
            elif isinstance(node, list):
                for index in range(len(node)):
                    places.append((node, index))
                    walk(node[index])

        walk(copy_)
        holder, key = rng.choice(places)
        if rng.random() < 0.3 and isinstance(holder, dict):
            del holder[key]
        else:
            holder[key] = copy.deepcopy(rng.choice(self.JUNK))
        return copy_

    def test_garbage_gives_a_plan_or_a_format_error_and_nothing_else(self) -> None:
        import random

        rng = random.Random(20261113)
        base = plan(
            rationale="Why",
            workouts=[
                workout(
                    zone_system="power",
                    zone=2,
                    slot="morning",
                    stretching_minutes=10,
                    segments=[segment(zone_system="power", zone=4)],
                ),
                workout(day="2027-07-15", sport="running", goal="tempo", slot="evening"),
            ],
        )
        outcomes = {"plan": 0, "error": 0}

        for _ in range(3000):
            data = self.mutated(rng, base)
            for _ in range(rng.randint(0, 2)):
                data = self.mutated(rng, data)
            try:
                result = parse_week_plan(data)
            except PlanFormatError as error:
                assert error.problems
                assert all(isinstance(p.path, str) and p.message for p in error.problems)
                outcomes["error"] += 1
            else:
                assert parse_week_plan(to_json(result)) == result
                outcomes["plan"] += 1

        assert outcomes["error"] > 1000 and outcomes["plan"] > 50  # both outcomes are exercised

    @pytest.mark.parametrize("data", JUNK)
    def test_any_junk_as_the_whole_input_is_a_format_error(self, data: Any) -> None:
        with pytest.raises(PlanFormatError):
            parse_week_plan(data)

    def test_very_deep_nesting_inside_an_unknown_field_is_not_followed(self) -> None:
        deep: Any = []
        for _ in range(50_000):
            deep = [deep]

        assert paths_of(plan(extra=deep)) == [""]

    def test_random_valid_plans_survive_the_round_trip(self) -> None:
        import random

        rng = random.Random(7)
        for _ in range(300):
            workouts = []
            for _ in range(rng.randint(0, 8)):
                system = rng.choice([None, "power", "heart_rate", "pace"])
                zone = None if system is None else rng.randint(1, 7 if system == "power" else 5)
                segments = [
                    segment(
                        kind=rng.choice(["warmup", "steady", "work", "recovery", "cooldown"]),
                        seconds=rng.randint(1, 3600),
                        repeat=rng.randint(1, 50),
                        **({} if system is None else {"zone_system": system, "zone": zone}),
                    )
                    for _ in range(rng.randint(0, 6))
                ]
                workouts.append(
                    workout(
                        day=(MONDAY + timedelta(days=rng.randint(0, 6))).isoformat(),
                        sport=rng.choice(["running", "cycling", "swimming", "strength"]),
                        goal=rng.choice(["recovery", "endurance", "tempo", "threshold", "vo2max"]),
                        duration_minutes=rng.randint(1, 1440),
                        slot=rng.choice([None, "morning", "afternoon", "evening"]),
                        stretching_minutes=rng.randint(0, 60),
                        segments=segments,
                        **({} if system is None else {"zone_system": system, "zone": zone}),
                    )
                )
            original = parse_week_plan(plan(workouts=workouts))

            assert parse_week_plan(to_json(original)) == original
