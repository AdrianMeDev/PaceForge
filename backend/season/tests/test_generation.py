import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from django.core.exceptions import ValidationError

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
    PlanNotChangeable,
    PlanNotUsable,
    PlanUnchanged,
    change,
    generate,
)
from season.inputs import skeleton_for
from season.models import SeasonPlanVersion
from season.prompt import SEASON_MAX_TOKENS, SYSTEM_PROMPT, change_message, first_message
from season.reassessment import reassess
from season.rules import SeasonContext, validate_season
from season.schema import Focus, KeySession, PlanWeek, SeasonPlan, SessionKind, to_json
from season.skeleton import Skeleton
from season.snapshots import collect_inputs

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
    @pytest.mark.parametrize("repair", [False, True])
    def test_the_snapshot_is_captured_before_calls_and_kept_across_repairs(
        self, alice: User, provide: Callable[..., Scripted], repair: bool
    ) -> None:
        AvailabilitySettings.objects.create(owner=alice, typical_weekly_minutes=300)
        snapshot = collect_inputs(alice)
        replies = [broken(alice), good(alice)] if repair else [good(alice)]
        scripted = provide(*replies)

        def change_inputs() -> None:
            Goal.objects.for_user(alice).update(title="Changed during generation")
            AvailabilitySettings.objects.for_user(alice).update(typical_weekly_minutes=600)

        scripted.before_answer = change_inputs

        stored = generate(alice).plan

        stored.refresh_from_db()
        assert stored.input_snapshot == snapshot
        assert stored.input_snapshot != collect_inputs(alice)
        assert len(scripted.calls) == (2 if repair else 1)

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
        assert versions(alice)[0].input_snapshot == collect_inputs(alice)

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


def tempo(user: User) -> str:
    """The season as it is, but with the focus of the first week changed."""
    plan = following(skeleton_for(user))
    weeks = (replace(plan.weeks[0], focus=Focus.TEMPO, reason="Harder."), *plan.weeks[1:])
    return json.dumps(to_json(SeasonPlan(weeks, plan.rationale)))


def confirmed(user: User) -> SeasonPlanVersion:
    skeleton = skeleton_for(user)
    stored = services.save_draft(
        user, following(skeleton), SeasonContext(skeleton), input_snapshot=collect_inputs(user)
    )
    return services.confirm(user, stored.pk)


WISH = "Less cycling in January"


class TestChangingASeason:
    @pytest.mark.parametrize("known", [True, False])
    @pytest.mark.parametrize("status", ["draft", "confirmed"])
    def test_a_change_captures_current_inputs_even_when_the_original_inputs_are_unknown(
        self, alice: User, provide: Callable[..., Scripted], known: bool, status: str
    ) -> None:
        skeleton = skeleton_for(alice)
        snapshot = collect_inputs(alice) if known else None
        base = services.save_draft(
            alice, following(skeleton), SeasonContext(skeleton), input_snapshot=snapshot
        )
        if status == "confirmed":
            services.confirm(alice, base.pk)
        Goal.objects.for_user(alice).update(title="Changed after drafting")
        AvailabilitySettings.objects.create(owner=alice, typical_weekly_minutes=600)
        current = collect_inputs(alice)
        provide(tempo(alice))

        changed = change(alice, base.pk, WISH).plan

        changed.refresh_from_db()
        base.refresh_from_db()
        assert changed.input_snapshot == current
        assert base.input_snapshot == snapshot
        assert changed.input_snapshot != snapshot

    @pytest.mark.parametrize("repair", [False, True])
    def test_changes_during_the_call_remain_detectable_against_the_captured_baseline(
        self, alice: User, provide: Callable[..., Scripted], repair: bool
    ) -> None:
        base = confirmed(alice)
        Goal.objects.for_user(alice).update(target_date=MONDAY + timedelta(weeks=9, days=6))
        WeekdayMinutes.objects.for_user(alice).update(minutes=90)
        snapshot = collect_inputs(alice)
        context = SeasonContext(skeleton_for(alice))
        briefing = build_briefing(alice, NOW.date(), context.skeleton)
        replies = [broken(alice), good(alice)] if repair else [good(alice)]
        scripted = provide(*replies)

        def change_inputs() -> None:
            Goal.objects.for_user(alice).update(target_date=MONDAY + timedelta(weeks=12, days=6))
            WeekdayMinutes.objects.for_user(alice).update(minutes=30)

        scripted.before_answer = change_inputs

        result = change(alice, base.pk, WISH)

        assert result.report.valid is True
        assert result.plan.input_snapshot == snapshot
        assert services.read(result.plan).context == context
        assert len(scripted.calls) == (2 if repair else 1)
        expected = change_message(briefing, services.read(base).plan, WISH)
        assert all(messages[0] == expected for _, messages, _ in scripted.calls)
        services.confirm(alice, result.plan.pk)
        assert reassess(alice)["reasons"] == ["goals_changed", "training_time_changed"]

    def test_a_changed_answer_is_stored_as_the_next_draft_made_from_the_old_version(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = confirmed(alice)
        provide(tempo(alice))

        result = change(alice, base.pk, WISH)

        stored = result.plan
        assert (stored.version, stored.status, stored.parent_id) == (2, "draft", base.pk)
        assert stored.reason == "Changed on request from version 1"
        assert stored.request == WISH
        assert stored.weeks[0]["focus"] == "tempo"
        assert result.report.valid is True

    def test_the_old_version_stays_as_it_is_and_confirmed(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = confirmed(alice)
        before = SeasonPlanVersion.objects.values().get(pk=base.pk)
        provide(tempo(alice))

        change(alice, base.pk, WISH)

        assert SeasonPlanVersion.objects.values().get(pk=base.pk) == before
        assert base.status == "confirmed"

    @pytest.mark.parametrize("change_kind", ["earlier_race", "later_race", "capacity", "budget"])
    def test_the_new_version_uses_the_current_frame_and_keeps_the_parent_and_request(
        self, alice: User, provide: Callable[..., Scripted], change_kind: str
    ) -> None:
        base = confirmed(alice)
        before = SeasonPlanVersion.objects.values().get(pk=base.pk)
        if change_kind in ("earlier_race", "later_race"):
            weeks = 5 if change_kind == "earlier_race" else 10
            Goal.objects.for_user(alice).update(target_date=MONDAY + timedelta(weeks=weeks, days=6))
        elif change_kind == "capacity":
            WeekdayMinutes.objects.for_user(alice).update(minutes=30)
        else:
            AvailabilitySettings.objects.create(owner=alice, weekly_budget_minutes=180)
        frame = skeleton_for(alice)
        briefing = build_briefing(alice, NOW.date(), frame)
        scripted = provide(good(alice))

        result = change(alice, base.pk, WISH)

        assert result.report.valid is True
        assert services.read(result.plan).context.skeleton == frame
        assert result.plan.skeleton != base.skeleton
        assert (result.plan.parent_id, result.plan.request) == (base.pk, WISH)
        assert result.plan.input_snapshot == collect_inputs(alice)
        assert scripted.calls[0][1] == [change_message(briefing, services.read(base).plan, WISH)]
        assert SeasonPlanVersion.objects.values().get(pk=base.pk) == before
        assert reassess(alice)["reasons"]  # Drafting does not acknowledge the hint.
        services.confirm(alice, result.plan.pk)
        assert reassess(alice)["reasons"] == []

    def test_the_new_version_uses_the_current_sports(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = confirmed(alice)
        AvailabilitySettings.objects.create(owner=alice, sports=["swimming"])
        plan = following(skeleton_for(alice))
        answer = replace(
            plan,
            weeks=tuple(
                replace(
                    week,
                    minutes=((Sport.SWIMMING, week.total),),
                    key_sessions=tuple(
                        replace(session, sport=Sport.SWIMMING) for session in week.key_sessions
                    ),
                )
                for week in plan.weeks
            ),
        )
        provide(json.dumps(to_json(answer)))

        result = change(alice, base.pk, WISH)

        assert result.report.valid is True
        assert result.plan.sports == ["swimming"]
        assert services.read(result.plan).plan == answer

    def test_the_coach_gets_the_old_plan_the_wish_and_the_current_sports(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = confirmed(alice)
        AvailabilitySettings.objects.create(owner=alice, sports=["running"])
        scripted = provide(tempo(alice))

        change(alice, base.pk, WISH)

        ((system, messages, limit),) = scripted.calls
        loaded = services.read(base)
        briefing = build_briefing(alice, NOW.date(), skeleton_for(alice))
        assert system == SYSTEM_PROMPT
        assert limit == SEASON_MAX_TOKENS
        assert messages == [change_message(briefing, loaded.plan, WISH)]
        assert scripted.json_outputs == [True]
        assert json.loads(messages[0].content.split("\n\n", 1)[1])["sports"] == ["running"]

    def test_a_draft_can_be_changed_too(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        skeleton = skeleton_for(alice)
        draft = services.save_draft(alice, following(skeleton), SeasonContext(skeleton))
        provide(tempo(alice))

        stored = change(alice, draft.pk, WISH).plan

        assert (stored.version, stored.parent_id) == (2, draft.pk)

    def test_one_call_is_recorded_with_the_season_model(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        AIProviderConfiguration.objects.filter(owner=alice).update(season_model="claude-opus-5-5")
        base = confirmed(alice)
        provide(tempo(alice))

        change(alice, base.pk, WISH)

        (record,) = records(alice)
        assert (record.purpose, record.model) == ("season_plan", "claude-opus-5-5")

    def test_a_bad_answer_is_repaired_as_when_drafting(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = confirmed(alice)
        scripted = provide("nonsense", broken(alice), tempo(alice))

        result = change(alice, base.pk, WISH)

        assert len(scripted.calls) == 3
        assert [m.role for m in scripted.calls[1][1]] == ["user", "assistant", "user"]
        assert scripted.calls[1][1][0] == scripted.calls[0][1][0]  # the change request stays
        assert result.report.valid is True

    def test_a_plan_with_errors_is_stored_and_cannot_be_confirmed(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = confirmed(alice)
        provide(*[broken(alice)] * 3)

        result = change(alice, base.pk, WISH)

        assert result.report.valid is False
        assert result.plan.request == WISH
        with pytest.raises(services.PlanNotConfirmable):
            services.confirm(alice, result.plan.pk)

    def test_nothing_is_stored_if_no_answer_was_readable(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = confirmed(alice)
        provide("a", "b", "c")

        with pytest.raises(PlanNotUsable):
            change(alice, base.pk, WISH)

        assert [v.version for v in versions(alice)] == [1]

    def test_an_answer_that_is_the_season_as_it_was_is_not_stored(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = confirmed(alice)
        provide(good(alice))

        with pytest.raises(PlanUnchanged):
            change(alice, base.pk, WISH)

        assert [v.version for v in versions(alice)] == [1]
        assert len(records(alice)) == 1

    @pytest.mark.parametrize("change_kind", ["capacity", "sports", "inputs", "unknown_baseline"])
    def test_identical_content_is_stored_when_the_frame_or_input_baseline_changes(
        self, alice: User, provide: Callable[..., Scripted], change_kind: str
    ) -> None:
        AvailabilitySettings.objects.create(owner=alice, typical_weekly_minutes=210)
        base = confirmed(alice)
        if change_kind == "capacity":
            WeekdayMinutes.objects.for_user(alice).update(minutes=90)
        elif change_kind == "sports":
            AvailabilitySettings.objects.for_user(alice).update(sports=["running"])
        elif change_kind == "inputs":
            Goal.objects.for_user(alice).update(target_time_seconds=2400)
        else:
            SeasonPlanVersion.objects.filter(pk=base.pk).update(input_snapshot=None)
        old_plan = services.read(base).plan
        provide(json.dumps(to_json(old_plan)))

        result = change(alice, base.pk, WISH)

        assert result.report.valid is True
        assert services.read(result.plan).plan == old_plan
        assert result.plan.input_snapshot == collect_inputs(alice)
        assert result.plan.parent_id == base.pk

    def test_the_old_frame_is_checked_against_current_inputs_and_cannot_be_confirmed(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = confirmed(alice)
        old_answer = good(alice)
        Goal.objects.for_user(alice).update(target_date=MONDAY + timedelta(weeks=10, days=6))
        WeekdayMinutes.objects.for_user(alice).update(minutes=20)
        AvailabilitySettings.objects.create(owner=alice, sports=["swimming"])
        scripted = provide(*[old_answer] * ATTEMPTS)

        result = change(alice, base.pk, WISH)

        assert len(scripted.calls) == ATTEMPTS
        assert result.report.valid is False
        assert {"weeks_mismatch", "sport_not_selected", "minutes_above_capacity"} <= {
            finding.code for finding in result.report.errors
        }
        with pytest.raises(services.PlanNotConfirmable):
            services.confirm(alice, result.plan.pk)
        base.refresh_from_db()
        assert base.status == "confirmed"

    @pytest.mark.parametrize("no_time", ["weekdays", "budget", "absence"])
    def test_no_current_capacity_is_refused_before_even_looking_for_a_provider(
        self, alice: User, provide: Callable[..., Scripted], no_time: str
    ) -> None:
        base = confirmed(alice)
        if no_time == "weekdays":
            WeekdayMinutes.objects.for_user(alice).update(minutes=0)
        elif no_time == "budget":
            AvailabilitySettings.objects.create(owner=alice, weekly_budget_minutes=0)
        else:
            UnavailablePeriod.objects.create(
                owner=alice,
                kind="vacation",
                start_date=MONDAY,
                end_date=MONDAY + timedelta(weeks=9),
            )
        AIProviderConfiguration.objects.filter(owner=alice).delete()
        scripted = provide("never asked")

        with pytest.raises(NothingToPlan):
            change(alice, base.pk, WISH)

        assert scripted.calls == []
        assert records(alice) == []
        assert len(versions(alice)) == 1

    def test_a_provider_that_fails_stores_nothing(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = confirmed(alice)
        provide(ProviderUnavailableError("down"))

        with pytest.raises(ProviderUnavailableError):
            change(alice, base.pk, WISH)

        assert [v.version for v in versions(alice)] == [1]

    @pytest.mark.parametrize("status", ["superseded", "discarded"])
    def test_a_replaced_or_discarded_version_is_refused_before_anything_is_sent(
        self, alice: User, provide: Callable[..., Scripted], status: str
    ) -> None:
        skeleton = skeleton_for(alice)
        old = services.save_draft(alice, following(skeleton), SeasonContext(skeleton))
        if status == "discarded":
            services.discard(alice, old.pk)
        else:
            services.confirm(alice, old.pk)
            services.confirm(
                alice, services.save_draft(alice, following(skeleton), SeasonContext(skeleton)).pk
            )
        scripted = provide("never asked")

        with pytest.raises(PlanNotChangeable):
            change(alice, old.pk, WISH)

        assert scripted.calls == []

    def test_a_version_of_another_user_is_not_found_before_anything_is_sent(
        self, alice: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        theirs = confirmed(bob)
        scripted = provide("never asked")

        with pytest.raises(services.PlanNotFound):
            change(alice, theirs.pk, WISH)

        assert scripted.calls == []

    @pytest.mark.parametrize("wish", ["", "   \n ", "x" * 501, "bell\x07"])
    def test_a_wish_that_is_empty_too_long_or_not_plain_is_refused_before_anything_is_sent(
        self, alice: User, provide: Callable[..., Scripted], wish: str
    ) -> None:
        base = confirmed(alice)
        scripted = provide("never asked")

        with pytest.raises(ValidationError) as raised:
            change(alice, base.pk, wish)

        assert "request" in raised.value.message_dict
        assert scripted.calls == []

    def test_without_a_provider_nothing_happens(self, alice: User) -> None:
        base = confirmed(alice)
        AIProviderConfiguration.objects.filter(owner=alice).delete()

        with pytest.raises(NotConfiguredError):
            change(alice, base.pk, WISH)

        assert [v.version for v in versions(alice)] == [1]
