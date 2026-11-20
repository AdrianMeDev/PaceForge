from dataclasses import replace
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import pytest

from chat.actions import (
    ALONE_PROBLEM,
    OTHER_WEEK_PROBLEM,
    REPLAN_DAYS_MAX,
    REPLAN_DAYS_MIN,
    REPLAN_START_MAX_DAYS,
    ActionFormatError,
    FreeDay,
    MarkSick,
    MoveWorkout,
    ReduceWeek,
    ReplanFrom,
    ShortenWorkout,
    SkipWorkout,
    SwapSport,
    Symptoms,
    apply,
    as_data,
    read_actions,
)
from planning.rules import EASY_UP_TO_ZONE, Intensity, intensity_of
from planning.schema import Goal, Segment, SegmentKind, Slot, Sport, WeekPlan, Workout, ZoneSystem

MONDAY = date(2026, 11, 16)
NEXT_MONDAY = date(2026, 11, 23)
TODAY = date(2026, 11, 17)  # a Tuesday: Monday is over
RUN = UUID("0195f3a0-0000-7000-8000-000000000001")
RIDE = UUID("0195f3a0-0000-7000-8000-000000000002")
OLD = UUID("0195f3a0-0000-7000-8000-000000000003")
STRENGTH = UUID("0195f3a0-0000-7000-8000-000000000004")
NEXT_RUN = UUID("0195f3a0-0000-7000-8000-000000000005")


def day(n: int) -> date:
    return date(2026, 11, 16 + n)


def make_plan() -> WeekPlan:
    return WeekPlan(
        MONDAY,
        (
            Workout(day(0), Sport.RUNNING, "Done run", Goal.ENDURANCE, 45, lineage=OLD),
            Workout(
                day(1),
                Sport.RUNNING,
                "Intervals",
                Goal.THRESHOLD,
                60,
                segments=(
                    Segment(SegmentKind.WARMUP, 900),
                    Segment(SegmentKind.WORK, 2400, 1, ZoneSystem.PACE, 4),
                    Segment(SegmentKind.COOLDOWN, 300),
                ),
                zone_system=ZoneSystem.PACE,
                zone=4,
                notes="Hard one",
                slot=Slot.MORNING,
                lineage=RUN,
            ),
            Workout(day(3), Sport.CYCLING, "Ride", Goal.ENDURANCE, 90, lineage=RIDE),
            Workout(day(5), Sport.STRENGTH, "Legs", Goal.STRENGTH, 40, lineage=STRENGTH),
        ),
        "Rationale.",
    )


def make_next_plan() -> WeekPlan:
    return WeekPlan(
        NEXT_MONDAY,
        (
            Workout(
                date(2026, 11, 24), Sport.RUNNING, "Next run", Goal.ENDURANCE, 50, lineage=NEXT_RUN
            ),
        ),
        "Next week.",
    )


def apply_(plan: WeekPlan, actions: Any) -> Any:
    return apply(plan, actions, TODAY)


def read(*items: dict[str, Any]) -> tuple[Any, ...]:
    return read_actions(list(items), make_plan(), TODAY)


def problems_of(*items: Any) -> dict[str, str]:
    with pytest.raises(ActionFormatError) as caught:
        read_actions(list(items), make_plan(), TODAY)
    return {problem.path: problem.message for problem in caught.value.problems}


def by_lineage(plan: WeekPlan, lineage: UUID) -> Workout:
    return next(w for w in plan.workouts if w.lineage == lineage)


class TestReadingTheActions:
    def test_each_tool_is_read(self) -> None:
        actions = read(
            {"tool": "move_workout", "id": str(RUN), "day": day(2).isoformat(), "slot": "evening"},
            {"tool": "skip_workout", "id": str(RIDE)},
            {"tool": "swap_sport", "id": str(RUN), "sport": "cycling", "minutes": 45},
            {"tool": "shorten_workout", "id": str(RIDE), "minutes": 60},
            {"tool": "reduce_week", "percent": 20},
            {"tool": "free_day", "day": day(5).isoformat()},
            {"tool": "mark_sick", "symptoms": "above_neck", "fever": False, "days": 2},
        )

        assert actions == (
            MoveWorkout(RUN, day(2), Slot.EVENING),
            SkipWorkout(RIDE),
            SwapSport(RUN, Sport.CYCLING, 45),
            ShortenWorkout(RIDE, 60),
            ReduceWeek(20),
            FreeDay(day(5)),
            MarkSick(Symptoms.ABOVE_NECK, False, 2),
        )

    def test_mark_sick_boundaries_and_as_data(self) -> None:
        (mild,) = read({"tool": "mark_sick", "symptoms": "above_neck", "fever": False, "days": 1})
        (severe,) = read({"tool": "mark_sick", "symptoms": "below_neck", "fever": True, "days": 14})

        assert mild == MarkSick(Symptoms.ABOVE_NECK, False, 1)
        assert severe == MarkSick(Symptoms.BELOW_NECK, True, 14)
        assert as_data([mild, severe]) == [
            {"tool": "mark_sick", "symptoms": "above_neck", "fever": False, "days": 1},
            {"tool": "mark_sick", "symptoms": "below_neck", "fever": True, "days": 14},
        ]

    def test_no_actions_are_no_change(self) -> None:
        assert read_actions([], make_plan(), TODAY) == ()

    def test_a_slot_is_optional(self) -> None:
        (action,) = read({"tool": "move_workout", "id": str(RUN), "day": day(2).isoformat()})

        assert action == MoveWorkout(RUN, day(2), None)

    @pytest.mark.parametrize("data", [None, {}, "move", 3])
    def test_the_actions_must_be_a_list(self, data: object) -> None:
        with pytest.raises(ActionFormatError):
            read_actions(data, make_plan(), TODAY)

    def test_at_most_ten_at_once(self) -> None:
        with pytest.raises(ActionFormatError):
            read_actions([{"tool": "reduce_week", "percent": 10}] * 11, make_plan(), TODAY)


def trip(**fields: Any) -> dict[str, Any]:
    return {
        "tool": "replan_from",
        "start": "2026-11-23",
        "days": 21,
        "kind": "other",
        **fields,
    }


class TestReplanFrom:
    def test_is_read_with_its_limits_and_as_data(self) -> None:
        (found,) = read(trip())
        (first,) = read(trip(start=TODAY.isoformat(), days=REPLAN_DAYS_MIN, kind="vacation"))
        (last,) = read(
            trip(
                start=(TODAY + timedelta(days=REPLAN_START_MAX_DAYS)).isoformat(),
                days=REPLAN_DAYS_MAX,
            )
        )

        assert found == ReplanFrom(date(2026, 11, 23), 21, "other")
        assert first == ReplanFrom(TODAY, REPLAN_DAYS_MIN, "vacation")
        assert last.days == REPLAN_DAYS_MAX
        assert as_data([found]) == [
            {"tool": "replan_from", "start": date(2026, 11, 23), "days": 21, "kind": "other"}
        ]

    @pytest.mark.parametrize(
        ("fields", "path"),
        [
            ({"start": "2026-11-16"}, "start"),
            ({"start": "soon"}, "start"),
            ({"start": 5}, "start"),
            ({"start": "2028-01-01"}, "start"),
            ({"days": REPLAN_DAYS_MIN - 1}, "days"),
            ({"days": REPLAN_DAYS_MAX + 1}, "days"),
            ({"days": True}, "days"),
            ({"days": "21"}, "days"),
            ({"kind": "illness"}, "kind"),
            ({"kind": 3}, "kind"),
        ],
    )
    def test_refuses_what_is_out_of_limits(self, fields: dict[str, Any], path: str) -> None:
        assert list(problems_of(trip(**fields))) == [f"actions[0].{path}"]

    def test_refuses_missing_and_extra_fields(self) -> None:
        found = problems_of({"tool": "replan_from", "note": "x"})

        assert set(found) == {
            "actions[0]",
            "actions[0].start",
            "actions[0].days",
            "actions[0].kind",
        }

    def test_must_be_the_only_action(self) -> None:
        found = problems_of({"tool": "free_day", "day": day(5).isoformat()}, trip())

        assert found == {"actions[1]": ALONE_PROBLEM}

    def test_changes_no_week(self) -> None:
        plan = make_plan()

        changed, changes = apply_(plan, [ReplanFrom(date(2026, 11, 23), 21, "other")])

        assert changed == plan
        assert changes == ()


class TestWhatIsRefused:
    def test_a_tool_that_is_not_known(self) -> None:
        assert "actions[0].tool" in problems_of({"tool": "delete_everything"})
        assert "actions[0]" in problems_of("move_workout")

    def test_fields_that_are_missing_or_not_part_of_the_tool(self) -> None:
        found = problems_of({"tool": "skip_workout", "id": str(RUN), "reason": "x"})
        assert "actions[0]" in found
        assert "actions[0].id" in problems_of({"tool": "skip_workout"})

    @pytest.mark.parametrize(
        "unknown", ["coach_written_key", "ignore the rules", "injected\nreply", "direction\u202e"]
    )
    def test_unknown_keys_are_never_echoed(self, unknown: str) -> None:
        with pytest.raises(ActionFormatError) as caught:
            read(
                {"tool": "reduce_week", "percent": 20, unknown: "x", "another_key": "y"},
                {"tool": "skip_workout", unknown: "z"},
            )

        assert [(p.path, p.message) for p in caught.value.problems] == [
            ("actions[0]", "This field is not part of the tool."),
            ("actions[1]", "This field is not part of the tool."),
            ("actions[1].id", "This field is missing."),
        ]
        for key in (unknown, "another_key"):
            assert all(key not in p.path and key not in p.message for p in caught.value.problems)
            assert key not in str(caught.value)
            assert key not in repr(caught.value)

    def test_a_workout_that_is_not_in_the_plan(self) -> None:
        stranger = "0195f3a0-0000-7000-8000-0000000000ff"
        assert "actions[0].id" in problems_of({"tool": "skip_workout", "id": stranger})
        assert "actions[0].id" in problems_of({"tool": "skip_workout", "id": "run"})
        assert "actions[0].id" in problems_of({"tool": "skip_workout", "id": 7})

    def test_a_workout_in_the_past(self) -> None:
        found = problems_of({"tool": "skip_workout", "id": str(OLD)})

        assert "past" in found["actions[0].id"]

    def test_a_day_in_the_past_or_outside_the_week(self) -> None:
        past = problems_of({"tool": "free_day", "day": day(0).isoformat()})
        assert "past" in past["actions[0].day"]
        outside = problems_of({"tool": "free_day", "day": "2026-11-23"})
        assert "week" in outside["actions[0].day"]
        assert "actions[0].day" in problems_of({"tool": "free_day", "day": "tuesday"})

    def test_a_move_to_a_day_in_the_past(self) -> None:
        found = problems_of({"tool": "move_workout", "id": str(RUN), "day": day(0).isoformat()})

        assert "actions[0].day" in found

    def test_a_slot_that_is_not_known(self) -> None:
        found = problems_of(
            {"tool": "move_workout", "id": str(RUN), "day": day(2).isoformat(), "slot": "noon"}
        )

        assert "actions[0].slot" in found

    @pytest.mark.parametrize("minutes", [9, 0, -5, 1441, "60", 60.5, True, None])
    def test_minutes_must_be_a_sensible_whole_number(self, minutes: object) -> None:
        found = problems_of({"tool": "shorten_workout", "id": str(RIDE), "minutes": minutes})

        assert "actions[0].minutes" in found

    def test_shortening_must_make_it_shorter(self) -> None:
        found = problems_of({"tool": "shorten_workout", "id": str(RIDE), "minutes": 90})

        assert "shorter" in found["actions[0].minutes"]

    @pytest.mark.parametrize("percent", [4, 51, 0, "20", 20.5, True])
    def test_a_percentage_in_range(self, percent: object) -> None:
        assert "actions[0].percent" in problems_of({"tool": "reduce_week", "percent": percent})

    def test_every_problem_of_every_action_is_reported(self) -> None:
        found = problems_of(
            {"tool": "skip_workout", "id": "x"},
            {"tool": "free_day", "day": "never"},
        )

        assert set(found) == {"actions[0].id", "actions[1].day"}

    @pytest.mark.parametrize("symptoms", ["cough", "ABOVE_NECK", "", 1, True, None])
    def test_mark_sick_requires_known_symptoms(self, symptoms: object) -> None:
        found = problems_of({"tool": "mark_sick", "symptoms": symptoms, "fever": False, "days": 2})

        assert "actions[0].symptoms" in found
        if isinstance(symptoms, str) and symptoms:
            assert symptoms not in found["actions[0].symptoms"]

    @pytest.mark.parametrize("fever", [0, 1, "true", "false", None, []])
    def test_mark_sick_requires_a_bool_fever(self, fever: object) -> None:
        found = problems_of(
            {"tool": "mark_sick", "symptoms": "above_neck", "fever": fever, "days": 2}
        )

        assert "actions[0].fever" in found

    @pytest.mark.parametrize("days", [0, -1, 15, 2.5, "3", True, False, None])
    def test_mark_sick_requires_days_in_range(self, days: object) -> None:
        found = problems_of(
            {"tool": "mark_sick", "symptoms": "above_neck", "fever": False, "days": days}
        )

        assert "actions[0].days" in found

    def test_mark_sick_checks_missing_extra_and_all_bad_fields(self) -> None:
        missing = problems_of({"tool": "mark_sick", "symptoms": "above_neck"})
        assert set(missing) == {"actions[0].fever", "actions[0].days"}

        extra = problems_of(
            {"tool": "mark_sick", "symptoms": "above_neck", "fever": False, "days": 2, "note": "x"}
        )
        assert set(extra) == {"actions[0]"}

        all_bad = problems_of({"tool": "mark_sick", "symptoms": "bad", "fever": "yes", "days": 99})
        assert set(all_bad) == {"actions[0].symptoms", "actions[0].fever", "actions[0].days"}

    def test_at_most_one_mark_sick_per_answer(self) -> None:
        found = problems_of(
            {"tool": "mark_sick", "symptoms": "above_neck", "fever": False, "days": 2},
            {"tool": "free_day", "day": day(5).isoformat()},
            {"tool": "mark_sick", "symptoms": "below_neck", "fever": True, "days": 4},
        )

        assert "actions[2]" in found
        assert "mark_sick" in found["actions[2]"]

    def test_a_workout_from_another_week_reports_one_week_per_answer(self) -> None:
        with pytest.raises(ActionFormatError) as caught:
            read_actions(
                [
                    {"tool": "skip_workout", "id": str(RUN)},
                    {"tool": "skip_workout", "id": str(NEXT_RUN)},
                ],
                make_plan(),
                TODAY,
                other_weeks=[make_next_plan()],
            )

        found = {problem.path: problem.message for problem in caught.value.problems}
        assert found == {"actions[1].id": OTHER_WEEK_PROBLEM}
        assert OTHER_WEEK_PROBLEM == "One week per answer: this is in another week."

    def test_a_day_from_another_week_reports_one_week_per_answer(self) -> None:
        with pytest.raises(ActionFormatError) as caught:
            read_actions(
                [
                    {"tool": "move_workout", "id": str(RUN), "day": "2026-11-24"},
                    {"tool": "free_day", "day": "2026-11-29"},
                ],
                make_plan(),
                TODAY,
                other_weeks=[make_next_plan()],
            )

        found = {problem.path: problem.message for problem in caught.value.problems}
        assert found == {
            "actions[0].day": OTHER_WEEK_PROBLEM,
            "actions[1].day": OTHER_WEEK_PROBLEM,
        }

    def test_unknown_id_or_day_outside_all_briefed_weeks_keeps_plain_error(self) -> None:
        stranger = "0195f3a0-0000-7000-8000-0000000000ff"
        with pytest.raises(ActionFormatError) as caught:
            read_actions(
                [
                    {"tool": "skip_workout", "id": stranger},
                    {"tool": "free_day", "day": "2026-12-02"},
                ],
                make_plan(),
                TODAY,
                other_weeks=[make_next_plan()],
            )

        found = {problem.path: problem.message for problem in caught.value.problems}
        assert found["actions[0].id"] == "This is not a workout of the plan."
        assert found["actions[1].day"] == "This day is not in the week of the plan."

    def test_single_week_actions_still_succeed_when_other_weeks_are_present(self) -> None:
        actions = read_actions(
            [
                {"tool": "move_workout", "id": str(RUN), "day": day(2).isoformat()},
                {"tool": "skip_workout", "id": str(RIDE)},
            ],
            make_plan(),
            TODAY,
            other_weeks=[make_plan(), make_next_plan()],
        )

        assert actions == (MoveWorkout(RUN, day(2), None), SkipWorkout(RIDE))


class TestApplyingThem:
    def test_a_move_changes_the_day_and_keeps_the_lineage(self) -> None:
        plan, changes = apply_(make_plan(), [MoveWorkout(RUN, day(2), Slot.EVENING)])

        moved = by_lineage(plan, RUN)
        assert (moved.day, moved.slot, moved.title) == (day(2), Slot.EVENING, "Intervals")
        assert changes == ("Run on Tue (60 min) moved to Wed",)

    def test_a_move_without_a_slot_keeps_the_slot(self) -> None:
        plan, _ = apply_(make_plan(), [MoveWorkout(RUN, day(2))])

        assert by_lineage(plan, RUN).slot is Slot.MORNING

    def test_skipping_takes_the_workout_out(self) -> None:
        plan, changes = apply_(make_plan(), [SkipWorkout(RIDE)])

        assert RIDE not in {w.lineage for w in plan.workouts}
        assert changes == ("Ride on Thu (90 min) removed",)

    def test_a_swap_makes_a_plain_session_of_the_other_sport(self) -> None:
        plan, changes = apply_(make_plan(), [SwapSport(RUN, Sport.CYCLING, None)])

        swapped = by_lineage(plan, RUN)
        assert swapped.sport is Sport.CYCLING
        assert swapped.duration_minutes == 60
        assert swapped.segments == ()
        assert (swapped.zone_system, swapped.zone, swapped.notes) == (None, None, "")
        assert swapped.title == "Intervals"
        assert changes == ("Run on Tue (60 min) replaced by Ride (60 min)",)

    def test_a_swap_can_name_the_minutes(self) -> None:
        plan, changes = apply_(make_plan(), [SwapSport(RIDE, Sport.RUNNING, 50)])

        assert by_lineage(plan, RIDE).duration_minutes == 50
        assert changes == ("Ride on Thu (90 min) replaced by Run (50 min)",)

    def test_shortening_drops_the_steps_that_no_longer_add_up(self) -> None:
        plan, changes = apply_(make_plan(), [ShortenWorkout(RUN, 40)])

        shorter = by_lineage(plan, RUN)
        assert (shorter.duration_minutes, shorter.segments) == (40, ())
        assert (shorter.zone_system, shorter.zone) == (ZoneSystem.PACE, 4)
        assert changes == ("Run on Tue (60 min) shortened to 40 min",)

    def test_reducing_the_week_shortens_every_workout_from_today_on(self) -> None:
        plan, changes = apply_(make_plan(), [ReduceWeek(50)])

        assert by_lineage(plan, RUN).duration_minutes == 30
        assert by_lineage(plan, RIDE).duration_minutes == 45
        assert by_lineage(plan, STRENGTH).duration_minutes == 20
        assert changes == ("Week reduced by 50 %: 3 workouts shortened",)

    def test_a_workout_is_never_made_shorter_than_the_least(self) -> None:
        small = replace(
            make_plan(), workouts=(replace(make_plan().workouts[2], duration_minutes=12),)
        )

        plan, _ = apply_(small, [ReduceWeek(50)])

        assert plan.workouts[0].duration_minutes == 10

    def test_freeing_a_day_takes_all_its_workouts_out(self) -> None:
        plan, changes = apply_(make_plan(), [FreeDay(day(3))])

        assert RIDE not in {w.lineage for w in plan.workouts}
        assert changes == ("Thu freed: 1 workout removed",)
        assert apply_(make_plan(), [FreeDay(day(4))])[1] == ("Fri freed: 0 workouts removed",)

    def test_several_actions_are_done_in_order(self) -> None:
        plan, changes = apply_(
            make_plan(), [MoveWorkout(RUN, day(2)), ShortenWorkout(RUN, 30), SkipWorkout(RIDE)]
        )

        assert (by_lineage(plan, RUN).day, by_lineage(plan, RUN).duration_minutes) == (day(2), 30)
        assert len(changes) == 3

    def test_a_workout_that_an_earlier_action_took_out_is_refused(self) -> None:
        with pytest.raises(ActionFormatError) as caught:
            apply_(make_plan(), [SkipWorkout(RIDE), ShortenWorkout(RIDE, 30)])

        assert caught.value.problems[0].path == "actions[1].id"

    def test_the_plan_that_was_given_is_not_changed(self) -> None:
        original = make_plan()

        apply_(original, [SkipWorkout(RIDE), ReduceWeek(20)])

        assert original == make_plan()

    def test_the_past_stays_as_it_was(self) -> None:
        plan, _ = apply_(make_plan(), [ReduceWeek(50), FreeDay(day(5))])

        assert by_lineage(plan, OLD) == by_lineage(make_plan(), OLD)


def day_lineage(n: int) -> UUID:
    return UUID(f"0195f3a0-0000-7000-8000-00000000010{n}")


def full_week_plan() -> WeekPlan:
    """One hard workout per day from Monday (day 0) to Sunday (day 6)."""
    workouts = tuple(
        Workout(
            day(n),
            Sport.RUNNING,
            f"Hard {n}",
            Goal.THRESHOLD,
            60,
            segments=(
                Segment(SegmentKind.WARMUP, 900),
                Segment(SegmentKind.WORK, 2400, 1, ZoneSystem.PACE, 4),
                Segment(SegmentKind.COOLDOWN, 300),
            ),
            zone_system=ZoneSystem.PACE,
            zone=4,
            lineage=day_lineage(n),
        )
        for n in range(7)
    )
    return WeekPlan(MONDAY, workouts, "Rationale.")


class TestMarkSick:
    def test_pauses_sick_days_and_leaves_the_past_untouched(self) -> None:
        original = full_week_plan()
        # Today is Tue (day 1); 2 sick days pause Tue-Wed, then 2 return days cover Thu-Fri.
        plan, changes = apply_(original, [MarkSick(Symptoms.ABOVE_NECK, False, 2)])

        remaining_days = {w.day for w in plan.workouts}
        assert day(1) not in remaining_days
        assert day(2) not in remaining_days
        assert by_lineage(plan, day_lineage(0)) == original.workouts[0]
        assert changes == (
            "Sick pause (2 days, 2026-11-17 to 2026-11-18): 2 workouts removed",
            "Easy return (2 days, 2026-11-19 to 2026-11-20): 2 workouts made easy and shorter",
        )

    def test_pauses_multiple_workouts_on_the_same_sick_day(self) -> None:
        am = Workout(
            day(1), Sport.RUNNING, "AM", Goal.ENDURANCE, 40, slot=Slot.MORNING, lineage=RUN
        )
        pm = Workout(
            day(1), Sport.STRENGTH, "PM", Goal.STRENGTH, 30, slot=Slot.EVENING, lineage=STRENGTH
        )
        plan = WeekPlan(MONDAY, (am, pm))

        changed, changes = apply_(plan, [MarkSick(Symptoms.ABOVE_NECK, False, 1)])

        assert changed.workouts == ()
        assert changes[0] == "Sick pause (1 day, 2026-11-17): 2 workouts removed"

    @pytest.mark.parametrize(
        ("symptoms", "fever", "expected_return_days"),
        [
            (Symptoms.ABOVE_NECK, False, 2),
            (Symptoms.ABOVE_NECK, True, 4),
            (Symptoms.BELOW_NECK, False, 4),
            (Symptoms.BELOW_NECK, True, 4),
        ],
    )
    def test_return_window_depends_on_severity(
        self, symptoms: Symptoms, fever: bool, expected_return_days: int
    ) -> None:
        original = full_week_plan()
        # Today is Tue (day 1); 1 sick day => Tue (1) paused.
        # Mild: Wed (2), Thu (3) return; Fri (4), Sat (5), Sun (6) untouched.
        # Severe: Wed (2), Thu (3), Fri (4), Sat (5) return; Sun (6) untouched.
        plan, _ = apply_(original, [MarkSick(symptoms, fever, 1)])

        return_indices = range(2, 2 + expected_return_days)
        later_indices = range(2 + expected_return_days, 7)

        for n in return_indices:
            workout = by_lineage(plan, day_lineage(n))
            assert intensity_of(workout) is Intensity.EASY
            assert workout.duration_minutes == 36
            assert workout.goal is Goal.ENDURANCE
            assert workout.segments == ()
            assert workout.zone == EASY_UP_TO_ZONE

        for n in later_indices:
            assert by_lineage(plan, day_lineage(n)) == original.workouts[n]

    @pytest.mark.parametrize(
        ("goal", "expected_goal"),
        [
            (Goal.TEMPO, Goal.ENDURANCE),
            (Goal.THRESHOLD, Goal.ENDURANCE),
            (Goal.VO2MAX, Goal.ENDURANCE),
            (Goal.RECOVERY, Goal.RECOVERY),
            (Goal.ENDURANCE, Goal.ENDURANCE),
            (Goal.STRENGTH, Goal.STRENGTH),
            (Goal.OTHER, Goal.OTHER),
        ],
    )
    def test_return_days_have_no_intensity_for_every_goal(
        self, goal: Goal, expected_goal: Goal
    ) -> None:
        sport = Sport.STRENGTH if goal is Goal.STRENGTH else Sport.RUNNING
        zone_system = None if sport is Sport.STRENGTH else ZoneSystem.PACE
        zone = None if sport is Sport.STRENGTH else 5
        workout = Workout(
            day(2),
            sport,
            "Session",
            goal,
            50,
            segments=(Segment(SegmentKind.WORK, 3000, 1, ZoneSystem.PACE, 5),)
            if sport is Sport.RUNNING
            else (),
            zone_system=zone_system,
            zone=zone,
            lineage=RUN,
        )
        plan = WeekPlan(MONDAY, (workout,))

        changed, _ = apply_(plan, [MarkSick(Symptoms.ABOVE_NECK, False, 1)])

        updated = by_lineage(changed, RUN)
        assert intensity_of(updated) is Intensity.EASY
        assert updated.goal is expected_goal
        assert updated.segments == ()
        assert updated.duration_minutes == 30
        assert updated.zone == (None if zone is None else EASY_UP_TO_ZONE)

    def test_return_day_keeps_zone_1_and_respects_minimum_minutes(self) -> None:
        z1 = Workout(
            day(2),
            Sport.RUNNING,
            "Easy",
            Goal.RECOVERY,
            15,
            zone_system=ZoneSystem.HEART_RATE,
            zone=1,
            lineage=RUN,
        )
        tiny = Workout(day(3), Sport.STRENGTH, "Core", Goal.STRENGTH, 8, lineage=STRENGTH)
        plan = WeekPlan(MONDAY, (z1, tiny))

        changed, _ = apply_(plan, [MarkSick(Symptoms.ABOVE_NECK, False, 1)])

        updated_z1 = by_lineage(changed, RUN)
        assert updated_z1.zone == 1
        assert updated_z1.duration_minutes == 10
        assert intensity_of(updated_z1) is Intensity.EASY
        # Already below MIN_MINUTES: never made longer.
        assert by_lineage(changed, STRENGTH).duration_minutes == 8

    def test_illness_reaching_past_the_week_pauses_the_rest_of_this_week(self) -> None:
        original = full_week_plan()

        plan, changes = apply_(original, [MarkSick(Symptoms.BELOW_NECK, True, 10)])

        # Only Monday (past) stays in this week.
        assert [w.day for w in plan.workouts] == [day(0)]
        assert changes == (
            "Sick pause (10 days, 2026-11-17 to 2026-11-26): 6 workouts removed",
            "Easy return (4 days, 2026-11-27 to 2026-11-30): 0 workouts made easy and shorter",
        )

    def test_later_action_on_a_paused_workout_is_refused(self) -> None:
        with pytest.raises(ActionFormatError) as caught:
            apply_(
                make_plan(),
                [MarkSick(Symptoms.ABOVE_NECK, False, 1), ShortenWorkout(RUN, 30)],
            )

        assert caught.value.problems[0].path == "actions[1].id"
