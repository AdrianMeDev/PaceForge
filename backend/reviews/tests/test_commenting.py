import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from accounts.models import User
from coach import services as coach_services
from coach.models import AIProviderConfiguration, AIUsageRecord
from coach.providers.base import (
    Completion,
    EndpointNotAllowedError,
    InvalidKeyError,
    ProviderUnavailableError,
    RateLimitedError,
    UnexpectedResponseError,
)
from goals import services as goal_services
from planning.tests.scripted import Scripted
from reviews import commenting
from reviews.briefing import build_briefing, to_json
from reviews.commenting import (
    ATTEMPTS,
    COMMENT_MAX_TOKENS,
    CommentNotUsable,
    NothingToReview,
    comment_on,
)
from reviews.models import WeekComment, WeekFeedback
from reviews.prompt import SYSTEM_PROMPT
from reviews.services import WeekNotReviewable, week_review

from .builders import MONDAY, NOW, make_activity, make_plan

pytestmark = pytest.mark.django_db

KEY = "sk-ant-test-0123456789-abcdefghij"
MARKER = "SECRETMARKER"


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def workout_fields() -> dict[str, Any]:
    return {}


@pytest.fixture
def alice(workout_fields: dict[str, Any]) -> User:
    user = User.objects.create_user("alice@example.com")
    AIProviderConfiguration.objects.create(
        owner=user, provider="anthropic", model="claude-sonnet-5-5", api_key=KEY
    )
    make_plan(user, workouts=[workout_fields] * 2)
    make_activity(user, "2026-11-09T07:00", rpe=6)
    return user


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def good(comment: str = "A steady week.", next_week: str = "hold") -> str:
    return json.dumps({"comment": comment, "next_week": next_week})


def records(user: User) -> list[AIUsageRecord]:
    return list(AIUsageRecord.objects.for_user(user).order_by("id"))


def comments(user: User) -> list[WeekComment]:
    return list(WeekComment.objects.for_user(user))


class TestAGoodAnswer:
    def test_the_comment_is_stored_for_the_week(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good("Two sessions planned, one done.", "reduce"))

        stored = comment_on(alice, MONDAY)

        assert comments(alice) == [stored]
        assert (stored.owner, stored.week_start) == (alice, MONDAY)
        assert (stored.comment, stored.next_week) == ("Two sessions planned, one done.", "reduce")

    def test_the_call_is_made_with_the_briefing_the_prompt_and_json_output(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())

        comment_on(alice, MONDAY)

        ((system, messages, max_tokens),) = scripted.calls
        assert system == SYSTEM_PROMPT
        assert max_tokens == COMMENT_MAX_TOKENS
        assert scripted.json_outputs == [True]
        (message,) = messages
        assert message.role == "user"
        assert message.content.endswith(to_json(build_briefing(week_review(alice, MONDAY))))

    def test_one_call_is_one_usage_record_for_the_week_review(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good())

        comment_on(alice, MONDAY)

        (record,) = records(alice)
        assert (record.purpose, record.outcome) == ("week_review", "success")
        assert (record.input_tokens, record.output_tokens) == (100, 50)

    @pytest.mark.parametrize("workout_fields", [{"title": MARKER, "notes": MARKER}])
    def test_the_coach_is_told_no_free_text(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        make_activity(alice, "2026-11-11T07:00", notes=MARKER, sport="strength")
        WeekFeedback.objects.create(owner=alice, week_start=MONDAY, fatigue=4, notes=MARKER)
        scripted = provide(good())

        comment_on(alice, MONDAY)

        (system, messages, _) = scripted.calls[0]
        assert MARKER not in system
        assert all(MARKER not in message.content for message in messages)

    def test_a_comment_asked_for_again_replaces_the_first_one(
        self, alice: User, provide: Callable[..., Scripted], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provide(good("First.", "hold"), good("Second.", "increase"))
        first_time = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
        monkeypatch.setattr(commenting, "_now", lambda: first_time)
        first = comment_on(alice, MONDAY)
        monkeypatch.setattr(commenting, "_now", lambda: first_time + timedelta(hours=2))

        second = comment_on(alice, MONDAY)

        assert second.pk == first.pk
        (stored,) = comments(alice)
        assert (stored.comment, stored.next_week) == ("Second.", "increase")
        assert stored.created_at == first_time + timedelta(hours=2)

    def test_another_week_and_another_user_are_not_touched(
        self, alice: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        before = MONDAY - timedelta(weeks=1)
        WeekComment.objects.create(owner=alice, week_start=before, comment="old", next_week="hold")
        WeekComment.objects.create(owner=bob, week_start=MONDAY, comment="bobs", next_week="hold")
        provide(good("new"))

        comment_on(alice, MONDAY)

        assert WeekComment.objects.get(owner=bob).comment == "bobs"
        assert WeekComment.objects.get(owner=alice, week_start=before).comment == "old"
        assert WeekComment.objects.get(owner=alice, week_start=MONDAY).comment == "new"


class TestARepair:
    def test_an_unreadable_answer_is_told_what_was_wrong_and_the_second_is_used(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide("Looks like a good week!", good("Fixed."))

        stored = comment_on(alice, MONDAY)

        assert stored.comment == "Fixed."
        assert len(scripted.calls) == ATTEMPTS == 2
        _, messages, _ = scripted.calls[1]
        assert [message.role for message in messages] == ["user", "assistant", "user"]
        assert messages[1].content == "Looks like a good week!"
        assert "The answer is not one JSON object" in messages[2].content
        assert [r.outcome for r in records(alice)] == ["success", "success"]

    def test_the_problems_are_the_fixed_texts_and_nothing_of_the_answer(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(json.dumps({"comment": "", "next_week": "up", MARKER: 1}), good())

        comment_on(alice, MONDAY)

        _, messages, _ = scripted.calls[1]
        repair = messages[2].content
        assert "- comment: The comment must not be empty." in repair
        assert '- next_week: Use one of "increase", "hold", "reduce".' in repair
        assert "not part of the format" in repair
        assert MARKER not in repair.replace(messages[1].content, "")

    def test_an_answer_that_was_cut_off_is_not_used(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(
            Completion(good("Cut", "hold"), 100, 1000, truncated=True), good("Whole")
        )

        stored = comment_on(alice, MONDAY)

        assert stored.comment == "Whole"
        assert "cut off" in scripted.calls[1][1][2].content

    def test_an_answer_with_nothing_in_it_is_shown_as_such(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide("  ", good())

        comment_on(alice, MONDAY)

        assert scripted.calls[1][1][1].content == "(no answer)"

    def test_two_bad_answers_store_nothing_and_say_what_was_wrong(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide("nope", good(next_week="sideways"))

        with pytest.raises(CommentNotUsable) as raised:
            comment_on(alice, MONDAY)

        assert [(p.path, p.message) for p in raised.value.problems] == [
            ("next_week", 'Use one of "increase", "hold", "reduce".')
        ]
        assert comments(alice) == []
        assert len(records(alice)) == 2

    def test_a_failed_try_leaves_the_earlier_comment_alone(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        WeekComment.objects.create(owner=alice, week_start=MONDAY, comment="old", next_week="hold")
        provide("nope", "still nope")

        with pytest.raises(CommentNotUsable):
            comment_on(alice, MONDAY)

        assert [c.comment for c in comments(alice)] == ["old"]

    def test_two_cut_off_answers(self, alice: User, provide: Callable[..., Scripted]) -> None:
        cut = Completion("{", 100, 1000, truncated=True)
        provide(cut, cut)

        with pytest.raises(CommentNotUsable) as raised:
            comment_on(alice, MONDAY)

        assert "cut off" in raised.value.problems[0].message


class TestWhenTheProviderFails:
    @pytest.mark.parametrize(
        ("error", "status", "outcome"),
        [
            (InvalidKeyError("refused"), "invalid", "invalid_key"),
            (ProviderUnavailableError("down"), "unavailable", "unavailable"),
            (RateLimitedError("slow", 5), "untested", "rate_limited"),
            (UnexpectedResponseError("odd"), "untested", "unexpected"),
        ],
    )
    def test_the_error_passes_through_and_nothing_is_stored(
        self,
        alice: User,
        provide: Callable[..., Scripted],
        error: Exception,
        status: str,
        outcome: str,
    ) -> None:
        provide(error)

        with pytest.raises(type(error)):
            comment_on(alice, MONDAY)

        assert comments(alice) == []
        assert [r.outcome for r in records(alice)] == [outcome]
        assert AIProviderConfiguration.objects.get(owner=alice).status == status

    def test_an_error_on_the_second_call_passes_through_too(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide("nope", RateLimitedError("slow"))

        with pytest.raises(RateLimitedError):
            comment_on(alice, MONDAY)

        assert comments(alice) == []
        assert [r.outcome for r in records(alice)] == ["success", "rate_limited"]

    def test_an_address_that_is_not_allowed_sends_nothing(
        self, alice: User, provide: Callable[..., Scripted], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(configuration: Any, model: str | None = None, effort: str = "") -> Any:
            raise EndpointNotAllowedError("not allowed")

        monkeypatch.setattr(coach_services, "provider_for", refuse)

        with pytest.raises(EndpointNotAllowedError):
            comment_on(alice, MONDAY)

        assert records(alice) == [] and comments(alice) == []

    def test_without_a_provider_nothing_is_asked(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())
        AIProviderConfiguration.objects.filter(owner=alice).delete()

        with pytest.raises(coach_services.NotConfiguredError):
            comment_on(alice, MONDAY)

        assert scripted.calls == [] and comments(alice) == []


class TestBeforeAnythingIsSent:
    def test_a_week_with_nothing_in_it_is_not_asked_about(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())

        with pytest.raises(NothingToReview):
            comment_on(alice, MONDAY - timedelta(weeks=1))

        assert scripted.calls == [] and records(alice) == []

    def test_nothing_is_asked_without_a_provider_either_when_there_is_nothing_to_review(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        AIProviderConfiguration.objects.filter(owner=alice).delete()

        with pytest.raises(NothingToReview):
            comment_on(alice, MONDAY - timedelta(weeks=1))

    @pytest.mark.parametrize("offset", [-6, 1, 5])
    def test_a_week_that_cannot_be_reviewed_is_not_asked_about(
        self, alice: User, provide: Callable[..., Scripted], offset: int
    ) -> None:
        scripted = provide(good())

        with pytest.raises(WeekNotReviewable):
            comment_on(alice, MONDAY + timedelta(weeks=offset))

        assert scripted.calls == []

    def test_a_day_that_is_no_monday(self, alice: User, provide: Callable[..., Scripted]) -> None:
        scripted = provide(good())

        with pytest.raises(WeekNotReviewable):
            comment_on(alice, MONDAY + timedelta(days=1))

        assert scripted.calls == []

    def test_feedback_alone_is_enough_to_look_back_on(
        self, alice: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        WeekFeedback.objects.create(owner=alice, week_start=MONDAY - timedelta(weeks=1), pain=3)
        provide(good())

        assert comment_on(alice, MONDAY - timedelta(weeks=1)).comment == "A steady week."

    def test_the_data_of_another_user_is_never_told(
        self, alice: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        make_plan(bob, MONDAY - timedelta(weeks=1), workouts=3)
        scripted = provide(good())

        with pytest.raises(NothingToReview):
            comment_on(alice, MONDAY - timedelta(weeks=1))

        assert scripted.calls == []


class TestTheLimitsAreWrittenOutOnPurpose:
    def test_the_numbers(self) -> None:
        assert (ATTEMPTS, COMMENT_MAX_TOKENS) == (2, 1000)


class TestTheDeadline:
    def test_the_answer_and_its_repair_share_one_deadline(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide("Looks like a good week!", good())

        comment_on(alice, MONDAY)

        first, second = scripted.deadlines
        assert first is not None
        assert first is second

    def test_no_repair_is_started_without_time_for_it(
        self, alice: User, provide: Callable[..., Scripted], settings: Any
    ) -> None:
        settings.AI_REQUEST_DEADLINE_SECONDS = coach_services.MIN_ATTEMPT_SECONDS - 1
        scripted = provide("Looks like a good week!", good())

        with pytest.raises(CommentNotUsable):
            comment_on(alice, MONDAY)

        assert len(scripted.calls) == 1
