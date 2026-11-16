from datetime import UTC, date, datetime, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from athletes import best_times
from athletes.models import AthleteProfile, BestTime, ThresholdValue
from goals import services
from goals.assessing import assess_goals, form_of
from goals.models import Goal
from goals.realism import Rating, Reason

pytestmark = pytest.mark.django_db

NOW = datetime(2027, 7, 12, 12, 0, tzinfo=UTC)
TODAY = NOW.date()


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(services, "_utc_now", lambda: NOW)
    monkeypatch.setattr(best_times, "_today", lambda: TODAY)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def best(
    user: User, distance: str = "10k", seconds: int = 2481, day: date | None = None
) -> BestTime:
    return BestTime.objects.create(
        owner=user,
        distance=distance,
        seconds=seconds,
        date=day or TODAY - timedelta(days=30),
    )


def race(user: User, weeks: int = 10, seconds: int = 2400, **fields: object) -> Goal:
    data: dict[str, object] = {
        "kind": "race",
        "title": "Race",
        "priority": "secondary",
        "target_date": TODAY + timedelta(weeks=weeks),
        "discipline": "running",
        "distance_m": 10_000,
        "target_time_seconds": seconds,
        **fields,
    }
    return Goal.objects.create(owner=user, **data)


class TestTheForm:
    def test_without_anything_there_is_no_form(self, alice: User) -> None:
        form = form_of(alice)

        assert (form.vdot, form.ftp, form.threshold_pace) == (None, None, None)

    def test_the_vdot_is_the_one_of_the_best_time_that_counts(self, alice: User) -> None:
        best(alice, "10k", 2481)  # about VDOT 50

        assert form_of(alice).vdot == pytest.approx(50, abs=0.2)

    def test_a_best_time_older_than_a_year_does_not_count(self, alice: User) -> None:
        best(alice, day=TODAY - timedelta(days=400))

        assert form_of(alice).vdot is None

    def test_the_thresholds_are_the_ones_that_count(self, alice: User) -> None:
        for source, value in (("estimated", 200), ("manual", 250)):
            ThresholdValue.objects.create(
                owner=alice, sport="ride", metric="ftp", value=value, source=source, basis="t"
            )

        assert form_of(alice).ftp == 250

    def test_the_threshold_pace_may_come_from_a_best_time(self, alice: User) -> None:
        best(alice)

        assert form_of(alice).threshold_pace is not None

    def test_nothing_of_another_user_counts(self, alice: User, bob: User) -> None:
        best(bob)
        ThresholdValue.objects.create(
            owner=bob, sport="ride", metric="ftp", value=300, source="manual", basis="t"
        )

        form = form_of(alice)

        assert (form.vdot, form.ftp, form.threshold_pace) == (None, None, None)


class TestAssessingGoals:
    def test_each_active_goal_is_judged_by_its_id(self, alice: User) -> None:
        best(alice)
        easy = race(alice, seconds=2600)
        hard = race(alice, seconds=1800, priority="preparation")

        found = assess_goals(alice, [easy, hard])

        assert set(found) == {easy.pk, hard.pk}
        assert found[easy.pk].rating is Rating.REALISTIC
        assert found[hard.pk].rating is Rating.UNREALISTIC

    def test_a_goal_that_is_not_active_is_left_out(self, alice: User) -> None:
        best(alice)
        done = race(alice, status="achieved")
        dropped = race(alice, status="dropped", priority="preparation")

        assert assess_goals(alice, [done, dropped]) == {}

    def test_without_goals_nothing_is_looked_up(self, alice: User) -> None:
        with CaptureQueriesContext(connection) as queries:
            assert assess_goals(alice, []) == {}

        assert len(queries) == 0

    def test_a_goal_of_another_user_is_refused(self, alice: User, bob: User) -> None:
        theirs = race(bob)

        with pytest.raises(ValueError, match="another user"):
            assess_goals(alice, [theirs])

    def test_the_form_of_the_user_is_used_not_the_one_of_another(
        self, alice: User, bob: User
    ) -> None:
        best(bob)
        mine = race(alice)

        found = assess_goals(alice, [mine])

        assert (found[mine.pk].rating, found[mine.pk].reason) == (Rating.UNKNOWN, Reason.NO_FORM)

    def test_the_day_of_the_user_counts_not_the_one_of_the_server(self, alice: User) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="Pacific/Auckland")  # already the 13th
        best(alice)
        goal = race(alice, target_date=TODAY + timedelta(days=7))

        found = assess_goals(alice, [goal])

        assert found[goal.pk].weeks == 0  # six days to go in Auckland

    def test_a_given_day_is_not_looked_up_again(self, alice: User) -> None:
        best(alice)
        goal = race(alice)

        with CaptureQueriesContext(connection) as queries:
            assess_goals(alice, [goal], TODAY)

        assert len(queries) == 2

    def test_the_queries_do_not_grow_with_the_goals(self, alice: User) -> None:
        best(alice)
        one = [race(alice)]
        with CaptureQueriesContext(connection) as few:
            assess_goals(alice, one)
        many = [race(alice, priority="preparation") for _ in range(19)] + one

        with CaptureQueriesContext(connection) as lots:
            assess_goals(alice, many)

        assert len(few) == len(lots) == 3
