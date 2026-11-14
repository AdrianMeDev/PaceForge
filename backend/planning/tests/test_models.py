from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from accounts.models import User
from athletes.zones import heart_rate_zones, pace_zones, power_zones
from planning.models import (
    NOTES_MAX,
    RATIONALE_MAX,
    REASON_MAX,
    STRETCHING_MAX,
    TITLE_MAX,
    ZONE_COUNT,
    PlannedWorkout,
    WeeklyPlan,
    WorkoutExport,
)
from planning.schema import Slot

pytestmark = pytest.mark.django_db

MONDAY = date(2027, 7, 12)
assert MONDAY.weekday() == 0
NEXT_MONDAY = MONDAY + timedelta(days=7)
CONFIRMED_AT = datetime(2027, 7, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def plan_fields(**fields: Any) -> dict[str, Any]:
    return {"week_start": MONDAY, **fields}


def make_plan(owner: User, **fields: Any) -> WeeklyPlan:
    return WeeklyPlan.objects.create(owner=owner, **plan_fields(**fields))


def confirmed(owner: User, **fields: Any) -> WeeklyPlan:
    return make_plan(owner, status="confirmed", confirmed_at=CONFIRMED_AT, **fields)


def workout_fields(**fields: Any) -> dict[str, Any]:
    return {
        "day": MONDAY + timedelta(days=1),
        "sport": "cycling",
        "title": "Endurance ride",
        "goal": "endurance",
        "duration_minutes": 90,
        **fields,
    }


def make_workout(plan: WeeklyPlan, **fields: Any) -> PlannedWorkout:
    return PlannedWorkout.objects.create(owner=plan.owner, plan=plan, **workout_fields(**fields))


def rejected_by_database(model: type[Any], **fields: Any) -> str:
    with pytest.raises(IntegrityError) as raised, transaction.atomic():
        model.objects.create(**fields)
    return str(raised.value)


def refused(instance: Any, field: str) -> None:
    with pytest.raises(ValidationError) as raised:
        instance.full_clean(exclude=["owner"])
    assert field in raised.value.message_dict, raised.value.message_dict


class TestLimits:
    def test_the_limits_are_written_out_on_purpose(self) -> None:
        # The other tests read the constants and would follow a change.
        assert (TITLE_MAX, NOTES_MAX, REASON_MAX, RATIONALE_MAX) == (100, 500, 200, 1000)
        assert STRETCHING_MAX == 60

    def test_the_zone_counts_are_those_of_the_zone_models(self) -> None:
        power = power_zones(250)
        by_lthr = heart_rate_zones(lthr=160)
        by_max = heart_rate_zones(max_hr=190)
        pace = pace_zones(300)
        assert power is not None and by_lthr is not None and by_max is not None
        assert pace is not None

        assert ZONE_COUNT == {
            "power": len(power.zones),
            "heart_rate": len(by_lthr.zones),
            "pace": len(pace.zones),
        }
        assert len(by_max.zones) == ZONE_COUNT["heart_rate"]


class TestAPlan:
    def test_a_plan_has_sensible_defaults(self, alice: User) -> None:
        plan = make_plan(alice)

        assert (plan.version, plan.status) == (1, "draft")
        assert plan.parent is None
        assert plan.confirmed_at is None
        assert plan.created_at is not None
        assert (plan.reason, plan.rationale) == ("", "")

    def test_the_id_is_not_a_counter(self, alice: User) -> None:
        first, second = make_plan(alice), make_plan(alice, version=2)

        assert first.pk != second.pk
        assert first.pk.version == 7

    @pytest.mark.parametrize("offset", [1, 2, 3, 4, 5, 6])
    def test_a_week_starts_on_a_monday(self, alice: User, offset: int) -> None:
        day = MONDAY + timedelta(days=offset)

        message = rejected_by_database(WeeklyPlan, owner=alice, week_start=day)
        assert "planning_week_starts_on_monday" in message
        refused(WeeklyPlan(owner=alice, week_start=day), "week_start")

    def test_any_monday_is_fine(self, alice: User) -> None:
        for weeks in range(0, 60, 7):
            make_plan(alice, week_start=MONDAY + timedelta(weeks=weeks))

    @pytest.mark.parametrize("version", [0])
    def test_versions_count_from_one(self, alice: User, version: int) -> None:
        message = rejected_by_database(WeeklyPlan, owner=alice, **plan_fields(version=version))

        assert "planning_version_from_one" in message

    def test_a_version_exists_once_per_user_and_week(self, alice: User, bob: User) -> None:
        make_plan(alice)
        make_plan(bob)
        make_plan(alice, version=2)
        make_plan(alice, week_start=NEXT_MONDAY)

        message = rejected_by_database(WeeklyPlan, owner=alice, **plan_fields())

        assert "planning_one_per_version" in message

    @pytest.mark.parametrize("status", ["draft", "confirmed", "superseded", "discarded"])
    def test_every_status_is_valid(self, alice: User, status: str) -> None:
        stamp = CONFIRMED_AT if status in {"confirmed", "superseded"} else None
        WeeklyPlan(owner=alice, **plan_fields(status=status, confirmed_at=stamp)).full_clean(
            exclude=["owner"]
        )

    @pytest.mark.parametrize(
        ("status", "stamp"),
        [
            ("draft", None),
            ("discarded", None),
            ("confirmed", CONFIRMED_AT),
            ("superseded", CONFIRMED_AT),
        ],
    )
    def test_every_status_can_be_stored_with_its_time_of_confirmation(
        self, alice: User, status: str, stamp: datetime | None
    ) -> None:
        plan = make_plan(alice, version=1, status=status, confirmed_at=stamp)

        plan.refresh_from_db()

        assert (plan.status, plan.confirmed_at) == (status, stamp)

    def test_an_unknown_status_is_refused(self, alice: User) -> None:
        refused(WeeklyPlan(owner=alice, **plan_fields(status="done")), "status")

    def test_only_one_version_of_a_week_is_confirmed(self, alice: User, bob: User) -> None:
        confirmed(alice)
        confirmed(bob)
        confirmed(alice, week_start=NEXT_MONDAY)
        make_plan(alice, version=2)
        make_plan(alice, version=3, status="superseded", confirmed_at=CONFIRMED_AT)

        message = rejected_by_database(
            WeeklyPlan,
            owner=alice,
            **plan_fields(version=4, status="confirmed", confirmed_at=CONFIRMED_AT),
        )

        assert "planning_one_confirmed_per_week" in message

    @pytest.mark.parametrize(
        ("status", "stamp"),
        [
            ("draft", CONFIRMED_AT),
            ("discarded", CONFIRMED_AT),
            ("confirmed", None),
            ("superseded", None),
        ],
    )
    def test_the_time_of_confirmation_goes_with_the_status(
        self, alice: User, status: str, stamp: datetime | None
    ) -> None:
        message = rejected_by_database(
            WeeklyPlan, owner=alice, **plan_fields(status=status, confirmed_at=stamp)
        )

        assert "planning_confirmed_at_matches_status" in message

    def test_a_plan_is_not_its_own_parent(self, alice: User) -> None:
        plan = make_plan(alice)
        plan.parent = plan

        with pytest.raises(IntegrityError), transaction.atomic():
            plan.save()

    def test_reason_and_rationale_have_limits(self, alice: User) -> None:
        WeeklyPlan(
            owner=alice, **plan_fields(reason="r" * REASON_MAX, rationale="x" * RATIONALE_MAX)
        ).full_clean(exclude=["owner"])
        refused(WeeklyPlan(owner=alice, **plan_fields(reason="r" * (REASON_MAX + 1))), "reason")
        refused(
            WeeklyPlan(owner=alice, **plan_fields(rationale="x" * (RATIONALE_MAX + 1))),
            "rationale",
        )


class TestRevisions:
    def test_a_newer_version_of_the_same_week_may_replace_an_older_one(self, alice: User) -> None:
        first = confirmed(alice)

        second = WeeklyPlan(
            owner=alice, **plan_fields(version=2, parent=first, reason="Knee hurts")
        )

        second.full_clean(exclude=["owner"])
        second.save()
        assert list(first.revisions.all()) == [second]
        assert second.reason == "Knee hurts"

    def test_a_version_cannot_replace_one_of_another_week(self, alice: User) -> None:
        other_week = make_plan(alice, week_start=NEXT_MONDAY)

        plan = WeeklyPlan(owner=alice, **plan_fields(version=2, parent=other_week))

        refused(plan, "parent")

    def test_a_version_cannot_replace_one_of_another_user(self, alice: User, bob: User) -> None:
        theirs = make_plan(bob)

        refused(WeeklyPlan(owner=alice, **plan_fields(version=2, parent=theirs)), "parent")

    @pytest.mark.parametrize("version", [1, 2])
    def test_a_version_must_be_newer_than_its_parent(self, alice: User, version: int) -> None:
        parent = make_plan(alice, version=2)

        refused(WeeklyPlan(owner=alice, **plan_fields(version=version, parent=parent)), "version")

    def test_deleting_a_parent_keeps_the_later_version(self, alice: User) -> None:
        first = make_plan(alice)
        second = make_plan(alice, version=2, parent=first)

        first.delete()

        second.refresh_from_db()
        assert second.parent is None


class TestAWorkout:
    def test_a_complete_workout_is_valid(self, alice: User) -> None:
        plan = make_plan(alice)

        workout = PlannedWorkout(owner=alice, plan=plan, **workout_fields())

        workout.full_clean(exclude=["owner"])

    def test_the_defaults(self, alice: User) -> None:
        workout = make_workout(make_plan(alice))

        assert workout.segments == []
        assert (workout.zone_system, workout.zone) == ("", None)
        assert (workout.position, workout.notes) == (0, "")
        assert workout.pk.version == 7

    def test_the_defaults_of_time_of_day_and_stretching(self, alice: User) -> None:
        workout = make_workout(make_plan(alice))

        assert (workout.slot, workout.stretching_minutes) == ("", 0)

    @pytest.mark.parametrize("slot", ["", "morning", "afternoon", "evening"])
    def test_every_time_of_day_is_valid(self, alice: User, slot: str) -> None:
        PlannedWorkout(owner=alice, plan=make_plan(alice), **workout_fields(slot=slot)).full_clean(
            exclude=["owner"]
        )

    @pytest.mark.parametrize("slot", ["noon", "Morning", "night", "0"])
    def test_another_time_of_day_is_refused(self, alice: User, slot: str) -> None:
        workout = PlannedWorkout(owner=alice, plan=make_plan(alice), **workout_fields(slot=slot))

        refused(workout, "slot")

    @pytest.mark.parametrize("minutes", [0, 1, 30, 60])
    def test_up_to_an_hour_of_stretching_is_valid(self, alice: User, minutes: int) -> None:
        PlannedWorkout(
            owner=alice, plan=make_plan(alice), **workout_fields(stretching_minutes=minutes)
        ).full_clean(exclude=["owner"])

    @pytest.mark.parametrize("minutes", [STRETCHING_MAX + 1, 100, 1000])
    def test_more_stretching_is_refused_by_the_database(self, alice: User, minutes: int) -> None:
        message = rejected_by_database(
            PlannedWorkout,
            owner=alice,
            plan=make_plan(alice),
            **workout_fields(stretching_minutes=minutes),
        )

        assert "planning_stretching_in_range" in message

    def test_the_database_refuses_an_unknown_time_of_day(self, alice: User) -> None:
        message = rejected_by_database(
            PlannedWorkout, owner=alice, plan=make_plan(alice), **workout_fields(slot="noon")
        )

        assert "planning_slot_is_known" in message

    def test_the_times_of_day_are_those_of_the_format(self) -> None:
        assert [slot.value for slot in PlannedWorkout.Slot] == [slot.value for slot in Slot]

    @pytest.mark.parametrize("sport", ["running", "cycling", "swimming", "strength"])
    def test_every_sport_is_valid(self, alice: User, sport: str) -> None:
        PlannedWorkout(
            owner=alice, plan=make_plan(alice), **workout_fields(sport=sport)
        ).full_clean(exclude=["owner"])

    @pytest.mark.parametrize(
        "goal",
        ["recovery", "endurance", "tempo", "threshold", "vo2max", "strength", "other"],
    )
    def test_every_goal_is_valid(self, alice: User, goal: str) -> None:
        PlannedWorkout(owner=alice, plan=make_plan(alice), **workout_fields(goal=goal)).full_clean(
            exclude=["owner"]
        )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("sport", "rowing"),
            ("goal", "fun"),
            ("zone_system", "rpe"),
            ("sport", ""),
            ("goal", ""),
        ],
    )
    def test_unknown_choices_are_refused(self, alice: User, field: str, value: str) -> None:
        workout = PlannedWorkout(
            owner=alice, plan=make_plan(alice), **workout_fields(**{field: value})
        )

        refused(workout, field)

    def test_a_title_is_needed_and_limited(self, alice: User) -> None:
        plan = make_plan(alice)
        PlannedWorkout(owner=alice, plan=plan, **workout_fields(title="t" * TITLE_MAX)).full_clean(
            exclude=["owner"]
        )
        refused(PlannedWorkout(owner=alice, plan=plan, **workout_fields(title="")), "title")
        refused(
            PlannedWorkout(owner=alice, plan=plan, **workout_fields(title="t" * (TITLE_MAX + 1))),
            "title",
        )

    def test_the_database_refuses_an_empty_title(self, alice: User) -> None:
        message = rejected_by_database(
            PlannedWorkout,
            owner=alice,
            plan=make_plan(alice),
            **workout_fields(title=""),
        )

        assert "planning_workout_has_a_title" in message

    def test_notes_are_limited(self, alice: User) -> None:
        plan = make_plan(alice)
        PlannedWorkout(owner=alice, plan=plan, **workout_fields(notes="n" * NOTES_MAX)).full_clean(
            exclude=["owner"]
        )
        refused(
            PlannedWorkout(owner=alice, plan=plan, **workout_fields(notes="n" * (NOTES_MAX + 1))),
            "notes",
        )

    @pytest.mark.parametrize("minutes", [1, 90, 1440])
    def test_a_duration_between_a_minute_and_a_day_is_valid(
        self, alice: User, minutes: int
    ) -> None:
        PlannedWorkout(
            owner=alice, plan=make_plan(alice), **workout_fields(duration_minutes=minutes)
        ).full_clean(exclude=["owner"])

    @pytest.mark.parametrize("minutes", [0, 1441, 5000])
    def test_other_durations_are_refused_by_the_database(self, alice: User, minutes: int) -> None:
        message = rejected_by_database(
            PlannedWorkout,
            owner=alice,
            plan=make_plan(alice),
            **workout_fields(duration_minutes=minutes),
        )

        assert "planning_duration_in_range" in message

    def test_the_duration_is_needed(self, alice: User) -> None:
        workout = PlannedWorkout(
            owner=alice, plan=make_plan(alice), **workout_fields(duration_minutes=None)
        )

        refused(workout, "duration_minutes")

    def test_a_slot_holds_one_workout(self, alice: User) -> None:
        plan = make_plan(alice)
        make_workout(plan, position=0)
        make_workout(plan, position=1)
        make_workout(plan, position=0, day=MONDAY)
        make_workout(make_plan(alice, version=2), position=0)

        message = rejected_by_database(
            PlannedWorkout, owner=alice, plan=plan, **workout_fields(position=0)
        )

        assert "planning_one_workout_per_slot" in message

    def test_workouts_come_in_the_order_of_day_and_position(self, alice: User) -> None:
        plan = make_plan(alice)
        late = make_workout(plan, day=MONDAY + timedelta(days=3), position=0)
        second = make_workout(plan, day=MONDAY + timedelta(days=1), position=1)
        first = make_workout(plan, day=MONDAY + timedelta(days=1), position=0)

        assert list(plan.workouts.all()) == [first, second, late]


class TestIntensity:
    @pytest.mark.parametrize(
        ("system", "zone"),
        [("power", 1), ("power", 7), ("heart_rate", 1), ("heart_rate", 5), ("pace", 5)],
    )
    def test_a_zone_that_exists_in_its_system_is_valid(
        self, alice: User, system: str, zone: int
    ) -> None:
        make_workout(make_plan(alice), zone_system=system, zone=zone)

    @pytest.mark.parametrize(
        ("system", "zone"),
        [("power", 8), ("heart_rate", 6), ("pace", 6), ("power", 0), ("pace", 0), ("power", 100)],
    )
    def test_a_zone_that_does_not_exist_is_refused_by_the_database(
        self, alice: User, system: str, zone: int
    ) -> None:
        message = rejected_by_database(
            PlannedWorkout,
            owner=alice,
            plan=make_plan(alice),
            **workout_fields(zone_system=system, zone=zone),
        )

        assert "planning_zone_exists_in_its_system" in message

    @pytest.mark.parametrize(("system", "zone"), [("power", None), ("", 3), ("pace", None)])
    def test_system_and_zone_come_together(
        self, alice: User, system: str, zone: int | None
    ) -> None:
        message = rejected_by_database(
            PlannedWorkout,
            owner=alice,
            plan=make_plan(alice),
            **workout_fields(zone_system=system, zone=zone),
        )

        # a zone without a system breaks both rules and the database names one of them
        assert "planning_zone_" in message

    @pytest.mark.parametrize(("system", "zone"), [("power", None), ("pace", None)])
    def test_a_system_without_a_zone_breaks_the_pairing_rule(
        self, alice: User, system: str, zone: int | None
    ) -> None:
        message = rejected_by_database(
            PlannedWorkout,
            owner=alice,
            plan=make_plan(alice),
            **workout_fields(zone_system=system, zone=zone),
        )

        assert "planning_zone_with_its_system" in message

    def test_the_zone_counts_are_the_documented_ones(self) -> None:
        assert ZONE_COUNT == {"power": 7, "heart_rate": 5, "pace": 5}


class TestAWorkoutInItsPlan:
    def test_the_whole_week_is_inside(self, alice: User) -> None:
        plan = make_plan(alice)
        for offset in range(7):
            PlannedWorkout(
                owner=alice, plan=plan, **workout_fields(day=MONDAY + timedelta(days=offset))
            ).full_clean(exclude=["owner"])

    @pytest.mark.parametrize("offset", [-1, 7, 14, -30])
    def test_a_day_outside_the_week_is_refused(self, alice: User, offset: int) -> None:
        workout = PlannedWorkout(
            owner=alice,
            plan=make_plan(alice),
            **workout_fields(day=MONDAY + timedelta(days=offset)),
        )

        refused(workout, "day")

    def test_a_workout_belongs_to_a_plan_of_the_same_user(self, alice: User, bob: User) -> None:
        workout = PlannedWorkout(owner=alice, plan=make_plan(bob), **workout_fields())

        refused(workout, "plan")

    @pytest.mark.parametrize("segments", [{}, "x", 5, None])
    def test_segments_are_a_list(self, alice: User, segments: Any) -> None:
        workout = PlannedWorkout(
            owner=alice, plan=make_plan(alice), **workout_fields(segments=segments)
        )

        with pytest.raises(ValidationError) as raised:
            workout.full_clean(exclude=["owner"])
        assert "segments" in raised.value.message_dict

    def test_segments_keep_what_they_were_given(self, alice: User) -> None:
        segments = [{"kind": "work", "seconds": 600, "zone_system": "power", "zone": 4}]
        workout = make_workout(make_plan(alice), segments=segments)

        workout.refresh_from_db()

        assert workout.segments == segments

    def test_the_text_names_neither_title_nor_notes(self, alice: User) -> None:
        workout = make_workout(make_plan(alice), title="secret knee test", notes="secret diagnosis")

        text = str(workout)

        assert "secret" not in text
        assert str(alice.pk) in text
        assert "cycling" in text

    def test_the_text_of_a_plan_names_neither_reason_nor_rationale(self, alice: User) -> None:
        text = str(make_plan(alice, reason="secret reason", rationale="secret rationale"))

        assert "secret" not in text
        assert str(alice.pk) in text
        assert "v1" in text


class TestOwnership:
    def test_for_user_shows_only_the_own_rows(self, alice: User, bob: User) -> None:
        mine = make_plan(alice)
        theirs = make_plan(bob)
        my_workout = make_workout(mine)
        make_workout(theirs)

        assert list(WeeklyPlan.objects.for_user(alice)) == [mine]
        assert list(PlannedWorkout.objects.for_user(alice)) == [my_workout]

    def test_an_anonymous_user_owns_nothing(self, alice: User) -> None:
        make_workout(make_plan(alice))

        assert not WeeklyPlan.objects.for_user(AnonymousUser()).exists()
        assert not PlannedWorkout.objects.for_user(AnonymousUser()).exists()

    def test_deleting_a_plan_deletes_its_workouts_only(self, alice: User) -> None:
        plan, other = make_plan(alice), make_plan(alice, version=2)
        make_workout(plan)
        keep = make_workout(other)

        plan.delete()

        assert list(PlannedWorkout.objects.all()) == [keep]

    def test_deleting_a_user_deletes_their_plans_and_workouts(self, alice: User, bob: User) -> None:
        make_workout(make_plan(alice))
        keep = make_workout(make_plan(bob))

        alice.delete()

        assert list(PlannedWorkout.objects.all()) == [keep]
        assert WeeklyPlan.objects.count() == 1


class TestAPlanThatIsNoDraft:
    @pytest.mark.parametrize("status", ["confirmed", "superseded", "discarded"])
    def test_its_workouts_cannot_be_added(self, alice: User, status: str) -> None:
        stamp = CONFIRMED_AT if status in {"confirmed", "superseded"} else None
        plan = make_plan(alice, status=status, confirmed_at=stamp)

        with pytest.raises(ValidationError, match="not a draft"):
            make_workout(plan)

        assert PlannedWorkout.objects.count() == 0

    def test_its_workouts_cannot_be_changed(self, alice: User) -> None:
        plan = make_plan(alice)
        workout = make_workout(plan)
        WeeklyPlan.objects.filter(pk=plan.pk).update(status="confirmed", confirmed_at=CONFIRMED_AT)
        workout.plan.refresh_from_db()

        workout.title = "Changed"
        with pytest.raises(ValidationError, match="not a draft"):
            workout.save()

        workout.refresh_from_db()
        assert workout.title == "Endurance ride"

    def test_the_workouts_of_a_draft_can_be_added_and_changed(self, alice: User) -> None:
        workout = make_workout(make_plan(alice))

        workout.title = "Changed"
        workout.save()

        workout.refresh_from_db()
        assert workout.title == "Changed"


def export_fields(owner: User, **fields: Any) -> dict[str, Any]:
    return {
        "owner": owner,
        "week_start": MONDAY,
        "external_id": "paceforge-1",
        "status": "synced",
        "event_id": 4711,
        **fields,
    }


class TestWorkoutExport:
    def test_a_synced_export(self, alice: User) -> None:
        workout = make_workout(make_plan(alice))

        export = WorkoutExport.objects.create(**export_fields(alice, workout=workout))

        assert export.workout == workout
        assert export.error_code == ""
        assert export.pushed_at is not None
        assert list(workout.exports.all()) == [export]

    def test_a_failed_export_has_a_code_and_may_have_an_event(self, alice: User) -> None:
        WorkoutExport.objects.create(
            **export_fields(alice, status="failed", event_id=None, error_code="rejected")
        )
        WorkoutExport.objects.create(
            **export_fields(alice, external_id="paceforge-2", status="failed", error_code="x")
        )

        assert WorkoutExport.objects.filter(status="failed").count() == 2

    @pytest.mark.parametrize(
        "changes",
        [
            {"status": "synced", "event_id": None},
            {"status": "synced", "error_code": "rejected"},
            {"status": "failed", "event_id": None, "error_code": ""},
            {"status": "failed", "error_code": ""},
            {"status": "pending"},
            {"week_start": MONDAY + timedelta(days=1)},
        ],
    )
    def test_the_database_refuses_an_inconsistent_state(
        self, alice: User, changes: dict[str, Any]
    ) -> None:
        message = rejected_by_database(WorkoutExport, **export_fields(alice, **changes))

        assert "planning_export" in message

    def test_an_external_id_is_used_once_per_user(self, alice: User, bob: User) -> None:
        WorkoutExport.objects.create(**export_fields(alice))
        WorkoutExport.objects.create(**export_fields(bob))  # another user: fine

        message = rejected_by_database(WorkoutExport, **export_fields(alice, event_id=1))

        assert "planning_one_export_per_external_id" in message

    def test_the_export_stays_when_the_workout_is_deleted(self, alice: User) -> None:
        plan = make_plan(alice)
        export = WorkoutExport.objects.create(**export_fields(alice, workout=make_workout(plan)))

        plan.delete()

        export.refresh_from_db()
        assert export.workout is None
        assert export.event_id == 4711

    def test_for_user_shows_only_the_own_rows(self, alice: User, bob: User) -> None:
        mine = WorkoutExport.objects.create(**export_fields(alice))
        WorkoutExport.objects.create(**export_fields(bob))

        assert list(WorkoutExport.objects.for_user(alice)) == [mine]
        assert not WorkoutExport.objects.for_user(AnonymousUser()).exists()

    def test_deleting_a_user_deletes_their_exports(self, alice: User, bob: User) -> None:
        WorkoutExport.objects.create(**export_fields(alice))
        keep = WorkoutExport.objects.create(**export_fields(bob))

        alice.delete()

        assert list(WorkoutExport.objects.all()) == [keep]

    def test_it_shows_no_free_text(self, alice: User) -> None:
        export = WorkoutExport.objects.create(
            **export_fields(alice, status="failed", error_code="rejected")
        )

        assert str(export) == f"Export of user {alice.pk} for the week of {MONDAY} (failed)"
