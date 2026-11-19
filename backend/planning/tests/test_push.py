from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.db.models import F

from accounts.models import User
from goals import services as goal_services
from integrations import services as integrations
from integrations.intervals import (
    IntervalsUnavailableError,
    InvalidKeyError,
    RejectedError,
    UnexpectedResponseError,
)
from integrations.models import ProviderConnection
from planning import services
from planning.editing import revise
from planning.models import PlannedWorkout, WeeklyPlan, WorkoutExport
from planning.push import (
    REJECTED,
    UNAVAILABLE,
    UNEXPECTED,
    NotConfirmed,
    PushResult,
    export_state,
    external_id,
    push,
)
from planning.schema import Segment, SegmentKind, WeekPlan, Workout, ZoneSystem, to_json

from .fake_calendar import Calendar
from .test_services import MONDAY, NEXT_MONDAY, good_week, prepared, workout

pytestmark = pytest.mark.django_db

KEY = "k3y-0123456789-abcdefghij"
MARKER = "SECRETMARKER"


def connect(owner: User) -> ProviderConnection:
    return ProviderConnection.objects.create(
        owner=owner, provider="intervals_icu", api_key=KEY, athlete_id="i100"
    )


@pytest.fixture
def alice() -> User:
    user = prepared(User.objects.create_user("alice@example.com"))
    connect(user)
    return user


@pytest.fixture
def bob() -> User:
    user = prepared(User.objects.create_user("bob@example.com"))
    connect(user)
    return user


def confirmed(user: User, week: WeekPlan | None = None, **kwargs: Any) -> WeeklyPlan:
    draft = services.save_draft(user, week or good_week(), **kwargs)
    return services.confirm(user, draft.pk)


def exports(user: User) -> dict[str, WorkoutExport]:
    return {row.external_id: row for row in WorkoutExport.objects.for_user(user)}


class TestSendingAWeek:
    def test_every_workout_becomes_one_event(self, alice: User, calendar: Calendar) -> None:
        plan = confirmed(alice)

        result = push(alice, plan.pk)

        assert result == PushResult(synced=4, failed=0, removed=0, left_behind=0)
        assert len(calendar.events) == 4
        ids = {row.pk: external_id(row.lineage) for row in PlannedWorkout.objects.filter(plan=plan)}
        assert {event["external_id"] for event in calendar.events.values()} == set(ids.values())
        assert calendar.keys == [KEY]  # the key of the user, once

    def test_the_events_are_what_the_export_describes(
        self, alice: User, calendar: Calendar
    ) -> None:
        push(alice, confirmed(alice).pk)

        first = min(calendar.events.values(), key=lambda event: event["start_date_local"])
        assert first["start_date_local"] == "2027-07-12T00:00:00"
        assert first["type"] == "Ride"
        assert first["category"] == "WORKOUT"
        # An FTP of 250: zone 2 is 138 to 188 watts.
        assert "- 1h30m 138-188w" in first["description"]

    def test_the_result_is_recorded_per_workout(self, alice: User, calendar: Calendar) -> None:
        plan = confirmed(alice)

        push(alice, plan.pk)

        rows = exports(alice)
        assert len(rows) == 4
        for row in rows.values():
            assert row.status == "synced"
            assert row.error_code == ""
            assert row.week_start == MONDAY
            assert row.workout is not None
            assert row.workout.plan_id == plan.pk
            assert row.event_id in calendar.events
            assert row.external_id == external_id(row.workout.lineage)

    def test_sending_again_changes_nothing_in_the_calendar(
        self, alice: User, calendar: Calendar
    ) -> None:
        plan = confirmed(alice)
        push(alice, plan.pk)
        before = {event_id: dict(event) for event_id, event in calendar.events.items()}
        rows = {key: row.event_id for key, row in exports(alice).items()}

        result = push(alice, plan.pk)

        assert result == PushResult(synced=4, failed=0, removed=0, left_behind=0)
        assert calendar.events == before
        assert {key: row.event_id for key, row in exports(alice).items()} == rows
        assert WorkoutExport.objects.count() == 4
        assert calendar.count("delete") == 0


class TestWhatIsNotSent:
    @pytest.mark.parametrize("decided", ["draft", "discarded", "superseded"])
    def test_only_a_confirmed_plan_is_sent(
        self, alice: User, calendar: Calendar, decided: str
    ) -> None:
        plan = services.save_draft(alice, good_week())
        if decided == "discarded":
            services.discard(alice, plan.pk)
        if decided == "superseded":
            services.confirm(alice, plan.pk)
            newer = services.save_draft(alice, good_week(), parent=plan.pk)
            services.confirm(alice, newer.pk)

        with pytest.raises(NotConfirmed):
            push(alice, plan.pk)

        assert calendar.calls == []
        assert WorkoutExport.objects.count() == 0

    def test_a_plan_of_another_user_does_not_exist(
        self, alice: User, bob: User, calendar: Calendar
    ) -> None:
        plan = confirmed(alice)

        with pytest.raises(services.PlanNotFound):
            push(bob, plan.pk)

        assert calendar.calls == []

    def test_without_a_connection_nothing_is_sent(self, alice: User, calendar: Calendar) -> None:
        plan = confirmed(alice)
        ProviderConnection.objects.all().delete()

        with pytest.raises(integrations.NotConnectedError):
            push(alice, plan.pk)

        assert calendar.calls == []
        assert WorkoutExport.objects.count() == 0


class TestANewVersion:
    def test_the_events_of_the_version_it_replaces_are_removed(
        self, alice: User, calendar: Calendar
    ) -> None:
        old = confirmed(alice)
        push(alice, old.pk)
        old_events = set(calendar.events)
        newer = services.save_draft(alice, good_week(rationale="Revised"), parent=old.pk)
        services.confirm(alice, newer.pk)

        result = push(alice, newer.pk)

        assert result == PushResult(synced=4, failed=0, removed=4, left_behind=0)
        assert len(calendar.events) == 4
        assert not old_events & set(calendar.events)
        assert WorkoutExport.objects.count() == 4
        assert {row.workout.plan_id for row in exports(alice).values() if row.workout} == {newer.pk}
        assert all(row.workout is not None for row in exports(alice).values())

    def test_a_workout_that_is_gone_is_removed_and_the_others_stay(
        self, alice: User, calendar: Calendar
    ) -> None:
        old = confirmed(alice)
        push(alice, old.pk)
        week = good_week()
        shorter = WeekPlan(week.week_start, week.workouts[:3], week.rationale)
        newer = services.save_draft(alice, shorter, parent=old.pk)
        services.confirm(alice, newer.pk)

        result = push(alice, newer.pk)

        assert result.synced == 3
        assert result.removed == 4  # the whole old version: its workouts have other ids
        assert len(calendar.events) == 3

    def test_an_event_that_is_gone_at_intervals_is_not_a_problem(
        self, alice: User, calendar: Calendar
    ) -> None:
        old = confirmed(alice)
        push(alice, old.pk)
        calendar.events.clear()  # the user deleted everything in Intervals.icu
        newer = services.save_draft(alice, good_week(), parent=old.pk)
        services.confirm(alice, newer.pk)

        result = push(alice, newer.pk)

        assert result == PushResult(synced=4, failed=0, removed=4, left_behind=0)
        assert len(calendar.events) == 4

    def test_other_weeks_are_left_alone(self, alice: User, calendar: Calendar) -> None:
        this_week = confirmed(alice)
        next_week = confirmed(
            alice,
            WeekPlan(NEXT_MONDAY, (workout(NEXT_MONDAY, 0, 60),)),
        )
        push(alice, this_week.pk)

        result = push(alice, next_week.pk)

        assert result == PushResult(synced=1, failed=0, removed=0, left_behind=0)
        assert len(calendar.events) == 5
        assert WorkoutExport.objects.filter(week_start=MONDAY).count() == 4


def revised(
    user: User, old: WeeklyPlan, change: Callable[[tuple[Workout, ...]], tuple[Workout, ...]]
) -> WeeklyPlan:
    """The next version of a week, made from the one before: its workouts, changed, with their
    lineages, confirmed."""
    copy = services.load(user, old.pk)
    newer = services.save_draft(
        user, WeekPlan(copy.week_start, change(copy.workouts), copy.rationale), parent=old.pk
    )
    return services.confirm(user, newer.pk)


def light_week() -> WeekPlan:
    """Four short workouts (Monday, Wednesday, Friday, Saturday) that leave room on each day, so
    that a workout can be moved or added without breaking a rule."""
    return WeekPlan(MONDAY, tuple(workout(MONDAY, offset, 30) for offset in (0, 2, 4, 5)))


class TestAVersionMadeFromAnother:
    def test_nothing_changed_updates_every_event_and_removes_nothing(
        self, alice: User, calendar: Calendar
    ) -> None:
        old = confirmed(alice)
        push(alice, old.pk)
        before = dict(calendar.events)

        newer = revised(alice, old, lambda workouts: workouts)
        result = push(alice, newer.pk)

        assert result == PushResult(synced=4, failed=0, removed=0, left_behind=0)
        assert set(calendar.events) == set(before)  # the same events, not new ones
        assert calendar.count("delete") == 0
        assert WorkoutExport.objects.count() == 4

    def test_a_plan_changed_by_hand_through_revise_updates_the_same_events(
        self, alice: User, calendar: Calendar, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Changing a week is for the weeks that can be planned: this is the week of the 12th.
        monkeypatch.setattr(
            goal_services, "_utc_now", lambda: datetime(2027, 7, 14, 12, tzinfo=UTC)
        )
        old = confirmed(alice, light_week())
        push(alice, old.pk)
        events = set(calendar.events)
        data = to_json(services.load(alice, old.pk))
        rows = PlannedWorkout.objects.filter(plan=old).order_by("day", "position", "id")
        for item, row in zip(data["workouts"], rows, strict=True):
            item["lineage"] = str(row.lineage)
        data["workouts"][0]["day"] = (MONDAY + timedelta(days=2)).isoformat()
        del data["workouts"][3]

        newer = services.confirm(alice, revise(alice, old.pk, data).pk)
        result = push(alice, newer.pk)

        assert result == PushResult(synced=3, failed=0, removed=1, left_behind=0)
        assert set(calendar.events) < events  # the same events (three of them), none new

    def test_revising_segments_and_pushing_updates_the_existing_event_in_place(
        self, alice: User, calendar: Calendar, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            goal_services, "_utc_now", lambda: datetime(2027, 7, 14, 12, tzinfo=UTC)
        )
        week = WeekPlan(
            MONDAY,
            (
                workout(
                    MONDAY,
                    0,
                    50,
                    segments=(
                        Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 2),
                        Segment(SegmentKind.WORK, 600, 3, ZoneSystem.POWER, 4),
                        Segment(SegmentKind.COOLDOWN, 600, 1, ZoneSystem.POWER, 1),
                    ),
                ),
            ),
        )
        old = confirmed(alice, week)
        push(alice, old.pk)
        (event_id,) = calendar.events
        ext_id = calendar.events[event_id]["external_id"]

        data = to_json(services.load(alice, old.pk))
        row = PlannedWorkout.objects.get(plan=old)
        data["workouts"][0]["lineage"] = str(row.lineage)
        data["workouts"][0]["duration_minutes"] = 52
        data["workouts"][0]["segments"][1] = {
            "kind": "work",
            "seconds": 480,
            "repeat": 4,
            "zone_system": "power",
            "zone": 4,
        }

        newer = services.confirm(alice, revise(alice, old.pk, data).pk)
        result = push(alice, newer.pk)

        assert result == PushResult(synced=1, failed=0, removed=0, left_behind=0)
        assert set(calendar.events) == {event_id}
        assert calendar.events[event_id]["external_id"] == ext_id
        description = calendar.events[event_id]["description"]
        assert "Work 4x" in description
        assert "- 8m" in description
        assert "Work 3x" not in description
        assert calendar.count("delete") == 0

    def test_a_workout_that_was_moved_updates_its_event_to_the_new_day(
        self, alice: User, calendar: Calendar
    ) -> None:
        old = confirmed(alice, light_week())
        push(alice, old.pk)
        events = {e["external_id"]: event_id for event_id, e in calendar.events.items()}
        moved = services.load(alice, old.pk).workouts[0]  # Monday
        wednesday = moved.day + timedelta(days=2)

        def move(workouts: tuple[Workout, ...]) -> tuple[Workout, ...]:
            return (replace(moved, day=wednesday), *workouts[1:])

        newer = revised(alice, old, move)
        result = push(alice, newer.pk)

        assert result == PushResult(synced=4, failed=0, removed=0, left_behind=0)
        key = external_id(moved.lineage)  # type: ignore[arg-type]
        assert calendar.events[events[key]]["start_date_local"].startswith(wednesday.isoformat())
        assert {e["external_id"] for e in calendar.events.values()} == set(events)

    def test_the_export_row_follows_the_workout_of_the_new_version(
        self, alice: User, calendar: Calendar
    ) -> None:
        old = confirmed(alice)
        push(alice, old.pk)
        newer = revised(alice, old, lambda workouts: workouts)

        push(alice, newer.pk)

        assert {row.workout.plan_id for row in exports(alice).values() if row.workout} == {newer.pk}
        for row in exports(alice).values():
            assert row.workout is not None
            assert row.external_id == external_id(row.workout.lineage)

    def test_a_workout_that_was_taken_out_loses_its_event_and_only_that(
        self, alice: User, calendar: Calendar
    ) -> None:
        old = confirmed(alice)
        push(alice, old.pk)
        gone = services.load(alice, old.pk).workouts[3]

        newer = revised(alice, old, lambda workouts: workouts[:3])
        result = push(alice, newer.pk)

        assert result == PushResult(synced=3, failed=0, removed=1, left_behind=0)
        assert len(calendar.events) == 3
        assert external_id(gone.lineage) not in {  # type: ignore[arg-type]
            e["external_id"] for e in calendar.events.values()
        }

    def test_a_workout_that_was_added_gets_an_event_and_the_others_stay(
        self, alice: User, calendar: Calendar
    ) -> None:
        old = confirmed(alice, light_week())
        push(alice, old.pk)
        before = set(calendar.events)

        newer = revised(alice, old, lambda workouts: (*workouts, workout(MONDAY, 0, 30)))
        result = push(alice, newer.pk)

        assert result == PushResult(synced=5, failed=0, removed=0, left_behind=0)
        assert before < set(calendar.events) and len(calendar.events) == 5

    def test_a_week_the_coach_drafted_anew_still_replaces_the_events_of_the_version_before(
        self, alice: User, calendar: Calendar
    ) -> None:
        old = confirmed(alice)
        push(alice, old.pk)
        before = set(calendar.events)
        newer = services.save_draft(alice, good_week(rationale="Again"), parent=old.pk)
        services.confirm(alice, newer.pk)

        result = push(alice, newer.pk)

        assert result == PushResult(synced=4, failed=0, removed=4, left_behind=0)
        assert not before & set(calendar.events)

    def test_the_state_of_an_unsent_version_is_that_of_the_events_of_its_lineages(
        self, alice: User, calendar: Calendar
    ) -> None:
        old = confirmed(alice, light_week())
        push(alice, old.pk)

        newer = revised(alice, old, lambda workouts: (*workouts[:3], workout(MONDAY, 0, 30)))
        state = export_state(alice, newer)

        assert sorted(w.status for w in state.workouts) == [
            "not_sent",
            "synced",
            "synced",
            "synced",
        ]
        assert state.older == 1  # the event of the workout that was taken out

    def test_a_workout_of_a_new_version_the_coach_drafted_shows_as_not_sent(
        self, alice: User, calendar: Calendar
    ) -> None:
        old = confirmed(alice)
        push(alice, old.pk)
        newer = services.save_draft(alice, good_week(rationale="Again"), parent=old.pk)
        services.confirm(alice, newer.pk)

        state = export_state(alice, newer)

        assert {w.status for w in state.workouts} == {"not_sent"}
        assert state.older == 4


class TestEventsThatWereSentBeforeTheLineageExisted:
    def test_a_key_made_from_the_id_of_a_workout_is_still_the_key_when_it_is_its_own_lineage(
        self, alice: User, calendar: Calendar
    ) -> None:
        plan = confirmed(alice)
        # What the migration did to every workout that existed: its lineage is its own id.
        PlannedWorkout.objects.filter(plan=plan).update(lineage=F("pk"))
        for row in PlannedWorkout.objects.filter(plan=plan):
            assert external_id(row.lineage) == f"paceforge-{row.pk}"

        push(alice, plan.pk)
        push(alice, plan.pk)

        assert WorkoutExport.objects.count() == 4
        assert len(calendar.events) == 4
        assert calendar.count("delete") == 0
        keys = {row.external_id for row in WorkoutExport.objects.all()}
        assert keys == {f"paceforge-{row.pk}" for row in PlannedWorkout.objects.filter(plan=plan)}


class TestOtherUsers:
    def test_the_exports_of_other_users_are_never_touched(
        self, alice: User, bob: User, calendar: Calendar
    ) -> None:
        theirs = confirmed(bob)
        push(bob, theirs.pk)
        their_events = set(calendar.events)
        mine = confirmed(alice)

        push(alice, mine.pk)
        newer = services.save_draft(alice, good_week(), parent=mine.pk)
        services.confirm(alice, newer.pk)
        push(alice, newer.pk)

        assert their_events <= set(calendar.events)
        assert WorkoutExport.objects.for_user(bob).count() == 4
        assert WorkoutExport.objects.for_user(alice).count() == 4


class TestWhenSomethingFails:
    def test_a_workout_that_is_rejected_does_not_keep_the_others_from_arriving(
        self, alice: User, calendar: Calendar
    ) -> None:
        calendar.upsert_failures = [None, RejectedError(MARKER), None, None]

        result = push(alice, confirmed(alice).pk)

        assert result == PushResult(synced=3, failed=1, removed=0, left_behind=0)
        rows = list(exports(alice).values())
        failed = [row for row in rows if row.status == "failed"]
        assert [(row.error_code, row.event_id) for row in failed] == [(REJECTED, None)]
        assert len([row for row in rows if row.status == "synced"]) == 3
        assert len(calendar.events) == 3

    def test_nothing_of_the_error_is_kept(self, alice: User, calendar: Calendar) -> None:
        calendar.upsert_failures = [RejectedError(MARKER)] * 4

        push(alice, confirmed(alice).pk)

        for row in WorkoutExport.objects.all():
            assert MARKER not in f"{row.error_code} {row}"

    def test_an_unexpected_answer_is_a_failure_of_that_workout(
        self, alice: User, calendar: Calendar
    ) -> None:
        calendar.upsert_failures = [UnexpectedResponseError("odd"), None, None, None]

        result = push(alice, confirmed(alice).pk)

        assert result == PushResult(synced=3, failed=1, removed=0, left_behind=0)
        assert [row.error_code for row in exports(alice).values() if row.status == "failed"] == [
            UNEXPECTED
        ]

    def test_trying_again_sends_what_failed_and_clears_the_error(
        self, alice: User, calendar: Calendar
    ) -> None:
        plan = confirmed(alice)
        calendar.upsert_failures = [None, RejectedError("no"), None, None]
        push(alice, plan.pk)

        result = push(alice, plan.pk)

        assert result == PushResult(synced=4, failed=0, removed=0, left_behind=0)
        assert {row.status for row in exports(alice).values()} == {"synced"}
        assert {row.error_code for row in exports(alice).values()} == {""}
        assert len(calendar.events) == 4

    def test_a_failed_update_keeps_the_event_it_has(self, alice: User, calendar: Calendar) -> None:
        plan = confirmed(alice)
        push(alice, plan.pk)
        events = {key: row.event_id for key, row in exports(alice).items()}
        calendar.upsert_failures = [UnexpectedResponseError("odd")]

        push(alice, plan.pk)

        failed = [row for row in exports(alice).values() if row.status == "failed"]
        assert len(failed) == 1
        assert failed[0].event_id == events[failed[0].external_id]
        assert len(calendar.events) == 4

    def test_when_intervals_is_down_the_rest_is_not_tried_and_marked(
        self, alice: User, calendar: Calendar
    ) -> None:
        calendar.upsert_failures = [None, IntervalsUnavailableError("down")]

        result = push(alice, confirmed(alice).pk)

        assert result == PushResult(synced=1, failed=3, removed=0, left_behind=0)
        assert calendar.count("upsert") == 2  # the third and fourth were not tried
        failed = [row for row in exports(alice).values() if row.status == "failed"]
        assert {row.error_code for row in failed} == {UNAVAILABLE}
        assert len(failed) == 3

    def test_when_intervals_is_down_nothing_is_removed(
        self, alice: User, calendar: Calendar
    ) -> None:
        old = confirmed(alice)
        push(alice, old.pk)
        newer = services.save_draft(alice, good_week(), parent=old.pk)
        services.confirm(alice, newer.pk)
        calendar.upsert_failures = [IntervalsUnavailableError("down")]

        result = push(alice, newer.pk)

        assert result == PushResult(synced=0, failed=4, removed=0, left_behind=4)
        assert calendar.count("delete") == 0
        assert len(calendar.events) == 4  # the old version is still there, and still known
        assert WorkoutExport.objects.count() == 8

    def test_an_event_that_cannot_be_removed_stays_known_for_the_next_push(
        self, alice: User, calendar: Calendar
    ) -> None:
        old = confirmed(alice)
        push(alice, old.pk)
        newer = services.save_draft(alice, good_week(), parent=old.pk)
        services.confirm(alice, newer.pk)
        calendar.delete_failures = [UnexpectedResponseError("odd")]

        first = push(alice, newer.pk)
        second = push(alice, newer.pk)

        assert first == PushResult(synced=4, failed=0, removed=3, left_behind=1)
        assert second == PushResult(synced=4, failed=0, removed=1, left_behind=0)
        assert len(calendar.events) == 4
        assert WorkoutExport.objects.count() == 4

    def test_a_refused_key_stops_everything_and_marks_the_connection(
        self, alice: User, calendar: Calendar
    ) -> None:
        calendar.upsert_failures = [InvalidKeyError("no")]

        with pytest.raises(InvalidKeyError):
            push(alice, confirmed(alice).pk)

        assert calendar.count("upsert") == 1
        assert WorkoutExport.objects.count() == 0
        connection = integrations.get_connection(alice)
        assert connection is not None
        assert connection.status == ProviderConnection.Status.INVALID


def test_the_prefix_makes_the_ids_recognisable(alice: User) -> None:
    plan = services.save_draft(alice, good_week())
    row = PlannedWorkout.objects.filter(plan=plan).first()

    assert row is not None
    assert external_id(row.lineage) == f"paceforge-{row.lineage}"


def test_the_week_of_the_exports_is_the_week_of_the_plan(alice: User, calendar: Calendar) -> None:
    week = WeekPlan(NEXT_MONDAY, (workout(NEXT_MONDAY, 0, 60), workout(NEXT_MONDAY, 2, 60)))
    plan = confirmed(alice, week)

    push(alice, plan.pk)

    assert {row.week_start for row in WorkoutExport.objects.all()} == {NEXT_MONDAY}
