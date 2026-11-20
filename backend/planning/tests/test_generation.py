import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from django.core.exceptions import ValidationError

from accounts.models import User
from athletes.models import AthleteProfile, ThresholdValue
from availability.models import AvailabilitySettings, UnavailablePeriod, WeekdayMinutes
from coach import services as coach_services
from coach.models import AIProviderConfiguration, AIUsageRecord
from coach.providers.base import (
    Completion,
    InvalidKeyError,
    Message,
    ProviderUnavailableError,
    RateLimitedError,
)
from goals import services as goal_services
from goals.models import Goal as GoalRow
from planning import services
from planning.generation import (
    ATTEMPTS,
    PLAN_MAX_TOKENS,
    REASON,
    WEEKS_AHEAD,
    NoTimeAvailable,
    PlanNotUsable,
    WeekNotPlannable,
    generate,
    plannable_weeks,
)
from planning.models import NOTE_MAX, PlannedWorkout, WeeklyPlan
from planning.prompt import SYSTEM_PROMPT
from planning.schema import Goal, Sport, WeekPlan, Workout, ZoneSystem, to_json

from .scripted import Scripted

pytestmark = pytest.mark.django_db

# A Wednesday: the week that can be planned first starts on Monday the 12th.
NOW = datetime(2027, 7, 14, 12, 0, tzinfo=UTC)
THIS_WEEK = date(2027, 7, 12)
MONDAY = date(2027, 7, 19)
KEY = "test-provider-marker-0123456789"
Status = WeeklyPlan.Status


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    user = User.objects.create_user("alice@example.com")
    for weekday, minutes in enumerate([90, 0, 90, 0, 120, 120, 0]):
        WeekdayMinutes.objects.create(owner=user, weekday=weekday, minutes=minutes)
    ThresholdValue.objects.create(
        owner=user, sport="ride", metric="ftp", value=250, source="manual", basis="test"
    )
    AIProviderConfiguration.objects.create(
        owner=user, provider="anthropic", model="claude-sonnet-5-5", api_key=KEY
    )
    return user


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def ride(offset: int, minutes: int = 60, monday: date = MONDAY, **fields: Any) -> Workout:
    data: dict[str, Any] = {
        "day": monday + timedelta(days=offset),
        "sport": Sport.CYCLING,
        "title": "Endurance ride",
        "goal": Goal.ENDURANCE,
        "duration_minutes": minutes,
        "zone_system": ZoneSystem.POWER,
        "zone": 2,
        **fields,
    }
    return Workout(**data)


def good(monday: date = MONDAY) -> str:
    plan = WeekPlan(monday, (ride(0, monday=monday), ride(2, monday=monday)), "Base")
    return text_of(plan)


def bad() -> str:
    """Readable, but Tuesday offers nothing: a rule error."""
    return text_of(WeekPlan(MONDAY, (ride(0), ride(1))))


def text_of(plan: WeekPlan) -> str:
    return json.dumps(to_json(plan))


def records(user: User) -> list[AIUsageRecord]:
    return list(AIUsageRecord.objects.for_user(user).order_by("id"))


def plans(user: User) -> list[WeeklyPlan]:
    return list(WeeklyPlan.objects.for_user(user).order_by("version"))


class TestThePlannableWeeks:
    def test_it_is_this_week_and_the_next_four(self, alice: User) -> None:
        weeks = plannable_weeks(alice)

        assert weeks == tuple(THIS_WEEK + timedelta(weeks=n) for n in range(WEEKS_AHEAD + 1))
        assert all(week.weekday() == 0 for week in weeks)
        assert len(weeks) == 5

    def test_the_week_of_the_user_counts_not_the_week_of_the_server(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Sunday evening in UTC is already Monday in Tokyo
        late = datetime(2027, 7, 18, 23, 30, tzinfo=UTC)
        monkeypatch.setattr(goal_services, "_utc_now", lambda: late)
        assert plannable_weeks(alice)[0] == THIS_WEEK

        AthleteProfile.objects.create(owner=alice, timezone="Asia/Tokyo")

        assert plannable_weeks(alice)[0] == MONDAY

    @pytest.mark.parametrize(
        "monday",
        [
            THIS_WEEK - timedelta(weeks=1),
            THIS_WEEK + timedelta(weeks=WEEKS_AHEAD + 1),
            MONDAY + timedelta(days=1),
            date(2000, 1, 3),
        ],
    )
    def test_any_other_week_is_refused_before_anything_is_asked(
        self, alice: User, provide: Callable[..., Scripted], monday: date
    ) -> None:
        scripted = provide(good())

        with pytest.raises(WeekNotPlannable):
            generate(alice, monday)

        assert scripted.calls == []
        assert records(alice) == []
        assert plans(alice) == []

    @pytest.mark.parametrize("monday", [THIS_WEEK, THIS_WEEK + timedelta(weeks=WEEKS_AHEAD)])
    def test_the_first_and_the_last_week_are_accepted(
        self, alice: User, provide: Callable[..., Scripted], monday: date
    ) -> None:
        provide(good(monday))

        assert generate(alice, monday).plan.week_start == monday


class TestADraftFromTheFirstAnswer:
    def test_a_good_answer_is_stored_as_a_draft(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good())

        result = generate(alice, MONDAY)

        stored = result.plan
        assert (stored.owner, stored.week_start, stored.version, stored.status) == (
            alice,
            MONDAY,
            1,
            Status.DRAFT,
        )
        assert (stored.reason, stored.rationale, stored.parent) == (REASON, "Base", None)
        assert result.report.valid
        assert result.report.findings == ()
        assert PlannedWorkout.objects.filter(plan=stored).count() == 2
        assert services.load(alice, stored.pk).workouts[0].title == "Endurance ride"

    @pytest.mark.parametrize("offset", [0, 6])
    def test_week_boundary_days_can_be_saved(
        self, alice: User, provide: Callable[..., Scripted], offset: int
    ) -> None:
        answer = text_of(WeekPlan(MONDAY, (ride(offset),)))
        provide(answer, answer)  # Sunday has a capacity error, but remains saveable.

        result = generate(alice, MONDAY)

        assert services.load(alice, result.plan.pk).workouts[0].day == MONDAY + timedelta(
            days=offset
        )
        assert len(plans(alice)) == 1

    def test_the_coach_is_asked_once_with_the_prompt_the_briefing_and_a_limit(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())
        GoalRow.objects.create(owner=alice, kind="general", title="Build my endurance")

        generate(alice, MONDAY)

        ((system, messages, limit),) = scripted.calls
        assert system == SYSTEM_PROMPT
        assert limit == PLAN_MAX_TOKENS
        (message,) = messages
        assert message.role == "user"
        assert message.content.startswith("Plan the training week that starts on 2027-07-19.")
        assert "Build my endurance" in message.content

    def test_nothing_of_another_user_is_told_to_the_coach(
        self, alice: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())
        GoalRow.objects.create(owner=bob, kind="general", title="Bobs secret goal")
        WeekdayMinutes.objects.create(owner=bob, weekday=1, minutes=777)

        generate(alice, MONDAY)

        content = scripted.calls[0][1][0].content
        assert "Bobs secret goal" not in content
        assert "777" not in content

    def test_the_provider_key_is_never_sent_to_the_coach(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())

        generate(alice, MONDAY)

        for system, messages, _ in scripted.calls:
            assert KEY not in system
            assert all(KEY not in message.content for message in messages)

    def test_one_call_is_recorded_with_its_purpose(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good())

        generate(alice, MONDAY)

        (record,) = records(alice)
        assert (record.purpose, record.outcome) == ("weekly_plan", "success")
        assert (record.input_tokens, record.output_tokens) == (100, 50)

    def test_the_week_model_is_used_and_recorded_if_there_is_one(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        AIProviderConfiguration.objects.filter(owner=alice).update(week_model="claude-haiku-5-5")
        provide(good())

        generate(alice, MONDAY)

        (record,) = records(alice)
        assert (record.purpose, record.model) == ("weekly_plan", "claude-haiku-5-5")

    def test_a_code_fence_around_the_answer_does_no_harm(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(f"```json\n{good()}\n```")

        assert generate(alice, MONDAY).report.valid

    def test_workouts_are_stored_by_day_and_the_findings_point_into_that_order(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        # given Friday first, then the empty Tuesday: stored as Tuesday (0), Friday (1)
        plan = WeekPlan(MONDAY, (ride(4), ride(1)))
        provide(text_of(plan), text_of(plan))

        result = generate(alice, MONDAY)

        assert [f.path for f in result.report.errors if f.code == "day_over_capacity"] == [
            "workouts[0]"
        ]
        stored = services.load(alice, result.plan.pk)
        assert [w.day.weekday() for w in stored.workouts] == [1, 4]

    def test_each_generation_is_a_new_version_of_the_week(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good(), good())

        first = generate(alice, MONDAY).plan
        second = generate(alice, MONDAY).plan

        assert (first.version, second.version) == (1, 2)
        assert [p.status for p in plans(alice)] == [Status.DRAFT, Status.DRAFT]


class TestTheNoteOfTheAthlete:
    NOTE = "No time on Tuesday.\nA trip on Saturday."

    def test_it_is_told_to_the_coach_as_data_and_stored_with_the_draft(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())

        result = generate(alice, MONDAY, self.NOTE)

        (message,) = scripted.calls[0][1]
        data = json.loads(message.content.split("The data follows.\n\n", 1)[1])
        assert data["athlete_note"] == self.NOTE
        assert result.plan.note == self.NOTE
        assert plans(alice)[0].note == self.NOTE

    def test_it_is_cleaned_before_the_coach_and_the_database_see_it(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())

        result = generate(alice, MONDAY, "  one\r\ntwo \n")

        assert '"athlete_note":"one\\ntwo"' in scripted.calls[0][1][0].content
        assert result.plan.note == "one\ntwo"

    def test_without_a_note_none_is_told_and_none_is_stored(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())

        result = generate(alice, MONDAY)

        assert '"athlete_note":null' in scripted.calls[0][1][0].content
        assert result.plan.note == ""

    def test_the_repair_round_keeps_the_note(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide("not a plan", good())

        result = generate(alice, MONDAY, self.NOTE)

        assert len(scripted.calls) == 2
        for _, messages, _ in scripted.calls:
            assert self.NOTE.replace("\n", "\\n") in messages[0].content
        assert result.plan.note == self.NOTE

    def test_each_version_has_its_own_note(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good(), good())

        generate(alice, MONDAY, "first")
        generate(alice, MONDAY)

        assert [plan.note for plan in plans(alice)] == ["first", ""]

    @pytest.mark.parametrize("note", ["x" * (NOTE_MAX + 1), "a\x00b", "a\u202eb"])
    def test_a_note_that_does_not_fit_is_refused_before_anything_is_asked(
        self, alice: User, provide: Callable[..., Scripted], note: str
    ) -> None:
        scripted = provide(good())

        with pytest.raises(ValidationError) as raised:
            generate(alice, MONDAY, note)

        assert set(raised.value.message_dict) == {"note"}
        assert scripted.calls == []
        assert records(alice) == []
        assert plans(alice) == []

    def test_a_bad_note_is_said_before_a_week_that_cannot_be_planned(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good())

        with pytest.raises(ValidationError):
            generate(alice, MONDAY + timedelta(weeks=20), "x" * (NOTE_MAX + 1))

    def test_a_week_without_time_asks_nothing_whatever_the_note_says(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())
        WeekdayMinutes.objects.filter(owner=alice).update(minutes=0)

        with pytest.raises(NoTimeAvailable):
            generate(alice, MONDAY, self.NOTE)

        assert scripted.calls == []


class TestJsonOutput:
    def test_every_call_for_a_plan_asks_for_json(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide("Sure!", good())

        generate(alice, MONDAY)

        assert scripted.json_outputs == [True, True]


class TestTheRepairRound:
    @pytest.mark.parametrize("offset", [-1, 7])
    def test_an_out_of_week_answer_can_be_repaired(
        self, alice: User, provide: Callable[..., Scripted], offset: int
    ) -> None:
        stray = text_of(WeekPlan(MONDAY, (ride(offset),)))
        scripted = provide(stray, good())

        result = generate(alice, MONDAY)

        assert result.report.valid
        assert "workouts[0].day" in scripted.calls[1][1][2].content
        assert "within the week" in scripted.calls[1][1][2].content
        assert len(plans(alice)) == 1
        assert PlannedWorkout.objects.count() == 2

    @pytest.mark.parametrize("offset", [-1, 7])
    def test_out_of_week_answers_exhaust_the_unusable_answer_path(
        self, alice: User, provide: Callable[..., Scripted], offset: int
    ) -> None:
        stray = text_of(WeekPlan(MONDAY, (ride(offset),)))
        scripted = provide(stray, stray)

        with pytest.raises(PlanNotUsable) as raised:
            generate(alice, MONDAY)

        assert [p.path for p in raised.value.problems] == ["workouts[0].day"]
        assert len(scripted.calls) == ATTEMPTS
        assert plans(alice) == []
        assert PlannedWorkout.objects.count() == 0

    @pytest.mark.parametrize("stray_first", [False, True])
    def test_an_out_of_week_answer_cannot_replace_an_in_week_plan_with_rule_errors(
        self, alice: User, provide: Callable[..., Scripted], stray_first: bool
    ) -> None:
        stray = text_of(WeekPlan(MONDAY, (ride(7),)))
        provide(*([stray, bad()] if stray_first else [bad(), stray]))

        result = generate(alice, MONDAY)

        assert not result.report.valid
        assert [w.day for w in services.load(alice, result.plan.pk).workouts] == [
            MONDAY,
            MONDAY + timedelta(days=1),
        ]
        assert len(plans(alice)) == 1

    def test_an_unreadable_answer_is_told_what_was_wrong_and_may_try_again(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide("Sure! Here is a plan.", good())

        result = generate(alice, MONDAY)

        assert result.report.valid
        assert len(scripted.calls) == ATTEMPTS == 2
        _, messages, _ = scripted.calls[1]
        assert [m.role for m in messages] == ["user", "assistant", "user"]
        assert messages[0] == scripted.calls[0][1][0]
        assert messages[1].content == "Sure! Here is a plan."
        assert "The answer is not one JSON object" in messages[2].content
        assert [r.outcome for r in records(alice)] == ["success", "success"]
        assert plans(alice)[0].version == 1

    def test_rule_errors_are_told_and_a_fixed_plan_is_stored(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(bad(), good())

        result = generate(alice, MONDAY)

        assert result.report.valid
        repair = scripted.calls[1][1][2].content
        assert "workouts[1]: Tuesday offers 0 minutes" in repair
        assert "(error)" in repair
        assert len(plans(alice)) == 1  # the first answer was not stored
        assert len(result.plan.workouts.all()) == 2

    def test_an_empty_answer_goes_back_as_a_placeholder(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide("", good())

        generate(alice, MONDAY)

        assert scripted.calls[1][1][1] == Message("assistant", "(no answer)")

    def test_an_answer_that_is_cut_off_is_not_read_and_the_coach_is_told(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(Completion(good(), 10, 8000, truncated=True), good())

        result = generate(alice, MONDAY)

        assert result.report.valid
        assert "cut off" in scripted.calls[1][1][2].content

    def test_no_third_try(self, alice: User, provide: Callable[..., Scripted]) -> None:
        scripted = provide("no", "still no", good())

        with pytest.raises(PlanNotUsable):
            generate(alice, MONDAY)

        assert len(scripted.calls) == 2
        assert len(scripted.replies) == 1

    def test_nothing_is_stored_if_no_answer_was_readable(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide("no", "SECRET still no")

        with pytest.raises(PlanNotUsable) as raised:
            generate(alice, MONDAY)

        assert plans(alice) == []
        assert raised.value.problems[0].path == ""
        assert "SECRET" not in repr(raised.value.problems)
        assert len(records(alice)) == 2

    def test_a_cut_off_answer_twice_is_not_usable(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        cut = Completion(good(), 10, 8000, truncated=True)
        provide(cut, cut)

        with pytest.raises(PlanNotUsable) as raised:
            generate(alice, MONDAY)

        assert "cut off" in raised.value.problems[0].message


class TestAPlanWithErrors:
    def test_errors_that_remain_are_stored_as_a_draft_that_cannot_be_confirmed(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(bad(), bad())

        result = generate(alice, MONDAY)

        assert not result.report.valid
        assert result.plan.status == Status.DRAFT
        with pytest.raises(services.PlanNotConfirmable):
            services.confirm(alice, result.plan.pk)

    def test_the_better_of_two_plans_is_kept(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        two_errors = text_of(WeekPlan(MONDAY, (ride(1), ride(3), ride(0))))
        one_error = bad()
        provide(one_error, two_errors)

        result = generate(alice, MONDAY)

        assert len(result.report.errors) == 1
        assert len(result.plan.workouts.all()) == 2  # the plan with one error has two workouts

    def test_a_second_answer_that_cannot_be_read_does_not_lose_the_first_plan(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(bad(), "sorry, no")

        result = generate(alice, MONDAY)

        assert not result.report.valid
        assert len(plans(alice)) == 1
        assert len(result.plan.workouts.all()) == 2

    def test_a_tie_goes_to_the_later_answer(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        first = WeekPlan(MONDAY, (ride(0), ride(1)), "first")
        second = WeekPlan(MONDAY, (ride(0), ride(1)), "second")
        provide(text_of(first), text_of(second))

        assert generate(alice, MONDAY).plan.rationale == "second"

    def test_the_plan_is_checked_against_what_the_user_can_do_after_the_answer(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good(), good())

        def the_user_changes_the_week() -> None:
            WeekdayMinutes.objects.filter(owner=alice, weekday=0).update(minutes=0)

        scripted.before_answer = the_user_changes_the_week

        result = generate(alice, MONDAY)

        assert "day_over_capacity" in {f.code for f in result.report.errors}


class TestWhenTheProviderFails:
    @pytest.mark.parametrize(
        ("error", "status", "outcome"),
        [
            (InvalidKeyError("refused"), "invalid", "invalid_key"),
            (ProviderUnavailableError("down"), "unavailable", "unavailable"),
            (RateLimitedError("slow", 5), "untested", "rate_limited"),
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
            generate(alice, MONDAY)

        assert plans(alice) == []
        assert [r.outcome for r in records(alice)] == [outcome]
        assert AIProviderConfiguration.objects.get(owner=alice).status == status

    def test_an_error_on_the_second_call_loses_a_readable_plan_not(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(bad(), RateLimitedError("slow"))

        result = generate(alice, MONDAY)

        assert not result.report.valid
        assert [r.outcome for r in records(alice)] == ["success", "rate_limited"]

    def test_a_provider_removed_meanwhile_loses_a_readable_plan_not(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(bad(), good())

        def the_user_removes_the_provider() -> None:
            AIProviderConfiguration.objects.filter(owner=alice).delete()

        scripted.before_answer = the_user_removes_the_provider

        result = generate(alice, MONDAY)

        assert not result.report.valid
        assert len(scripted.calls) == 1
        assert len(plans(alice)) == 1

    def test_an_error_on_the_second_call_is_raised_if_there_is_no_plan_yet(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide("no", ProviderUnavailableError("down"))

        with pytest.raises(ProviderUnavailableError):
            generate(alice, MONDAY)

        assert plans(alice) == []

    def test_without_a_provider_nothing_happens(self, bob: User) -> None:
        WeekdayMinutes.objects.create(owner=bob, weekday=0, minutes=60)

        with pytest.raises(coach_services.NotConfiguredError):
            generate(bob, MONDAY)

        assert records(bob) == []
        assert plans(bob) == []


class TestAWeekWithoutTime:
    """With no time at all there is nothing to plan: the coach is not asked, nothing is paid."""

    def nothing_happens(self, user: User, scripted: Scripted) -> None:
        with pytest.raises(NoTimeAvailable):
            generate(user, MONDAY)

        assert scripted.calls == []
        assert records(user) == []
        assert plans(user) == []

    def free(self, user: User) -> None:
        WeekdayMinutes.objects.filter(owner=user).update(minutes=0)

    def test_days_without_minutes_are_no_time(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())
        self.free(alice)

        self.nothing_happens(alice, scripted)

    def test_a_user_who_never_entered_a_day_has_no_time(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())
        WeekdayMinutes.objects.filter(owner=alice).delete()

        self.nothing_happens(alice, scripted)

    def test_a_budget_of_zero_is_no_time(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())
        AvailabilitySettings.objects.create(owner=alice, weekly_budget_minutes=0)

        self.nothing_happens(alice, scripted)

    def test_away_the_whole_week_is_no_time(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())
        UnavailablePeriod.objects.create(
            owner=alice, kind="vacation", start_date=MONDAY, end_date=MONDAY + timedelta(days=6)
        )

        self.nothing_happens(alice, scripted)

    def test_a_single_minute_is_enough_to_ask(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good(), good())  # one minute is too little for this plan: a repair
        self.free(alice)
        WeekdayMinutes.objects.filter(owner=alice, weekday=0).update(minutes=1)

        generate(alice, MONDAY)

        assert len(scripted.calls) >= 1

    def test_free_time_in_another_week_does_not_count(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())
        UnavailablePeriod.objects.create(
            owner=alice,
            kind="illness",
            start_date=MONDAY + timedelta(days=7),
            end_date=MONDAY + timedelta(days=13),
        )

        generate(alice, MONDAY)

        assert len(scripted.calls) == 1

    def test_the_typical_week_is_no_time(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())
        self.free(alice)
        AvailabilitySettings.objects.create(owner=alice, typical_weekly_minutes=600)

        self.nothing_happens(alice, scripted)

    def test_it_is_said_before_a_missing_provider(self, bob: User) -> None:
        with pytest.raises(NoTimeAvailable):
            generate(bob, MONDAY)

    def test_a_week_that_cannot_be_planned_is_said_first(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())
        self.free(alice)

        with pytest.raises(WeekNotPlannable):
            generate(alice, THIS_WEEK - timedelta(weeks=1))

        assert scripted.calls == []
