import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from typing import Any
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from accounts.tests.conftest import AuthApi
from athletes.models import ThresholdValue
from availability.models import WeekdayMinutes
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
from planning import services
from planning.models import PlannedWorkout, WeeklyPlan
from planning.schema import Goal, Sport, WeekPlan, Workout, ZoneSystem, to_json

from .conftest import make_user, signed_in
from .scripted import Scripted

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
    "rationale",
    "parent",
    "created_at",
    "confirmed_at",
    "workouts",
    "report",
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
    plan = WeekPlan(monday, workouts or (ride(0), ride(2)))
    return services.save_draft(user, plan, reason="by hand")


def generate_url(week: str = "2027-07-19") -> str:
    return f"/api/planning/weeks/{week}/generate/"


def plan_url(plan: Any, action: str = "") -> str:
    return f"/api/planning/plans/{plan}/{action}"


ENDPOINTS = [
    ("GET", WEEKS),
    ("POST", generate_url()),
    ("GET", plan_url(uuid4())),
    ("POST", plan_url(uuid4(), "confirm/")),
    ("POST", plan_url(uuid4(), "discard/")),
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
            ("DELETE", plan_url(uuid4())),
            ("PATCH", plan_url(uuid4())),
            ("GET", plan_url(uuid4(), "confirm/")),
            ("GET", plan_url(uuid4(), "discard/")),
        ],
    )
    def test_other_methods_are_not_allowed(self, alice: User, method: str, url: str) -> None:
        response = signed_in(alice).call(method, url)

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED


class TestTheWeeks:
    def test_five_weeks_with_nothing_in_them(self, alice: User) -> None:
        response = signed_in(alice).call("GET", WEEKS)

        assert response.status_code == HTTPStatus.OK
        assert body(response) == {
            "weeks": [
                {"week_start": f"2027-{month:02d}-{day:02d}", "plans": []}
                for month, day in [(7, 12), (7, 19), (7, 26), (8, 2), (8, 9)]
            ]
        }

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
        (record,) = AIUsageRecord.objects.filter(owner=alice)
        assert (record.purpose, record.outcome) == ("weekly_plan", "success")

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
