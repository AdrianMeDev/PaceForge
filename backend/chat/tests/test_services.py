import json
from collections.abc import Callable
from typing import Any

import pytest
from django.core.exceptions import ValidationError

from accounts.models import User
from chat import services
from chat.models import USER_TEXT_MAX, ChatMessage
from chat.services import ATTEMPTS, HISTORY_TOLD, NOT_USABLE, REASON, clean_text, clear, send
from coach import services as coach_services
from coach.models import AIProviderConfiguration, AIUsageRecord
from coach.providers.base import Completion, ProviderUnavailableError, RateLimitedError
from goals import services as goal_services
from planning.models import PlannedWorkout, WeeklyPlan
from planning.tests.scripted import Scripted
from reviews.tests.builders import MONDAY, NOW, make_plan

pytestmark = pytest.mark.django_db

KEY = "sk-ant-test-0123456789-abcdefghij"
SATURDAY = "2026-11-14"
SUNDAY = "2026-11-15"


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


def said(reply: str = "Done.", actions: list[dict[str, Any]] | None = None) -> str:
    return json.dumps({"reply": reply, "actions": actions or []})


def saturday_workout(user: User) -> PlannedWorkout:
    return PlannedWorkout.objects.for_user(user).get(day=SATURDAY)


def drafts(user: User) -> list[WeeklyPlan]:
    return list(WeeklyPlan.objects.for_user(user).filter(status="draft"))


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
        provide(said("You have no plan yet."))

        sent = send(alice, "What is next?")

        assert sent.coach.text == "You have no plan yet."


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
