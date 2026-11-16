from datetime import date, timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from planning.schema import Sport
from season import services
from season.models import SeasonPlanVersion
from season.rules import SeasonContext
from season.schema import Focus, KeySession, PlanWeek, SeasonPlan, SessionKind
from season.skeleton import Phase, Race, Skeleton, SkeletonInputs, build_skeleton
from season.weeks import SeasonWeekFacts, confirmed_week

pytestmark = pytest.mark.django_db

MONDAY = date(2026, 11, 16)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def skeleton(weeks: int = 4) -> Skeleton:
    races = (Race(MONDAY + timedelta(weeks=weeks - 1, days=6), "main", "running", 10_000, "Race"),)
    return build_skeleton(SkeletonInputs(MONDAY, (600,) * 52, races, 300, "normal"))


def plan_for(skel: Skeleton) -> SeasonPlan:
    return SeasonPlan(
        tuple(
            PlanWeek(
                week.week_start,
                ((Sport.RUNNING, week.target_minutes),),
                Focus.ENDURANCE,
                f"Reason {index}.",
                (KeySession(Sport.RUNNING, SessionKind.LONG, 60, "easy"),)
                if index == 0
                else (KeySession(Sport.RUNNING, SessionKind.RACE, 1),)
                if week.races
                else (),
            )
            for index, week in enumerate(skel.weeks)
        ),
        "The season.",
    )


def confirmed(user: User, skel: Skeleton | None = None) -> SeasonPlanVersion:
    skel = skel or skeleton()
    stored = services.save_draft(user, plan_for(skel), SeasonContext(skel))
    return services.confirm(user, stored.pk)


class TestTheConfirmedWeek:
    def test_it_is_the_week_of_the_skeleton_and_of_the_plan(self, alice: User) -> None:
        skel = skeleton()
        confirmed(alice, skel)

        facts = confirmed_week(alice, MONDAY)

        assert facts == SeasonWeekFacts(
            week_start=MONDAY,
            phase=skel.weeks[0].phase,
            recovery=skel.weeks[0].recovery,
            target_minutes=skel.weeks[0].target_minutes,
            capacity_minutes=skel.weeks[0].capacity_minutes,
            races=(),
            minutes=((Sport.RUNNING, skel.weeks[0].target_minutes),),
            focus=Focus.ENDURANCE,
            key_sessions=(KeySession(Sport.RUNNING, SessionKind.LONG, 60, "easy"),),
            reason="Reason 0.",
        )
        assert facts is not None
        assert facts.total_minutes == skel.weeks[0].target_minutes

    def test_the_week_of_a_race_has_the_race(self, alice: User) -> None:
        confirmed(alice)

        facts = confirmed_week(alice, MONDAY + timedelta(weeks=3))

        assert facts is not None
        assert [race.title for race in facts.races] == ["Race"]
        assert facts.phase in Phase

    def test_a_week_outside_the_skeleton_has_none(self, alice: User) -> None:
        confirmed(alice)

        assert confirmed_week(alice, MONDAY - timedelta(weeks=1)) is None
        assert confirmed_week(alice, MONDAY + timedelta(weeks=4)) is None

    def test_a_day_that_is_no_week_start_has_none(self, alice: User) -> None:
        confirmed(alice)

        assert confirmed_week(alice, MONDAY + timedelta(days=1)) is None

    def test_a_user_without_a_plan_has_none(self, alice: User) -> None:
        assert confirmed_week(alice, MONDAY) is None

    @pytest.mark.parametrize("status", ["draft", "discarded"])
    def test_only_a_confirmed_plan_counts(self, alice: User, status: str) -> None:
        skel = skeleton()
        stored = services.save_draft(alice, plan_for(skel), SeasonContext(skel))
        if status == "discarded":
            services.discard(alice, stored.pk)

        assert confirmed_week(alice, MONDAY) is None

    def test_a_replaced_plan_does_not_count(self, alice: User) -> None:
        skel = skeleton()
        first = confirmed(alice, skel)
        other = plan_for(skel)
        newer = SeasonPlan(
            tuple(PlanWeek(w.week_start, w.minutes, Focus.TEMPO, "New.") for w in other.weeks)
        )
        stored = services.save_draft(alice, newer, SeasonContext(skel))
        services.confirm(alice, stored.pk)

        facts = confirmed_week(alice, MONDAY)

        first.refresh_from_db()
        assert first.status == "superseded"
        assert facts is not None
        assert (facts.focus, facts.reason) == (Focus.TEMPO, "New.")

    def test_the_plan_of_another_user_does_not_count(self, alice: User, bob: User) -> None:
        confirmed(bob)

        assert confirmed_week(alice, MONDAY) is None

    @pytest.mark.parametrize(
        "damage",
        [
            {"weeks": [{"week_start": "garbage"}]},
            {"weeks": "no list"},
            {"skeleton": {}},
            {"skeleton": {"weeks": "x"}},
            {"skeleton": []},
        ],
    )
    def test_a_plan_that_cannot_be_read_has_none_and_does_not_raise(
        self, alice: User, damage: dict[str, Any]
    ) -> None:
        stored = confirmed(alice)
        SeasonPlanVersion.objects.filter(pk=stored.pk).update(**damage)

        assert confirmed_week(alice, MONDAY) is None

    def test_a_week_missing_from_the_plan_has_none(self, alice: User) -> None:
        stored = confirmed(alice)
        SeasonPlanVersion.objects.filter(pk=stored.pk).update(weeks=stored.weeks[1:])

        assert confirmed_week(alice, MONDAY) is None

    def test_it_is_one_query_however_long_the_season(self, alice: User) -> None:
        confirmed(alice, skeleton(30))

        with CaptureQueriesContext(connection) as queries:
            confirmed_week(alice, MONDAY + timedelta(weeks=20))

        assert len(queries) == 1
