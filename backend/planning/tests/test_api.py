import dataclasses
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.db import connection
from django.http import QueryDict
from django.test.utils import CaptureQueriesContext
from rest_framework.parsers import FormParser, JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from accounts.models import User
from accounts.tests.conftest import AuthApi
from activities.models import Activity
from athletes.models import AthleteProfile, ThresholdValue
from availability.models import AvailabilitySettings, WeekdayMinutes
from coach.models import AIProviderConfiguration, AIUsageRecord
from coach.providers.base import (
    EndpointNotAllowedError,
    InvalidKeyError,
    ProviderUnavailableError,
    RateLimitedError,
    UnexpectedResponseError,
)
from coach.views import PROBLEMS
from goals import services as goal_services
from integrations.intervals import InvalidKeyError as IntervalsKeyError
from integrations.intervals import RejectedError
from integrations.models import ProviderConnection
from planning import services
from planning.models import PlannedWorkout, WeeklyPlan
from planning.schema import (
    Exercise,
    ExerciseEquipment,
    ExerciseRegion,
    Goal,
    Segment,
    SegmentKind,
    Slot,
    Sport,
    WeekPlan,
    Workout,
    ZoneSystem,
    to_json,
)
from planning.throttles import PlanPushThrottle
from planning.views import ConfirmView

from .conftest import make_user, signed_in
from .fake_calendar import Calendar
from .scripted import Scripted

# A fixed id for the tests that are parametrized: the id is part of the name of a test, and
# every worker of a parallel run has to collect the same names.
UNKNOWN_ID = UUID("0195f3a0-0000-7000-8000-000000000001")

pytestmark = pytest.mark.django_db

NOW = datetime(2027, 7, 14, 12, 0, tzinfo=UTC)  # a Wednesday
THIS_WEEK = date(2027, 7, 12)
MONDAY = date(2027, 7, 19)
KEY = "sk-ant-test-0123456789-abcdefghij"
MARKER = "SECRETMARKER"
WEEKS = "/api/planning/weeks/"
Status = WeeklyPlan.Status
PLAN_FIELDS = {
    "id",
    "week_start",
    "version",
    "status",
    "reason",
    "note",
    "rationale",
    "parent",
    "created_at",
    "confirmed_at",
    "workouts",
    "report",
    "export",
    "load",
}
WORKOUT_FIELDS = {
    "day",
    "sport",
    "title",
    "goal",
    "duration_minutes",
    "zone_system",
    "zone",
    "notes",
    "slot",
    "stretching_minutes",
    "segments",
    "lineage",
    "target",
    "export",
    "exercises",
    "estimated_load",
}


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    user = make_user("alice@example.com")
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
    return make_user("bob@example.com")


def ride(offset: int, minutes: int = 60, monday: date = MONDAY) -> Workout:
    return Workout(
        day=monday + timedelta(days=offset),
        sport=Sport.CYCLING,
        title="Endurance ride",
        goal=Goal.ENDURANCE,
        duration_minutes=minutes,
        zone_system=ZoneSystem.POWER,
        zone=2,
    )


def good(monday: date = MONDAY) -> str:
    plan = WeekPlan(monday, (ride(2, monday=monday), ride(0, monday=monday)), "Base")
    return json.dumps(to_json(plan))


def bad() -> str:
    """Readable, but Tuesday offers nothing: a rule error."""
    return json.dumps(to_json(WeekPlan(MONDAY, (ride(0), ride(1)))))


def body(response: Any) -> Any:
    return json.loads(response.content)


def draft(user: User, *workouts: Workout, monday: date = MONDAY) -> WeeklyPlan:
    plan = WeekPlan(monday, workouts or (ride(0, monday=monday), ride(2, monday=monday)))
    return services.save_draft(user, plan, reason="by hand")


def generate_url(week: str = "2027-07-19") -> str:
    return f"/api/planning/weeks/{week}/generate/"


def check_url(week: str = "2027-07-19") -> str:
    return f"/api/planning/weeks/{week}/check/"


def plan_url(plan: Any, action: str = "") -> str:
    return f"/api/planning/plans/{plan}/{action}"


ENDPOINTS = [
    ("GET", WEEKS),
    ("POST", generate_url()),
    ("POST", check_url()),
    ("GET", plan_url(UNKNOWN_ID)),
    ("POST", plan_url(UNKNOWN_ID, "revise/")),
    ("POST", plan_url(UNKNOWN_ID, "restore/")),
    ("POST", plan_url(UNKNOWN_ID, "confirm/")),
    ("POST", plan_url(UNKNOWN_ID, "push/")),
    ("POST", plan_url(UNKNOWN_ID, "discard/")),
]


class TestAccess:
    @pytest.mark.parametrize(("method", "url"), ENDPOINTS)
    def test_anonymous_visitors_are_refused(self, method: str, url: str) -> None:
        response = AuthApi().call(method, url)

        assert response.status_code == HTTPStatus.FORBIDDEN

    @pytest.mark.parametrize(("method", "url"), [e for e in ENDPOINTS if e[0] == "POST"])
    def test_a_post_without_the_csrf_token_is_refused(
        self, alice: User, provide: Callable[..., Scripted], method: str, url: str
    ) -> None:
        scripted = provide(good())
        api = signed_in(alice)

        response = api.client.generic(method, url, data=b"", content_type="application/json")

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert scripted.calls == []

    @pytest.mark.parametrize(
        ("method", "url"),
        [
            ("POST", WEEKS),
            ("PUT", WEEKS),
            ("GET", generate_url()),
            ("GET", check_url()),
            ("PUT", check_url()),
            ("DELETE", plan_url(UNKNOWN_ID)),
            ("PATCH", plan_url(UNKNOWN_ID)),
            ("GET", plan_url(UNKNOWN_ID, "revise/")),
            ("PUT", plan_url(UNKNOWN_ID, "revise/")),
            ("GET", plan_url(UNKNOWN_ID, "restore/")),
            ("PUT", plan_url(UNKNOWN_ID, "restore/")),
            ("GET", plan_url(UNKNOWN_ID, "confirm/")),
            ("GET", plan_url(UNKNOWN_ID, "discard/")),
        ],
    )
    def test_other_methods_are_not_allowed(self, alice: User, method: str, url: str) -> None:
        response = signed_in(alice).call(method, url)

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED


def confirm_season(user: User, *, weeks: int, status: str = "confirmed") -> None:
    """A season plan whose first ``weeks`` weeks start on the first week that can be planned."""
    from season import services as season_services
    from season.rules import SeasonContext
    from season.schema import Focus, KeySession, PlanWeek, SeasonPlan, SessionKind
    from season.skeleton import Race, SkeletonInputs, build_skeleton

    monday = date(2027, 7, 12)
    race = Race(
        monday + timedelta(weeks=weeks - 1, days=6), "main", "running", 10_000, "Secret title"
    )
    skeleton = build_skeleton(SkeletonInputs(monday, (600,) * 52, (race,), 300, "normal"))
    plan = SeasonPlan(
        tuple(
            PlanWeek(
                week.week_start,
                ((Sport.RUNNING, week.target_minutes),),
                Focus.THRESHOLD,
                "Build the base.",
                (KeySession(Sport.RUNNING, SessionKind.LONG, 60, "easy"),) if index == 0 else (),
            )
            for index, week in enumerate(skeleton.weeks)
        )
    )
    stored = season_services.save_draft(user, plan, SeasonContext(skeleton))
    if status == "confirmed":
        season_services.confirm(user, stored.pk)
    elif status == "discarded":
        season_services.discard(user, stored.pk)


class TestTheWeeks:
    def test_five_weeks_with_nothing_in_them(self, alice: User) -> None:
        response = signed_in(alice).call("GET", WEEKS)

        assert response.status_code == HTTPStatus.OK
        assert body(response) == {
            "weeks": [
                {"week_start": f"2027-{month:02d}-{day:02d}", "season": None, "plans": []}
                for month, day in [(7, 12), (7, 19), (7, 26), (8, 2), (8, 9)]
            ]
        }

    def test_a_week_of_the_confirmed_season_plan_comes_with_it(self, alice: User) -> None:
        confirm_season(alice, weeks=2)

        weeks = body(signed_in(alice).call("GET", WEEKS))["weeks"]

        season = weeks[0]["season"]
        assert set(season) == {
            "phase",
            "recovery",
            "target_minutes",
            "minutes",
            "total_minutes",
            "focus",
            "key_sessions",
            "reason",
            "races",
        }
        assert season["focus"] == "threshold"
        assert season["reason"] == "Build the base."
        assert season["key_sessions"] == [
            {"sport": "running", "kind": "long", "minutes": 60, "detail": "easy"}
        ]
        assert [w["season"] is not None for w in weeks] == [True, True, False, False, False]

    def test_the_title_of_a_race_is_not_in_it(self, alice: User) -> None:
        confirm_season(alice, weeks=2)

        text = signed_in(alice).call("GET", WEEKS).content.decode()

        assert "Secret title" not in text

    @pytest.mark.parametrize("status", ["draft", "discarded"])
    def test_only_a_confirmed_season_plan_is_shown(self, alice: User, status: str) -> None:
        confirm_season(alice, weeks=2, status=status)

        weeks = body(signed_in(alice).call("GET", WEEKS))["weeks"]

        assert [w["season"] for w in weeks] == [None] * 5

    def test_the_season_plan_of_another_user_is_not_shown(self, alice: User) -> None:
        confirm_season(make_user("bob@example.com"), weeks=2)

        weeks = body(signed_in(alice).call("GET", WEEKS))["weeks"]

        assert [w["season"] for w in weeks] == [None] * 5

    def test_the_number_of_queries_does_not_depend_on_the_season(self, alice: User) -> None:
        api = signed_in(alice)
        with CaptureQueriesContext(connection) as without:
            api.call("GET", WEEKS)
        confirm_season(alice, weeks=5)

        with CaptureQueriesContext(connection) as with_season:
            api.call("GET", WEEKS)

        assert len(with_season) == len(without)

    def test_the_versions_of_a_week_come_newest_first_with_their_facts(self, alice: User) -> None:
        first = draft(alice)
        second = draft(alice, ride(0), ride(1), ride(2))
        services.discard(alice, first.pk)

        weeks = body(signed_in(alice).call("GET", WEEKS))["weeks"]

        plans = weeks[1]["plans"]
        assert [(p["version"], p["status"], p["workout_count"]) for p in plans] == [
            (2, "draft", 3),
            (1, "discarded", 2),
        ]
        assert set(plans[0]) == {
            "id",
            "version",
            "status",
            "reason",
            "workout_count",
            "created_at",
            "confirmed_at",
        }
        assert (plans[0]["id"], plans[0]["reason"], plans[0]["confirmed_at"]) == (
            str(second.pk),
            "by hand",
            None,
        )
        assert [w["plans"] for w in weeks if w is not weeks[1]] == [[]] * 4

    def test_a_confirmed_plan_shows_when(self, alice: User) -> None:
        plan = services.confirm(alice, draft(alice).pk)

        (shown,) = body(signed_in(alice).call("GET", WEEKS))["weeks"][1]["plans"]

        assert shown["status"] == "confirmed"
        assert shown["confirmed_at"] is not None
        assert shown["id"] == str(plan.pk)

    def test_weeks_outside_the_window_and_other_users_plans_are_not_shown(
        self, alice: User, bob: User
    ) -> None:
        draft(
            alice,
            ride(0, monday=THIS_WEEK - timedelta(weeks=1)),
            monday=THIS_WEEK - timedelta(weeks=1),
        )
        draft(bob)

        weeks = body(signed_in(alice).call("GET", WEEKS))["weeks"]

        assert all(week["plans"] == [] for week in weeks)

    def test_the_number_of_queries_does_not_depend_on_the_plans(self, alice: User) -> None:
        api = signed_in(alice)
        with CaptureQueriesContext(connection) as empty:
            api.call("GET", WEEKS)
        for _ in range(4):
            draft(alice)
        draft(alice, monday=THIS_WEEK + timedelta(weeks=2))

        with CaptureQueriesContext(connection) as full:
            api.call("GET", WEEKS)

        assert len(full) == len(empty)


class TestGenerating:
    def test_a_good_answer_gives_a_draft(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good())

        response = signed_in(alice).call("POST", generate_url())

        assert response.status_code == HTTPStatus.CREATED
        data = body(response)
        assert set(data) == PLAN_FIELDS
        assert (data["week_start"], data["version"], data["status"]) == ("2027-07-19", 1, "draft")
        assert (data["reason"], data["parent"], data["confirmed_at"]) == (
            "Drafted by the coach",
            None,
            None,
        )
        assert data["rationale"] == "Base"
        assert data["report"] == {"valid": True, "findings": []}
        assert [w["day"] for w in data["workouts"]] == ["2027-07-19", "2027-07-21"]
        assert set(data["workouts"][0]) == WORKOUT_FIELDS
        assert PlannedWorkout.objects.filter(plan_id=data["id"]).count() == 2
        stored = PlannedWorkout.objects.filter(plan_id=data["id"]).order_by("day")
        assert [w["lineage"] for w in data["workouts"]] == [str(w.lineage) for w in stored]
        (record,) = AIUsageRecord.objects.filter(owner=alice)
        assert (record.purpose, record.outcome) == ("weekly_plan", "success")

    def test_a_note_goes_to_the_coach_and_comes_back_with_the_draft(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())

        response = signed_in(alice).call("POST", generate_url(), {"note": "No time on Tuesday."})

        assert response.status_code == HTTPStatus.CREATED
        assert body(response)["note"] == "No time on Tuesday."
        assert '"athlete_note":"No time on Tuesday."' in scripted.calls[0][1][0].content
        assert WeeklyPlan.objects.get().note == "No time on Tuesday."
        assert body(signed_in(alice).call("GET", plan_url(body(response)["id"])))["note"] == (
            "No time on Tuesday."
        )

    def test_no_body_and_an_empty_note_give_a_draft_without_one(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good(), good())

        first = signed_in(alice).call("POST", generate_url())
        second = signed_in(alice).call("POST", generate_url(), {"note": "  "})

        assert (first.status_code, second.status_code) == (HTTPStatus.CREATED, HTTPStatus.CREATED)
        assert (body(first)["note"], body(second)["note"]) == ("", "")

    @pytest.mark.parametrize(
        ("note", "fields"),
        [
            ("x" * 301, {"note"}),
            ("x" * 4001, {"note"}),
            ("a\x00b", {"note"}),
            (5, {"note"}),
            (True, {"note"}),
            (["a"], {"note"}),
            (None, {"note"}),
        ],
    )
    def test_a_note_that_does_not_fit_is_refused_and_nothing_is_asked(
        self, alice: User, provide: Callable[..., Scripted], note: Any, fields: set[str]
    ) -> None:
        scripted = provide(good())

        response = signed_in(alice).call("POST", generate_url(), {"note": note})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert set(body(response)) == fields
        assert scripted.calls == []
        assert WeeklyPlan.objects.count() == 0

    def test_nothing_of_the_note_is_repeated_in_an_error(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good())

        for note in (MARKER * 100, MARKER + "\x00"):
            response = signed_in(alice).call("POST", generate_url(), {"note": note})

            assert response.status_code == HTTPStatus.BAD_REQUEST
            assert MARKER not in response.content.decode()

    def test_deeply_nested_body_is_bad_request_and_asks_nothing(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())
        api = signed_in(alice)
        deep = "[" * 1500 + f'"{MARKER}"' + "]" * 1500

        response = api.client.post(
            generate_url(),
            data=deep,
            content_type="application/json",
            headers={"X-CSRFToken": api._csrf_token()},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert MARKER not in response.content.decode()
        assert scripted.calls == []
        assert not WeeklyPlan.objects.exists()

    def test_decoder_recursion_error_is_bad_request_and_asks_nothing(
        self,
        alice: User,
        provide: Callable[..., Scripted],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        scripted = provide(good())

        def _boom(*_args: Any, **_kwargs: Any) -> Any:
            raise RecursionError(MARKER)

        monkeypatch.setattr(JSONParser, "parse", _boom)

        response = signed_in(alice).call("POST", generate_url(), {"note": MARKER})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert MARKER not in response.content.decode()
        assert scripted.calls == []
        assert not WeeklyPlan.objects.exists()

    def test_rule_errors_are_part_of_the_answer_not_a_failure(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(bad(), bad())

        response = signed_in(alice).call("POST", generate_url())

        assert response.status_code == HTTPStatus.CREATED
        data = body(response)
        assert data["status"] == "draft"
        assert data["report"]["valid"] is False
        (finding,) = [f for f in data["report"]["findings"] if f["severity"] == "error"]
        assert set(finding) == {"severity", "code", "message", "path"}
        assert (finding["code"], finding["path"]) == ("day_over_capacity", "workouts[1]")

    @pytest.mark.parametrize(
        "week",
        [
            "2027-07-20",
            "2027-07-05",
            "2027-08-16",
            "2027-7-19",
            "2027-02-30",
            "20270719",
            "2027-W29-1",
            "x",
            "٢٠٢٧-٠٧-١٩",
        ],
    )
    def test_a_week_that_cannot_be_planned_is_not_found_and_nothing_is_asked(
        self, alice: User, provide: Callable[..., Scripted], week: str
    ) -> None:
        scripted = provide(good())

        response = signed_in(alice).call("POST", generate_url(week))

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response)["code"] == "week_not_plannable"
        assert scripted.calls == []
        assert not WeeklyPlan.objects.exists()

    def test_without_a_provider_it_is_a_conflict(self, bob: User) -> None:
        WeekdayMinutes.objects.create(owner=bob, weekday=0, minutes=60)

        response = signed_in(bob).call("POST", generate_url())

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response) == {"detail": "No AI provider is set up.", "code": "not_configured"}

    def test_a_week_without_time_is_a_conflict_of_its_own_and_nothing_is_asked(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())
        WeekdayMinutes.objects.filter(owner=alice).update(minutes=0)

        response = signed_in(alice).call("POST", generate_url())

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response) == {
            "detail": (
                "You have no training time for this week. Enter it on the Training time page."
            ),
            "code": "no_time",
        }
        assert scripted.calls == []
        assert not AIUsageRecord.objects.exists()
        assert not WeeklyPlan.objects.exists()

    def test_the_two_conflicts_are_told_apart(self, alice: User, bob: User) -> None:
        # alice has a provider but no time, bob has time but no provider
        WeekdayMinutes.objects.filter(owner=alice).update(minutes=0)
        WeekdayMinutes.objects.create(owner=bob, weekday=0, minutes=60)

        no_time = body(signed_in(alice).call("POST", generate_url()))["code"]
        no_provider = body(signed_in(bob).call("POST", generate_url()))["code"]

        assert (no_time, no_provider) == ("no_time", "not_configured")

    @pytest.mark.parametrize(
        ("error", "http_status", "code"),
        [
            (InvalidKeyError(MARKER), 502, "invalid_key"),
            (ProviderUnavailableError(MARKER), 503, "unavailable"),
            (UnexpectedResponseError(MARKER), 502, "unexpected"),
            (EndpointNotAllowedError(MARKER), 502, "not_allowed"),
        ],
    )
    def test_a_provider_problem_has_its_own_status_and_a_fixed_text(
        self,
        alice: User,
        provide: Callable[..., Scripted],
        error: Exception,
        http_status: int,
        code: str,
    ) -> None:
        provide(error)

        response = signed_in(alice).call("POST", generate_url())

        assert response.status_code == http_status
        assert body(response) == {"detail": PROBLEMS[code], "code": code}
        assert MARKER not in response.content.decode()
        assert not WeeklyPlan.objects.exists()

    def test_rate_limiting_says_how_long_to_wait(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(RateLimitedError(MARKER, 17))

        response = signed_in(alice).call("POST", generate_url())

        assert response.status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert response["Retry-After"] == "17"
        assert body(response) == {
            "detail": PROBLEMS["rate_limited"],
            "code": "rate_limited",
            "retry_after": 17,
        }

    def test_rate_limiting_without_a_time_sends_no_header(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(RateLimitedError(MARKER))

        response = signed_in(alice).call("POST", generate_url())

        assert response.status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert "Retry-After" not in response
        assert body(response)["retry_after"] is None

    def test_an_answer_that_cannot_be_used_is_unprocessable_and_says_only_what_was_wrong(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(f"{MARKER} no", f"{MARKER} still no")

        response = signed_in(alice).call("POST", generate_url())

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        data = body(response)
        assert (data["code"], data["detail"]) == (
            "not_usable",
            "The coach did not give a plan that can be used. Please try again.",
        )
        assert data["problems"][0]["path"] == ""
        assert "one JSON object" in data["problems"][0]["message"]
        assert MARKER not in response.content.decode()
        assert not WeeklyPlan.objects.exists()

    @pytest.mark.parametrize("path", ["", "workouts[0]"])
    def test_unknown_identifier_keys_never_leak_in_an_unusable_answer(
        self, alice: User, provide: Callable[..., Scripted], path: str
    ) -> None:
        data = json.loads(good())
        target = data["workouts"][0] if path else data
        target.update({MARKER: 1, "ANOTHER_UNKNOWN_KEY": 2})
        provide(json.dumps(data), json.dumps(data))

        response = signed_in(alice).call("POST", generate_url())

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert body(response)["code"] == "not_usable"
        assert body(response)["problems"] == [{"path": path, "message": "Unknown field."}]
        assert MARKER not in response.content.decode()
        assert "ANOTHER_UNKNOWN_KEY" not in response.content.decode()
        assert not WeeklyPlan.objects.exists()

    def test_the_sixth_request_within_a_minute_is_throttled_before_the_provider(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(*[good()] * 6)
        api = signed_in(alice)

        statuses = [api.call("POST", generate_url()).status_code for _ in range(6)]

        assert statuses == [HTTPStatus.CREATED] * 5 + [HTTPStatus.TOO_MANY_REQUESTS]
        assert len(scripted.calls) == 5

    def test_reading_and_deciding_are_not_throttled(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(*[good()] * 5)
        api = signed_in(alice)
        for _ in range(5):
            api.call("POST", generate_url())

        assert [api.call("GET", WEEKS).status_code for _ in range(8)] == [HTTPStatus.OK] * 8

    def test_another_users_week_and_setup_are_never_used(
        self, alice: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())
        draft(bob)

        signed_in(alice).call("POST", generate_url())

        assert scripted.calls
        assert WeeklyPlan.objects.filter(owner=alice).count() == 1
        assert WeeklyPlan.objects.filter(owner=bob).count() == 1


def edited(*workouts: Workout, monday: date = MONDAY, **lineages: str | None) -> dict[str, Any]:
    """A plan as the page sends it for a check; ``w0="…"`` gives the first workout a lineage."""
    data = to_json(WeekPlan(monday, workouts or (ride(0), ride(2), ride(4, 90)), "By hand"))
    for name, lineage in lineages.items():
        data["workouts"][int(name[1:])]["lineage"] = lineage
    return data


class TestChecking:
    def test_a_good_plan_has_no_findings_and_nothing_is_stored(self, alice: User) -> None:
        response = signed_in(alice).call("POST", check_url(), edited())

        assert response.status_code == HTTPStatus.OK
        assert body(response) == {"valid": True, "findings": [], "order": [0, 1, 2]}
        assert not WeeklyPlan.objects.exists()
        assert not PlannedWorkout.objects.exists()

    def test_the_findings_come_with_the_text_the_page_shows(self, alice: User) -> None:
        data = edited(ride(0), ride(1))  # Tuesday offers nothing

        response = signed_in(alice).call("POST", check_url(), data)

        assert response.status_code == HTTPStatus.OK
        answer = body(response)
        assert answer["valid"] is False
        (finding,) = [f for f in answer["findings"] if f["severity"] == "error"]
        assert set(finding) == {"severity", "code", "message", "path"}
        assert (finding["code"], finding["path"]) == ("day_over_capacity", "workouts[1]")

    def test_it_says_where_the_workouts_were_in_what_was_sent(self, alice: User) -> None:
        data = edited(ride(2), ride(0))

        assert body(signed_in(alice).call("POST", check_url(), data))["order"] == [1, 0]

    def test_a_lineage_is_accepted(self, alice: User) -> None:
        data = edited(w0=str(uuid4()), w1=None)

        assert signed_in(alice).call("POST", check_url(), data).status_code == HTTPStatus.OK

    def test_a_plan_that_cannot_be_read_is_unprocessable_with_fixed_texts(
        self, alice: User
    ) -> None:
        data = edited(w0=MARKER)
        data["workouts"][1]["duration_minutes"] = 0

        response = signed_in(alice).call("POST", check_url(), data)

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert body(response) == {
            "detail": "The plan cannot be read. Please check the problems.",
            "code": "invalid_plan",
            "problems": [
                {"path": "workouts[0].lineage", "message": "A lineage is an id or null."},
                {"path": "workouts[1].duration_minutes", "message": "Must be between 1 and 1440."},
            ],
        }
        assert MARKER not in response.content.decode()

    @pytest.mark.parametrize("path", ["", "workouts[0]"])
    def test_unknown_identifier_keys_never_leak_in_an_invalid_plan(
        self, alice: User, path: str
    ) -> None:
        data = edited()
        target = data["workouts"][0] if path else data
        target.update({MARKER: 1, "ANOTHER_UNKNOWN_KEY": 2})

        response = signed_in(alice).call("POST", check_url(), data)

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert body(response)["code"] == "invalid_plan"
        assert body(response)["problems"] == [{"path": path, "message": "Unknown field."}]
        assert MARKER not in response.content.decode()
        assert "ANOTHER_UNKNOWN_KEY" not in response.content.decode()

    def test_a_plan_for_another_week_is_unprocessable(self, alice: User) -> None:
        other = date(2027, 7, 26)

        response = signed_in(alice).call("POST", check_url(), edited(monday=other))

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert body(response)["problems"] == [
            {
                "path": "week_start",
                "message": "The plan must be for the week that starts on 2027-07-19.",
            }
        ]

    @pytest.mark.parametrize("payload", [None, {}, {"workouts": "x"}])
    def test_a_body_that_is_no_plan_is_unprocessable(self, alice: User, payload: Any) -> None:
        response = signed_in(alice).call("POST", check_url(), payload)

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert body(response)["code"] == "invalid_plan"

    def test_a_body_that_is_not_json_is_refused_as_such(self, alice: User) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            "POST",
            check_url(),
            data=b"{not json",
            content_type="application/json",
            headers={"X-CSRFToken": api._csrf_token()},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST

    @pytest.mark.parametrize(
        "week", ["2027-07-05", "2027-09-06", "2027-07-20", "2027-02-30", "nonsense", "20270719"]
    )
    def test_a_week_that_cannot_be_planned_is_a_404(self, alice: User, week: str) -> None:
        response = signed_in(alice).call("POST", check_url(week), edited())

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response) == {
            "detail": "This week cannot be planned.",
            "code": "week_not_plannable",
        }

    def test_nothing_of_the_request_is_repeated_in_an_error(self, alice: User) -> None:
        response = signed_in(alice).call("POST", check_url(MARKER), edited())

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert MARKER not in response.content.decode()

    def test_the_time_of_another_user_is_not_used(self, alice: User, bob: User) -> None:
        assert body(signed_in(alice).call("POST", check_url(), edited()))["valid"] is True
        assert body(signed_in(bob).call("POST", check_url(), edited()))["valid"] is False

    def test_no_provider_is_asked_and_nothing_is_recorded(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())

        signed_in(alice).call("POST", check_url(), edited())

        assert scripted.calls == []
        assert not AIUsageRecord.objects.exists()

    def test_it_is_not_limited_like_drafting(self, alice: User) -> None:
        api = signed_in(alice)

        statuses = [api.call("POST", check_url(), edited()).status_code for _ in range(8)]

        assert set(statuses) == {HTTPStatus.OK}

    def test_edited_segments_are_checked_and_isolated_by_user(self, alice: User, bob: User) -> None:
        valid_workout = Workout(
            day=MONDAY,
            sport=Sport.CYCLING,
            title="Threshold",
            goal=Goal.THRESHOLD,
            duration_minutes=52,
            segments=(
                Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 2),
                Segment(SegmentKind.WORK, 480, 4, ZoneSystem.POWER, 4),
                Segment(SegmentKind.COOLDOWN, 600, 1, ZoneSystem.POWER, 1),
            ),
        )
        data = edited(valid_workout, ride(2, 90), ride(4, 90))
        alice_resp = signed_in(alice).call("POST", check_url(), data)
        bob_resp = signed_in(bob).call("POST", check_url(), data)

        assert alice_resp.status_code == HTTPStatus.OK
        assert body(alice_resp) == {"valid": True, "findings": [], "order": [0, 1, 2]}
        assert bob_resp.status_code == HTTPStatus.OK
        assert body(bob_resp)["valid"] is False

    def test_segments_mismatch_is_reported_by_check(self, alice: User) -> None:
        mismatched = Workout(
            day=MONDAY,
            sport=Sport.CYCLING,
            title="Threshold",
            goal=Goal.THRESHOLD,
            duration_minutes=60,
            segments=(
                Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 2),
                Segment(SegmentKind.WORK, 480, 4, ZoneSystem.POWER, 4),
            ),
        )

        response = signed_in(alice).call("POST", check_url(), edited(mismatched))

        assert response.status_code == HTTPStatus.OK
        answer = body(response)
        assert answer["valid"] is False
        assert any(
            f["code"] == "segments_mismatch" and f["path"] == "workouts[0].segments"
            for f in answer["findings"]
        )


def stored_body(plan: WeeklyPlan) -> dict[str, Any]:
    """What the page sends back for a stored plan: its workouts, each with its lineage."""
    rows = PlannedWorkout.objects.filter(plan=plan).order_by("day", "position", "id")
    data = to_json(services.load(plan.owner, plan.pk))
    for item, row in zip(data["workouts"], rows, strict=True):
        item["lineage"] = str(row.lineage)
    return data


class TestRevising:
    def confirmed(self, user: User) -> WeeklyPlan:
        return services.confirm(user, draft(user, ride(0), ride(2), ride(4, 90)).pk)

    def test_a_change_is_a_new_draft_with_its_checks(self, alice: User) -> None:
        old = self.confirmed(alice)
        data = stored_body(old)
        data["workouts"][1]["title"] = "Changed"

        response = signed_in(alice).call("POST", plan_url(old.pk, "revise/"), data)

        assert response.status_code == HTTPStatus.CREATED
        answer = body(response)
        assert set(answer) == PLAN_FIELDS
        assert (answer["status"], answer["version"], answer["parent"]) == (
            "draft",
            2,
            str(old.pk),
        )
        assert answer["reason"] == "Changed by hand"
        assert answer["report"] == {"valid": True, "findings": []}
        assert answer["workouts"][1]["title"] == "Changed"
        assert [w["lineage"] for w in answer["workouts"]] == [
            w["lineage"] for w in data["workouts"]
        ]
        assert WeeklyPlan.objects.get(pk=old.pk).status == "confirmed"

    def test_the_exercises_of_a_strength_workout_survive_a_change_and_are_in_the_answer(
        self, alice: User
    ) -> None:
        squat = Exercise(
            "Goblet squat",
            ExerciseRegion.LEGS,
            ExerciseEquipment.DUMBBELLS,
            3,
            reps=10,
            rpe=7,
            rest_seconds=90,
        )
        lift = Workout(
            day=MONDAY,
            sport=Sport.STRENGTH,
            title="Strength",
            goal=Goal.STRENGTH,
            duration_minutes=45,
            exercises=(squat,),
        )
        old = services.confirm(alice, draft(alice, lift, ride(2), ride(4, 90)).pk)
        data = stored_body(old)
        data["workouts"][1]["title"] = "Changed"

        response = signed_in(alice).call("POST", plan_url(old.pk, "revise/"), data)

        assert response.status_code == HTTPStatus.CREATED
        shown = body(response)["workouts"][0]["exercises"]
        assert [(e["name"], e["sets"], e["reps"], e["rpe"]) for e in shown] == [
            ("Goblet squat", 3, 10, 7)
        ]
        read = signed_in(alice).call("GET", plan_url(body(response)["id"]))
        assert body(read)["workouts"][0]["exercises"] == shown

    def test_a_workout_that_was_moved_keeps_its_lineage_in_the_answer(self, alice: User) -> None:
        old = self.confirmed(alice)
        data = stored_body(old)
        data["workouts"][0]["day"] = (MONDAY + timedelta(days=5)).isoformat()  # Saturday

        answer = body(signed_in(alice).call("POST", plan_url(old.pk, "revise/"), data))

        moved = next(
            w for w in answer["workouts"] if w["lineage"] == data["workouts"][0]["lineage"]
        )
        assert moved["day"] == (MONDAY + timedelta(days=5)).isoformat()

    def test_a_plan_with_errors_is_stored_and_says_what_is_wrong(self, alice: User) -> None:
        old = self.confirmed(alice)
        data = stored_body(old)
        data["workouts"][0]["day"] = (MONDAY + timedelta(days=1)).isoformat()  # Tuesday: no time

        response = signed_in(alice).call("POST", plan_url(old.pk, "revise/"), data)

        assert response.status_code == HTTPStatus.CREATED
        answer = body(response)
        assert answer["report"]["valid"] is False
        assert WeeklyPlan.objects.filter(parent=old).count() == 1
        confirm = signed_in(alice).call("POST", plan_url(answer["id"], "confirm/"))
        assert confirm.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_confirming_the_change_replaces_the_version_it_started_from(self, alice: User) -> None:
        old = self.confirmed(alice)
        answer = body(signed_in(alice).call("POST", plan_url(old.pk, "revise/"), stored_body(old)))

        confirmed = signed_in(alice).call("POST", plan_url(answer["id"], "confirm/"))

        assert confirmed.status_code == HTTPStatus.OK
        assert WeeklyPlan.objects.get(pk=old.pk).status == "superseded"

    @pytest.mark.parametrize("offset", [-1, 7])
    def test_out_of_week_revision_is_a_handled_error(self, alice: User, offset: int) -> None:
        old = self.confirmed(alice)
        data = stored_body(old)
        data["workouts"][2]["day"] = (MONDAY + timedelta(days=offset)).isoformat()
        counts = (WeeklyPlan.objects.count(), PlannedWorkout.objects.count())

        response = signed_in(alice).call("POST", plan_url(old.pk, "revise/"), data)

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert body(response)["code"] == "invalid_plan"
        assert body(response)["problems"] == [
            {
                "path": "workouts[2].day",
                "message": "The workout does not lie within the week of the plan.",
            }
        ]
        assert (WeeklyPlan.objects.count(), PlannedWorkout.objects.count()) == counts

    def test_a_lineage_that_is_not_one_of_the_plan_is_unprocessable(self, alice: User) -> None:
        old = self.confirmed(alice)
        data = stored_body(old)
        data["workouts"][2]["lineage"] = str(uuid4())
        count = WeeklyPlan.objects.count()

        response = signed_in(alice).call("POST", plan_url(old.pk, "revise/"), data)

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert body(response) == {
            "detail": "The plan cannot be read. Please check the problems.",
            "code": "invalid_plan",
            "problems": [
                {
                    "path": "workouts[2].lineage",
                    "message": "This workout is not in the plan that is changed.",
                }
            ],
        }
        assert WeeklyPlan.objects.count() == count

    def test_a_plan_that_cannot_be_read_is_unprocessable(self, alice: User) -> None:
        old = self.confirmed(alice)
        data = stored_body(old)
        data["workouts"][0]["sport"] = MARKER

        response = signed_in(alice).call("POST", plan_url(old.pk, "revise/"), data)

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert MARKER not in response.content.decode()

    @pytest.mark.parametrize("payload", [None, {}, {"workouts": "x"}])
    def test_a_body_that_is_no_plan_is_unprocessable(self, alice: User, payload: Any) -> None:
        old = self.confirmed(alice)

        response = signed_in(alice).call("POST", plan_url(old.pk, "revise/"), payload)

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert body(response)["code"] == "invalid_plan"

    @pytest.mark.parametrize("status", ["superseded", "discarded"])
    def test_an_older_version_is_a_conflict(self, alice: User, status: str) -> None:
        plan = draft(alice)
        data = stored_body(plan)
        WeeklyPlan.objects.filter(pk=plan.pk).update(
            status=status, confirmed_at=NOW if status == "superseded" else None
        )

        response = signed_in(alice).call("POST", plan_url(plan.pk, "revise/"), data)

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response) == {
            "detail": (
                "Only a draft or a confirmed plan can be changed. Restore an older version first."
            ),
            "code": "not_revisable",
        }

    def test_a_week_that_can_no_longer_be_planned_is_a_404(self, alice: User) -> None:
        old = draft(alice, ride(0, monday=date(2027, 7, 5)), monday=date(2027, 7, 5))

        response = signed_in(alice).call("POST", plan_url(old.pk, "revise/"), stored_body(old))

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response)["code"] == "week_not_plannable"

    def test_the_plan_of_another_user_does_not_exist(self, alice: User, bob: User) -> None:
        theirs = draft(bob)
        data = stored_body(theirs)

        response = signed_in(alice).call("POST", plan_url(theirs.pk, "revise/"), data)

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response) == {"detail": "There is no such plan.", "code": "not_found"}
        assert WeeklyPlan.objects.filter(owner=bob).count() == 1

    def test_an_unknown_plan_is_a_404(self, alice: User) -> None:
        response = signed_in(alice).call("POST", plan_url(uuid4(), "revise/"), edited())

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_no_provider_is_asked(self, alice: User, provide: Callable[..., Scripted]) -> None:
        scripted = provide(good())
        old = self.confirmed(alice)

        signed_in(alice).call("POST", plan_url(old.pk, "revise/"), stored_body(old))

        assert scripted.calls == []
        assert not AIUsageRecord.objects.exists()

    def test_revising_segments_updates_targets_estimated_load_and_week_load(
        self, alice: User, bob: User
    ) -> None:
        interval_ride = Workout(
            day=MONDAY,
            sport=Sport.CYCLING,
            title="Threshold intervals",
            goal=Goal.THRESHOLD,
            duration_minutes=50,
            segments=(
                Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 2),
                Segment(SegmentKind.WORK, 600, 3, ZoneSystem.POWER, 4),
                Segment(SegmentKind.COOLDOWN, 600, 1, ZoneSystem.POWER, 1),
            ),
        )
        old = services.confirm(alice, draft(alice, interval_ride, ride(2, 90), ride(4, 90)).pk)
        old_data = body(signed_in(alice).call("GET", plan_url(old.pk)))
        old_workout_load = old_data["workouts"][0]["estimated_load"]
        old_week_load = old_data["load"]["total"]["planned_load"]

        data = stored_body(old)
        data["workouts"][0]["duration_minutes"] = 52
        data["workouts"][0]["segments"][1] = {
            "kind": "work",
            "seconds": 480,
            "repeat": 4,
            "zone_system": "power",
            "zone": 4,
        }

        # Another user cannot revise Alice's plan.
        bob_resp = signed_in(bob).call("POST", plan_url(old.pk, "revise/"), data)
        assert bob_resp.status_code == HTTPStatus.NOT_FOUND

        response = signed_in(alice).call("POST", plan_url(old.pk, "revise/"), data)

        assert response.status_code == HTTPStatus.CREATED
        answer = body(response)
        assert answer["report"] == {"valid": True, "findings": []}
        updated = answer["workouts"][0]
        assert updated["duration_minutes"] == 52
        assert updated["segments"][1] == {
            "kind": "work",
            "seconds": 480,
            "repeat": 4,
            "zone_system": "power",
            "zone": 4,
            "target": {"low": 225, "high": 263, "unit": "W"},
        }
        assert updated["estimated_load"] > old_workout_load
        assert answer["load"]["total"]["planned_minutes"] == 232
        assert answer["load"]["total"]["planned_load"] == (
            old_week_load - old_workout_load + updated["estimated_load"]
        )


class TestRestoring:
    def old_version(self, user: User, status: str = "superseded") -> WeeklyPlan:
        plan = draft(user, ride(0), ride(2), ride(4, 90))
        WeeklyPlan.objects.filter(pk=plan.pk).update(
            status=status, confirmed_at=NOW if status == "superseded" else None
        )
        plan.refresh_from_db()
        return plan

    @pytest.mark.parametrize("status", ["superseded", "discarded"])
    def test_an_older_version_comes_back_as_a_draft_with_its_checks(
        self, alice: User, status: str
    ) -> None:
        old = self.old_version(alice, status)

        response = signed_in(alice).call("POST", plan_url(old.pk, "restore/"))

        assert response.status_code == HTTPStatus.CREATED
        answer = body(response)
        assert set(answer) == PLAN_FIELDS
        assert (answer["status"], answer["version"], answer["parent"]) == (
            "draft",
            2,
            str(old.pk),
        )
        assert answer["reason"] == "Restored from version 1"
        assert answer["report"] == {"valid": True, "findings": []}
        assert [w["lineage"] for w in answer["workouts"]] == [
            str(w.lineage) for w in PlannedWorkout.objects.filter(plan=old).order_by("day")
        ]
        assert WeeklyPlan.objects.get(pk=old.pk).status == status

    def test_the_checks_are_those_of_today(self, alice: User) -> None:
        old = self.old_version(alice)
        WeekdayMinutes.objects.filter(owner=alice, weekday=0).update(minutes=0)

        answer = body(signed_in(alice).call("POST", plan_url(old.pk, "restore/")))

        assert answer["report"]["valid"] is False

    @pytest.mark.parametrize("status", ["draft", "confirmed"])
    def test_a_draft_and_a_confirmed_plan_are_a_conflict(self, alice: User, status: str) -> None:
        plan = draft(alice)
        if status == "confirmed":
            plan = services.confirm(alice, plan.pk)

        response = signed_in(alice).call("POST", plan_url(plan.pk, "restore/"))

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response) == {
            "detail": "Only a version that was replaced or discarded can be restored.",
            "code": "not_restorable",
        }
        assert WeeklyPlan.objects.count() == 1

    def test_a_week_that_can_no_longer_be_planned_is_a_404(self, alice: User) -> None:
        past = date(2027, 7, 5)
        plan = draft(alice, ride(0, monday=past), monday=past)
        WeeklyPlan.objects.filter(pk=plan.pk).update(status="discarded")

        response = signed_in(alice).call("POST", plan_url(plan.pk, "restore/"))

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response)["code"] == "week_not_plannable"

    def test_the_plan_of_another_user_does_not_exist(self, alice: User, bob: User) -> None:
        theirs = self.old_version(bob, "discarded")

        response = signed_in(alice).call("POST", plan_url(theirs.pk, "restore/"))

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response) == {"detail": "There is no such plan.", "code": "not_found"}
        assert WeeklyPlan.objects.filter(owner=bob).count() == 1

    def test_no_provider_is_asked(self, alice: User, provide: Callable[..., Scripted]) -> None:
        scripted = provide(good())
        old = self.old_version(alice)

        signed_in(alice).call("POST", plan_url(old.pk, "restore/"))

        assert scripted.calls == []
        assert not AIUsageRecord.objects.exists()


class TestPlanLoad:
    @pytest.mark.parametrize(
        "action", ["get", "generate", "revise", "restore", "confirm", "push", "discard"]
    )
    def test_every_detail_response_has_workout_estimates_and_week_totals(
        self, alice: User, provide: Callable[..., Scripted], calendar: Calendar, action: str
    ) -> None:
        provide(good())
        plan = draft(alice)
        Activity.objects.create(
            owner=alice,
            source="manual",
            sport="cycling",
            start_time=datetime(2027, 7, 20, 12, tzinfo=UTC),
            timer_seconds=1800,
            rpe=5,
        )
        api = signed_in(alice)
        if action == "get":
            response = api.call("GET", plan_url(plan.pk))
        elif action == "generate":
            response = api.call("POST", generate_url())
        elif action == "revise":
            response = api.call("POST", plan_url(plan.pk, "revise/"), stored_body(plan))
        else:
            if action == "restore":
                services.discard(alice, plan.pk)
            elif action == "push":
                services.confirm(alice, plan.pk)
                connect_intervals(alice)
            response = api.call("POST", plan_url(plan.pk, f"{action}/"))

        assert response.status_code in (HTTPStatus.OK, HTTPStatus.CREATED)
        data = body(response)
        assert [w["estimated_load"] for w in data["workouts"]] == [50, 50]
        assert all(type(w["estimated_load"]) is int for w in data["workouts"])
        assert data["load"] == {
            "sports": [
                {
                    "sport": "cycling",
                    "planned_minutes": 120,
                    "done_minutes": 30,
                    "planned_load": 100,
                    "done_load": 25,
                }
            ],
            "total": {
                "planned_minutes": 120,
                "done_minutes": 30,
                "planned_load": 100,
                "done_load": 25,
            },
        }

    def test_done_totals_use_the_users_local_week_and_never_another_users_activities(
        self, alice: User, bob: User
    ) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="Europe/Berlin")
        plan = draft(alice)
        # Berlin's week begins Sunday at 22:00 UTC in July. Both bounds matter.
        cases: list[tuple[User, datetime, str, dict[str, Any]]] = [
            (
                alice,
                datetime(2027, 7, 18, 22, tzinfo=UTC),
                "running",
                {"elapsed_seconds": 1800, "rpe": 7},
            ),
            (
                alice,
                datetime(2027, 7, 25, 21, 59, 59, tzinfo=UTC),
                "other",
                {"timer_seconds": 3600, "training_load": 80.5},
            ),
            (
                alice,
                datetime(2027, 7, 18, 21, 59, 59, tzinfo=UTC),
                "cycling",
                {"timer_seconds": 3600, "rpe": 10},
            ),
            (
                alice,
                datetime(2027, 7, 25, 22, tzinfo=UTC),
                "cycling",
                {"timer_seconds": 3600, "rpe": 10},
            ),
            (
                bob,
                datetime(2027, 7, 20, 12, tzinfo=UTC),
                "swimming",
                {"timer_seconds": 3600, "training_load": 9999},
            ),
        ]
        for owner, start, sport, values in cases:
            Activity.objects.create(
                owner=owner, source="manual", sport=sport, start_time=start, **values
            )

        data = body(signed_in(alice).call("GET", plan_url(plan.pk)))

        assert data["load"] == {
            "sports": [
                {
                    "sport": "running",
                    "planned_minutes": 0,
                    "done_minutes": 30,
                    "planned_load": 0,
                    "done_load": 35,
                },
                {
                    "sport": "cycling",
                    "planned_minutes": 120,
                    "done_minutes": 0,
                    "planned_load": 100,
                    "done_load": 0,
                },
                {
                    "sport": "other",
                    "planned_minutes": 0,
                    "done_minutes": 60,
                    "planned_load": 0,
                    "done_load": 81,
                },
            ],
            "total": {
                "planned_minutes": 120,
                "done_minutes": 90,
                "planned_load": 100,
                "done_load": 116,
            },
        }

    def test_queries_do_not_grow_with_the_number_of_workouts_or_activities(
        self, alice: User
    ) -> None:
        small = services.discard(alice, draft(alice, ride(0)).pk)
        large = services.discard(alice, draft(alice, *(ride(d, 30) for d in range(7))).pk)
        api = signed_in(alice)
        with CaptureQueriesContext(connection) as before:
            first = api.call("GET", plan_url(small.pk))
        for day in range(7):
            Activity.objects.create(
                owner=alice,
                source="manual",
                sport="running",
                start_time=datetime(2027, 7, 19 + day, 12, tzinfo=UTC),
                timer_seconds=3600,
                rpe=5,
            )
        with CaptureQueriesContext(connection) as after:
            second = api.call("GET", plan_url(large.pk))

        assert first.status_code == second.status_code == HTTPStatus.OK
        assert body(first)["load"]["total"]["done_load"] == 0
        assert body(second)["load"]["total"]["done_load"] == 350
        assert len(after) == len(before)
        assert sum('FROM "activities_activity"' in q["sql"] for q in after) == 1

    @pytest.mark.parametrize("field", ["estimated_load", "load"])
    def test_computed_fields_are_not_accepted_in_the_edit_schema(
        self, alice: User, field: str
    ) -> None:
        data = edited(ride(0))
        target = data["workouts"][0] if field == "estimated_load" else data
        target[field] = 9999

        response = signed_in(alice).call("POST", check_url(), data)

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert body(response)["code"] == "invalid_plan"


class TestReadingAPlan:
    def test_a_draft_comes_with_its_report(self, alice: User) -> None:
        plan = draft(alice, ride(2), ride(1), ride(0))  # Tuesday offers nothing

        response = signed_in(alice).call("GET", plan_url(plan.pk))

        assert response.status_code == HTTPStatus.OK
        data = body(response)
        assert set(data) == PLAN_FIELDS
        assert data["id"] == str(plan.pk)
        assert data["reason"] == "by hand"
        assert [w["day"] for w in data["workouts"]] == ["2027-07-19", "2027-07-20", "2027-07-21"]
        assert data["report"]["valid"] is False
        assert data["report"]["findings"][0]["path"] == "workouts[1]"

    def test_time_of_day_and_stretching_are_part_of_every_workout(self, alice: User) -> None:
        plan = services.save_draft(
            alice,
            WeekPlan(
                MONDAY,
                (
                    ride(0).__class__(
                        day=MONDAY,
                        sport=Sport.RUNNING,
                        title="Easy run",
                        goal=Goal.ENDURANCE,
                        duration_minutes=50,
                        slot=Slot.MORNING,
                        stretching_minutes=10,
                    ),
                    ride(0),
                ),
            ),
        )

        data = body(signed_in(alice).call("GET", plan_url(plan.pk)))

        assert [(w["title"], w["slot"], w["stretching_minutes"]) for w in data["workouts"]] == [
            ("Easy run", "morning", 10),
            ("Endurance ride", None, 0),
        ]

    def test_zones_come_with_their_target_ranges(self, alice: User) -> None:
        ThresholdValue.objects.create(
            owner=alice, sport="run", metric="lthr", value=170, source="manual", basis="test"
        )
        interval = Workout(
            day=MONDAY,
            sport=Sport.RUNNING,
            title="Intervals",
            goal=Goal.VO2MAX,
            duration_minutes=50,
            segments=(
                Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.HEART_RATE, 1),
                Segment(SegmentKind.WORK, 300, 4, ZoneSystem.HEART_RATE, 5),
                Segment(SegmentKind.COOLDOWN, 600),
            ),
        )
        plan = draft(alice, ride(2), interval)

        data = body(signed_in(alice).call("GET", plan_url(plan.pk)))

        run, cycling = data["workouts"]
        assert cycling["target"] == {"low": 138, "high": 188, "unit": "W"}
        assert run["target"] is None  # no zone for the whole session
        assert [segment["target"] for segment in run["segments"]] == [
            {"low": 111, "high": 145, "unit": "bpm"},
            {"low": 170, "high": 179, "unit": "bpm"},
            None,
        ]

    def test_a_zone_without_a_threshold_has_no_target(self, alice: User) -> None:
        ThresholdValue.objects.filter(owner=alice).delete()
        plan = draft(alice, ride(0))

        data = body(signed_in(alice).call("GET", plan_url(plan.pk)))

        assert data["workouts"][0]["zone"] == 2
        assert data["workouts"][0]["target"] is None

    def test_a_confirmed_plan_has_no_report(self, alice: User) -> None:
        plan = services.confirm(alice, draft(alice).pk)

        data = body(signed_in(alice).call("GET", plan_url(plan.pk)))

        assert (data["status"], data["report"]) == ("confirmed", None)
        assert data["confirmed_at"] is not None

    def test_a_new_version_names_the_one_it_replaces(self, alice: User) -> None:
        first = draft(alice)
        second = services.save_draft(
            alice, services.load(alice, first.pk), reason="by hand", parent=first.pk
        )

        data = body(signed_in(alice).call("GET", plan_url(second.pk)))

        assert data["parent"] == str(first.pk)

    def test_the_text_of_the_plan_is_returned_as_stored(self, alice: User) -> None:
        workout = Workout(
            day=MONDAY,
            sport=Sport.CYCLING,
            title='<b>"quoted"</b>',
            goal=Goal.ENDURANCE,
            duration_minutes=60,
            notes="Line one",
        )
        plan = draft(alice, workout)

        (shown,) = body(signed_in(alice).call("GET", plan_url(plan.pk)))["workouts"]

        assert (shown["title"], shown["notes"]) == ('<b>"quoted"</b>', "Line one")

    def test_another_users_plan_does_not_exist(self, alice: User, bob: User) -> None:
        plan = draft(bob)
        api = signed_in(alice)

        foreign = api.call("GET", plan_url(plan.pk))
        unknown = api.call("GET", plan_url(uuid4()))

        assert foreign.status_code == unknown.status_code == HTTPStatus.NOT_FOUND
        assert (
            body(foreign)
            == body(unknown)
            == {"detail": "There is no such plan.", "code": "not_found"}
        )

    def test_an_id_that_is_no_uuid_is_not_found(self, alice: User) -> None:
        assert signed_in(alice).call("GET", "/api/planning/plans/12/").status_code == 404


class TestConfirming:
    def test_a_good_draft_is_confirmed_and_replaces_the_one_before(self, alice: User) -> None:
        old = services.confirm(alice, draft(alice).pk)
        new = draft(alice)

        response = signed_in(alice).call("POST", plan_url(new.pk, "confirm/"))

        assert response.status_code == HTTPStatus.OK
        data = body(response)
        assert (data["status"], data["report"]) == ("confirmed", None)
        assert data["confirmed_at"] is not None
        old.refresh_from_db()
        assert old.status == Status.SUPERSEDED

    def test_a_draft_with_errors_is_refused_with_the_findings(self, alice: User) -> None:
        plan = draft(alice, ride(0), ride(1))

        response = signed_in(alice).call("POST", plan_url(plan.pk, "confirm/"))

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        data = body(response)
        assert (data["code"], data["detail"]) == (
            "not_confirmable",
            "The plan has errors and cannot be confirmed.",
        )
        assert [f["code"] for f in data["findings"] if f["severity"] == "error"] == [
            "day_over_capacity"
        ]
        plan.refresh_from_db()
        assert plan.status == Status.DRAFT

    @pytest.mark.parametrize("decided", ["confirm", "discard"])
    def test_only_a_draft_can_be_confirmed(self, alice: User, decided: str) -> None:
        plan = draft(alice)
        getattr(services, decided)(alice, plan.pk)

        response = signed_in(alice).call("POST", plan_url(plan.pk, "confirm/"))

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response)["code"] == "not_a_draft"

    def test_another_users_plan_cannot_be_confirmed(self, alice: User, bob: User) -> None:
        plan = draft(bob)

        response = signed_in(alice).call("POST", plan_url(plan.pk, "confirm/"))

        assert response.status_code == HTTPStatus.NOT_FOUND
        plan.refresh_from_db()
        assert plan.status == Status.DRAFT


class TestTheIntensityLevel:
    """The rules use the limits of the user's level: three hard days are too many for "normal"."""

    @staticmethod
    def three_hard_days() -> tuple[Workout, ...]:
        return tuple(dataclasses.replace(ride(d), goal=Goal.THRESHOLD) for d in (0, 2, 4))

    def test_normal_refuses_to_confirm_three_hard_days(self, alice: User) -> None:
        plan = draft(alice, *self.three_hard_days())

        response = signed_in(alice).call("POST", plan_url(plan.pk, "confirm/"))

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert [f["code"] for f in body(response)["findings"] if f["severity"] == "error"] == [
            "too_many_hard_days"
        ]

    def test_intensive_confirms_them(self, alice: User) -> None:
        plan = draft(alice, *self.three_hard_days())
        AvailabilitySettings.objects.create(owner=alice, intensity_level="intensive")

        response = signed_in(alice).call("POST", plan_url(plan.pk, "confirm/"))

        assert response.status_code == HTTPStatus.OK
        assert body(response)["status"] == "confirmed"

    def test_an_own_number_of_hard_days_counts_too(self, alice: User) -> None:
        plan = draft(alice, *self.three_hard_days())
        AvailabilitySettings.objects.create(owner=alice, intensity_level="relaxed", max_hard_days=3)

        assert signed_in(alice).call("POST", plan_url(plan.pk, "confirm/")).status_code == (
            HTTPStatus.OK
        )

    def test_the_check_of_the_editor_uses_the_level_of_the_user(
        self, alice: User, bob: User
    ) -> None:
        data = edited(*self.three_hard_days())
        AvailabilitySettings.objects.create(owner=bob, intensity_level="intensive")

        def errors() -> list[str]:
            answer = body(signed_in(alice).call("POST", check_url(), data))
            return [f["code"] for f in answer["findings"] if f["severity"] == "error"]

        assert errors() == ["too_many_hard_days"]
        AvailabilitySettings.objects.create(owner=alice, intensity_level="intensive")
        assert errors() == []


class TestDiscarding:
    def test_a_draft_is_discarded(self, alice: User) -> None:
        plan = draft(alice)

        response = signed_in(alice).call("POST", plan_url(plan.pk, "discard/"))

        assert response.status_code == HTTPStatus.OK
        data = body(response)
        assert (data["status"], data["report"]) == ("discarded", None)
        plan.refresh_from_db()
        assert plan.status == Status.DISCARDED

    @pytest.mark.parametrize("decided", ["confirm", "discard"])
    def test_only_a_draft_can_be_discarded(self, alice: User, decided: str) -> None:
        plan = draft(alice)
        getattr(services, decided)(alice, plan.pk)
        before = WeeklyPlan.objects.get(pk=plan.pk).status

        response = signed_in(alice).call("POST", plan_url(plan.pk, "discard/"))

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response)["code"] == "not_a_draft"
        assert WeeklyPlan.objects.get(pk=plan.pk).status == before

    def test_another_users_plan_cannot_be_discarded(self, alice: User, bob: User) -> None:
        plan = draft(bob)

        response = signed_in(alice).call("POST", plan_url(plan.pk, "discard/"))

        assert response.status_code == HTTPStatus.NOT_FOUND
        plan.refresh_from_db()
        assert plan.status == Status.DRAFT


def connect_intervals(user: User) -> None:
    ProviderConnection.objects.create(
        owner=user, provider="intervals_icu", api_key="k3y-0123456789", athlete_id="i100"
    )


def sent(user: User, *workouts: Workout) -> WeeklyPlan:
    """A confirmed plan, ready to be sent."""
    return services.confirm(user, draft(user, *workouts).pk)


class TestSendingAPlan:
    def test_a_confirmed_plan_is_sent_and_the_answer_says_how_it_went(
        self, alice: User, calendar: Calendar
    ) -> None:
        connect_intervals(alice)
        plan = sent(alice)

        response = signed_in(alice).call("POST", plan_url(plan.pk, "push/"))

        assert response.status_code == HTTPStatus.OK
        data = body(response)
        assert set(data) == PLAN_FIELDS | {"push"}
        assert data["push"] == {
            "ok": True,
            "synced": 2,
            "failed": 0,
            "removed": 0,
            "left_behind": 0,
        }
        assert [w["export"]["status"] for w in data["workouts"]] == ["synced", "synced"]
        assert [w["export"]["error_code"] for w in data["workouts"]] == ["", ""]
        assert all(w["export"]["pushed_at"] for w in data["workouts"])
        assert data["export"] == {"synced": 2, "failed": 0, "not_sent": 0, "older": 0}
        assert len(calendar.events) == 2

    def test_reading_the_plan_afterwards_shows_the_same_state_without_a_push_result(
        self, alice: User, calendar: Calendar
    ) -> None:
        connect_intervals(alice)
        plan = sent(alice)
        api = signed_in(alice)
        api.call("POST", plan_url(plan.pk, "push/"))

        data = body(api.call("GET", plan_url(plan.pk)))

        assert "push" not in data
        assert data["export"] == {"synced": 2, "failed": 0, "not_sent": 0, "older": 0}

    def test_before_the_first_push_every_workout_is_not_sent(
        self, alice: User, calendar: Calendar
    ) -> None:
        plan = sent(alice)

        data = body(signed_in(alice).call("GET", plan_url(plan.pk)))

        assert [w["export"]["status"] for w in data["workouts"]] == ["not_sent", "not_sent"]
        assert data["export"] == {"synced": 0, "failed": 0, "not_sent": 2, "older": 0}
        assert calendar.calls == []

    def test_a_plan_that_is_not_confirmed_has_no_export(self, alice: User) -> None:
        plan = draft(alice)

        data = body(signed_in(alice).call("GET", plan_url(plan.pk)))

        assert data["export"] is None
        assert [w["export"] for w in data["workouts"]] == [None, None]

    def test_a_workout_that_fails_is_told_by_a_code_and_the_others_arrive(
        self, alice: User, calendar: Calendar
    ) -> None:
        connect_intervals(alice)
        calendar.upsert_failures = [RejectedError("SECRETMARKER"), None]
        plan = sent(alice)

        response = signed_in(alice).call("POST", plan_url(plan.pk, "push/"))

        assert response.status_code == HTTPStatus.OK
        data = body(response)
        assert data["push"]["failed"] == 1
        assert [w["export"]["status"] for w in data["workouts"]] == ["failed", "synced"]
        assert data["workouts"][0]["export"]["error_code"] == "rejected"
        assert data["export"] == {"synced": 1, "failed": 1, "not_sent": 0, "older": 0}
        assert "SECRETMARKER" not in response.content.decode()

    def test_a_new_version_shows_the_events_of_the_old_one_until_it_is_sent(
        self, alice: User, calendar: Calendar
    ) -> None:
        connect_intervals(alice)
        old = sent(alice)
        api = signed_in(alice)
        api.call("POST", plan_url(old.pk, "push/"))
        newer = services.confirm(
            alice, services.save_draft(alice, WeekPlan(MONDAY, (ride(0),)), parent=old.pk).pk
        )

        before = body(api.call("GET", plan_url(newer.pk)))
        after = body(api.call("POST", plan_url(newer.pk, "push/")))

        assert before["export"] == {"synced": 0, "failed": 0, "not_sent": 1, "older": 2}
        assert after["push"] == {
            "ok": True,
            "synced": 1,
            "failed": 0,
            "removed": 2,
            "left_behind": 0,
        }
        assert after["export"] == {"synced": 1, "failed": 0, "not_sent": 0, "older": 0}

    @pytest.mark.parametrize("decided", ["draft", "discarded", "superseded"])
    def test_only_a_confirmed_plan_can_be_sent(
        self, alice: User, calendar: Calendar, decided: str
    ) -> None:
        connect_intervals(alice)
        plan = draft(alice)
        if decided == "discarded":
            services.discard(alice, plan.pk)
        if decided == "superseded":
            services.confirm(alice, plan.pk)
            services.confirm(
                alice, services.save_draft(alice, WeekPlan(MONDAY, (ride(0),)), parent=plan.pk).pk
            )

        response = signed_in(alice).call("POST", plan_url(plan.pk, "push/"))

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response) == {
            "detail": "Only a confirmed plan can be sent to Intervals.icu.",
            "code": "not_confirmed",
        }
        assert calendar.calls == []

    def test_without_intervals_connected_it_is_a_conflict(
        self, alice: User, calendar: Calendar
    ) -> None:
        plan = sent(alice)

        response = signed_in(alice).call("POST", plan_url(plan.pk, "push/"))

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response)["code"] == "not_connected"
        assert calendar.calls == []

    def test_a_key_that_is_refused_is_a_bad_gateway_and_marks_the_connection(
        self, alice: User, calendar: Calendar
    ) -> None:
        connect_intervals(alice)
        calendar.upsert_failures = [IntervalsKeyError("SECRETMARKER")]
        plan = sent(alice)

        response = signed_in(alice).call("POST", plan_url(plan.pk, "push/"))

        assert response.status_code == HTTPStatus.BAD_GATEWAY
        assert body(response) == {
            "detail": "Intervals.icu did not accept the stored API key. Connect it again.",
            "code": "invalid_key",
        }
        assert ProviderConnection.objects.get().status == "invalid"

    def test_another_users_plan_does_not_exist(
        self, alice: User, bob: User, calendar: Calendar
    ) -> None:
        connect_intervals(alice)
        for weekday, minutes in enumerate([90, 0, 90, 0, 120, 120, 0]):
            WeekdayMinutes.objects.create(owner=bob, weekday=weekday, minutes=minutes)
        ThresholdValue.objects.create(
            owner=bob, sport="ride", metric="ftp", value=250, source="manual", basis="test"
        )
        plan = sent(bob)

        response = signed_in(alice).call("POST", plan_url(plan.pk, "push/"))

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response)["code"] == "not_found"
        assert calendar.calls == []

    def test_the_eleventh_push_within_a_minute_is_throttled(
        self, alice: User, calendar: Calendar
    ) -> None:
        connect_intervals(alice)
        plan = sent(alice)
        api = signed_in(alice)

        statuses = [api.call("POST", plan_url(plan.pk, "push/")).status_code for _ in range(11)]

        assert statuses == [HTTPStatus.OK] * 10 + [HTTPStatus.TOO_MANY_REQUESTS]


class TestConfirmingAndSending:
    def test_confirming_without_the_wish_sends_nothing(
        self, alice: User, calendar: Calendar
    ) -> None:
        connect_intervals(alice)
        plan = draft(alice)

        data = body(signed_in(alice).call("POST", plan_url(plan.pk, "confirm/")))

        assert "push" not in data
        assert calendar.calls == []

    @pytest.mark.parametrize("wish", [{}, {"push": False}])
    def test_no_wish_for_a_push_sends_nothing(
        self, alice: User, calendar: Calendar, wish: dict[str, Any]
    ) -> None:
        connect_intervals(alice)
        plan = draft(alice)

        response = signed_in(alice).call("POST", plan_url(plan.pk, "confirm/"), wish)

        assert body(response)["status"] == "confirmed"
        assert calendar.calls == []

    def test_confirming_with_the_wish_sends_the_week(self, alice: User, calendar: Calendar) -> None:
        connect_intervals(alice)
        plan = draft(alice)

        response = signed_in(alice).call("POST", plan_url(plan.pk, "confirm/"), {"push": True})

        assert response.status_code == HTTPStatus.OK
        data = body(response)
        assert data["status"] == "confirmed"
        assert data["push"]["ok"] is True
        assert data["export"]["synced"] == 2
        assert len(calendar.events) == 2

    def test_a_plan_with_errors_is_not_confirmed_and_not_sent(
        self, alice: User, calendar: Calendar
    ) -> None:
        connect_intervals(alice)
        plan = draft(alice, ride(0), ride(1))

        response = signed_in(alice).call("POST", plan_url(plan.pk, "confirm/"), {"push": True})

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert calendar.calls == []

    def test_a_problem_with_intervals_does_not_undo_the_confirmation(
        self, alice: User, calendar: Calendar
    ) -> None:
        plan = draft(alice)  # Intervals.icu is not connected

        response = signed_in(alice).call("POST", plan_url(plan.pk, "confirm/"), {"push": True})

        assert response.status_code == HTTPStatus.OK
        data = body(response)
        assert data["status"] == "confirmed"
        assert data["push"] == {
            "ok": False,
            "problem": "not_connected",
            "message": "Intervals.icu is not connected. Connect it on the Connections page.",
        }
        plan.refresh_from_db()
        assert plan.status == Status.CONFIRMED

    def test_a_refused_key_is_part_of_the_answer_too(self, alice: User, calendar: Calendar) -> None:
        connect_intervals(alice)
        calendar.upsert_failures = [IntervalsKeyError("no")]
        plan = draft(alice)

        data = body(signed_in(alice).call("POST", plan_url(plan.pk, "confirm/"), {"push": True}))

        assert data["status"] == "confirmed"
        assert data["push"]["problem"] == "invalid_key"

    @pytest.mark.parametrize("wish", [{"push": "maybe"}, {"push": 5}, {"push": []}])
    def test_a_wish_that_is_not_a_boolean_is_refused_and_nothing_changes(
        self, alice: User, calendar: Calendar, wish: dict[str, Any]
    ) -> None:
        connect_intervals(alice)
        plan = draft(alice)

        response = signed_in(alice).call("POST", plan_url(plan.pk, "confirm/"), wish)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        plan.refresh_from_db()
        assert plan.status == Status.DRAFT
        assert calendar.calls == []

    @pytest.mark.parametrize(
        "wish",
        [{"push": True}, {"push": "true"}, {"push": 1}, {"push": "1"}],
    )
    def test_every_push_representation_shares_the_push_throttle_with_push(
        self, alice: User, calendar: Calendar, wish: dict[str, Any]
    ) -> None:
        connect_intervals(alice)
        confirmed = draft(alice)
        target = draft(alice)
        api = signed_in(alice)

        first = api.call("POST", plan_url(confirmed.pk, "confirm/"), wish)
        assert first.status_code == HTTPStatus.OK
        for _ in range(9):
            assert api.call("POST", plan_url(confirmed.pk, "push/")).status_code == HTTPStatus.OK

        calendar.calls.clear()
        throttled = api.call("POST", plan_url(target.pk, "confirm/"), wish)

        assert throttled.status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert calendar.calls == []
        target.refresh_from_db()
        assert target.status == Status.DRAFT

    def test_querydict_push_payload_triggers_push_throttle(self, alice: User) -> None:
        django_request = APIRequestFactory().post(
            plan_url(UNKNOWN_ID, "confirm/"),
            data=QueryDict("push=true").urlencode(),
            content_type="application/x-www-form-urlencoded",
        )
        django_request.user = alice
        view = ConfirmView()
        view.request = Request(django_request, parsers=[FormParser()])

        throttles = view.get_throttles()

        assert isinstance(view.request.data, QueryDict)
        assert len(throttles) == 1
        assert isinstance(throttles[0], PlanPushThrottle)

    def test_non_push_and_invalid_confirm_bodies_do_not_consume_push_limit(
        self, alice: User, calendar: Calendar
    ) -> None:
        connect_intervals(alice)
        api = signed_in(alice)

        for non_push in (None, {}, {"push": False}, {"push": "false"}, {"push": 0}):
            response = api.call("POST", plan_url(draft(alice).pk, "confirm/"), non_push)
            assert response.status_code == HTTPStatus.OK

        invalid_bodies: tuple[dict[str, Any], ...] = ({"push": "maybe"}, {"push": 5}, {"push": []})
        for invalid in invalid_bodies:
            response = api.call("POST", plan_url(draft(alice).pk, "confirm/"), invalid)
            assert response.status_code == HTTPStatus.BAD_REQUEST

        assert calendar.calls == []
        confirmed = sent(alice)
        for _ in range(10):
            assert api.call("POST", plan_url(confirmed.pk, "push/")).status_code == HTTPStatus.OK

        after_limit = api.call("POST", plan_url(draft(alice).pk, "confirm/"), {"push": False})
        assert after_limit.status_code == HTTPStatus.OK
        assert (
            api.call("POST", plan_url(confirmed.pk, "push/")).status_code
            == HTTPStatus.TOO_MANY_REQUESTS
        )

    def test_deeply_nested_body_is_bad_request_and_changes_nothing(
        self, alice: User, calendar: Calendar
    ) -> None:
        connect_intervals(alice)
        plan = draft(alice)
        api = signed_in(alice)
        deep = "[" * 1500 + f'"{MARKER}"' + "]" * 1500

        response = api.client.post(
            plan_url(plan.pk, "confirm/"),
            data=deep,
            content_type="application/json",
            headers={"X-CSRFToken": api._csrf_token()},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert MARKER not in response.content.decode()
        plan.refresh_from_db()
        assert plan.status == Status.DRAFT
        assert calendar.calls == []

    def test_decoder_recursion_error_is_bad_request_and_changes_nothing(
        self,
        alice: User,
        calendar: Calendar,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        connect_intervals(alice)
        plan = draft(alice)

        def _boom(*_args: Any, **_kwargs: Any) -> Any:
            raise RecursionError(MARKER)

        monkeypatch.setattr(JSONParser, "parse", _boom)

        response = signed_in(alice).call("POST", plan_url(plan.pk, "confirm/"), {"push": True})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert MARKER not in response.content.decode()
        plan.refresh_from_db()
        assert plan.status == Status.DRAFT
        assert calendar.calls == []
