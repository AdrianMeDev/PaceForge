from collections.abc import Mapping
from typing import Any

import pytest

from accounts.models import User
from integrations import services as integrations
from integrations.intervals import (
    Event,
    IntervalsUnavailableError,
    InvalidKeyError,
    RejectedError,
    UnexpectedResponseError,
)
from integrations.models import ProviderConnection
from planning import services
from planning.models import PlannedWorkout, WeeklyPlan, WorkoutExport
from planning.push import (
    REJECTED,
    UNAVAILABLE,
    UNEXPECTED,
    NotConfirmed,
    PushResult,
    external_id,
    push,
)
from planning.schema import WeekPlan

from .test_services import MONDAY, NEXT_MONDAY, good_week, prepared, workout

pytestmark = pytest.mark.django_db

KEY = "k3y-0123456789-abcdefghij"
MARKER = "SECRETMARKER"
Failure = Exception | None


class Calendar:
    """What Intervals.icu would hold, and the calls made to it."""

    def __init__(self) -> None:
        self.events: dict[int, dict[str, Any]] = {}
        self.calls: list[tuple[str, Any]] = []
        # One entry per upsert, consumed in order: what to raise instead of storing (None: store).
        self.upsert_failures: list[Failure] = []
        self.delete_failures: list[Failure] = []
        self.keys: list[str] = []
        self._next = 100

    def upsert(self, event: Mapping[str, Any]) -> Event:
        self.calls.append(("upsert", event["external_id"]))
        failure = self.upsert_failures.pop(0) if self.upsert_failures else None
        if failure is not None:
            raise failure
        for event_id, stored in self.events.items():
            if stored["external_id"] == event["external_id"]:
                self.events[event_id] = dict(event)
                return Event(event_id, event["external_id"])
        self._next += 1
        self.events[self._next] = dict(event)
        return Event(self._next, event["external_id"])

    def delete(self, event_id: int) -> None:
        self.calls.append(("delete", event_id))
        failure = self.delete_failures.pop(0) if self.delete_failures else None
        if failure is not None:
            raise failure
        self.events.pop(event_id, None)  # one that is gone counts as removed

    def count(self, kind: str) -> int:
        return sum(1 for call, _ in self.calls if call == kind)


class FakeClient:
    def __init__(self, calendar: Calendar, key: str) -> None:
        self._calendar = calendar
        calendar.keys.append(key)

    def upsert_event(self, event: Mapping[str, Any]) -> Event:
        return self._calendar.upsert(event)

    def delete_event(self, event_id: int) -> None:
        self._calendar.delete(event_id)


@pytest.fixture
def calendar(monkeypatch: pytest.MonkeyPatch) -> Calendar:
    calendar = Calendar()
    monkeypatch.setattr(integrations, "IntervalsClient", lambda key: FakeClient(calendar, key))
    return calendar


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
        ids = {row.pk: external_id(row.pk) for row in PlannedWorkout.objects.filter(plan=plan)}
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
            assert row.external_id == external_id(row.workout.pk)

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
    assert external_id(row.pk) == f"paceforge-{row.pk}"


def test_the_week_of_the_exports_is_the_week_of_the_plan(alice: User, calendar: Calendar) -> None:
    week = WeekPlan(NEXT_MONDAY, (workout(NEXT_MONDAY, 0, 60), workout(NEXT_MONDAY, 2, 60)))
    plan = confirmed(alice, week)

    push(alice, plan.pk)

    assert {row.week_start for row in WorkoutExport.objects.all()} == {NEXT_MONDAY}
