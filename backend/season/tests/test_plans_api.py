import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from typing import Any
from uuid import UUID

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from accounts.tests.conftest import AuthApi
from activities.models import Activity
from availability.models import WeekdayMinutes
from coach.models import AIProviderConfiguration, AIUsageRecord
from coach.providers.base import InvalidKeyError, ProviderUnavailableError, RateLimitedError
from goals import services as goal_services
from goals.models import Goal
from planning.schema import Sport
from planning.tests.scripted import Scripted
from season import services
from season.inputs import skeleton_for
from season.models import SeasonPlanVersion
from season.rules import SeasonContext
from season.schema import Focus, KeySession, PlanWeek, SeasonPlan, SessionKind, to_json
from season.skeleton import Skeleton

from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

# A fixed id for the tests that are parametrized: the id is part of the name of a test, and every
# worker of a parallel run has to collect the same names.
UNKNOWN_ID = UUID("0195f3a0-0000-7000-8000-000000000001")
PLANS = "/api/season/plans/"
GENERATE = f"{PLANS}generate/"
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
MONDAY = date(2026, 11, 16)
KEY = "sk-ant-test-0123456789-abcdefghij"
DETAIL_FIELDS = {
    "id",
    "version",
    "status",
    "reason",
    "request",
    "rationale",
    "parent",
    "created_at",
    "confirmed_at",
    "skeleton",
    "weeks",
    "report",
}
SUMMARY_FIELDS = {"id", "version", "status", "reason", "week_count", "created_at", "confirmed_at"}


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    user = make_user("alice@example.com")
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
        target_date=MONDAY + timedelta(weeks=5, days=6),
        discipline="running",
        distance_m=10_000,
    )
    return user


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def body(response: Any) -> Any:
    return json.loads(response.content)


def following(skeleton: Skeleton) -> SeasonPlan:
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


def draft(user: User, plan: SeasonPlan | None = None) -> SeasonPlanVersion:
    skeleton = skeleton_for(user)
    return services.save_draft(user, plan or following(skeleton), SeasonContext(skeleton))


def url(plan: Any, action: str = "") -> str:
    return f"{PLANS}{plan}/{action}"


class TestWhoMayCome:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", PLANS),
            ("POST", GENERATE),
            ("GET", url(UNKNOWN_ID)),
            ("POST", url(UNKNOWN_ID, "confirm/")),
            ("POST", url(UNKNOWN_ID, "discard/")),
            ("POST", url(UNKNOWN_ID, "restore/")),
        ],
    )
    def test_a_visitor_who_is_not_signed_in_is_refused(self, method: str, path: str) -> None:
        assert AuthApi().call(method, path).status_code == HTTPStatus.FORBIDDEN

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("POST", PLANS),
            ("DELETE", PLANS),
            ("GET", GENERATE),
            ("PUT", GENERATE),
            ("POST", url(UNKNOWN_ID)),
            ("DELETE", url(UNKNOWN_ID)),
            ("PATCH", url(UNKNOWN_ID)),
            ("GET", url(UNKNOWN_ID, "confirm/")),
            ("GET", url(UNKNOWN_ID, "discard/")),
            ("GET", url(UNKNOWN_ID, "restore/")),
            ("PUT", url(UNKNOWN_ID, "restore/")),
        ],
    )
    def test_other_methods_are_not_allowed(self, alice: User, method: str, path: str) -> None:
        assert signed_in(alice).call(method, path).status_code == HTTPStatus.METHOD_NOT_ALLOWED


class TestGenerating:
    def test_a_good_answer_gives_a_draft_with_its_report(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good(alice))

        response = signed_in(alice).call("POST", GENERATE)

        assert response.status_code == HTTPStatus.CREATED
        data = body(response)
        assert set(data) == DETAIL_FIELDS
        assert (data["status"], data["version"], data["parent"]) == ("draft", 1, None)
        assert data["reason"] == "Drafted by the coach"
        assert data["rationale"] == "The season."
        assert data["report"] == {"valid": True, "findings": []}
        assert len(data["weeks"]) == 6
        assert data["skeleton"]["weeks"][0]["week_start"] == "2026-11-16"
        assert SeasonPlanVersion.objects.count() == 1

    def test_a_week_has_its_minutes_its_total_and_its_key_sessions(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good(alice))

        data = body(signed_in(alice).call("POST", GENERATE))

        first, last = data["weeks"][0], data["weeks"][-1]
        assert set(first) == {
            "week_start",
            "minutes",
            "focus",
            "key_sessions",
            "reason",
            "total_minutes",
            "done",
        }
        assert first["minutes"] == {"running": data["skeleton"]["weeks"][0]["target_minutes"]}
        assert first["total_minutes"] == first["minutes"]["running"]
        assert last["key_sessions"] == [
            {"sport": "running", "kind": "race", "minutes": 1, "detail": ""}
        ]

    def test_a_plan_with_errors_is_stored_and_shown_with_them(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        wrong = following(skeleton_for(alice))
        wrong = SeasonPlan(wrong.weeks[:2])
        provide(*[json.dumps(to_json(wrong))] * 3)

        response = signed_in(alice).call("POST", GENERATE)

        assert response.status_code == HTTPStatus.CREATED
        report = body(response)["report"]
        assert report["valid"] is False
        assert {"severity", "code", "message", "path"} == set(report["findings"][0])
        assert "weeks_mismatch" in [f["code"] for f in report["findings"]]

    def test_the_call_is_recorded_for_the_season(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good(alice))

        signed_in(alice).call("POST", GENERATE)

        assert [r.purpose for r in AIUsageRecord.objects.for_user(alice)] == ["season_plan"]

    def test_no_provider_is_a_409_before_anything_is_sent(self, bob: User) -> None:
        WeekdayMinutes.objects.create(owner=bob, weekday=0, minutes=60)

        response = signed_in(bob).call("POST", GENERATE)

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response)["code"] == "not_configured"
        assert body(response)["detail"] == "No AI provider is set up."

    def test_no_time_is_a_409_and_the_provider_is_not_asked(
        self, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide("never")

        response = signed_in(bob).call("POST", GENERATE)

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response)["code"] == "no_time"
        assert scripted.calls == []

    def test_an_answer_that_cannot_be_read_is_a_422_with_fixed_problems(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide("SECRET-1", "SECRET-2", "SECRET-3")

        response = signed_in(alice).call("POST", GENERATE)

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        data = body(response)
        assert data["code"] == "not_usable"
        assert data["problems"] == [
            {
                "path": "",
                "message": "The answer is not one JSON object. Send the object and nothing else.",
            }
        ]
        assert "SECRET" not in response.content.decode()
        assert not SeasonPlanVersion.objects.exists()

    @pytest.mark.parametrize(
        ("error", "status", "code"),
        [
            (InvalidKeyError("x"), HTTPStatus.BAD_GATEWAY, "invalid_key"),
            (RateLimitedError("x", 30), HTTPStatus.TOO_MANY_REQUESTS, "rate_limited"),
            (ProviderUnavailableError("x"), HTTPStatus.SERVICE_UNAVAILABLE, "unavailable"),
        ],
    )
    def test_a_provider_that_fails_is_a_fixed_text_and_a_code(
        self,
        alice: User,
        provide: Callable[..., Scripted],
        error: Exception,
        status: int,
        code: str,
    ) -> None:
        provide(error)

        response = signed_in(alice).call("POST", GENERATE)

        assert response.status_code == status
        assert body(response)["code"] == code

    def test_the_fourth_request_within_a_minute_is_throttled_before_the_provider(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(*[good(alice)] * 4)
        api = signed_in(alice)

        statuses = [api.call("POST", GENERATE).status_code for _ in range(4)]

        assert statuses == [201, 201, 201, HTTPStatus.TOO_MANY_REQUESTS]
        assert len(scripted.calls) == 3

    def test_reading_is_not_throttled(self, alice: User) -> None:
        api = signed_in(alice)

        assert {api.call("GET", PLANS).status_code for _ in range(10)} == {200}


class TestReading:
    def test_a_user_without_plans_has_an_empty_list(self, alice: User) -> None:
        assert body(signed_in(alice).call("GET", PLANS)) == {"plans": []}

    def test_the_versions_come_newest_first_with_a_summary(self, alice: User) -> None:
        first, second = draft(alice), draft(alice)

        data = body(signed_in(alice).call("GET", PLANS))

        assert [p["id"] for p in data["plans"]] == [str(second.pk), str(first.pk)]
        assert set(data["plans"][0]) == SUMMARY_FIELDS
        assert (data["plans"][0]["version"], data["plans"][0]["week_count"]) == (2, 6)

    def test_a_draft_is_read_with_a_fresh_report(self, alice: User) -> None:
        stored = draft(alice)

        data = body(signed_in(alice).call("GET", url(stored.pk)))

        assert set(data) == DETAIL_FIELDS
        assert data["report"] == {"valid": True, "findings": []}

    def test_a_plan_that_was_decided_on_has_no_report(self, alice: User) -> None:
        stored = services.confirm(alice, draft(alice).pk)

        data = body(signed_in(alice).call("GET", url(stored.pk)))

        assert (data["status"], data["report"]) == ("confirmed", None)

    def test_the_plan_of_another_user_is_not_found(self, alice: User, bob: User) -> None:
        theirs = draft(bob)

        response = signed_in(alice).call("GET", url(theirs.pk))

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response) == {"detail": "There is no such season plan.", "code": "not_found"}

    def test_the_list_shows_only_the_own_plans(self, alice: User, bob: User) -> None:
        mine = draft(alice)
        draft(bob)

        data = body(signed_in(alice).call("GET", PLANS))

        assert [p["id"] for p in data["plans"]] == [str(mine.pk)]

    @pytest.mark.parametrize("path", ["not-an-id", "1234", "x" * 40])
    def test_an_id_that_is_no_uuid_does_not_exist(self, alice: User, path: str) -> None:
        assert signed_in(alice).call("GET", f"{PLANS}{path}/").status_code == HTTPStatus.NOT_FOUND


def trained(user: User, start: str, seconds: float, sport: str = "running", n: int = 0) -> None:
    Activity.objects.create(
        owner=user,
        source="fit_file",
        source_hash=f"{user.pk}-{start}-{n}".ljust(64, "0")[:64],
        sport=sport,
        start_time=datetime.fromisoformat(start).replace(tzinfo=UTC),
        timer_seconds=seconds,
    )


class TestTheMinutesDone:
    def weeks(self, user: User, plan_id: object) -> list[dict[str, Any]]:
        return body(signed_in(user).call("GET", url(plan_id)))["weeks"]

    def test_the_confirmed_plan_has_them_for_the_weeks_that_have_begun(self, alice: User) -> None:
        stored = services.confirm(alice, draft(alice).pk)
        trained(alice, "2026-11-17T08:00", 3600, "running", 1)
        trained(alice, "2026-11-18T08:00", 1800, "cycling", 2)
        trained(alice, "2026-11-25T08:00", 3600, "running", 3)  # next week: not begun yet

        weeks = self.weeks(alice, stored.pk)

        assert weeks[0]["done"] == [
            {"sport": "running", "minutes": 60},
            {"sport": "cycling", "minutes": 30},
        ]
        assert [week["done"] for week in weeks[1:]] == [None] * 5

    def test_a_week_that_has_begun_without_activities_is_empty_not_missing(
        self, alice: User
    ) -> None:
        stored = services.confirm(alice, draft(alice).pk)

        assert self.weeks(alice, stored.pk)[0]["done"] == []

    def test_a_week_before_the_season_has_no_effect(self, alice: User) -> None:
        stored = services.confirm(alice, draft(alice).pk)
        trained(alice, "2026-11-10T08:00", 3600)

        assert self.weeks(alice, stored.pk)[0]["done"] == []

    @pytest.mark.parametrize("status", ["draft", "superseded", "discarded"])
    def test_no_other_version_has_them(self, alice: User, status: str) -> None:
        stored = draft(alice)
        if status == "discarded":
            stored = services.discard(alice, stored.pk)
        elif status == "superseded":
            services.confirm(alice, stored.pk)
            newer = draft(alice)
            services.confirm(alice, newer.pk)
            stored.refresh_from_db()
        trained(alice, "2026-11-17T08:00", 3600)

        weeks = self.weeks(alice, stored.pk)

        assert stored.status == status
        assert [week["done"] for week in weeks] == [None] * 6

    def test_the_activities_of_another_user_do_not_show(self, alice: User, bob: User) -> None:
        stored = services.confirm(alice, draft(alice).pk)
        trained(bob, "2026-11-17T08:00", 3600)

        assert self.weeks(alice, stored.pk)[0]["done"] == []

    def test_the_answer_of_confirming_has_them_too(self, alice: User) -> None:
        trained(alice, "2026-11-17T08:00", 3600)
        stored = draft(alice)

        data = body(signed_in(alice).call("POST", url(stored.pk, "confirm/")))

        assert data["weeks"][0]["done"] == [{"sport": "running", "minutes": 60}]

    def test_the_number_of_queries_does_not_depend_on_the_weeks(self, alice: User) -> None:
        stored = services.confirm(alice, draft(alice).pk)
        api = signed_in(alice)
        with CaptureQueriesContext(connection) as before:
            api.call("GET", url(stored.pk))
        for n in range(20):
            trained(alice, f"2026-11-{(n % 3) + 16}T{8 + n // 3:02d}:00", 600, n=n)

        with CaptureQueriesContext(connection) as after:
            api.call("GET", url(stored.pk))

        assert len(after) == len(before)


class TestConfirming:
    def test_a_draft_is_confirmed(self, alice: User) -> None:
        stored = draft(alice)

        response = signed_in(alice).call("POST", url(stored.pk, "confirm/"))

        assert response.status_code == HTTPStatus.OK
        data = body(response)
        assert (data["status"], data["report"]) == ("confirmed", None)
        assert data["confirmed_at"] is not None

    def test_the_plan_confirmed_before_is_superseded(self, alice: User) -> None:
        first = services.confirm(alice, draft(alice).pk)
        second = draft(alice)

        signed_in(alice).call("POST", url(second.pk, "confirm/"))

        first.refresh_from_db()
        assert first.status == "superseded"

    def test_a_plan_with_errors_is_refused_with_the_findings(self, alice: User) -> None:
        skeleton = skeleton_for(alice)
        stored = services.save_draft(
            alice, SeasonPlan(following(skeleton).weeks[:2]), SeasonContext(skeleton)
        )

        response = signed_in(alice).call("POST", url(stored.pk, "confirm/"))

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        data = body(response)
        assert data["code"] == "not_confirmable"
        assert data["detail"] == "The plan has errors and cannot be confirmed."
        assert "weeks_mismatch" in [f["code"] for f in data["findings"]]
        stored.refresh_from_db()
        assert stored.status == "draft"

    def test_only_a_draft_can_be_confirmed(self, alice: User) -> None:
        stored = services.confirm(alice, draft(alice).pk)

        response = signed_in(alice).call("POST", url(stored.pk, "confirm/"))

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response)["code"] == "not_a_draft"

    def test_the_plan_of_another_user_is_not_found_and_not_confirmed(
        self, alice: User, bob: User
    ) -> None:
        theirs = draft(bob)

        response = signed_in(alice).call("POST", url(theirs.pk, "confirm/"))

        assert response.status_code == HTTPStatus.NOT_FOUND
        theirs.refresh_from_db()
        assert theirs.status == "draft"


class TestDiscarding:
    def test_a_draft_is_discarded(self, alice: User) -> None:
        stored = draft(alice)

        response = signed_in(alice).call("POST", url(stored.pk, "discard/"))

        assert response.status_code == HTTPStatus.OK
        assert body(response)["status"] == "discarded"
        assert SeasonPlanVersion.objects.filter(pk=stored.pk).exists()

    def test_only_a_draft_can_be_discarded(self, alice: User) -> None:
        stored = services.confirm(alice, draft(alice).pk)

        response = signed_in(alice).call("POST", url(stored.pk, "discard/"))

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response)["code"] == "not_a_draft"

    def test_the_plan_of_another_user_is_not_found_and_not_discarded(
        self, alice: User, bob: User
    ) -> None:
        theirs = draft(bob)

        response = signed_in(alice).call("POST", url(theirs.pk, "discard/"))

        assert response.status_code == HTTPStatus.NOT_FOUND
        theirs.refresh_from_db()
        assert theirs.status == "draft"


class TestRestoring:
    def replaced(self, user: User) -> SeasonPlanVersion:
        first = services.confirm(user, draft(user).pk)
        services.confirm(user, draft(user).pk)
        first.refresh_from_db()
        return first

    def test_a_replaced_version_comes_back_as_a_new_draft_with_its_checks(
        self, alice: User
    ) -> None:
        old = self.replaced(alice)

        response = signed_in(alice).call("POST", url(old.pk, "restore/"))

        assert response.status_code == HTTPStatus.CREATED
        data = body(response)
        assert set(data) == DETAIL_FIELDS
        assert (data["status"], data["version"], data["parent"]) == ("draft", 3, str(old.pk))
        assert data["reason"] == "Restored from version 1"
        assert data["report"] == {"valid": True, "findings": []}
        assert data["weeks"] == body(signed_in(alice).call("GET", url(old.pk)))["weeks"]

    def test_a_discarded_version_comes_back_too(self, alice: User) -> None:
        old = services.discard(alice, draft(alice).pk)

        response = signed_in(alice).call("POST", url(old.pk, "restore/"))

        assert response.status_code == HTTPStatus.CREATED
        assert body(response)["parent"] == str(old.pk)

    def test_the_new_draft_can_be_confirmed(self, alice: User) -> None:
        old = self.replaced(alice)
        new = body(signed_in(alice).call("POST", url(old.pk, "restore/")))

        response = signed_in(alice).call("POST", url(new["id"], "confirm/"))

        assert (response.status_code, body(response)["status"]) == (HTTPStatus.OK, "confirmed")

    def test_the_old_version_is_not_touched(self, alice: User) -> None:
        old = self.replaced(alice)

        signed_in(alice).call("POST", url(old.pk, "restore/"))

        old.refresh_from_db()
        assert old.status == "superseded"

    @pytest.mark.parametrize("status", ["draft", "confirmed"])
    def test_a_draft_and_the_confirmed_version_cannot_be_restored(
        self, alice: User, status: str
    ) -> None:
        stored = draft(alice)
        if status == "confirmed":
            stored = services.confirm(alice, stored.pk)

        response = signed_in(alice).call("POST", url(stored.pk, "restore/"))

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response) == {
            "detail": "Only a version that was replaced or discarded can be restored.",
            "code": "not_restorable",
        }
        assert SeasonPlanVersion.objects.count() == 1

    def test_the_version_of_another_user_is_not_found_and_not_copied(
        self, alice: User, bob: User
    ) -> None:
        theirs = services.discard(bob, draft(bob).pk)

        response = signed_in(alice).call("POST", url(theirs.pk, "restore/"))

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response)["code"] == "not_found"
        assert SeasonPlanVersion.objects.count() == 1

    def test_an_id_that_does_not_exist_is_not_found(self, alice: User) -> None:
        response = signed_in(alice).call("POST", url(UNKNOWN_ID, "restore/"))

        assert response.status_code == HTTPStatus.NOT_FOUND


class TestWithoutCsrf:
    @pytest.mark.parametrize(
        "action", ["generate/", "{id}/confirm/", "{id}/discard/", "{id}/restore/"]
    )
    def test_a_post_without_the_token_is_refused(self, alice: User, action: str) -> None:
        stored = draft(alice)
        api = signed_in(alice)

        response = api.client.generic(
            "POST", PLANS + action.format(id=stored.pk), data=b"", content_type="application/json"
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        stored.refresh_from_db()
        assert stored.status == "draft"
