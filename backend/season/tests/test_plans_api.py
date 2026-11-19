import json
from collections.abc import Callable
from dataclasses import replace
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
from availability.models import AvailabilitySettings, WeekdayMinutes
from coach.models import AIProviderConfiguration, AIUsageRecord
from coach.providers.base import InvalidKeyError, ProviderUnavailableError, RateLimitedError
from goals import services as goal_services
from goals.models import Goal
from planning import services as planning_services
from planning.models import WeeklyPlan
from planning.schema import Goal as WorkoutGoal
from planning.schema import Sport, WeekPlan, Workout
from planning.tests.scripted import Scripted
from season import services
from season.inputs import skeleton_for
from season.models import SeasonPlanVersion
from season.rules import SeasonContext
from season.schema import Focus, KeySession, PlanWeek, SeasonPlan, SessionKind, to_json
from season.skeleton import Skeleton
from season.snapshots import collect_inputs

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
            ("POST", url(UNKNOWN_ID, "change/")),
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
            ("GET", url(UNKNOWN_ID, "change/")),
            ("PUT", url(UNKNOWN_ID, "change/")),
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
            "planned_load",
            "total_planned_load",
            "done",
            "done_load",
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


def trained(
    user: User, start: str, seconds: float | None, sport: str = "running", n: int = 0, **fields: Any
) -> None:
    Activity.objects.create(
        owner=user,
        source="fit_file",
        source_hash=f"{user.pk}-{start}-{n}".ljust(64, "0")[:64],
        sport=sport,
        start_time=datetime.fromisoformat(start).replace(tzinfo=UTC),
        timer_seconds=seconds,
        **fields,
    )


def weekly(user: User, monday: date = MONDAY) -> None:
    stored = planning_services.save_draft(
        user, WeekPlan(monday, (Workout(monday, Sport.CYCLING, "Ride", WorkoutGoal.THRESHOLD, 60),))
    )
    WeeklyPlan.objects.filter(pk=stored.pk).update(status="confirmed", confirmed_at=NOW)


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
        assert self.weeks(alice, stored.pk)[0]["done_load"] == []

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
        assert [week["done_load"] for week in weeks] == [None] * 6

    def test_the_activities_of_another_user_do_not_show(self, alice: User, bob: User) -> None:
        stored = services.confirm(alice, draft(alice).pk)
        trained(bob, "2026-11-17T08:00", 3600)

        assert self.weeks(alice, stored.pk)[0]["done"] == []
        assert self.weeks(alice, stored.pk)[0]["done_load"] == []

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


class TestLoad:
    def test_season_estimates_and_totals_are_returned_even_for_a_draft(self, alice: User) -> None:
        stored = draft(
            alice,
            SeasonPlan(
                (
                    PlanWeek(
                        MONDAY,
                        ((Sport.RUNNING, 120), (Sport.SWIMMING, 60), (Sport.STRENGTH, 30)),
                        Focus.ENDURANCE,
                        "Base.",
                        (KeySession(Sport.RUNNING, SessionKind.TEMPO, 60),),
                    ),
                )
            ),
        )

        response = signed_in(alice).call("GET", url(stored.pk))

        assert response.status_code == HTTPStatus.OK
        week = body(response)["weeks"][0]
        assert week["planned_load"] == {"running": 130, "swimming": 55, "strength": 30}
        assert week["total_planned_load"] == 215
        assert week["done_load"] is None

    def test_confirmed_weekly_workouts_override_only_their_week(self, alice: User) -> None:
        stored = services.confirm(alice, draft(alice).pk)
        weekly(alice)

        response = signed_in(alice).call("GET", url(stored.pk))

        weeks = body(response)["weeks"]
        assert weeks[0]["planned_load"] == {"cycling": 95}
        assert weeks[0]["total_planned_load"] == 95
        assert set(weeks[1]["planned_load"]) == {"running"}
        assert weeks[1]["total_planned_load"] == (weeks[1]["total_minutes"] * 55 + 30) // 60

    def test_done_load_uses_intervals_and_rpe_only_for_begun_confirmed_weeks(
        self, alice: User
    ) -> None:
        stored = services.confirm(alice, draft(alice).pk)
        trained(alice, "2026-11-17T08:00", 3600, training_load=80.5, rpe=10)
        trained(alice, "2026-11-18T08:00", 1800, "cycling", rpe=6)
        trained(alice, "2026-11-18T09:00", 600, "swimming")  # unknown load adds zero
        trained(alice, "2026-11-18T10:00", None, "other", training_load=10)
        trained(alice, "2026-11-25T08:00", 3600, training_load=200)
        trained(alice, "2026-11-10T08:00", 3600, training_load=200)

        weeks = body(signed_in(alice).call("GET", url(stored.pk)))["weeks"]

        assert weeks[0]["done_load"] == [
            {"sport": "running", "load": 81},
            {"sport": "cycling", "load": 30},
            {"sport": "other", "load": 10},
        ]
        assert [week["done_load"] for week in weeks[1:]] == [None] * 5

    def test_other_users_workouts_and_activities_never_contribute(
        self, alice: User, bob: User
    ) -> None:
        stored = services.confirm(alice, draft(alice).pk)
        api = signed_in(alice)
        before = body(api.call("GET", url(stored.pk)))
        weekly(bob)
        trained(bob, "2026-11-17T08:00", 3600, training_load=500)

        assert body(api.call("GET", url(stored.pk))) == before

    def test_confirmation_returns_load_too(self, alice: User) -> None:
        stored = draft(alice)
        weekly(alice)
        trained(alice, "2026-11-17T08:00", 3600, rpe=6)

        response = signed_in(alice).call("POST", url(stored.pk, "confirm/"))

        week = body(response)["weeks"][0]
        assert week["planned_load"] == {"cycling": 95}
        assert week["total_planned_load"] == 95
        assert week["done_load"] == [{"sport": "running", "load": 60}]

    @pytest.mark.parametrize("status", ["draft", "confirmed"])
    def test_queries_are_constant_for_one_or_fifty_two_weeks(
        self, alice: User, monkeypatch: pytest.MonkeyPatch, status: str
    ) -> None:
        api = signed_in(alice)
        frame = skeleton_for(alice)
        counts = []
        monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW + timedelta(weeks=52))
        for count in (1, 52):
            skeleton = replace(
                frame,
                weeks=tuple(
                    replace(frame.weeks[0], week_start=MONDAY + timedelta(weeks=n), races=())
                    for n in range(count)
                ),
            )
            stored = services.save_draft(alice, following(skeleton), SeasonContext(skeleton))
            if status == "confirmed":
                services.confirm(alice, stored.pk)
            if count == 52:
                for n in range(count):
                    monday = MONDAY + timedelta(weeks=n)
                    weekly(alice, monday)
                    trained(alice, f"{monday.isoformat()}T08:00", 3600, rpe=6)

            with CaptureQueriesContext(connection) as queries:
                response = api.call("GET", url(stored.pk))

            assert response.status_code == HTTPStatus.OK
            assert len(body(response)["weeks"]) == count
            counts.append(len(queries))

        assert counts[0] == counts[1]


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


def tempo(user: User) -> str:
    """The season as it is, but with the focus of the first week changed."""
    plan = following(skeleton_for(user))
    weeks = (replace(plan.weeks[0], focus=Focus.TEMPO, reason="Harder."), *plan.weeks[1:])
    return json.dumps(to_json(SeasonPlan(weeks, plan.rationale)))


class TestChanging:
    WISH = {"request": "Less cycling in January"}

    def confirmed(self, user: User) -> SeasonPlanVersion:
        skeleton = skeleton_for(user)
        stored = services.save_draft(
            user, following(skeleton), SeasonContext(skeleton), input_snapshot=collect_inputs(user)
        )
        return services.confirm(user, stored.pk)

    def test_a_good_answer_gives_the_new_draft_with_its_checks(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = self.confirmed(alice)
        provide(tempo(alice))

        response = signed_in(alice).call("POST", url(base.pk, "change/"), self.WISH)

        assert response.status_code == HTTPStatus.CREATED
        data = body(response)
        assert set(data) == DETAIL_FIELDS
        assert (data["status"], data["version"], data["parent"]) == ("draft", 2, str(base.pk))
        assert data["reason"] == "Changed on request from version 1"
        assert data["request"] == "Less cycling in January"
        assert data["report"] == {"valid": True, "findings": []}
        assert data["weeks"][0]["focus"] == "tempo"

    @pytest.mark.parametrize("change_kind", ["race", "capacity"])
    def test_the_draft_is_checked_against_current_inputs_and_the_parent_is_untouched(
        self, alice: User, provide: Callable[..., Scripted], change_kind: str
    ) -> None:
        base = self.confirmed(alice)
        before = SeasonPlanVersion.objects.values().get(pk=base.pk)
        if change_kind == "race":
            Goal.objects.for_user(alice).update(target_date=MONDAY + timedelta(weeks=9, days=6))
        else:
            WeekdayMinutes.objects.for_user(alice).update(minutes=30)
        expected = skeleton_for(alice)
        scripted = provide(good(alice))

        response = signed_in(alice).call("POST", url(base.pk, "change/"), self.WISH)

        assert response.status_code == HTTPStatus.CREATED
        data = body(response)
        assert data["report"] == {"valid": True, "findings": []}
        assert (data["parent"], data["request"]) == (str(base.pk), self.WISH["request"])
        stored = services.get(alice, UUID(data["id"]))
        assert services.read(stored).context.skeleton == expected
        assert stored.input_snapshot == collect_inputs(alice)
        told = json.loads(scripted.calls[0][1][0].content.split("\n\n", 1)[1])
        assert [week["week_start"] for week in told["weeks"]] == [
            week.week_start.isoformat() for week in expected.weeks
        ]
        assert told["current_plan"] == to_json(services.read(base).plan)
        assert SeasonPlanVersion.objects.values().get(pk=base.pk) == before

    def test_an_answer_in_the_old_frame_stays_an_unconfirmable_draft(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = self.confirmed(alice)
        old_answer = good(alice)
        Goal.objects.for_user(alice).update(target_date=MONDAY + timedelta(weeks=9, days=6))
        provide(old_answer, old_answer, old_answer)
        api = signed_in(alice)

        response = api.call("POST", url(base.pk, "change/"), self.WISH)

        assert response.status_code == HTTPStatus.CREATED
        data = body(response)
        assert data["report"]["valid"] is False
        assert "weeks_mismatch" in [finding["code"] for finding in data["report"]["findings"]]
        refused = api.call("POST", url(data["id"], "confirm/"))
        assert refused.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert body(refused)["code"] == "not_confirmable"
        base.refresh_from_db()
        assert base.status == "confirmed"

    @pytest.mark.parametrize("configured", [False, True])
    def test_no_current_time_returns_the_existing_no_time_response_without_a_call(
        self, alice: User, provide: Callable[..., Scripted], configured: bool
    ) -> None:
        base = self.confirmed(alice)
        AvailabilitySettings.objects.create(owner=alice, weekly_budget_minutes=0)
        if not configured:
            AIProviderConfiguration.objects.filter(owner=alice).delete()
        scripted = provide("never asked")

        response = signed_in(alice).call("POST", url(base.pk, "change/"), self.WISH)

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response) == {
            "code": "no_time",
            "detail": (
                "You have no training time in the weeks of your season. "
                "Enter it on the Training time page."
            ),
        }
        assert scripted.calls == []
        assert not AIUsageRecord.objects.for_user(alice).exists()
        assert SeasonPlanVersion.objects.for_user(alice).count() == 1

    def test_identical_content_with_a_new_frame_is_created_instead_of_unchanged(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        AvailabilitySettings.objects.create(owner=alice, typical_weekly_minutes=210)
        base = self.confirmed(alice)
        old_answer = good(alice)
        WeekdayMinutes.objects.for_user(alice).update(minutes=90)
        provide(old_answer)

        response = signed_in(alice).call("POST", url(base.pk, "change/"), self.WISH)

        assert response.status_code == HTTPStatus.CREATED
        data = body(response)
        assert data["report"] == {"valid": True, "findings": []}
        assert data["skeleton"] != base.skeleton
        assert data["skeleton"]["weeks"][0]["capacity_minutes"] == 630

    def test_the_old_version_stays_confirmed(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = self.confirmed(alice)
        provide(tempo(alice))

        signed_in(alice).call("POST", url(base.pk, "change/"), self.WISH)

        base.refresh_from_db()
        assert base.status == "confirmed"

    def test_the_call_is_recorded_for_the_season(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = self.confirmed(alice)
        provide(tempo(alice))

        signed_in(alice).call("POST", url(base.pk, "change/"), self.WISH)

        assert [r.purpose for r in AIUsageRecord.objects.for_user(alice)] == ["season_plan"]

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"request": ""},
            {"request": "  \n "},
            {"request": "x" * 501},
            {"request": "bell\x07"},
        ],
    )
    def test_a_request_that_is_missing_empty_too_long_or_not_plain_is_a_400_on_its_field(
        self, alice: User, provide: Callable[..., Scripted], payload: dict[str, Any]
    ) -> None:
        base = self.confirmed(alice)
        scripted = provide("never asked")

        response = signed_in(alice).call("POST", url(base.pk, "change/"), payload)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert set(body(response)) == {"request"}
        assert scripted.calls == []

    @pytest.mark.parametrize("value", [5, None, ["x"], {"a": 1}])
    def test_a_request_that_is_no_text_is_a_400(self, alice: User, value: Any) -> None:
        base = self.confirmed(alice)

        response = signed_in(alice).call("POST", url(base.pk, "change/"), {"request": value})

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_what_was_asked_is_not_repeated_in_an_error(self, alice: User) -> None:
        base = self.confirmed(alice)

        response = signed_in(alice).call(
            "POST", url(base.pk, "change/"), {"request": "SECRET-WISH\x07"}
        )

        assert "SECRET-WISH" not in response.content.decode()

    @pytest.mark.parametrize("status", ["superseded", "discarded"])
    def test_a_replaced_or_discarded_version_is_a_409(
        self, alice: User, provide: Callable[..., Scripted], status: str
    ) -> None:
        old = draft(alice)
        if status == "discarded":
            services.discard(alice, old.pk)
        else:
            services.confirm(alice, old.pk)
            services.confirm(alice, draft(alice).pk)
        scripted = provide("never asked")

        response = signed_in(alice).call("POST", url(old.pk, "change/"), self.WISH)

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response)["code"] == "not_changeable"
        assert scripted.calls == []

    def test_the_version_of_another_user_is_not_found(
        self, alice: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        theirs = self.confirmed(bob)
        scripted = provide("never asked")

        response = signed_in(alice).call("POST", url(theirs.pk, "change/"), self.WISH)

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response)["code"] == "not_found"
        assert scripted.calls == []

    def test_no_provider_is_a_409(self, alice: User) -> None:
        base = self.confirmed(alice)
        AIProviderConfiguration.objects.filter(owner=alice).delete()

        response = signed_in(alice).call("POST", url(base.pk, "change/"), self.WISH)

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response)["code"] == "not_configured"

    def test_an_answer_that_is_the_season_as_it_was_is_a_422_unchanged(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = self.confirmed(alice)
        provide(good(alice))

        response = signed_in(alice).call("POST", url(base.pk, "change/"), self.WISH)

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert body(response)["code"] == "unchanged"
        assert SeasonPlanVersion.objects.count() == 1

    def test_an_answer_that_cannot_be_read_is_a_422_with_fixed_problems(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = self.confirmed(alice)
        provide("SECRET-1", "SECRET-2", "SECRET-3")

        response = signed_in(alice).call("POST", url(base.pk, "change/"), self.WISH)

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert body(response)["code"] == "not_usable"
        assert "SECRET" not in response.content.decode()
        assert SeasonPlanVersion.objects.count() == 1

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
        base = self.confirmed(alice)
        provide(error)

        response = signed_in(alice).call("POST", url(base.pk, "change/"), self.WISH)

        assert response.status_code == status
        assert body(response)["code"] == code

    def test_it_is_throttled_with_drafting_before_the_provider(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        base = self.confirmed(alice)
        scripted = provide(tempo(alice), tempo(alice), tempo(alice), tempo(alice))
        api = signed_in(alice)

        statuses = [
            api.call("POST", url(base.pk, "change/"), self.WISH).status_code for _ in range(4)
        ]

        assert statuses == [201, 201, 201, HTTPStatus.TOO_MANY_REQUESTS]
        assert len(scripted.calls) == 3


class TestWithoutCsrf:
    @pytest.mark.parametrize(
        "action", ["generate/", "{id}/confirm/", "{id}/discard/", "{id}/restore/", "{id}/change/"]
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
