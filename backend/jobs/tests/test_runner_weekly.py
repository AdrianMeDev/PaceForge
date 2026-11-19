"""The Sunday jobs: a comment on the ending week and a draft of the next one.

Both only ever store what the athlete can look at: a comment and a draft. Neither confirms a plan
nor pushes anything to Intervals.icu, and neither redoes work that is already there. Every outcome
is one log row with a fixed code.
"""

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from django.utils import timezone

from jobs.models import Code, Job, JobRun, JobSettings, Outcome
from jobs.runner import run_draft, run_review
from planning.models import WeeklyPlan
from planning.schema import Goal, Sport, WeekPlan, Workout, ZoneSystem, to_json
from planning.tests.scripted import Scripted
from reviews.models import WeekComment

from .conftest import make_user

pytestmark = pytest.mark.django_db

# The clock of the jobs tests is a Thursday; its week starts on Monday the 16th.
THIS_MONDAY = date(2026, 11, 16)
NEXT_MONDAY = THIS_MONDAY + timedelta(weeks=1)
KEY = "sk-ant-test-0123456789-abcdefghij"
Status = WeeklyPlan.Status


@pytest.fixture
def provide(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Scripted]:
    """Install a provider that answers from a list, in place of the user's real one."""
    from coach import services as coach_services

    def install(*replies: Any) -> Scripted:
        scripted = Scripted(*replies)
        monkeypatch.setattr(
            coach_services, "provider_for", lambda configuration, model=None: scripted
        )
        return scripted

    return install


@pytest.fixture
def no_push_and_no_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    """A job never confirms a plan and never pushes to Intervals.icu."""

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("a background job must not confirm or push")

    from planning import push as planning_push
    from planning import services as planning_services

    monkeypatch.setattr(planning_push, "push", forbidden)
    monkeypatch.setattr(planning_services, "confirm", forbidden)


def athlete(email: str, *, minutes: list[int] | None = None) -> Any:
    """A user with training time on the days the test plans and a coach configured."""
    from athletes.models import ThresholdValue
    from availability.models import WeekdayMinutes
    from coach.models import AIProviderConfiguration

    user = make_user(email)
    for weekday, value in enumerate(
        minutes if minutes is not None else [90, 0, 90, 0, 120, 120, 0]
    ):
        WeekdayMinutes.objects.create(owner=user, weekday=weekday, minutes=value)
    ThresholdValue.objects.create(
        owner=user, sport="ride", metric="ftp", value=250, source="manual", basis="test"
    )
    AIProviderConfiguration.objects.create(
        owner=user, provider="anthropic", model="claude-sonnet-5-5", api_key=KEY
    )
    return user


def activity_in(user: Any, week: date, day: int) -> None:
    from activities.models import Activity

    Activity.objects.create(
        owner=user,
        source="manual",
        sport="running",
        start_time=datetime.combine(week + timedelta(days=day), datetime.min.time(), tzinfo=UTC),
        timer_seconds=3600.0,
    )


def ride(offset: int, monday: date = NEXT_MONDAY) -> Workout:
    return Workout(
        day=monday + timedelta(days=offset),
        sport=Sport.CYCLING,
        title="Endurance ride",
        goal=Goal.ENDURANCE,
        duration_minutes=60,
        zone_system=ZoneSystem.POWER,
        zone=2,
    )


def good_plan() -> str:
    return json.dumps(to_json(WeekPlan(NEXT_MONDAY, (ride(0), ride(2)), "Base")))


def bad_plan() -> str:
    """Readable, but Tuesday offers nothing: a rule error."""
    return json.dumps(to_json(WeekPlan(NEXT_MONDAY, (ride(0), ride(1)), "Base")))


def good_comment() -> str:
    return json.dumps({"comment": "A steady week.", "next_week": "hold"})


class TestTheDraft:
    def test_the_plan_is_stored_as_a_draft_and_nothing_is_pushed(
        self, provide: Callable[..., Scripted], no_push_and_no_confirm: None
    ) -> None:
        user = athlete("draft@example.com")
        scripted = provide(good_plan())

        run = run_draft(user, THIS_MONDAY)
        assert run is not None

        assert (run.job, run.outcome, run.code, run.week_start) == (
            Job.WEEK_DRAFT,
            Outcome.DONE,
            "",
            NEXT_MONDAY,
        )
        assert run.counts == {"errors": 0}
        plans = list(WeeklyPlan.objects.for_user(user))
        assert [p.status for p in plans] == [Status.DRAFT]
        assert plans[0].week_start == NEXT_MONDAY
        assert scripted.calls  # the coach was asked, and it was the only thing asked

    def test_a_plan_with_rule_errors_is_stored_with_its_error_count(
        self, provide: Callable[..., Scripted], no_push_and_no_confirm: None
    ) -> None:
        user = athlete("errors@example.com")
        provide(bad_plan(), bad_plan())

        run = run_draft(user, THIS_MONDAY)
        assert run is not None

        assert run.outcome == Outcome.DONE
        assert run.counts == {"errors": 1}
        plan = WeeklyPlan.objects.for_user(user).get()
        assert plan.status == Status.DRAFT

    def test_a_second_run_is_skipped_and_the_coach_is_not_asked_again(
        self, provide: Callable[..., Scripted], no_push_and_no_confirm: None
    ) -> None:
        user = athlete("twice@example.com")
        scripted = provide(good_plan())
        first = run_draft(user, THIS_MONDAY)
        assert first is not None

        second = run_draft(user, THIS_MONDAY)
        assert second is not None

        assert (second.outcome, second.code) == (Outcome.SKIPPED, Code.ALREADY_PLANNED)
        assert len(scripted.calls) == 1
        assert WeeklyPlan.objects.for_user(user).count() == 1

    def test_a_user_with_the_draft_turned_off_asks_nobody(
        self, provide: Callable[..., Scripted]
    ) -> None:
        user = athlete("off@example.com")
        scripted = provide(good_plan())
        JobSettings.objects.create(owner=user, week_draft=False)

        assert run_draft(user, THIS_MONDAY) is None

        assert JobRun.objects.count() == 0
        assert scripted.calls == []

    def test_a_confirmed_week_is_not_drafted_again(self, provide: Callable[..., Scripted]) -> None:
        user = athlete("confirmed@example.com")
        scripted = provide(good_plan())
        WeeklyPlan.objects.create(
            owner=user,
            week_start=NEXT_MONDAY,
            version=1,
            status="confirmed",
            confirmed_at=timezone.now(),
        )

        run = run_draft(user, THIS_MONDAY)
        assert run is not None

        assert (run.outcome, run.code) == (Outcome.SKIPPED, Code.ALREADY_PLANNED)
        assert scripted.calls == []

    def test_a_week_without_any_time_is_skipped_before_the_coach_is_asked(
        self, provide: Callable[..., Scripted]
    ) -> None:
        user = athlete("notime@example.com", minutes=[0] * 7)
        scripted = provide(good_plan())

        run = run_draft(user, THIS_MONDAY)
        assert run is not None

        assert (run.outcome, run.code) == (Outcome.SKIPPED, Code.NO_TIME)
        assert scripted.calls == []

    def test_no_coach_configured_is_skipped(self) -> None:
        user = athlete("nocoach@example.com")
        from coach.models import AIProviderConfiguration

        AIProviderConfiguration.objects.for_user(user).delete()

        run = run_draft(user, THIS_MONDAY)
        assert run is not None

        assert (run.outcome, run.code) == (Outcome.SKIPPED, Code.NO_COACH)

    def test_a_provider_that_does_not_answer_is_a_failure(
        self, provide: Callable[..., Scripted]
    ) -> None:
        from coach.providers.base import ProviderUnavailableError

        user = athlete("noanswer@example.com")
        provide(ProviderUnavailableError("provider is down"))

        run = run_draft(user, THIS_MONDAY)
        assert run is not None

        assert (run.outcome, run.code) == (Outcome.FAILED, Code.PROVIDER_ERROR)
        assert not WeeklyPlan.objects.exists()

    def test_an_unreadable_plan_is_a_failure(self, provide: Callable[..., Scripted]) -> None:
        user = athlete("garbled@example.com")
        provide("not json at all", "still not json")

        run = run_draft(user, THIS_MONDAY)
        assert run is not None

        assert (run.outcome, run.code) == (Outcome.FAILED, Code.PLAN_NOT_USABLE)
        assert not WeeklyPlan.objects.exists()


class TestTheReview:
    def test_the_comment_is_stored(self, provide: Callable[..., Scripted]) -> None:
        user = athlete("review@example.com")
        activity_in(user, THIS_MONDAY, 1)
        provide(good_comment())

        run = run_review(user, THIS_MONDAY)
        assert run is not None

        assert (run.job, run.outcome, run.code, run.week_start) == (
            Job.WEEK_REVIEW,
            Outcome.DONE,
            "",
            THIS_MONDAY,
        )
        assert run.counts == {}
        comment = WeekComment.objects.for_user(user).get()
        assert comment.comment == "A steady week."

    def test_a_week_that_already_has_a_comment_is_not_asked_again(
        self, provide: Callable[..., Scripted]
    ) -> None:
        user = athlete("asked@example.com")
        activity_in(user, THIS_MONDAY, 1)
        scripted = provide(good_comment())
        first = run_review(user, THIS_MONDAY)
        assert first is not None

        second = run_review(user, THIS_MONDAY)
        assert second is not None

        assert (second.outcome, second.code) == (Outcome.SKIPPED, Code.ALREADY_PLANNED)
        assert len(scripted.calls) == 1

    def test_an_empty_week_has_nothing_to_review(self, provide: Callable[..., Scripted]) -> None:
        user = athlete("empty@example.com")
        scripted = provide(good_comment())

        run = run_review(user, THIS_MONDAY)
        assert run is not None

        assert (run.outcome, run.code) == (Outcome.SKIPPED, Code.NOTHING_TO_REVIEW)
        assert scripted.calls == []
        assert not WeekComment.objects.exists()

    def test_a_user_with_the_review_turned_off_asks_nobody(
        self, provide: Callable[..., Scripted]
    ) -> None:
        user = athlete("off@example.com")
        activity_in(user, THIS_MONDAY, 1)
        scripted = provide(good_comment())
        JobSettings.objects.create(owner=user, week_review=False)

        assert run_review(user, THIS_MONDAY) is None

        assert JobRun.objects.count() == 0
        assert scripted.calls == []

    def test_no_coach_configured_is_skipped(self) -> None:
        user = athlete("nocoach@example.com")
        activity_in(user, THIS_MONDAY, 1)
        from coach.models import AIProviderConfiguration

        AIProviderConfiguration.objects.for_user(user).delete()

        run = run_review(user, THIS_MONDAY)
        assert run is not None

        assert (run.outcome, run.code) == (Outcome.SKIPPED, Code.NO_COACH)

    def test_an_unreadable_comment_is_a_failure(self, provide: Callable[..., Scripted]) -> None:
        user = athlete("garbled@example.com")
        activity_in(user, THIS_MONDAY, 1)
        provide("not json at all", "still not json")

        run = run_review(user, THIS_MONDAY)
        assert run is not None

        assert (run.outcome, run.code) == (Outcome.FAILED, Code.COMMENT_NOT_USABLE)
        assert not WeekComment.objects.exists()

    def test_two_users_each_get_their_own_comment_and_runs(
        self, provide: Callable[..., Scripted]
    ) -> None:
        alice = athlete("alice@example.com")
        activity_in(alice, THIS_MONDAY, 1)
        bob = athlete("bob@example.com")
        activity_in(bob, THIS_MONDAY, 2)
        provide(good_comment(), json.dumps({"comment": "More volume.", "next_week": "increase"}))

        alice_run = run_review(alice, THIS_MONDAY)
        bob_run = run_review(bob, THIS_MONDAY)
        assert alice_run is not None and bob_run is not None

        assert WeekComment.objects.for_user(alice).get().comment == "A steady week."
        assert WeekComment.objects.for_user(bob).get().comment == "More volume."
        assert set(JobRun.objects.values_list("owner_id", flat=True)) == {alice.id, bob.id}
