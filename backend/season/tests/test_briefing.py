import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from athletes.models import AthleteProfile, BestTime, ThresholdValue
from availability.models import (
    AvailabilitySettings,
    Limitation,
    SportPreference,
    UnavailablePeriod,
    WeekdayMinutes,
)
from goals import services as goal_services
from goals.models import Goal
from planning.schema import Sport
from season.briefing import (
    MAX_BYTES,
    MAX_RACES_TOLD,
    RACE_TITLE_TOLD_MAX,
    TAKEN_FROM_THE_WEEK,
    build_briefing,
    to_json,
)
from season.inputs import skeleton_for
from season.skeleton import MAX_WEEKS, Skeleton

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
TODAY = NOW.date()
MONDAY = date(2026, 11, 16)

# Every key that may appear anywhere in a briefing. A new fact has to be added here on purpose.
ALLOWED_KEYS = {
    "today",
    "rolling",
    "truncated",
    "peak_minutes",
    "weeks",
    "week_start",
    "phase",
    "recovery",
    "target_minutes",
    "capacity_minutes",
    "race_dates",
    "races",
    "date",
    "priority",
    "discipline",
    "distance_m",
    "title",
    "races_not_shown",
    # the assessment of a race: judged by code (goals.realism), numbers and fixed words
    "assessment",
    "rating",
    "reason",
    "current",
    "needed",
    "suggested",
    "prep_short",
    "prep_weeks",
    # taken from the briefing of the week plan, with what is under them
    "sports",
    "sport_preferences",
    "sport",
    "role",
    "sessions_min",
    "sessions_max",
    "strength_focus",
    "athlete",
    "age",
    "sex",
    "weight_kg",
    "resting_hr",
    "training_years",
    "years",
    "strength_experience",
    "strength_equipment",
    "best_times",
    "distance",
    "seconds",
    "vdot",
    "recent",
    "counts",
    "limits",
    "max_hard_days",
    "progression_warning_percent",
    "progression_error_percent",
    "easy_share_percent",
    "limitations",
    "body_part",
    "limitations_not_shown",
    "typical_weekly_minutes",
    "recent_weeks_minutes",
    "weekly_budget_minutes",
}


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def keys(node: Any) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in keys(v)}
    return set()


def race(owner: User, weeks: int, priority: str = "secondary", **fields: Any) -> Goal:
    data: dict[str, Any] = {
        "kind": "race",
        "title": f"Race {weeks}",
        "priority": priority,
        "target_date": MONDAY + timedelta(weeks=weeks, days=6),
        "discipline": "running",
        "distance_m": 42195,
        **fields,
    }
    return Goal.objects.create(owner=owner, **data)


def brief(user: User) -> dict[str, Any]:
    skeleton = skeleton_for(user)
    return build_briefing(user, TODAY, skeleton)


def full(alice: User) -> dict[str, Any]:
    for weekday in range(7):
        WeekdayMinutes.objects.create(owner=alice, weekday=weekday, minutes=60)
    AvailabilitySettings.objects.create(
        owner=alice, weekly_budget_minutes=300, typical_weekly_minutes=250, strength_focus="legs"
    )
    SportPreference.objects.create(owner=alice, sport="running", role="goal", sessions_min=3)
    AthleteProfile.objects.create(owner=alice, birth_year=1985, sex="female", weight_kg=61.5)
    ThresholdValue.objects.create(
        owner=alice, sport="run", metric="threshold_pace", value=300, source="manual", basis="t"
    )
    BestTime.objects.create(
        owner=alice, distance="5k", seconds=1200, date=TODAY - timedelta(days=9)
    )
    Limitation.objects.create(owner=alice, body_part="achilles", sports=["running"])
    race(alice, 14, "main", title="Berlin Marathon")
    race(alice, 6, "secondary", title="Spring 10k", distance_m=10_000)
    return brief(alice)


class TestWhatIsTold:
    def test_the_skeleton_is_there_week_by_week(self, alice: User) -> None:
        briefing = full(alice)

        assert briefing["today"] == "2026-11-19"
        assert (briefing["rolling"], briefing["truncated"]) == (False, False)
        assert len(briefing["weeks"]) == 15
        assert set(briefing["weeks"][0]) == {
            "week_start",
            "phase",
            "recovery",
            "target_minutes",
            "capacity_minutes",
            "race_dates",
        }
        assert briefing["weeks"][0]["week_start"] == "2026-11-16"
        assert briefing["weeks"][-1]["phase"] == "taper"
        assert briefing["peak_minutes"] == max(w["target_minutes"] for w in briefing["weeks"])

    def test_a_race_is_told_once_with_its_title_and_in_its_week_by_its_day(
        self, alice: User
    ) -> None:
        briefing = full(alice)

        assert [r["title"] for r in briefing["races"]] == ["Spring 10k", "Berlin Marathon"]
        assessment = briefing["races"][1].pop("assessment")
        assert (assessment["rating"], assessment["reason"]) == ("unknown", "no_target")
        assert briefing["races"][1] == {
            "date": "2027-02-28",
            "priority": "main",
            "discipline": "running",
            "distance_m": 42195,
            "title": "Berlin Marathon",
        }
        assert briefing["weeks"][14]["race_dates"] == ["2027-02-28"]
        assert briefing["weeks"][0]["race_dates"] == []
        assert "Berlin" not in json.dumps(briefing["weeks"])

    def test_the_facts_of_the_athlete_are_the_ones_of_the_week_plan(self, alice: User) -> None:
        briefing = full(alice)

        assert briefing["sports"] == ["running", "cycling", "swimming", "strength"]
        assert briefing["athlete"]["age"] == 41
        assert briefing["athlete"]["sex"] == "female"
        assert briefing["sport_preferences"][0]["role"] == "goal"
        assert briefing["strength_focus"] == "legs"
        assert briefing["vdot"] is not None
        assert briefing["best_times"][0]["distance"] == "5k"
        assert briefing["limitations"] == [{"body_part": "achilles", "sports": ["running"]}]
        assert briefing["limits"]["max_hard_days"] == 2
        assert briefing["typical_weekly_minutes"] == 250
        assert briefing["weekly_budget_minutes"] == 300

    def test_what_is_taken_over_is_what_the_week_plan_tells(self, alice: User) -> None:
        from planning.briefing import build_briefing as week_briefing

        briefing = full(alice)
        week = week_briefing(alice, MONDAY)

        for name in TAKEN_FROM_THE_WEEK:
            assert briefing[name] == week[name], name

    def test_a_user_with_nothing_has_the_rolling_skeleton_and_empty_facts(
        self, alice: User
    ) -> None:
        briefing = brief(alice)

        assert briefing["rolling"] is True
        assert len(briefing["weeks"]) == 12
        assert briefing["races"] == []
        assert briefing["athlete"]["age"] is None
        assert briefing["best_times"] == []
        assert briefing["limitations"] == []

    def test_an_absence_is_a_week_without_capacity(self, alice: User) -> None:
        WeekdayMinutes.objects.create(owner=alice, weekday=0, minutes=60)
        UnavailablePeriod.objects.create(
            owner=alice,
            kind="vacation",
            start_date=MONDAY + timedelta(weeks=1),
            end_date=MONDAY + timedelta(weeks=1, days=6),
        )
        race(alice, 6, "main")

        briefing = brief(alice)

        assert [w["capacity_minutes"] for w in briefing["weeks"][:3]] == [60, 0, 60]
        assert briefing["weeks"][1]["target_minutes"] == 0


class TestTheAssessmentOfARace:
    def test_a_race_with_a_goal_that_can_be_judged_is_told_how_realistic_it_is(
        self, alice: User
    ) -> None:
        BestTime.objects.create(
            owner=alice, distance="10k", seconds=2481, date=TODAY - timedelta(days=9)
        )
        race(alice, 14, distance_m=10_000, target_time_seconds=1800, priority="main")

        (told,) = brief(alice)["races"]

        assert told["assessment"]["rating"] == "unrealistic"
        assert told["assessment"]["suggested"] > 1800

    def test_a_race_without_a_target_time_says_so(self, alice: User) -> None:
        race(alice, 14)

        (told,) = brief(alice)["races"]

        assert told["assessment"]["reason"] == "no_target"

    def test_a_race_that_is_no_goal_of_the_user_has_none(self, alice: User, bob: User) -> None:
        race(bob, 14, target_time_seconds=1800)
        race(alice, 14)

        assert [r["assessment"]["reason"] for r in brief(alice)["races"]] == ["no_target"]

    def test_a_goal_that_is_not_active_is_not_used(self, alice: User) -> None:
        race(alice, 14, status="achieved", priority="main", target_time_seconds=1800)
        race(alice, 14, priority="main")

        assert [r["assessment"]["reason"] for r in brief(alice)["races"]] == ["no_target"]

    def test_it_holds_nothing_of_the_titles(self, alice: User) -> None:
        race(alice, 14, title="SECRET-TITLE", notes="SECRET-NOTES")

        (told,) = brief(alice)["races"]

        assert "SECRET" not in str(told["assessment"])


class TestWhatIsNotTold:
    def test_no_key_is_there_that_was_not_decided_on(self, alice: User) -> None:
        assert keys(full(alice)) <= ALLOWED_KEYS

    def test_nothing_that_identifies_the_user_is_there(self, alice: User) -> None:
        text = to_json(full(alice))

        assert "alice" not in text
        assert "example.com" not in text
        assert str(alice.pk) not in text
        assert "1985" not in text  # the birth year is not told, only the age

    def test_the_data_of_another_user_is_not_told(self, alice: User, bob: User) -> None:
        WeekdayMinutes.objects.create(owner=bob, weekday=0, minutes=500)
        race(bob, 5, "main", title="Bobs secret race")
        Limitation.objects.create(owner=bob, body_part="knee", sports=["running"])
        AthleteProfile.objects.create(owner=bob, birth_year=1950, weight_kg=99)

        text = to_json(brief(alice))

        assert "secret" not in text
        assert "knee" not in text
        assert "99" not in json.loads(text)["athlete"].__repr__()

    def test_the_notes_and_the_text_about_limitations_are_not_told(self, alice: User) -> None:
        race(alice, 6, "main", notes="NOTES-MARKER")
        AvailabilitySettings.objects.create(
            owner=alice, limitations="TEXT-MARKER", share_limitations_text=True
        )

        text = to_json(brief(alice))

        assert "NOTES-MARKER" not in text
        assert "TEXT-MARKER" not in text

    def test_the_title_of_a_race_is_cut(self, alice: User) -> None:
        race(alice, 6, "main", title="T" * 100)

        (told,) = brief(alice)["races"]

        assert told["title"] == "T" * RACE_TITLE_TOLD_MAX


class TestTheText:
    def test_the_keys_are_sorted_and_text_stays_readable(self) -> None:
        assert to_json({"b": 1, "a": ["ä", None]}) == '{"a":["ä",null],"b":1}'

    def test_the_text_is_the_same_for_the_same_data(self, alice: User) -> None:
        briefing = full(alice)

        assert to_json(briefing) == to_json(brief(alice))
        assert json.loads(to_json(briefing)) == briefing


class TestTheLimits:
    def test_the_limits_are_written_out_on_purpose(self) -> None:
        assert (MAX_RACES_TOLD, RACE_TITLE_TOLD_MAX, MAX_BYTES) == (20, 60, 24_000)

    def test_the_most_races_are_told_and_the_rest_is_counted(self, alice: User) -> None:
        for number in range(MAX_RACES_TOLD + 4):
            race(alice, 3 + number, "main" if number == 0 else "secondary")

        briefing = brief(alice)

        assert len(briefing["races"]) == MAX_RACES_TOLD
        assert briefing["races_not_shown"] == 4

    def test_the_worst_case_stays_below_the_limit(self, alice: User) -> None:
        # a year of weeks, the most races with titles of control characters (six bytes each)
        for weekday in range(7):
            WeekdayMinutes.objects.create(owner=alice, weekday=weekday, minutes=1440)
        for number in range(30):
            race(alice, 5 + number, "main" if number == 0 else "secondary", title="\x01" * 100)
        for distance, seconds in (
            ("5k", 1200),
            ("10k", 2500),
            ("half_marathon", 5600),
            ("marathon", 12000),
        ):
            BestTime.objects.create(
                owner=alice, distance=distance, seconds=seconds, date=TODAY - timedelta(days=5)
            )
        for _ in range(15):
            Limitation.objects.create(
                owner=alice,
                body_part="achilles",
                sports=["running", "cycling", "swimming", "strength"],
            )
        AthleteProfile.objects.create(
            owner=alice,
            birth_year=1900,
            sex="female",
            weight_kg=299.9,
            resting_hr=120,
            years_running=80,
            years_cycling=80,
            years_swimming=80,
            years_strength=80,
            strength_experience="advanced",
            strength_equipment=["gym", "home", "dumbbells"],
        )
        for sport in ("running", "cycling", "swimming", "strength"):
            SportPreference.objects.create(
                owner=alice, sport=sport, role="supplementary", sessions_min=14, sessions_max=14
            )
        skeleton = skeleton_for(alice)

        size = len(to_json(build_briefing(alice, TODAY, skeleton)).encode())

        assert len(skeleton.weeks) <= MAX_WEEKS
        assert size < MAX_BYTES, f"{size} bytes against a limit of {MAX_BYTES}"


class TestTheSportsOfAChange:
    def test_a_briefing_can_tell_the_sports_a_plan_was_made_for(self, alice: User) -> None:
        skeleton = skeleton_for(alice)

        told = build_briefing(
            alice, NOW.date(), skeleton, frozenset({Sport.CYCLING, Sport.RUNNING})
        )

        assert told["sports"] == ["running", "cycling"]

    def test_without_them_it_tells_the_sports_the_athlete_has_chosen_now(self, alice: User) -> None:
        AvailabilitySettings.objects.create(owner=alice, sports=["swimming"])

        told = build_briefing(alice, NOW.date(), skeleton_for(alice))

        assert told["sports"] == ["swimming"]

    def test_the_other_keys_are_the_same(self, alice: User) -> None:
        skeleton = skeleton_for(alice)

        plain = build_briefing(alice, NOW.date(), skeleton)
        told = build_briefing(alice, NOW.date(), skeleton, frozenset({Sport.CYCLING}))

        assert {k: v for k, v in told.items() if k != "sports"} == {
            k: v for k, v in plain.items() if k != "sports"
        }


class TestTheQueries:
    def test_their_number_does_not_depend_on_the_data(self, alice: User) -> None:
        with CaptureQueriesContext(connection) as empty:
            brief(alice)
        full(alice)
        for number in range(10):
            race(alice, 20 + number)

        with CaptureQueriesContext(connection) as many:
            brief(alice)

        assert len(empty) == len(many)


def test_a_skeleton_without_weeks_is_told_for_today() -> None:
    # not reachable through the inputs (there is always the current week), but not a crash either
    assert Skeleton((), None, 0, True, False).weeks == ()
