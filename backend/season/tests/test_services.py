from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from accounts.models import User
from availability.models import UnavailablePeriod
from goals.models import Goal
from planning.schema import Sport
from season import services
from season.models import SeasonPlanVersion
from season.rules import SeasonContext
from season.schema import Focus, KeySession, PlanWeek, SeasonPlan, SessionKind, to_json
from season.serializers import skeleton_data, skeleton_from_data
from season.services import (
    PlanNotConfirmable,
    PlanNotFound,
    PlanStateError,
    confirm,
    discard,
    get,
    list_versions,
    load,
    save_draft,
    validate,
)
from season.skeleton import Race, Skeleton, SkeletonInputs, build_skeleton

pytestmark = pytest.mark.django_db

MONDAY = date(2026, 11, 16)
NOW = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
Status = SeasonPlanVersion.Status


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(services, "_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def skeleton(weeks: int = 4) -> Skeleton:
    races = (Race(MONDAY + timedelta(weeks=weeks - 1, days=6), "main", "running", 10_000, "Race"),)
    return build_skeleton(SkeletonInputs(MONDAY, (600,) * 52, races, 300, "normal"))


def good(skel: Skeleton) -> SeasonPlan:
    return SeasonPlan(
        tuple(
            PlanWeek(
                week.week_start,
                ((Sport.RUNNING, week.target_minutes),),
                Focus.ENDURANCE,
                "Because.",
                (KeySession(Sport.RUNNING, SessionKind.RACE, 1),) if week.races else (),
            )
            for week in skel.weeks
        ),
        "The season.",
    )


def draft(user: User, skel: Skeleton | None = None, **kwargs: Any) -> SeasonPlanVersion:
    skel = skel or skeleton()
    return save_draft(user, good(skel), SeasonContext(skel), **kwargs)


class TestTheSkeletonAsStored:
    def test_it_comes_back_as_it_went_in(self) -> None:
        for weeks in (1, 3, 12, 30):
            skel = skeleton(weeks)

            assert skeleton_from_data(skeleton_data(skel)) == skel

    def test_a_rolling_skeleton_too(self) -> None:
        skel = build_skeleton(SkeletonInputs(MONDAY, (300,) * 52, (), 200, "relaxed"))

        assert skeleton_from_data(skeleton_data(skel)) == skel

    def test_races_with_nothing_said_come_back(self) -> None:
        races = (
            Race(MONDAY + timedelta(days=20), "main"),
            Race(MONDAY + timedelta(days=9), "preparation"),
        )
        skel = build_skeleton(SkeletonInputs(MONDAY, (300,) * 52, races, 200, "normal"))

        assert skeleton_from_data(skeleton_data(skel)) == skel

    @pytest.mark.parametrize(
        "data", [None, [], "x", {}, {"weeks": "x"}, {"weeks": [], "rolling": 1}]
    )
    def test_what_is_not_a_skeleton_is_refused(self, data: Any) -> None:
        with pytest.raises((ValueError, KeyError, TypeError)):
            skeleton_from_data(data)


class TestSavingADraft:
    def test_a_plan_is_stored_as_a_draft_of_version_one(self, alice: User) -> None:
        plan = draft(alice)

        assert (plan.owner, plan.version, plan.status, plan.parent) == (alice, 1, "draft", None)
        assert plan.confirmed_at is None

    def test_the_weeks_the_rationale_and_what_it_was_made_for_are_stored(self, alice: User) -> None:
        skel = skeleton()

        plan = draft(alice, skel)

        assert plan.rationale == "The season."
        assert plan.weeks == to_json(good(skel))["weeks"]
        assert plan.skeleton == skeleton_data(skel)
        assert plan.sports == ["running", "cycling", "swimming", "strength"]

    def test_the_sports_that_were_chosen_are_stored_in_their_order(self, alice: User) -> None:
        skel = skeleton()

        plan = save_draft(
            alice, good(skel), SeasonContext(skel, frozenset({Sport.STRENGTH, Sport.RUNNING}))
        )

        assert plan.sports == ["running", "strength"]

    def test_versions_count_up_per_user(self, alice: User, bob: User) -> None:
        assert [draft(alice).version, draft(alice).version, draft(bob).version] == [1, 2, 1]

    def test_a_new_version_can_name_the_one_it_replaces_and_why(self, alice: User) -> None:
        first = draft(alice)

        second = draft(alice, parent=first.pk, reason="  Drafted by the coach  ")

        assert (second.parent_id, second.reason) == (first.pk, "Drafted by the coach")

    def test_the_parent_must_be_the_users_own(self, alice: User, bob: User) -> None:
        theirs = draft(bob)

        with pytest.raises(PlanNotFound):
            draft(alice, parent=theirs.pk)
        assert not SeasonPlanVersion.objects.filter(owner=alice).exists()

    @pytest.mark.parametrize("reason", ["x" * 201, "two\nlines", "bell\x07"])
    def test_a_reason_that_is_not_one_plain_line_stores_nothing(
        self, alice: User, reason: str
    ) -> None:
        with pytest.raises(ValidationError):
            draft(alice, reason=reason)

        assert not SeasonPlanVersion.objects.exists()

    def test_a_plan_with_errors_is_stored_as_it_is(self, alice: User) -> None:
        skel = skeleton()
        bad = SeasonPlan(good(skel).weeks[:1])

        plan = save_draft(alice, bad, SeasonContext(skel))

        assert plan.status == "draft"
        assert len(plan.weeks) == 1

    def test_a_race_for_the_version_number_is_retried_once(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = services._store
        calls: list[int] = []

        def lose_the_race(*args: Any, **kwargs: Any) -> SeasonPlanVersion:
            calls.append(1)
            if len(calls) == 1:
                raise IntegrityError("season_one_per_version")
            return real(*args, **kwargs)

        monkeypatch.setattr(services, "_store", lose_the_race)

        assert draft(alice).version == 1
        assert len(calls) == 2

    def test_a_second_failure_is_not_hidden(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def always(*args: Any, **kwargs: Any) -> SeasonPlanVersion:
            raise IntegrityError("season_one_per_version")

        monkeypatch.setattr(services, "_store", always)

        with pytest.raises(IntegrityError):
            draft(alice)


class TestReadingAPlanBack:
    def test_it_comes_back_as_it_went_in(self, alice: User) -> None:
        skel = skeleton()
        stored = draft(alice, skel)

        loaded = load(alice, stored.pk)

        assert loaded.plan == good(skel)
        assert loaded.context == SeasonContext(skel)

    def test_it_is_the_same_after_a_copy(self, alice: User) -> None:
        first = draft(alice)

        second = save_draft(
            alice, load(alice, first.pk).plan, load(alice, first.pk).context, parent=first.pk
        )

        assert load(alice, second.pk) == load(alice, first.pk)

    def test_a_plan_of_another_user_is_not_found(self, alice: User, bob: User) -> None:
        theirs = draft(bob)

        with pytest.raises(PlanNotFound):
            load(alice, theirs.pk)
        with pytest.raises(PlanNotFound):
            get(alice, theirs.pk)

    def test_an_unknown_id_is_not_found(self, alice: User) -> None:
        with pytest.raises(PlanNotFound):
            load(alice, uuid4())

    def test_the_versions_of_a_user_come_newest_first_and_only_theirs(
        self, alice: User, bob: User
    ) -> None:
        first, second = draft(alice), draft(alice)
        draft(bob)

        assert [v.pk for v in list_versions(alice)] == [second.pk, first.pk]
        assert list_versions(User.objects.create_user("carol@example.com")) == []


class TestTheReport:
    def test_a_good_plan_has_no_errors(self, alice: User) -> None:
        assert validate(alice, draft(alice).pk).valid is True

    def test_it_is_checked_against_the_skeleton_it_was_made_for(self, alice: User) -> None:
        stored = draft(alice)
        # afterwards the athlete drops the race and goes away: the plan is still a good one for
        # what it was made for
        UnavailablePeriod.objects.create(
            owner=alice, kind="vacation", start_date=MONDAY, end_date=MONDAY + timedelta(days=60)
        )
        Goal.objects.create(owner=alice, kind="general", title="Something else")

        assert validate(alice, stored.pk).findings == ()
        assert confirm(alice, stored.pk).status == "confirmed"

    def test_a_plan_that_does_not_follow_its_skeleton_has_errors(self, alice: User) -> None:
        skel = skeleton()
        short = save_draft(alice, SeasonPlan(good(skel).weeks[:2]), SeasonContext(skel))

        report = validate(alice, short.pk)

        assert report.valid is False
        assert "weeks_mismatch" in [f.code for f in report.errors]


class TestConfirming:
    def test_a_draft_is_confirmed(self, alice: User) -> None:
        plan = confirm(alice, draft(alice).pk)

        assert (plan.status, plan.confirmed_at) == ("confirmed", NOW)
        assert SeasonPlanVersion.objects.get(pk=plan.pk).status == "confirmed"

    def test_the_plan_that_was_confirmed_before_is_superseded(self, alice: User) -> None:
        first = confirm(alice, draft(alice).pk)

        second = confirm(alice, draft(alice, parent=first.pk).pk)

        first.refresh_from_db()
        assert (first.status, second.status) == ("superseded", "confirmed")
        assert first.confirmed_at == NOW

    def test_a_plan_with_errors_is_refused_and_nothing_changes(self, alice: User) -> None:
        skel = skeleton()
        broken = save_draft(alice, SeasonPlan(good(skel).weeks[:1]), SeasonContext(skel))

        with pytest.raises(PlanNotConfirmable) as raised:
            confirm(alice, broken.pk)

        assert raised.value.report.valid is False
        broken.refresh_from_db()
        assert (broken.status, broken.confirmed_at) == ("draft", None)

    def test_a_refused_plan_leaves_the_confirmed_one_confirmed(self, alice: User) -> None:
        first = confirm(alice, draft(alice).pk)
        skel = skeleton()
        broken = save_draft(alice, SeasonPlan(), SeasonContext(skel))

        with pytest.raises(PlanNotConfirmable):
            confirm(alice, broken.pk)

        first.refresh_from_db()
        assert first.status == "confirmed"

    def test_a_warning_does_not_stop_it(self, alice: User) -> None:
        skel = skeleton()
        no_race_session = SeasonPlan(
            tuple(
                PlanWeek(w.week_start, ((Sport.RUNNING, w.target_minutes),), Focus.ENDURANCE, "x")
                for w in skel.weeks
            )
        )
        stored = save_draft(alice, no_race_session, SeasonContext(skel))
        assert [f.code for f in validate(alice, stored.pk).warnings] == ["race_week_without_race"]

        assert confirm(alice, stored.pk).status == "confirmed"

    @pytest.mark.parametrize("make_it", ["confirmed", "discarded", "superseded"])
    def test_only_a_draft_can_be_confirmed(self, alice: User, make_it: str) -> None:
        plan = draft(alice)
        if make_it == "confirmed":
            confirm(alice, plan.pk)
        elif make_it == "discarded":
            discard(alice, plan.pk)
        else:
            confirm(alice, plan.pk)
            confirm(alice, draft(alice).pk)

        with pytest.raises(PlanStateError):
            confirm(alice, plan.pk)

    def test_a_plan_of_another_user_is_not_found_and_not_confirmed(
        self, alice: User, bob: User
    ) -> None:
        theirs = draft(bob)

        with pytest.raises(PlanNotFound):
            confirm(alice, theirs.pk)

        theirs.refresh_from_db()
        assert theirs.status == "draft"

    def test_the_plan_of_another_user_stays_confirmed(self, alice: User, bob: User) -> None:
        bobs = confirm(bob, draft(bob).pk)

        confirm(alice, draft(alice).pk)

        bobs.refresh_from_db()
        assert bobs.status == "confirmed"

    def test_a_confirmed_plan_cannot_be_changed(self, alice: User) -> None:
        plan = confirm(alice, draft(alice).pk)

        plan.weeks = []

        with pytest.raises(ValidationError, match="cannot be changed"):
            plan.save()


class TestDiscarding:
    def test_a_draft_is_discarded(self, alice: User) -> None:
        plan = discard(alice, draft(alice).pk)

        assert (plan.status, plan.confirmed_at) == ("discarded", None)

    @pytest.mark.parametrize("first", ["confirm", "discard"])
    def test_only_a_draft_can_be_discarded(self, alice: User, first: str) -> None:
        plan = draft(alice)
        (confirm if first == "confirm" else discard)(alice, plan.pk)

        with pytest.raises(PlanStateError):
            discard(alice, plan.pk)

    def test_a_plan_of_another_user_is_not_found(self, alice: User, bob: User) -> None:
        theirs = draft(bob)

        with pytest.raises(PlanNotFound):
            discard(alice, theirs.pk)

        theirs.refresh_from_db()
        assert theirs.status == "draft"

    def test_a_discarded_plan_is_kept_as_a_record(self, alice: User) -> None:
        plan = discard(alice, draft(alice).pk)

        assert SeasonPlanVersion.objects.filter(pk=plan.pk).exists()
        assert [v.status for v in list_versions(alice)] == ["discarded"]
