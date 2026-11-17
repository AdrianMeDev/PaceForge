from collections.abc import Callable

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts.models import User
from athletes.models import AthleteProfile
from availability.models import WeekdayMinutes
from coach.models import AIProviderConfiguration
from dashboard.setup import setup_of
from goals.models import Goal
from integrations.models import ProviderConnection
from reviews.tests.builders import make_activity, make_plan
from season.models import SeasonPlanVersion

pytestmark = pytest.mark.django_db

KEYS = [
    "profile",
    "training_time",
    "ai_coach",
    "intervals",
    "goal",
    "activities",
    "season",
    "first_week",
]


def done(user: User) -> dict[str, bool]:
    return {step.key: step.done for step in setup_of(user)}


def make_season(owner: User, status: str) -> SeasonPlanVersion:
    stamp = timezone.now() if status in ("confirmed", "superseded") else None
    return SeasonPlanVersion.objects.create(owner=owner, status=status, confirmed_at=stamp)


# Each step with what turns it done.
MAKERS: dict[str, Callable[[User], object]] = {
    "profile": lambda u: AthleteProfile.objects.create(owner=u, timezone="Europe/Berlin"),
    "training_time": lambda u: WeekdayMinutes.objects.create(owner=u, weekday=0, minutes=60),
    "ai_coach": lambda u: AIProviderConfiguration.objects.create(
        owner=u, provider="anthropic", model="claude-sonnet-5-5", api_key="k" * 20
    ),
    "intervals": lambda u: ProviderConnection.objects.create(
        owner=u, provider="intervals_icu", api_key="k" * 20, athlete_id="i1"
    ),
    "goal": lambda u: Goal.objects.create(owner=u, kind="general", title="Build endurance"),
    "activities": lambda u: make_activity(u, "2026-11-10T08:00:00"),
    "season": lambda u: make_season(u, "confirmed"),
    "first_week": lambda u: make_plan(u, status="confirmed"),
}


class TestTheSteps:
    def test_they_come_in_the_order_of_the_setup_and_only_intervals_is_optional(
        self, alice: User
    ) -> None:
        steps = setup_of(alice)

        assert [step.key for step in steps] == KEYS
        assert [step.key for step in steps if step.optional] == ["intervals"]

    def test_a_new_account_has_done_nothing(self, alice: User) -> None:
        assert done(alice) == dict.fromkeys(KEYS, False)

    @pytest.mark.parametrize("key", KEYS)
    def test_a_step_is_done_by_its_data_and_by_nothing_else(self, alice: User, key: str) -> None:
        MAKERS[key](alice)

        assert done(alice) == {name: name == key for name in KEYS}

    @pytest.mark.parametrize("key", KEYS)
    def test_the_data_of_someone_else_counts_for_nothing(
        self, alice: User, bob: User, key: str
    ) -> None:
        MAKERS[key](bob)

        assert done(alice) == dict.fromkeys(KEYS, False)


class TestWhatDoesNotCount:
    def test_a_profile_without_a_time_zone(self, alice: User) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="")

        assert not done(alice)["profile"]

    def test_a_weekday_without_minutes(self, alice: User) -> None:
        WeekdayMinutes.objects.create(owner=alice, weekday=0, minutes=0)

        assert not done(alice)["training_time"]

    def test_a_goal_that_is_achieved_or_dropped(self, alice: User) -> None:
        Goal.objects.create(owner=alice, kind="general", title="Old", status="achieved")
        Goal.objects.create(owner=alice, kind="general", title="Older", status="dropped")

        assert not done(alice)["goal"]

    @pytest.mark.parametrize("status", ["draft", "superseded", "discarded"])
    def test_a_season_plan_that_is_not_confirmed(self, alice: User, status: str) -> None:
        make_season(alice, status)

        assert not done(alice)["season"]

    @pytest.mark.parametrize("status", ["draft", "superseded", "discarded"])
    def test_a_week_plan_that_is_not_confirmed(self, alice: User, status: str) -> None:
        make_plan(alice, status=status)

        assert not done(alice)["first_week"]


class TestTheQueries:
    def test_there_is_one_per_step_whatever_is_done(self, alice: User, bob: User) -> None:
        with CaptureQueriesContext(connection) as empty:
            setup_of(alice)
        for maker in MAKERS.values():
            maker(bob)
        with CaptureQueriesContext(connection) as full:
            setup_of(bob)

        assert len(empty) == len(full) == len(KEYS)
