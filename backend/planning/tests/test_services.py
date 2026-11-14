import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection
from django.db.models import QuerySet

from accounts.models import User
from athletes.models import ThresholdValue
from availability.models import AvailabilitySettings, UnavailablePeriod, WeekdayMinutes
from planning import services
from planning.models import PlannedWorkout, WeeklyPlan
from planning.schema import (
    Goal,
    Segment,
    SegmentKind,
    Slot,
    Sport,
    WeekPlan,
    Workout,
    ZoneSystem,
    to_json,
)
from planning.services import (
    PlanNotConfirmable,
    PlanNotFound,
    PlanStateError,
    canonical,
    confirm,
    discard,
    get,
    load,
    save_draft,
    validate,
)

pytestmark = pytest.mark.django_db

MONDAY = date(2027, 7, 12)
NEXT_MONDAY = MONDAY + timedelta(days=7)
NOW = datetime(2027, 7, 1, 9, 30, tzinfo=UTC)
Status = WeeklyPlan.Status


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(services, "_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    return prepared(User.objects.create_user("alice@example.com"))


@pytest.fixture
def bob() -> User:
    return prepared(User.objects.create_user("bob@example.com"))


def prepared(user: User) -> User:
    """A user who can train on Monday, Wednesday, Friday and Saturday and has an FTP and a pace."""
    for weekday, minutes in enumerate([90, 0, 90, 0, 120, 120, 0]):
        WeekdayMinutes.objects.create(owner=user, weekday=weekday, minutes=minutes)
    for sport, metric in (("ride", "ftp"), ("run", "threshold_pace")):
        ThresholdValue.objects.create(
            owner=user, sport=sport, metric=metric, value=250, source="manual", basis="test"
        )
    return user


def workout(monday: date, offset: int, minutes: int, **fields: Any) -> Workout:
    data: dict[str, Any] = {
        "day": monday + timedelta(days=offset),
        "sport": Sport.CYCLING,
        "title": "Ride",
        "goal": Goal.ENDURANCE,
        "duration_minutes": minutes,
        **fields,
    }
    return Workout(**data)


def good_week(monday: date = MONDAY, rationale: str = "Build the base") -> WeekPlan:
    return WeekPlan(
        monday,
        (
            workout(
                monday,
                0,
                90,
                zone_system=ZoneSystem.POWER,
                zone=2,
                segments=(Segment(SegmentKind.STEADY, 5400, 1, ZoneSystem.POWER, 2),),
            ),
            workout(
                monday,
                2,
                60,
                sport=Sport.RUNNING,
                zone_system=ZoneSystem.PACE,
                zone=3,
                notes="Easy",
            ),
            workout(
                monday,
                4,
                100,
                sport=Sport.RUNNING,
                goal=Goal.THRESHOLD,
                segments=(
                    Segment(SegmentKind.WARMUP, 1200, 1, ZoneSystem.PACE, 1),
                    Segment(SegmentKind.WORK, 600, 4, ZoneSystem.PACE, 4),
                    Segment(SegmentKind.RECOVERY, 300, 4, ZoneSystem.PACE, 1),
                    Segment(SegmentKind.COOLDOWN, 1200, 1, ZoneSystem.PACE, 1),
                ),
            ),
            workout(monday, 5, 90, zone_system=ZoneSystem.POWER, zone=2),
        ),
        rationale,
    )


def bad_week(monday: date = MONDAY) -> WeekPlan:
    return WeekPlan(monday, (workout(monday, 1, 60),))  # Tuesday offers nothing


def draft(user: User, plan: WeekPlan | None = None, **kwargs: Any) -> WeeklyPlan:
    return save_draft(user, plan or good_week(), **kwargs)


class TestSavingADraft:
    def test_a_plan_is_stored_as_a_draft_of_version_one(self, alice: User) -> None:
        plan = draft(alice)

        assert (plan.owner, plan.week_start, plan.version, plan.status) == (
            alice,
            MONDAY,
            1,
            Status.DRAFT,
        )
        assert plan.confirmed_at is None
        assert plan.parent is None
        assert plan.rationale == "Build the base"
        assert PlannedWorkout.objects.filter(plan=plan).count() == 4

    def test_the_workouts_are_stored_completely(self, alice: User) -> None:
        plan = draft(alice)

        row = PlannedWorkout.objects.get(plan=plan, day=MONDAY + timedelta(days=4))

        assert (row.owner, row.sport, row.goal, row.duration_minutes) == (
            alice,
            "running",
            "threshold",
            100,
        )
        assert (row.zone_system, row.zone, row.title, row.notes) == ("", None, "Ride", "")
        assert [s["kind"] for s in row.segments] == ["warmup", "work", "recovery", "cooldown"]
        assert row.segments[1] == {
            "kind": "work",
            "seconds": 600,
            "repeat": 4,
            "zone_system": "pace",
            "zone": 4,
        }

    def test_the_zone_of_a_session_is_stored(self, alice: User) -> None:
        plan = draft(alice)

        row = PlannedWorkout.objects.get(plan=plan, day=MONDAY + timedelta(days=2))

        assert (row.zone_system, row.zone, row.notes) == ("pace", 3, "Easy")

    def test_workouts_of_one_day_get_their_places_in_the_order_given(self, alice: User) -> None:
        plan = draft(
            alice,
            WeekPlan(
                MONDAY,
                (
                    workout(MONDAY, 0, 30, title="Second of the day"),
                    workout(MONDAY, 3, 30),
                    workout(MONDAY, 0, 31, title="Third", goal=Goal.TEMPO),
                    workout(MONDAY, 0, 32, title="Fourth", goal=Goal.RECOVERY),
                ),
            ),
        )

        places = [
            (w.day.weekday(), w.position, w.duration_minutes)
            for w in PlannedWorkout.objects.filter(plan=plan)
        ]

        assert places == [(0, 0, 30), (0, 1, 31), (0, 2, 32), (3, 0, 30)]

    def test_an_empty_week_can_be_stored(self, alice: User) -> None:
        plan = draft(alice, WeekPlan(MONDAY))

        assert PlannedWorkout.objects.filter(plan=plan).count() == 0

    def test_a_plan_with_things_wrong_can_still_be_stored_as_a_draft(self, alice: User) -> None:
        stray = WeekPlan(MONDAY, (workout(MONDAY, 9, 60), workout(MONDAY, 1, 600)))

        plan = draft(alice, stray)

        assert PlannedWorkout.objects.filter(plan=plan).count() == 2
        assert not validate(alice, plan.pk).valid

    def test_versions_of_a_week_count_up(self, alice: User) -> None:
        first = draft(alice)
        second = draft(alice)
        third = draft(alice)

        assert [first.version, second.version, third.version] == [1, 2, 3]

    def test_a_discarded_version_still_counts(self, alice: User) -> None:
        first = draft(alice)
        discard(alice, first.pk)

        assert draft(alice).version == 2

    def test_every_week_and_every_user_counts_on_its_own(self, alice: User, bob: User) -> None:
        draft(alice)
        draft(alice)

        assert draft(alice, good_week(NEXT_MONDAY)).version == 1
        assert draft(bob).version == 1

    def test_a_revision_points_to_what_it_replaces_and_says_why(self, alice: User) -> None:
        first = draft(alice)

        second = draft(alice, reason="  Knee hurts  ", parent=first.pk)

        assert (second.parent, second.reason, second.version) == (first, "Knee hurts", 2)
        assert list(first.revisions.all()) == [second]

    def test_a_revision_must_be_of_the_same_week(self, alice: User) -> None:
        other_week = draft(alice, good_week(NEXT_MONDAY))

        with pytest.raises(ValueError, match="same week"):
            draft(alice, parent=other_week.pk)

        assert WeeklyPlan.objects.count() == 1

    def test_a_plan_of_another_user_cannot_be_replaced(self, alice: User, bob: User) -> None:
        theirs = draft(bob)

        with pytest.raises(PlanNotFound):
            draft(alice, parent=theirs.pk)

        assert WeeklyPlan.objects.filter(owner=alice).count() == 0

    def test_an_unknown_parent_is_not_found(self, alice: User) -> None:
        with pytest.raises(PlanNotFound):
            draft(alice, parent=uuid4())

    @pytest.mark.parametrize("reason", ["x" * 201, "two\nlines", "tab\there", "bell\x07", "a b"])
    def test_a_reason_is_one_short_line_of_plain_text(self, alice: User, reason: str) -> None:
        with pytest.raises(ValidationError) as raised:
            draft(alice, reason=reason)

        assert "reason" in raised.value.message_dict
        assert WeeklyPlan.objects.count() == 0

    def test_a_reason_of_200_characters_is_fine(self, alice: User) -> None:
        assert draft(alice, reason="r" * 200).reason == "r" * 200

    def test_nothing_is_stored_when_the_workouts_cannot_be_(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("database trouble")

        monkeypatch.setattr(QuerySet, "bulk_create", broken)

        with pytest.raises(RuntimeError):
            draft(alice)
        monkeypatch.undo()

        assert WeeklyPlan.objects.count() == 0
        assert PlannedWorkout.objects.count() == 0

    def test_a_race_for_the_version_number_is_retried_once(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = services._store
        calls: list[int] = []

        def lose_the_race(*args: Any, **kwargs: Any) -> WeeklyPlan:
            calls.append(1)
            if len(calls) == 1:
                raise IntegrityError("planning_one_per_version")
            return real(*args, **kwargs)

        monkeypatch.setattr(services, "_store", lose_the_race)

        plan = draft(alice)

        assert len(calls) == 2
        assert plan.version == 1

    def test_a_second_failure_is_not_hidden(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def always(*args: Any, **kwargs: Any) -> WeeklyPlan:
            raise IntegrityError("planning_one_per_version")

        monkeypatch.setattr(services, "_store", always)

        with pytest.raises(IntegrityError):
            draft(alice)


class TestLoading:
    def test_a_plan_comes_back_as_it_went_in(self, alice: User) -> None:
        original = good_week()

        plan = draft(alice, original)

        assert load(alice, plan.pk) == canonical(original)

    def test_the_workouts_come_by_day_and_then_in_the_order_given(self, alice: User) -> None:
        scrambled = WeekPlan(
            MONDAY,
            (
                workout(MONDAY, 4, 40, title="Friday"),
                workout(MONDAY, 0, 41, title="Monday 1"),
                workout(MONDAY, 2, 42, title="Wednesday"),
                workout(MONDAY, 0, 43, title="Monday 2", goal=Goal.TEMPO),
            ),
        )

        plan = draft(alice, scrambled)

        assert [w.title for w in load(alice, plan.pk).workouts] == [
            "Monday 1",
            "Monday 2",
            "Wednesday",
            "Friday",
        ]

    def test_time_of_day_and_stretching_are_stored_and_read_back(self, alice: User) -> None:
        plan = draft(
            alice,
            WeekPlan(
                MONDAY,
                (
                    workout(MONDAY, 0, 50, title="Run", slot=Slot.MORNING, stretching_minutes=10),
                    workout(MONDAY, 0, 60, title="Ride", slot=Slot.AFTERNOON),
                    workout(MONDAY, 2, 40, title="Plain"),
                ),
            ),
        )

        rows = list(PlannedWorkout.objects.filter(plan=plan))
        assert [(r.title, r.slot, r.stretching_minutes) for r in rows] == [
            ("Run", "morning", 10),
            ("Ride", "afternoon", 0),
            ("Plain", "", 0),
        ]
        read = load(alice, plan.pk).workouts
        assert [(w.title, w.slot, w.stretching_minutes) for w in read] == [
            ("Run", Slot.MORNING, 10),
            ("Ride", Slot.AFTERNOON, 0),
            ("Plain", None, 0),
        ]

    def test_the_positions_follow_the_times_of_day_whatever_the_order_given(
        self, alice: User
    ) -> None:
        plan = draft(
            alice,
            WeekPlan(
                MONDAY,
                (
                    workout(MONDAY, 1, 30, title="Evening", slot=Slot.EVENING),
                    workout(MONDAY, 1, 31, title="No time"),
                    workout(MONDAY, 1, 32, title="Morning", slot=Slot.MORNING),
                ),
            ),
        )

        rows = PlannedWorkout.objects.filter(plan=plan).order_by("position")

        assert [(r.position, r.title) for r in rows] == [
            (0, "Morning"),
            (1, "Evening"),
            (2, "No time"),
        ]
        assert [w.title for w in load(alice, plan.pk).workouts] == ["Morning", "Evening", "No time"]

    def test_a_plan_that_was_saved_before_these_fields_reads_without_them(
        self, alice: User
    ) -> None:
        plan = draft(alice, WeekPlan(MONDAY, (workout(MONDAY, 0, 30),)))
        PlannedWorkout.objects.filter(plan=plan).update(slot="", stretching_minutes=0)

        (read,) = load(alice, plan.pk).workouts

        assert (read.slot, read.stretching_minutes) == (None, 0)

    def test_the_findings_of_a_double_day_point_into_the_stored_order(self, alice: User) -> None:
        # given evening first: stored and validated as morning (0), evening (1)
        plan = draft(
            alice,
            WeekPlan(
                MONDAY,
                (
                    workout(MONDAY, 1, 30, slot=Slot.EVENING),
                    workout(MONDAY, 1, 40, slot=Slot.MORNING),
                ),
            ),
        )

        stored = load(alice, plan.pk)

        assert [w.slot for w in stored.workouts] == [Slot.MORNING, Slot.EVENING]
        assert stored == canonical(stored)

    def test_the_position_decides_the_order_within_a_day_not_the_id(self, alice: User) -> None:
        plan = draft(
            alice,
            WeekPlan(
                MONDAY,
                (
                    workout(MONDAY, 0, 30, title="Stored first"),
                    workout(MONDAY, 0, 31, title="Stored second", goal=Goal.TEMPO),
                ),
            ),
        )
        PlannedWorkout.objects.filter(plan=plan, title="Stored first").update(position=5)
        PlannedWorkout.objects.filter(plan=plan, title="Stored second").update(position=2)

        assert [w.title for w in load(alice, plan.pk).workouts] == ["Stored second", "Stored first"]

    def test_the_canonical_form_puts_the_morning_before_the_evening_of_a_day(self) -> None:
        plan = WeekPlan(
            MONDAY,
            (
                workout(MONDAY, 1, 10, slot=Slot.EVENING),
                workout(MONDAY, 1, 20, slot=Slot.MORNING),
                workout(MONDAY, 0, 30, slot=Slot.EVENING),
                workout(MONDAY, 1, 40, slot=Slot.AFTERNOON),
                workout(MONDAY, 1, 50),
                workout(MONDAY, 1, 60, slot=Slot.MORNING),
            ),
        )

        # day 0 first; day 1: morning (in the order given), afternoon, evening, then no time
        assert [w.duration_minutes for w in canonical(plan).workouts] == [30, 20, 60, 40, 10, 50]
        assert canonical(canonical(plan)) == canonical(plan)

    def test_the_canonical_form_keeps_stretching_and_time_of_day(self) -> None:
        plan = WeekPlan(MONDAY, (workout(MONDAY, 0, 30, slot=Slot.MORNING, stretching_minutes=10),))

        (result,) = canonical(plan).workouts

        assert (result.slot, result.stretching_minutes) == (Slot.MORNING, 10)

    def test_the_canonical_form_sorts_by_day_and_keeps_the_order_within_a_day(self) -> None:
        plan = WeekPlan(
            MONDAY,
            (
                workout(MONDAY, 3, 10),
                workout(MONDAY, 0, 20),
                workout(MONDAY, 0, 30),
                workout(MONDAY, 1, 40),
            ),
        )

        assert [w.duration_minutes for w in canonical(plan).workouts] == [20, 30, 40, 10]
        assert canonical(plan).week_start == MONDAY
        assert canonical(canonical(plan)) == canonical(plan)

    def test_the_rationale_and_an_empty_week_survive(self, alice: User) -> None:
        plan = draft(alice, WeekPlan(MONDAY, (), "Rest week"))

        assert load(alice, plan.pk) == WeekPlan(MONDAY, (), "Rest week")

    def test_what_is_loaded_is_valid_json_again(self, alice: User) -> None:
        plan = draft(alice)

        assert to_json(load(alice, plan.pk))["workouts"][2]["segments"][1]["repeat"] == 4

    def test_a_plan_of_another_user_is_not_found(self, alice: User, bob: User) -> None:
        theirs = draft(bob)

        with pytest.raises(PlanNotFound):
            load(alice, theirs.pk)
        with pytest.raises(PlanNotFound):
            get(alice, theirs.pk)

    def test_an_unknown_id_is_not_found(self, alice: User) -> None:
        with pytest.raises(PlanNotFound):
            load(alice, uuid4())


class TestValidating:
    def test_a_good_week_is_valid(self, alice: User) -> None:
        report = validate(alice, draft(alice).pk)

        assert report.valid
        assert report.findings == ()

    def test_a_bad_week_says_why(self, alice: User) -> None:
        report = validate(alice, draft(alice, bad_week()).pk)

        assert [f.code for f in report.errors] == ["day_over_capacity"]
        assert report.errors[0].path == "workouts[0]"

    def test_the_data_of_now_counts_not_the_data_of_when_it_was_stored(self, alice: User) -> None:
        plan = draft(alice)
        assert validate(alice, plan.pk).valid

        UnavailablePeriod.objects.create(
            owner=alice, kind="illness", start_date=MONDAY, end_date=MONDAY
        )

        report = validate(alice, plan.pk)

        # Monday is lost, and the week then offers 330 minutes for 340 planned
        assert [f.code for f in report.errors] == ["day_in_absence", "week_over_capacity"]

    def test_a_weekly_budget_added_later_counts(self, alice: User) -> None:
        plan = draft(alice)
        AvailabilitySettings.objects.create(owner=alice, weekly_budget_minutes=200)

        assert "week_over_capacity" in [f.code for f in validate(alice, plan.pk).errors]

    def test_a_plan_of_another_user_is_not_found(self, alice: User, bob: User) -> None:
        with pytest.raises(PlanNotFound):
            validate(alice, draft(bob).pk)

    def test_the_thresholds_of_the_user_decide_which_zones_can_be_used(self, alice: User) -> None:
        plan = draft(alice)
        ThresholdValue.objects.filter(owner=alice, sport="ride").delete()

        codes = [f.code for f in validate(alice, plan.pk).errors]

        # Monday (session and segment) and Saturday ride in power zones
        assert codes == ["zone_system_unavailable"] * 3


class TestConfirming:
    def test_a_good_draft_is_confirmed_with_the_time(self, alice: User) -> None:
        plan = draft(alice)

        confirmed = confirm(alice, plan.pk)

        assert (confirmed.status, confirmed.confirmed_at) == (Status.CONFIRMED, NOW)
        stored = WeeklyPlan.objects.get(pk=plan.pk)
        assert (stored.status, stored.confirmed_at) == (Status.CONFIRMED, NOW)

    def test_a_plan_with_an_error_is_refused_and_nothing_changes(self, alice: User) -> None:
        plan = draft(alice, bad_week())

        with pytest.raises(PlanNotConfirmable) as raised:
            confirm(alice, plan.pk)

        assert not raised.value.report.valid
        assert [f.code for f in raised.value.report.errors] == ["day_over_capacity"]
        stored = WeeklyPlan.objects.get(pk=plan.pk)
        assert (stored.status, stored.confirmed_at) == (Status.DRAFT, None)

    def test_the_refusal_says_nothing_but_that_there_are_errors(self, alice: User) -> None:
        with pytest.raises(PlanNotConfirmable) as raised:
            confirm(alice, draft(alice, bad_week()).pk)

        assert str(raised.value) == "The plan has errors and cannot be confirmed."

    def test_warnings_do_not_stop_it(self, alice: User) -> None:
        hard = WeekPlan(
            MONDAY,
            (
                workout(MONDAY, 4, 60, goal=Goal.THRESHOLD),
                workout(MONDAY, 5, 60, goal=Goal.VO2MAX),
            ),
        )
        plan = draft(alice, hard)
        assert [f.code for f in validate(alice, plan.pk).warnings] == ["hard_days_in_a_row"]

        assert confirm(alice, plan.pk).status == Status.CONFIRMED

    def test_a_plan_that_was_fine_but_is_not_any_more_cannot_be_confirmed(
        self, alice: User
    ) -> None:
        plan = draft(alice)
        UnavailablePeriod.objects.create(
            owner=alice, kind="illness", start_date=MONDAY, end_date=MONDAY + timedelta(days=2)
        )

        with pytest.raises(PlanNotConfirmable) as raised:
            confirm(alice, plan.pk)

        assert "day_in_absence" in [f.code for f in raised.value.report.errors]
        assert WeeklyPlan.objects.get(pk=plan.pk).status == Status.DRAFT

    def test_the_next_version_replaces_the_confirmed_one(self, alice: User) -> None:
        first = confirm(alice, draft(alice).pk)
        second = draft(alice, parent=first.pk, reason="Changed")

        confirm(alice, second.pk)

        old, new = WeeklyPlan.objects.get(pk=first.pk), WeeklyPlan.objects.get(pk=second.pk)
        assert (old.status, new.status) == (Status.SUPERSEDED, Status.CONFIRMED)
        assert old.confirmed_at == NOW  # the time of its own confirmation stays
        assert WeeklyPlan.objects.filter(status=Status.CONFIRMED).count() == 1

    def test_a_refused_new_version_leaves_the_confirmed_one_in_force(self, alice: User) -> None:
        first = confirm(alice, draft(alice).pk)
        second = draft(alice, bad_week(), parent=first.pk)

        with pytest.raises(PlanNotConfirmable):
            confirm(alice, second.pk)

        assert WeeklyPlan.objects.get(pk=first.pk).status == Status.CONFIRMED

    def test_only_the_week_of_the_plan_is_touched(self, alice: User) -> None:
        other = confirm(alice, draft(alice, good_week(NEXT_MONDAY)).pk)
        draft(alice)
        confirm(alice, WeeklyPlan.objects.get(week_start=MONDAY).pk)

        assert WeeklyPlan.objects.get(pk=other.pk).status == Status.CONFIRMED

    def test_another_users_plan_of_the_same_week_is_not_touched(
        self, alice: User, bob: User
    ) -> None:
        theirs = confirm(bob, draft(bob).pk)

        confirm(alice, draft(alice).pk)

        assert WeeklyPlan.objects.get(pk=theirs.pk).status == Status.CONFIRMED

    @pytest.mark.parametrize("status", ["confirmed", "superseded", "discarded"])
    def test_only_a_draft_can_be_confirmed(self, alice: User, status: str) -> None:
        plan = draft(alice)
        stamp = NOW if status in {"confirmed", "superseded"} else None
        WeeklyPlan.objects.filter(pk=plan.pk).update(status=status, confirmed_at=stamp)

        with pytest.raises(PlanStateError):
            confirm(alice, plan.pk)

        assert WeeklyPlan.objects.get(pk=plan.pk).status == status

    def test_a_plan_cannot_be_confirmed_twice(self, alice: User) -> None:
        plan = confirm(alice, draft(alice).pk)

        with pytest.raises(PlanStateError):
            confirm(alice, plan.pk)

    def test_another_users_plan_cannot_be_confirmed(self, alice: User, bob: User) -> None:
        theirs = draft(bob)

        with pytest.raises(PlanNotFound):
            confirm(alice, theirs.pk)

        assert WeeklyPlan.objects.get(pk=theirs.pk).status == Status.DRAFT

    def test_an_unknown_id_is_not_found(self, alice: User) -> None:
        with pytest.raises(PlanNotFound):
            confirm(alice, uuid4())

    def test_the_workouts_of_a_confirmed_plan_cannot_be_changed(self, alice: User) -> None:
        plan = confirm(alice, draft(alice).pk)
        row = PlannedWorkout.objects.filter(plan=plan).first()
        assert row is not None
        row.plan.refresh_from_db()

        row.title = "Changed"
        with pytest.raises(ValidationError):
            row.save()


class TestDiscarding:
    def test_a_draft_is_discarded(self, alice: User) -> None:
        plan = draft(alice)

        discarded = discard(alice, plan.pk)

        assert (discarded.status, discarded.confirmed_at) == (Status.DISCARDED, None)
        assert WeeklyPlan.objects.get(pk=plan.pk).status == Status.DISCARDED

    def test_a_discarded_plan_stays_stored(self, alice: User) -> None:
        plan = draft(alice)
        discard(alice, plan.pk)

        assert PlannedWorkout.objects.filter(plan=plan).count() == 4
        assert load(alice, plan.pk) == canonical(good_week())

    @pytest.mark.parametrize("status", ["confirmed", "superseded", "discarded"])
    def test_only_a_draft_can_be_discarded(self, alice: User, status: str) -> None:
        plan = draft(alice)
        stamp = NOW if status in {"confirmed", "superseded"} else None
        WeeklyPlan.objects.filter(pk=plan.pk).update(status=status, confirmed_at=stamp)

        with pytest.raises(PlanStateError):
            discard(alice, plan.pk)

        assert WeeklyPlan.objects.get(pk=plan.pk).status == status

    def test_a_discarded_plan_cannot_be_confirmed(self, alice: User) -> None:
        plan = draft(alice)
        discard(alice, plan.pk)

        with pytest.raises(PlanStateError):
            confirm(alice, plan.pk)

    def test_another_users_plan_cannot_be_discarded(self, alice: User, bob: User) -> None:
        theirs = draft(bob)

        with pytest.raises(PlanNotFound):
            discard(alice, theirs.pk)

        assert WeeklyPlan.objects.get(pk=theirs.pk).status == Status.DRAFT


@pytest.mark.django_db(transaction=True)
class TestTwoConfirmationsAtOnce:
    def test_two_drafts_of_one_week_end_with_one_confirmed_and_one_superseded(self) -> None:
        user = prepared(User.objects.create_user("racer@example.com"))
        first, second = draft(user), draft(user)
        start = threading.Barrier(2)

        def run(plan: WeeklyPlan) -> str:
            try:
                start.wait(timeout=10)
                confirm(user, plan.pk)
                return "confirmed"
            except Exception as error:  # reported to the test, which then fails on it
                return repr(error)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, [first, second]))

        assert results == ["confirmed", "confirmed"]
        statuses = sorted(WeeklyPlan.objects.filter(owner=user).values_list("status", flat=True))
        assert statuses == [Status.CONFIRMED, Status.SUPERSEDED]
