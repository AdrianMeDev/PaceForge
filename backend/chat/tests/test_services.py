import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from django.core.exceptions import ValidationError

from accounts.models import User
from availability.models import UnavailablePeriod, WeekdayMinutes
from chat import services
from chat.actions import OTHER_WEEK_PROBLEM
from chat.models import USER_TEXT_MAX, ChatMessage
from chat.services import (
    ATTEMPTS,
    DOCTOR_HINT,
    HISTORY_TOLD,
    NO_SEASON_PLAN,
    NOT_USABLE,
    ONE_WEEK_ONLY,
    REASON,
    SEASON_CHANGE_FAILED,
    SEASON_DRAFT_MADE,
    SEASON_REQUEST,
    clean_text,
    clear,
    send,
)
from coach import services as coach_services
from coach.models import AIProviderConfiguration, AIUsageRecord
from coach.providers.base import Completion, ProviderUnavailableError, RateLimitedError
from goals import services as goal_services
from goals.models import Goal as GoalRow
from integrations.models import ProviderConnection
from planning import services as plan_services
from planning.models import PlannedWorkout, WeeklyPlan, WorkoutExport
from planning.push import export_state, push
from planning.rules import Intensity, intensity_of
from planning.schema import Sport
from planning.tests.fake_calendar import Calendar
from planning.tests.scripted import Scripted
from reviews.tests.builders import MONDAY, NOW, make_plan
from season import generation as season_generation
from season import services as season_services
from season.generation import PlanUnchanged
from season.inputs import skeleton_for
from season.models import SeasonPlanVersion
from season.rules import SeasonContext
from season.schema import Focus, KeySession, PlanWeek, SeasonPlan, SessionKind
from season.schema import to_json as season_json
from season.snapshots import collect_inputs

pytestmark = pytest.mark.django_db

KEY = "synthetic-test-token-abcdefghij"
INTERVALS_KEY = "k3y-0123456789-abcdefghij"
SATURDAY = "2026-11-14"
SUNDAY = "2026-11-15"
WEDNESDAY = "2026-11-11"
# A Wednesday morning; a mild illness pauses this day and eases the two days after it.
MIDWEEK = datetime(2026, 11, 11, 8, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def athlete(alice: User) -> User:
    AIProviderConfiguration.objects.create(
        owner=alice, provider="anthropic", model="claude-sonnet-5-5", api_key=KEY
    )
    make_plan(alice, MONDAY, workouts=7)
    return alice


_OMIT = object()


def said(
    reply: str = "Done.",
    actions: list[dict[str, Any]] | None = None,
    week: object = _OMIT,
) -> str:
    payload: dict[str, Any] = {"reply": reply, "actions": actions or []}
    if week is not _OMIT:
        payload["week"] = week
    return json.dumps(payload)


def saturday_workout(user: User) -> PlannedWorkout:
    return PlannedWorkout.objects.for_user(user).get(day=SATURDAY)


def drafts(user: User) -> list[WeeklyPlan]:
    return list(WeeklyPlan.objects.for_user(user).filter(status="draft"))


def room_to_train(user: User) -> None:
    """Three hours on every day, so that the plan of the athlete can be confirmed."""
    WeekdayMinutes.objects.for_user(user).delete()
    for weekday in range(7):
        WeekdayMinutes.objects.create(owner=user, weekday=weekday, minutes=180)


def key_of(workout: PlannedWorkout) -> str:
    """What the event of ``workout`` is called in the calendar."""
    return f"paceforge-{workout.lineage}"


def briefing_sent(provider: Scripted, call: int = 0) -> dict[str, Any]:
    """The JSON briefing sent in ``call`` of ``provider``."""
    data: dict[str, Any] = json.loads(provider.calls[call][1][0].content.split("\n\n")[1])
    return data


class TestAQuestion:
    def test_gets_an_answer_and_no_draft(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(said("Threshold builds your pace."))

        sent = send(athlete, "Why threshold today?")

        assert (sent.athlete.role, sent.athlete.text) == ("user", "Why threshold today?")
        assert (sent.coach.role, sent.coach.text) == ("coach", "Threshold builds your pace.")
        assert sent.coach.plan is None and sent.coach.changes == []
        assert drafts(athlete) == []

    def test_both_messages_are_kept_in_order(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(said("One."), said("Two."))

        send(athlete, "First")
        send(athlete, "Second")

        assert [m.text for m in services.history(athlete)] == ["First", "One.", "Second", "Two."]

    def test_asks_json_and_is_recorded_as_a_chat_call(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        provider = provide(said())

        send(athlete, "Hi")

        assert provider.json_outputs == [True]
        record = AIUsageRecord.objects.for_user(athlete).get()
        assert (record.purpose, record.outcome) == ("chat", "success")

    def test_the_chat_model_is_used_and_recorded_if_there_is_one(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        AIProviderConfiguration.objects.filter(owner=athlete).update(chat_model="claude-haiku-5-5")
        provide(said())

        send(athlete, "Hi")

        record = AIUsageRecord.objects.for_user(athlete).get()
        assert (record.purpose, record.model) == ("chat", "claude-haiku-5-5")

    def test_the_coach_is_told_the_week_the_messages_so_far_and_the_new_one(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        provider = provide(said("A."), said("B."))
        send(athlete, "Tuesday no time")

        send(athlete, "And Friday?")

        content = provider.calls[1][1][0].content
        assert "Tuesday no time" in content and '"text":"A."' in content
        assert "And Friday?" in content
        assert str(saturday_workout(athlete).lineage) in content

    def test_only_the_last_messages_are_told(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        for n in range(HISTORY_TOLD + 3):
            ChatMessage.objects.create(owner=athlete, role="user", text=f"old-{n:02d}")
        provider = provide(said())

        send(athlete, "New")

        content = provider.calls[0][1][0].content
        assert "old-02" not in content
        assert "old-03" in content and "old-12" in content

    def test_briefs_every_plannable_week_with_a_plan_in_order(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        next_monday = MONDAY + timedelta(weeks=1)
        third_monday = MONDAY + timedelta(weeks=2)
        make_plan(athlete, next_monday, status="confirmed", workouts=2)
        make_plan(athlete, next_monday, status="draft", workouts=3)
        make_plan(athlete, third_monday, status="confirmed", workouts=1)
        # Not included: discarded, past, or beyond the plannable horizon.
        make_plan(athlete, MONDAY + timedelta(weeks=3), status="discarded", workouts=2)
        make_plan(athlete, MONDAY - timedelta(weeks=1), status="confirmed", workouts=2)
        make_plan(athlete, MONDAY + timedelta(weeks=5), status="confirmed", workouts=2)
        provider = provide(said("Looks good."))

        send(athlete, "What is coming up?")

        briefing = briefing_sent(provider)
        assert [week["week_start"] for week in briefing["weeks"]] == [
            MONDAY.isoformat(),
            next_monday.isoformat(),
            third_monday.isoformat(),
        ]
        assert [len(week["workouts"]) for week in briefing["weeks"]] == [7, 3, 1]

    def test_another_users_weeks_are_never_in_the_briefing(
        self, athlete: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        next_monday = MONDAY + timedelta(weeks=1)
        bob_next = make_plan(bob, next_monday, status="confirmed", workouts=4)
        make_plan(bob, MONDAY, status="confirmed", workouts=3)
        provider = provide(said("Nothing planned next week."))

        send(athlete, "What is next week?")

        briefing = briefing_sent(provider)
        assert [week["week_start"] for week in briefing["weeks"]] == [MONDAY.isoformat()]
        content = provider.calls[0][1][0].content
        for workout in PlannedWorkout.objects.for_user(bob).filter(plan=bob_next):
            assert str(workout.lineage) not in content


class TestAChange:
    def test_makes_a_new_draft_with_a_reason_and_a_parent(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        workout = saturday_workout(athlete)
        before = WeeklyPlan.objects.for_user(athlete).get()
        provide(
            said(
                "I would move it to Sunday.",
                [{"tool": "move_workout", "id": str(workout.lineage), "day": SUNDAY}],
            )
        )

        sent = send(athlete, "Rain on Saturday, can I ride on Sunday?")

        (draft,) = drafts(athlete)
        assert sent.coach.plan == draft
        assert (draft.reason, draft.parent_id, draft.week_start) == (REASON, before.pk, MONDAY)
        assert sent.coach.changes == ["Run on Sat (60 min) moved to Sun"]
        moved = PlannedWorkout.objects.for_user(athlete).get(plan=draft, lineage=workout.lineage)
        assert moved.day.isoformat() == SUNDAY

    def test_never_changes_or_confirms_anything_by_itself(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        workout = saturday_workout(athlete)
        provide(said("Skipping.", [{"tool": "skip_workout", "id": str(workout.lineage)}]))

        send(athlete, "Skip Saturday")

        confirmed = WeeklyPlan.objects.for_user(athlete).get(status="confirmed")
        assert PlannedWorkout.objects.for_user(athlete).filter(plan=confirmed).count() == 7
        assert saturday_workout(athlete).plan == confirmed
        # the draft has one workout less, and is a draft
        (draft,) = drafts(athlete)
        assert PlannedWorkout.objects.for_user(athlete).filter(plan=draft).count() == 6
        assert draft.confirmed_at is None

    def test_actions_that_change_nothing_make_no_draft(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(said("Nothing to free.", [{"tool": "free_day", "day": SATURDAY}]))
        PlannedWorkout.objects.for_user(athlete).filter(day=SATURDAY).delete()

        sent = send(athlete, "Free Saturday")

        assert sent.coach.plan is None
        assert drafts(athlete) == []

    def test_works_on_the_newest_draft_when_there_is_one(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        workout = saturday_workout(athlete)
        provide(
            said("One.", [{"tool": "shorten_workout", "id": str(workout.lineage), "minutes": 30}]),
            said("Two.", [{"tool": "shorten_workout", "id": str(workout.lineage), "minutes": 20}]),
        )

        send(athlete, "Shorter")
        send(athlete, "Even shorter")

        versions = sorted(drafts(athlete), key=lambda p: p.version)
        assert [p.version for p in versions] == [2, 3]
        assert versions[1].parent_id == versions[0].pk

    def test_changes_only_the_first_week_when_week_is_omitted(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        next_monday = MONDAY + timedelta(weeks=1)
        next_plan = make_plan(athlete, next_monday, status="confirmed", workouts=2)
        next_workout = PlannedWorkout.objects.for_user(athlete).filter(plan=next_plan).first()
        assert next_workout is not None
        provider = provide(
            said(
                "Skipping next week.",
                [{"tool": "skip_workout", "id": str(next_workout.lineage)}],
            ),
            said("I need to name next week to change it."),
        )

        sent = send(athlete, "Skip Monday next week")

        assert sent.coach.text == "I need to name next week to change it."
        assert drafts(athlete) == []
        assert len(provider.calls) == ATTEMPTS

    def test_null_week_changes_the_first_week(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        next_monday = MONDAY + timedelta(weeks=1)
        make_plan(athlete, next_monday, status="confirmed", workouts=2)
        this_week = WeeklyPlan.objects.for_user(athlete).get(week_start=MONDAY)
        workout = saturday_workout(athlete)
        provide(
            said(
                "Skipping Saturday.",
                [{"tool": "skip_workout", "id": str(workout.lineage)}],
                week=None,
            )
        )

        sent = send(athlete, "Skip Saturday")

        (draft,) = drafts(athlete)
        assert sent.coach.plan == draft
        assert (draft.week_start, draft.parent_id) == (MONDAY, this_week.pk)

    def test_changes_a_named_week_and_leaves_this_week_untouched(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        next_monday = MONDAY + timedelta(weeks=1)
        next_plan = make_plan(athlete, next_monday, status="confirmed", workouts=3)
        next_workouts = list(
            PlannedWorkout.objects.for_user(athlete).filter(plan=next_plan).order_by("day")
        )
        run, ride, strength = next_workouts
        PlannedWorkout.objects.for_user(athlete).filter(pk=ride.pk).update(sport="cycling")
        PlannedWorkout.objects.for_user(athlete).filter(pk=strength.pk).update(
            sport="strength", goal="strength"
        )
        this_week = WeeklyPlan.objects.for_user(athlete).get(week_start=MONDAY)
        provide(
            said(
                "Swapped the ride for a run and took out strength for next week.",
                [
                    {"tool": "swap_sport", "id": str(ride.lineage), "sport": "running"},
                    {"tool": "skip_workout", "id": str(strength.lineage)},
                ],
                week=next_monday.isoformat(),
            )
        )

        sent = send(athlete, "Only running next week")

        (draft,) = drafts(athlete)
        assert sent.coach.plan == draft
        assert (draft.week_start, draft.parent_id, draft.reason) == (
            next_monday,
            next_plan.pk,
            REASON,
        )
        assert draft.confirmed_at is None
        draft_workouts = list(
            PlannedWorkout.objects.for_user(athlete).filter(plan=draft).order_by("day")
        )
        assert [w.lineage for w in draft_workouts] == [run.lineage, ride.lineage]
        assert [w.sport for w in draft_workouts] == ["running", "running"]
        assert sent.coach.changes == [
            "Ride on Tue (60 min) replaced by Run (60 min)",
            "Strength on Wed (60 min) removed",
        ]
        # This week and next week's confirmed plan are both untouched.
        assert list(WeeklyPlan.objects.for_user(athlete).filter(week_start=MONDAY)) == [this_week]
        assert PlannedWorkout.objects.for_user(athlete).filter(plan=this_week).count() == 7
        assert PlannedWorkout.objects.for_user(athlete).filter(plan=next_plan).count() == 3

    def test_works_on_the_newest_draft_of_a_named_week(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        next_monday = MONDAY + timedelta(weeks=1)
        make_plan(athlete, next_monday, status="confirmed", workouts=2)
        next_draft = make_plan(athlete, next_monday, status="draft", workouts=2)
        workout = PlannedWorkout.objects.for_user(athlete).filter(plan=next_draft).first()
        assert workout is not None
        provide(
            said(
                "Shorter.",
                [{"tool": "shorten_workout", "id": str(workout.lineage), "minutes": 30}],
                week=next_monday.isoformat(),
            )
        )

        sent = send(athlete, "Shorten Monday next week")

        assert sent.coach.plan is not None
        assert (sent.coach.plan.week_start, sent.coach.plan.parent_id) == (
            next_monday,
            next_draft.pk,
        )
        assert sent.coach.plan.version == next_draft.version + 1

    def test_a_week_without_a_plan_is_refused_and_repaired(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        unknown = MONDAY + timedelta(weeks=2)
        provider = provide(
            said(
                "Reduced that week.",
                [{"tool": "reduce_week", "percent": 20}],
                week=unknown.isoformat(),
            ),
            said("You do not have a plan for that week yet."),
        )

        sent = send(athlete, "Reduce the week after next by 20%")

        assert sent.coach.text == "You do not have a plan for that week yet."
        assert sent.coach.plan is None
        assert drafts(athlete) == []
        assert len(provider.calls) == ATTEMPTS
        assert "- week:" in provider.calls[1][1][-1].content

    def test_an_unknown_week_that_stays_wrong_stores_the_fixed_answer(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        unknown = MONDAY + timedelta(weeks=2)
        bad = said("Reduced.", [{"tool": "reduce_week", "percent": 20}], week=unknown.isoformat())
        provide(bad, bad)

        sent = send(athlete, "Reduce two weeks from now")

        assert sent.coach.text == NOT_USABLE
        assert sent.coach.plan is None
        assert drafts(athlete) == []

    def test_a_past_week_is_refused_even_when_it_has_a_plan(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        last_monday = MONDAY - timedelta(weeks=1)
        last_plan = make_plan(athlete, last_monday, status="confirmed", workouts=2)
        provider = provide(
            said(
                "Reduced last week.",
                [{"tool": "reduce_week", "percent": 20}],
                week=last_monday.isoformat(),
            ),
            said("Last week is in the past and cannot be changed."),
        )

        sent = send(athlete, "Change last week")

        assert sent.coach.text == "Last week is in the past and cannot be changed."
        assert sent.coach.plan is None
        assert drafts(athlete) == []
        assert len(provider.calls) == ATTEMPTS
        assert "- week:" in provider.calls[1][1][-1].content
        assert PlannedWorkout.objects.for_user(athlete).filter(plan=last_plan).count() == 2

    def test_another_users_week_is_refused(
        self, athlete: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        next_monday = MONDAY + timedelta(weeks=1)
        bob_plan = make_plan(bob, next_monday, status="confirmed", workouts=2)
        bob_workout = PlannedWorkout.objects.for_user(bob).filter(plan=bob_plan).first()
        assert bob_workout is not None
        provider = provide(
            said(
                "Skipped.",
                [{"tool": "skip_workout", "id": str(bob_workout.lineage)}],
                week=next_monday.isoformat(),
            ),
            said("You do not have a plan for next week yet."),
        )

        sent = send(athlete, "Skip Monday next week")

        assert sent.coach.text == "You do not have a plan for next week yet."
        assert sent.coach.plan is None
        assert drafts(athlete) == []
        assert drafts(bob) == []
        assert PlannedWorkout.objects.for_user(bob).filter(plan=bob_plan).count() == 2
        assert len(provider.calls) == ATTEMPTS
        assert "- week:" in provider.calls[1][1][-1].content

    def test_another_users_workout_on_a_shared_named_week_is_refused(
        self, athlete: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        next_monday = MONDAY + timedelta(weeks=1)
        make_plan(athlete, next_monday, status="confirmed", workouts=2)
        bob_plan = make_plan(bob, next_monday, status="confirmed", workouts=2)
        bob_workout = PlannedWorkout.objects.for_user(bob).filter(plan=bob_plan).first()
        assert bob_workout is not None
        provider = provide(
            said(
                "Skipped.",
                [{"tool": "skip_workout", "id": str(bob_workout.lineage)}],
                week=next_monday.isoformat(),
            ),
            said("I could not find that workout."),
        )

        sent = send(athlete, "Skip that workout next week")

        assert sent.coach.text == "I could not find that workout."
        assert sent.coach.plan is None
        assert drafts(athlete) == []
        assert drafts(bob) == []
        assert PlannedWorkout.objects.for_user(bob).filter(plan=bob_plan).count() == 2
        assert len(provider.calls) == ATTEMPTS

    def test_touching_two_weeks_by_workout_is_repaired_once_then_refused_with_one_week_only(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        next_monday = MONDAY + timedelta(weeks=1)
        next_plan = make_plan(athlete, next_monday, status="confirmed", workouts=2)
        this_workout = saturday_workout(athlete)
        next_workout = PlannedWorkout.objects.for_user(athlete).filter(plan=next_plan).first()
        assert next_workout is not None
        both_weeks = said(
            "Skipped both.",
            [
                {"tool": "skip_workout", "id": str(this_workout.lineage)},
                {"tool": "skip_workout", "id": str(next_workout.lineage)},
            ],
        )
        provider = provide(both_weeks, both_weeks)

        sent = send(athlete, "Skip Saturday this week and Monday next week")

        assert sent.athlete.text == "Skip Saturday this week and Monday next week"
        assert sent.coach.text == ONE_WEEK_ONLY
        assert sent.coach.plan is None
        assert sent.coach.changes == []
        assert drafts(athlete) == []
        assert len(provider.calls) == ATTEMPTS
        assert OTHER_WEEK_PROBLEM in provider.calls[1][1][-1].content
        assert PlannedWorkout.objects.for_user(athlete).filter(plan=next_plan).count() == 2

    def test_touching_two_weeks_by_day_is_repaired_once_then_refused_with_one_week_only(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        next_monday = MONDAY + timedelta(weeks=1)
        make_plan(athlete, next_monday, status="confirmed", workouts=2)
        this_workout = saturday_workout(athlete)
        cross_week = said(
            "Moved it to Monday next week.",
            [
                {
                    "tool": "move_workout",
                    "id": str(this_workout.lineage),
                    "day": next_monday.isoformat(),
                }
            ],
        )
        provider = provide(cross_week, cross_week)

        sent = send(athlete, "Move Saturday to next Monday")

        assert sent.athlete.text == "Move Saturday to next Monday"
        assert sent.coach.text == ONE_WEEK_ONLY
        assert sent.coach.plan is None
        assert drafts(athlete) == []
        assert len(provider.calls) == ATTEMPTS
        assert OTHER_WEEK_PROBLEM in provider.calls[1][1][-1].content

    def test_touching_two_weeks_with_a_named_week_is_refused_with_one_week_only(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        next_monday = MONDAY + timedelta(weeks=1)
        next_plan = make_plan(athlete, next_monday, status="confirmed", workouts=2)
        this_workout = saturday_workout(athlete)
        next_workout = PlannedWorkout.objects.for_user(athlete).filter(plan=next_plan).first()
        assert next_workout is not None
        both_weeks = said(
            "Skipped both.",
            [
                {"tool": "skip_workout", "id": str(next_workout.lineage)},
                {"tool": "skip_workout", "id": str(this_workout.lineage)},
            ],
            week=next_monday.isoformat(),
        )
        provider = provide(both_weeks, both_weeks)

        sent = send(athlete, "Skip Monday next week and Saturday this week")

        assert sent.coach.text == ONE_WEEK_ONLY
        assert sent.coach.plan is None
        assert drafts(athlete) == []
        assert len(provider.calls) == ATTEMPTS
        assert OTHER_WEEK_PROBLEM in provider.calls[1][1][-1].content

    def test_touching_two_weeks_can_be_repaired_into_a_plain_reply(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        next_monday = MONDAY + timedelta(weeks=1)
        next_plan = make_plan(athlete, next_monday, status="confirmed", workouts=2)
        this_workout = saturday_workout(athlete)
        next_workout = PlannedWorkout.objects.for_user(athlete).filter(plan=next_plan).first()
        assert next_workout is not None
        provider = provide(
            said(
                "Skipped both.",
                [
                    {"tool": "skip_workout", "id": str(this_workout.lineage)},
                    {"tool": "skip_workout", "id": str(next_workout.lineage)},
                ],
            ),
            said("I can only change one week at a time. Should we start with this week?"),
        )

        sent = send(athlete, "Skip Saturday and next Monday")

        assert (
            sent.coach.text
            == "I can only change one week at a time. Should we start with this week?"
        )
        assert sent.coach.plan is None
        assert drafts(athlete) == []
        assert len(provider.calls) == ATTEMPTS
        assert OTHER_WEEK_PROBLEM in provider.calls[1][1][-1].content

    def test_another_users_workout_does_not_trigger_one_week_only(
        self, athlete: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        next_monday = MONDAY + timedelta(weeks=1)
        bob_plan = make_plan(bob, next_monday, status="confirmed", workouts=2)
        bob_workout = PlannedWorkout.objects.for_user(bob).filter(plan=bob_plan).first()
        assert bob_workout is not None
        bad = said("Skipped.", [{"tool": "skip_workout", "id": str(bob_workout.lineage)}])
        provide(bad, bad)

        sent = send(athlete, "Skip that workout")

        assert sent.coach.text == NOT_USABLE
        assert sent.coach.plan is None
        assert drafts(athlete) == []
        assert drafts(bob) == []


class TestAnAnswerThatCannotBeUsed:
    def test_is_repaired_once(self, athlete: User, provide: Callable[..., Scripted]) -> None:
        provider = provide("Sure, done!", said("Fixed."))

        sent = send(athlete, "Hi")

        assert sent.coach.text == "Fixed."
        assert len(provider.calls) == ATTEMPTS
        repair = provider.calls[1][1][-1].content
        assert "cannot be used" in repair and "Sure" not in repair

    def test_an_action_that_is_not_allowed_is_repaired_too(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        past = PlannedWorkout.objects.for_user(athlete).get(day="2026-11-09")
        provider = provide(
            said("x", [{"tool": "skip_workout", "id": str(past.lineage)}]), said("Sorry, no.")
        )

        sent = send(athlete, "Skip Monday")

        assert sent.coach.text == "Sorry, no."
        assert "past" in provider.calls[1][1][-1].content
        assert drafts(athlete) == []

    def test_if_it_stays_unusable_the_message_is_kept_with_a_fixed_answer(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        provide("no json", "still no json")

        sent = send(athlete, "Hi")

        assert sent.athlete.text == "Hi"
        assert sent.coach.text == NOT_USABLE
        assert sent.coach.plan is None and drafts(athlete) == []
        assert len(AIUsageRecord.objects.for_user(athlete)) == 2

    def test_an_answer_that_was_cut_off_is_not_used(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(Completion(said("Cut"), 100, 50, truncated=True), said("Short."))

        assert send(athlete, "Hi").coach.text == "Short."


class TestWhatFailsStoresNothing:
    def test_no_provider(self, alice: User) -> None:
        make_plan(alice, MONDAY, workouts=3)

        with pytest.raises(coach_services.NotConfiguredError):
            send(alice, "Hi")

        assert ChatMessage.objects.count() == 0

    @pytest.mark.parametrize("error", [RateLimitedError("slow"), ProviderUnavailableError("down")])
    def test_the_provider_fails(
        self, athlete: User, provide: Callable[..., Scripted], error: Exception
    ) -> None:
        provide(error)

        with pytest.raises(type(error)):
            send(athlete, "Hi")

        assert ChatMessage.objects.count() == 0

    @pytest.mark.parametrize("text", ["", "   ", "x" * (USER_TEXT_MAX + 1), "a‮b"])
    def test_a_message_that_cannot_be_used(
        self, athlete: User, provide: Callable[..., Scripted], text: str
    ) -> None:
        provider = provide()

        with pytest.raises(ValidationError):
            send(athlete, text)

        assert provider.calls == [] and ChatMessage.objects.count() == 0


class TestWithoutAPlan:
    def test_a_question_is_answered(self, alice: User, provide: Callable[..., Scripted]) -> None:
        AIProviderConfiguration.objects.create(
            owner=alice, provider="anthropic", model="claude-sonnet-5-5", api_key=KEY
        )
        provider = provide(said("You have no plan yet."))

        sent = send(alice, "What is next?")

        assert sent.coach.text == "You have no plan yet."
        assert briefing_sent(provider)["weeks"] == []


class TestIllness:
    def test_a_sick_message_stores_a_draft_with_easy_return_and_an_absence(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        PlannedWorkout.objects.for_user(athlete).filter(day=SUNDAY).update(
            goal="threshold",
            zone_system="pace",
            zone=4,
            segments=[
                {
                    "kind": "work",
                    "seconds": 3600,
                    "repeat": 1,
                    "zone_system": "pace",
                    "zone": 4,
                }
            ],
        )
        provide(
            said(
                "Rest today, then take it easy.",
                [{"tool": "mark_sick", "symptoms": "above_neck", "fever": False, "days": 1}],
            )
        )

        sent = send(athlete, "I have a sore throat today.")

        (draft,) = drafts(athlete)
        assert sent.coach.plan == draft
        assert sent.coach.text == "Rest today, then take it easy."
        assert DOCTOR_HINT not in sent.coach.text
        loaded = plan_services.load(athlete, draft.pk)
        days = {w.day.isoformat(): w for w in loaded.workouts}
        assert SATURDAY not in days
        sunday = days[SUNDAY]
        assert intensity_of(sunday) is Intensity.EASY
        assert sunday.duration_minutes == 36
        (period,) = UnavailablePeriod.objects.for_user(athlete)
        assert period.kind == UnavailablePeriod.Kind.ILLNESS
        assert (period.start_date.isoformat(), period.end_date.isoformat()) == (SATURDAY, SATURDAY)
        assert sent.coach.changes == [
            f"Sick pause (1 day, {SATURDAY}): 1 workout removed",
            f"Easy return (2 days, {SUNDAY} to 2026-11-16): 1 workout made easy and shorter",
            f"Illness noted as an absence ({SATURDAY})",
        ]

    def test_stores_the_absence_and_change_even_without_a_plan(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        AIProviderConfiguration.objects.create(
            owner=alice, provider="anthropic", model="claude-sonnet-5-5", api_key=KEY
        )
        provide(
            said(
                "Get well soon.",
                [{"tool": "mark_sick", "symptoms": "below_neck", "fever": False, "days": 3}],
            )
        )

        sent = send(alice, "I am sick for three days.")

        assert sent.coach.plan is None
        assert drafts(alice) == []
        (period,) = UnavailablePeriod.objects.for_user(alice)
        assert period.kind == UnavailablePeriod.Kind.ILLNESS
        assert (period.start_date.isoformat(), period.end_date.isoformat()) == (
            SATURDAY,
            "2026-11-16",
        )
        assert sent.coach.changes == [f"Illness noted as an absence ({SATURDAY} to 2026-11-16)"]

    def test_fever_appends_the_doctor_hint(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(
            said(
                "Please rest.",
                [{"tool": "mark_sick", "symptoms": "below_neck", "fever": True, "days": 2}],
            )
        )

        sent = send(athlete, "I have a fever.")

        assert sent.coach.text == f"Please rest.\n\n{DOCTOR_HINT}"
        (period,) = UnavailablePeriod.objects.for_user(athlete)
        assert (period.start_date.isoformat(), period.end_date.isoformat()) == (SATURDAY, SUNDAY)

    def test_another_user_is_not_affected(
        self, athlete: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        bob_plan = make_plan(bob, MONDAY, workouts=7)
        bob_period = UnavailablePeriod.objects.create(
            owner=bob,
            kind=UnavailablePeriod.Kind.ILLNESS,
            start_date=MONDAY,
            end_date=MONDAY,
        )
        provide(
            said(
                "Rest up.",
                [{"tool": "mark_sick", "symptoms": "above_neck", "fever": True, "days": 2}],
            )
        )

        send(athlete, "Sick with fever")

        assert drafts(bob) == []
        assert PlannedWorkout.objects.for_user(bob).filter(plan=bob_plan).count() == 7
        bob_period.refresh_from_db()
        assert (bob_period.start_date, bob_period.end_date) == (MONDAY, MONDAY)
        assert UnavailablePeriod.objects.for_user(bob).count() == 1


class TestAConfirmedSickDraft:
    def test_takes_the_paused_workouts_out_of_the_calendar_and_updates_the_return_days(
        self,
        athlete: User,
        provide: Callable[..., Scripted],
        calendar: Calendar,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ProviderConnection.objects.create(
            owner=athlete, provider="intervals_icu", api_key=INTERVALS_KEY, athlete_id="i100"
        )
        room_to_train(athlete)
        before = WeeklyPlan.objects.for_user(athlete).get()
        assert push(athlete, before.pk).synced == 7
        events = {
            row.external_id: row.event_id
            for row in WorkoutExport.objects.for_user(athlete)
            if row.event_id is not None
        }
        paused = PlannedWorkout.objects.for_user(athlete).get(plan=before, day=WEDNESDAY)
        paused_event = events[key_of(paused)]
        sent_before = {event_id: dict(event) for event_id, event in calendar.events.items()}
        # A mild illness pauses the day and makes the two days after it easy and shorter.
        eased = list(
            PlannedWorkout.objects.for_user(athlete)
            .filter(plan=before, day__gt=paused.day)
            .order_by("day")[:2]
        )
        monkeypatch.setattr(goal_services, "_utc_now", lambda: MIDWEEK)
        provide(
            said(
                "Rest today.",
                [{"tool": "mark_sick", "symptoms": "above_neck", "fever": False, "days": 1}],
            )
        )

        draft = send(athlete, "Sore throat this morning.").coach.plan
        assert draft is not None
        plan_services.confirm(athlete, draft.pk)
        result = push(athlete, draft.pk)

        assert ("delete", paused_event) in calendar.calls
        assert paused_event not in calendar.events
        assert export_state(athlete, draft).older == 0
        updated = {event["external_id"]: event for event in calendar.events.values()}
        for workout in eased:
            was, now = sent_before[events[key_of(workout)]], updated[key_of(workout)]
            assert now["start_date_local"] == was["start_date_local"]  # the same day
            assert "- 36m" in now["description"] and now["description"] != was["description"]
        left = WorkoutExport.objects.for_user(athlete)
        assert paused_event not in {row.event_id for row in left}
        assert result.removed == 1 and result.left_behind == 0
        assert result.synced == len(events) - 1  # every workout that is still in the plan


class TestTheText:
    def test_is_trimmed_and_may_have_lines(self) -> None:
        assert clean_text("  Two\nlines  ") == "Two\nlines"

    def test_the_limit(self) -> None:
        assert len(clean_text("x" * USER_TEXT_MAX)) == USER_TEXT_MAX


class TestTheConversation:
    def test_is_only_the_own(
        self, athlete: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(said())
        send(athlete, "Mine")
        ChatMessage.objects.create(owner=bob, role="user", text="Bob's")

        assert [m.text for m in services.history(athlete)] == ["Mine", "Done."]

    def test_can_be_deleted_without_the_drafts(
        self, athlete: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        workout = saturday_workout(athlete)
        provide(said("Skipping.", [{"tool": "skip_workout", "id": str(workout.lineage)}]))
        send(athlete, "Skip Saturday")
        ChatMessage.objects.create(owner=bob, role="user", text="Bob's")

        assert clear(athlete) == 2

        assert services.history(athlete) == []
        assert len(drafts(athlete)) == 1
        assert ChatMessage.objects.for_user(bob).count() == 1


def season_following(user: User) -> SeasonPlan:
    """A season that follows the skeleton: all minutes in running."""
    return SeasonPlan(
        tuple(
            PlanWeek(
                week.week_start,
                ((Sport.RUNNING, week.target_minutes),),
                Focus.ENDURANCE,
                "Because.",
                (KeySession(Sport.RUNNING, SessionKind.RACE, 1),) if week.races else (),
            )
            for week in skeleton_for(user).weeks
        ),
        "The season.",
    )


def following_trip(user: User, days: int = 21) -> str:
    """The season answer for the trip: the skeleton is the one with the absence in it."""
    period = UnavailablePeriod.objects.create(
        owner=user,
        kind=UnavailablePeriod.Kind.OTHER,
        start_date=date(2026, 11, 23),
        end_date=date(2026, 11, 23) + timedelta(days=days - 1),
    )
    try:
        return json.dumps(season_json(season_following(user)))
    finally:
        period.delete()


def confirmed_season(user: User) -> SeasonPlanVersion:
    GoalRow.objects.create(
        owner=user,
        kind="race",
        title="Race",
        priority="main",
        target_date=MONDAY + timedelta(weeks=9, days=6),
        discipline="running",
        distance_m=10_000,
    )
    skeleton = skeleton_for(user)
    plan = season_following(user)
    stored = season_services.save_draft(
        user, plan, SeasonContext(skeleton), input_snapshot=collect_inputs(user)
    )
    return season_services.confirm(user, stored.pk)


TRIP = [{"tool": "replan_from", "start": "2026-11-23", "days": 21, "kind": "other"}]
TRIP_END = "2026-12-13"


class TestALongerAbsence:
    def test_a_three_week_trip_stores_the_absence_and_a_season_draft(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        room_to_train(athlete)
        base = confirmed_season(athlete)
        provider = provide(said("A new season around your trip.", TRIP), following_trip(athlete))

        sent = send(athlete, "I am on a business trip for three weeks from 23 November.")

        (period,) = UnavailablePeriod.objects.for_user(athlete)
        assert period.kind == UnavailablePeriod.Kind.OTHER
        assert (period.start_date.isoformat(), period.end_date.isoformat()) == (
            "2026-11-23",
            TRIP_END,
        )
        (draft,) = SeasonPlanVersion.objects.for_user(athlete).filter(status="draft")
        assert draft.parent == base
        assert draft.request == SEASON_REQUEST.format(
            start="2026-11-23", end=TRIP_END, days=21, kind="other"
        )
        assert sent.coach.season_plan == draft
        assert sent.coach.plan is None
        assert sent.coach.text == "A new season around your trip."
        assert sent.coach.changes == [
            f"Absence noted (2026-11-23 to {TRIP_END})",
            SEASON_DRAFT_MADE,
        ]
        assert drafts(athlete) == []
        assert len(provider.calls) == 2

    def test_nothing_is_confirmed_or_pushed(
        self, athlete: User, provide: Callable[..., Scripted], calendar: Calendar
    ) -> None:
        room_to_train(athlete)
        base = confirmed_season(athlete)
        provide(said("Around it.", TRIP), following_trip(athlete))
        confirmed_weeks = WeeklyPlan.objects.for_user(athlete).filter(status="confirmed").count()

        send(athlete, "Away for three weeks.")

        base.refresh_from_db()
        assert base.status == "confirmed"
        assert (
            not SeasonPlanVersion.objects.for_user(athlete)
            .filter(status="confirmed")
            .exclude(pk=base.pk)
        )
        assert (
            WeeklyPlan.objects.for_user(athlete).filter(status="confirmed").count()
            == confirmed_weeks
        )
        assert WorkoutExport.objects.count() == 0
        assert calendar.events == {}

    def test_the_newest_draft_is_the_one_to_change(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        room_to_train(athlete)
        confirmed_season(athlete)
        provide(said("Around it.", TRIP), following_trip(athlete))
        first = send(athlete, "Away for three weeks.").coach.season_plan
        provide(said("Longer.", [{**TRIP[0], "days": 28}]), following_trip(athlete, 28))

        second = send(athlete, "Make it four weeks.").coach.season_plan

        assert first is not None and second is not None
        assert second.parent == first
        assert second.version == first.version + 1

    def test_without_a_season_the_absence_is_kept_and_it_is_said(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(said("Around it.", TRIP))

        sent = send(athlete, "Away for three weeks.")

        assert UnavailablePeriod.objects.for_user(athlete).count() == 1
        assert sent.coach.season_plan is None
        assert sent.coach.changes == [f"Absence noted (2026-11-23 to {TRIP_END})", NO_SEASON_PLAN]

    @pytest.mark.parametrize(
        "season_answer",
        [
            "not json",
            ProviderUnavailableError("down"),
            RateLimitedError("slow"),
        ],
    )
    def test_when_the_season_change_fails_the_absence_is_kept(
        self, athlete: User, provide: Callable[..., Scripted], season_answer: object
    ) -> None:
        room_to_train(athlete)
        confirmed_season(athlete)
        provide(said("Around it.", TRIP), *([season_answer] * 3))

        sent = send(athlete, "Away for three weeks.")

        assert UnavailablePeriod.objects.for_user(athlete).count() == 1
        assert SeasonPlanVersion.objects.for_user(athlete).count() == 1
        assert sent.coach.season_plan is None
        assert sent.coach.changes == [
            f"Absence noted (2026-11-23 to {TRIP_END})",
            SEASON_CHANGE_FAILED,
        ]
        assert [m.role for m in services.history(athlete)] == ["user", "coach"]

    def test_a_season_that_stays_the_same_is_said_to_have_failed(
        self, athlete: User, provide: Callable[..., Scripted], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        room_to_train(athlete)
        confirmed_season(athlete)
        provide(said("Around it.", TRIP))

        def unchanged(*args: Any, **kwargs: Any) -> None:
            raise PlanUnchanged

        monkeypatch.setattr(season_generation, "change", unchanged)

        sent = send(athlete, "Away for three weeks.")

        assert sent.coach.changes[-1] == SEASON_CHANGE_FAILED

    def test_no_time_to_plan_is_said_to_have_failed(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        room_to_train(athlete)
        confirmed_season(athlete)
        WeekdayMinutes.objects.for_user(athlete).delete()
        provide(said("Around it.", TRIP))

        sent = send(athlete, "Away for three weeks.")

        assert sent.coach.changes == [
            f"Absence noted (2026-11-23 to {TRIP_END})",
            SEASON_CHANGE_FAILED,
        ]

    def test_another_action_with_it_is_refused_and_nothing_is_stored(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        room_to_train(athlete)
        confirmed_season(athlete)
        both: list[dict[str, Any]] = [*TRIP, {"tool": "free_day", "day": SUNDAY}]
        provide(said("Both.", both), said("Both.", both))

        sent = send(athlete, "Away for three weeks.")

        assert sent.coach.text == NOT_USABLE
        assert UnavailablePeriod.objects.for_user(athlete).count() == 0
        assert SeasonPlanVersion.objects.for_user(athlete).count() == 1

    def test_the_season_of_another_user_is_untouched(
        self, athlete: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        room_to_train(athlete)
        confirmed_season(athlete)
        room_to_train(bob)
        theirs = confirmed_season(bob)
        provide(said("Around it.", TRIP), following_trip(athlete))

        send(athlete, "Away for three weeks.")

        assert list(SeasonPlanVersion.objects.for_user(bob)) == [theirs]
        theirs.refresh_from_db()
        assert theirs.status == "confirmed"
        assert UnavailablePeriod.objects.for_user(bob).count() == 0
        assert ChatMessage.objects.for_user(bob).count() == 0
