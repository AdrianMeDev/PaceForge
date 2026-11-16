import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from accounts.models import User
from availability.models import AvailabilitySettings, UnavailablePeriod, WeekdayMinutes
from coach.models import AIProviderConfiguration, AIUsageRecord
from coach.providers.base import Completion, ProviderUnavailableError, RateLimitedError
from coach.services import NotConfiguredError
from goals import services as goal_services
from goals.models import Goal
from planning.prompt import repair_message
from planning.schema import Sport
from planning.tests.scripted import Scripted
from season import services
from season.briefing import build_briefing
from season.generation import (
    ATTEMPTS,
    REASON,
    NothingToPlan,
    PlanNotUsable,
    generate,
)
from season.inputs import skeleton_for
from season.models import SeasonPlanVersion
from season.prompt import SEASON_MAX_TOKENS, SYSTEM_PROMPT, first_message
from season.rules import SeasonContext, validate_season
from season.schema import Focus, KeySession, PlanWeek, SeasonPlan, SessionKind, to_json
from season.skeleton import Skeleton

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
MONDAY = date(2026, 11, 16)
KEY = "sk-ant-test-0123456789-abcdefghij"
Status = SeasonPlanVersion.Status


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    user = User.objects.create_user("alice@example.com")
    for weekday in range(7):
        WeekdayMinutes.objects.create(owner=user, weekday=weekday, minutes=60)
    AIProviderConfiguration.objects.create(
        owner=user, provider="anthropic", model="claude-sonnet-5-5", api_key=KEY
    )
    Goal.objects.create(
        owner=user,
        kind="race",
        title="Race",
        priority="main",
        target_date=MONDAY + timedelta(weeks=7, days=6),
        discipline="running",
        distance_m=10_000,
    )
    return user


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def following(skeleton: Skeleton) -> SeasonPlan:
    """What the skeleton asks for: all minutes in running, a race session where there is a race."""
    return SeasonPlan(
        tuple(
            PlanWeek(
                week.week_start,
                ((Sport.RUNNING, week.target_minutes),),
                Focus.ENDURANCE,
                "Because.",
                (KeySession(Sport.RUNNING, SessionKind.RACE, 1),) if week.races else (),
            )
            for week in skeleton.weeks
        ),
        "The season.",
    )


def good(user: User) -> str:
    return json.dumps(to_json(following(skeleton_for(user))))


def broken(user: User, how: int = 1) -> str:
    """Readable, but not what the skeleton asks for: ``how`` weeks without minutes."""
    plan = following(skeleton_for(user))
    weeks = tuple(
        PlanWeek(w.week_start, (), w.focus, w.reason, w.key_sessions) if index < how else w
        for index, w in enumerate(plan.weeks)
    )
    return json.dumps(to_json(SeasonPlan(weeks)))


def errors_of(user: User, text: str) -> int:
    skeleton = skeleton_for(user)
    from season.prompt import extract_plan

    return len(validate_season(extract_plan(text), SeasonContext(skeleton)).errors)


def records(user: User) -> list[AIUsageRecord]:
    return list(AIUsageRecord.objects.for_user(user).order_by("id"))


def versions(user: User) -> list[SeasonPlanVersion]:
    return list(SeasonPlanVersion.objects.for_user(user).order_by("version"))


class TestADraftFromTheFirstAnswer:
    def test_a_good_answer_is_stored_as_a_draft(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good(alice))

        result = generate(alice)

        assert result.report.findings == ()
        (stored,) = versions(alice)
        assert result.plan == stored
        assert (stored.status, stored.version, stored.reason) == ("draft", 1, REASON)
        assert stored.rationale == "The season."
        assert len(stored.weeks) == 8
        assert stored.skeleton["weeks"][0]["week_start"] == "2026-11-16"
        assert stored.sports == ["running", "cycling", "swimming", "strength"]

    def test_what_is_stored_is_the_plan_that_was_given(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good(alice))

        result = generate(alice)

        assert services.load(alice, result.plan.pk).plan == following(skeleton_for(alice))

    def test_the_coach_is_asked_once_with_the_prompt_the_briefing_and_a_limit(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good(alice))

        generate(alice)

        ((system, messages, limit),) = scripted.calls
        assert system == SYSTEM_PROMPT
        assert limit == SEASON_MAX_TOKENS == 16_000
        assert [m.role for m in messages] == ["user"]
        skeleton = skeleton_for(alice)
        assert messages[0] == first_message(build_briefing(alice, NOW.date(), skeleton))
        assert scripted.json_outputs == [True]

    def test_every_call_asks_for_json(self, alice: User, provide: Callable[..., Scripted]) -> None:
        scripted = provide(broken(alice), good(alice))

        generate(alice)

        assert scripted.json_outputs == [True, True]

    def test_one_call_is_recorded_with_its_purpose_and_the_season_model(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        AIProviderConfiguration.objects.filter(owner=alice).update(season_model="claude-opus-5-5")
        provide(good(alice))

        generate(alice)

        (record,) = records(alice)
        assert (record.purpose, record.outcome, record.model) == (
            "season_plan",
            "success",
            "claude-opus-5-5",
        )

    def test_a_code_fence_around_the_answer_does_no_harm(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide("```json\n" + good(alice) + "\n```")

        assert generate(alice).report.valid is True

    def test_each_generation_is_a_new_version(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good(alice), good(alice))

        generate(alice)
        generate(alice)

        assert [v.version for v in versions(alice)] == [1, 2]
        assert [v.status for v in versions(alice)] == ["draft", "draft"]

    def test_nothing_of_another_user_is_told_to_the_coach(
        self, alice: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        Goal.objects.create(
            owner=bob,
            kind="race",
            title="Bobs secret race",
            priority="main",
            target_date=MONDAY + timedelta(weeks=3),
            discipline="running",
        )
        scripted = provide(good(alice))

        generate(alice)

        assert "secret" not in scripted.calls[0][1][0].content
        assert "bob" not in scripted.calls[0][1][0].content

    def test_the_draft_can_be_confirmed(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good(alice))

        result = generate(alice)

        assert services.confirm(alice, result.plan.pk).status == "confirmed"


class TestTheRepairRounds:
    def test_three_answers_are_the_most(self) -> None:
        assert ATTEMPTS == 3

    def test_an_unreadable_answer_is_told_what_was_wrong_and_may_try_again(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide("Here you go: {}", good(alice))

        result = generate(alice)

        assert len(scripted.calls) == 2
        assert [m.role for m in scripted.calls[1][1]] == ["user", "assistant", "user"]
        assert scripted.calls[1][1][1].content == "Here you go: {}"
        assert "The answer is not one JSON object" in scripted.calls[1][1][2].content
        assert result.report.valid is True
        assert len(versions(alice)) == 1

    def test_rule_errors_are_told_by_their_fixed_texts_and_a_fixed_plan_is_stored(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        wrong = broken(alice)
        scripted = provide(wrong, good(alice))

        result = generate(alice)

        told = scripted.calls[1][1][2].content
        assert "minutes_outside_target" not in told  # codes are not told, the texts are
        assert "the skeleton aims for" in told
        assert result.report.valid is True
        (stored,) = versions(alice)
        # the week that was empty in the first answer has its minutes in the one that is kept
        assert stored.weeks[0]["minutes"] == {
            "running": skeleton_for(alice).weeks[0].target_minutes
        }

    def test_the_repair_message_is_the_one_of_the_week_plan(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide("nonsense", good(alice))

        generate(alice)

        from planning.schema import PlanFormatError
        from season.prompt import extract_plan

        with pytest.raises(PlanFormatError) as raised:
            extract_plan("nonsense")
        assert scripted.calls[1][1][2] == repair_message(raised.value.problems, ())

    def test_a_third_answer_may_fix_what_the_second_still_got_wrong(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(broken(alice, 3), broken(alice, 1), good(alice))

        result = generate(alice)

        assert len(scripted.calls) == 3
        assert result.report.valid is True
        assert [r.outcome for r in records(alice)] == ["success"] * 3

    def test_no_fourth_try(self, alice: User, provide: Callable[..., Scripted]) -> None:
        scripted = provide(*[broken(alice)] * 4)

        generate(alice)

        assert len(scripted.calls) == 3
        assert len(scripted.replies) == 1

    def test_an_empty_answer_goes_back_as_a_placeholder(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide("  ", good(alice))

        generate(alice)

        assert scripted.calls[1][1][1].content == "(no answer)"

    def test_an_answer_that_is_cut_off_is_not_read_and_the_coach_is_told(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(Completion(good(alice), 10, 16_000, truncated=True), good(alice))

        generate(alice)

        assert "cut off before its end" in scripted.calls[1][1][2].content
        assert len(versions(alice)) == 1

    def test_nothing_is_stored_if_no_answer_was_readable(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide("a", "b", "c")

        with pytest.raises(PlanNotUsable) as raised:
            generate(alice)

        assert [p.path for p in raised.value.problems] == [""]
        assert versions(alice) == []
        assert len(records(alice)) == 3

    def test_a_cut_off_answer_every_time_is_not_usable(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        cut = Completion(good(alice), 10, 16_000, truncated=True)
        provide(cut, cut, cut)

        with pytest.raises(PlanNotUsable):
            generate(alice)


class TestAPlanWithErrors:
    def test_errors_that_remain_are_stored_as_a_draft_that_cannot_be_confirmed(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(*[broken(alice)] * 3)

        result = generate(alice)

        assert result.report.valid is False
        assert result.plan.status == "draft"
        with pytest.raises(services.PlanNotConfirmable):
            services.confirm(alice, result.plan.pk)

    def test_the_better_of_the_plans_is_kept(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(broken(alice, 3), broken(alice, 1), broken(alice, 2))

        result = generate(alice)

        assert len(result.report.errors) == errors_of(alice, broken(alice, 1))
        assert result.plan.weeks[1]["minutes"] != {}
        assert result.plan.weeks[0]["minutes"] == {}

    def test_a_later_answer_that_cannot_be_read_does_not_lose_the_first_plan(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(broken(alice), "garbage", "more garbage")

        result = generate(alice)

        assert result.report.valid is False
        assert len(versions(alice)) == 1
        assert result.plan.weeks[0]["minutes"] == {}

    def test_a_tie_goes_to_the_later_answer(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        first = broken(alice, 1)
        second = json.dumps({**json.loads(first), "rationale": "The later one"})
        provide(first, second, second)

        result = generate(alice)

        assert result.plan.rationale == "The later one"


class TestWhenTheProviderFails:
    def test_the_error_passes_through_and_nothing_is_stored(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(ProviderUnavailableError("down"))

        with pytest.raises(ProviderUnavailableError):
            generate(alice)

        assert versions(alice) == []

    def test_an_error_on_a_later_call_loses_a_readable_plan_not(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(broken(alice), RateLimitedError("slow down"))

        result = generate(alice)

        assert result.report.valid is False
        assert len(versions(alice)) == 1

    def test_an_error_on_a_later_call_is_raised_if_there_is_no_plan_yet(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide("garbage", ProviderUnavailableError("down"))

        with pytest.raises(ProviderUnavailableError):
            generate(alice)

        assert versions(alice) == []

    def test_a_provider_removed_meanwhile_loses_a_readable_plan_not(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(broken(alice), good(alice))
        scripted.before_answer = None

        original = scripted.complete

        def remove_after_the_first(*args: Any, **kwargs: Any) -> Completion:
            answer = original(*args, **kwargs)
            AIProviderConfiguration.objects.filter(owner=alice).delete()
            return answer

        scripted.complete = remove_after_the_first  # type: ignore[method-assign]

        result = generate(alice)

        assert result.report.valid is False
        assert len(versions(alice)) == 1

    def test_without_a_provider_nothing_happens(self, bob: User) -> None:
        WeekdayMinutes.objects.create(owner=bob, weekday=0, minutes=60)

        with pytest.raises(NotConfiguredError):
            generate(bob)

        assert versions(bob) == []
        assert records(bob) == []


class TestASeasonWithoutTime:
    def test_nothing_to_fill_is_said_before_the_provider_is_asked(
        self, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide("never asked")

        with pytest.raises(NothingToPlan):
            generate(bob)

        assert scripted.calls == []
        assert records(bob) == []

    def test_it_is_said_before_a_missing_provider(self, bob: User) -> None:
        with pytest.raises(NothingToPlan):
            generate(bob)

    def test_a_budget_of_zero_is_no_time(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        AvailabilitySettings.objects.create(owner=alice, weekly_budget_minutes=0)
        scripted = provide("never asked")

        with pytest.raises(NothingToPlan):
            generate(alice)

        assert scripted.calls == []

    def test_away_the_whole_season_is_no_time(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        UnavailablePeriod.objects.create(
            owner=alice, kind="vacation", start_date=MONDAY, end_date=MONDAY + timedelta(weeks=9)
        )
        scripted = provide("never asked")

        with pytest.raises(NothingToPlan):
            generate(alice)

        assert scripted.calls == []

    def test_a_single_week_with_time_is_enough_to_ask(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        UnavailablePeriod.objects.create(
            owner=alice,
            kind="vacation",
            start_date=MONDAY,
            end_date=MONDAY + timedelta(weeks=6, days=6),
        )
        scripted = provide(good(alice))

        generate(alice)

        assert len(scripted.calls) == 1
