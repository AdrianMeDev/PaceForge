from dataclasses import replace
from datetime import date
from typing import Any
from uuid import UUID

import pytest

from chat.actions import (
    ActionFormatError,
    FreeDay,
    MoveWorkout,
    ReduceWeek,
    ShortenWorkout,
    SkipWorkout,
    SwapSport,
    apply,
    read_actions,
)
from planning.schema import Goal, Segment, SegmentKind, Slot, Sport, WeekPlan, Workout, ZoneSystem

MONDAY = date(2026, 11, 16)
TODAY = date(2026, 11, 17)  # a Tuesday: Monday is over
RUN = UUID("0195f3a0-0000-7000-8000-000000000001")
RIDE = UUID("0195f3a0-0000-7000-8000-000000000002")
OLD = UUID("0195f3a0-0000-7000-8000-000000000003")
STRENGTH = UUID("0195f3a0-0000-7000-8000-000000000004")


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
        )

        assert actions == (
            MoveWorkout(RUN, day(2), Slot.EVENING),
            SkipWorkout(RIDE),
            SwapSport(RUN, Sport.CYCLING, 45),
            ShortenWorkout(RIDE, 60),
            ReduceWeek(20),
            FreeDay(day(5)),
        )

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


class TestWhatIsRefused:
    def test_a_tool_that_is_not_known(self) -> None:
        assert "actions[0].tool" in problems_of({"tool": "delete_everything"})
        assert "actions[0]" in problems_of("move_workout")

    def test_fields_that_are_missing_or_not_part_of_the_tool(self) -> None:
        found = problems_of({"tool": "skip_workout", "id": str(RUN), "reason": "x"})
        assert "actions[0].reason" in found
        assert "actions[0].id" in problems_of({"tool": "skip_workout"})

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
