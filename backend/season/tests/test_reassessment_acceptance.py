"""API-level lifecycle acceptance tests for season change hints and deviation proposals."""

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from typing import Any
from unittest.mock import patch

import pytest

from accounts.models import User
from accounts.tests.conftest import AuthApi
from availability.models import WeekdayMinutes
from coach.models import AIProviderConfiguration
from goals import services as goal_services
from planning.schema import Sport
from planning.tests.scripted import Scripted
from reviews.tests.builders import make_activity, make_plan
from season import services
from season.inputs import skeleton_for
from season.models import SeasonPlanVersion
from season.schema import Focus, KeySession, PlanWeek, SeasonPlan, SessionKind, to_json
from season.skeleton import Skeleton

from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
MONDAY = date(2026, 11, 16)
KEY = "test-provider-marker-0123456789"

GOALS_URL = "/api/goals/"
PLANS_URL = "/api/season/plans/"
GENERATE_URL = f"{PLANS_URL}generate/"
REASSESSMENT_URL = "/api/season/reassessment/"
REVIEW_WEEKS_URL = "/api/reviews/weeks/"


def body(response: Any) -> Any:
    return json.loads(response.content)


def plan_url(plan_id: str, action: str = "") -> str:
    return f"{PLANS_URL}{plan_id}/{action}"


def following(skeleton: Skeleton, rationale: str = "Adjusted season.") -> str:
    plan = SeasonPlan(
        tuple(
            PlanWeek(
                week.week_start,
                ((Sport.RUNNING, week.target_minutes),),
                Focus.ENDURANCE,
                "Steady progression.",
                (KeySession(Sport.RUNNING, SessionKind.RACE, 1),) if week.races else (),
            )
            for week in skeleton.weeks
        ),
        rationale,
    )
    return json.dumps(to_json(plan))


def sent_payload(scripted: Scripted) -> dict[str, Any]:
    _, payload = scripted.calls[0][1][0].content.split("\n\n", 1)
    data = json.loads(payload)
    assert isinstance(data, dict)
    return data


def set_clock(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: moment)
    monkeypatch.setattr(services, "_now", lambda: moment)


def prepare_athlete(email: str) -> tuple[User, AuthApi]:
    user = make_user(email)
    for weekday in range(7):
        WeekdayMinutes.objects.create(owner=user, weekday=weekday, minutes=60)
    AIProviderConfiguration.objects.create(
        owner=user, provider="anthropic", model="claude-sonnet-5-5", api_key=KEY
    )
    return user, signed_in(user)


def create_main_race(api: AuthApi, race_date: date, title: str = "City 10k") -> str:
    response = api.call(
        "POST",
        GOALS_URL,
        {
            "kind": "race",
            "title": title,
            "priority": "main",
            "target_date": race_date.isoformat(),
            "discipline": "running",
            "distance_m": 10_000,
        },
    )
    assert response.status_code == HTTPStatus.CREATED
    return str(body(response)["id"])


def generate_and_confirm(
    user: User, api: AuthApi, provide: Callable[..., Scripted]
) -> dict[str, Any]:
    provide(following(skeleton_for(user), rationale="Initial season."))
    draft_response = api.call("POST", GENERATE_URL)
    assert draft_response.status_code == HTTPStatus.CREATED
    draft = body(draft_response)
    assert draft["status"] == "draft"
    confirm_response = api.call("POST", plan_url(draft["id"], "confirm/"))
    assert confirm_response.status_code == HTTPStatus.OK
    confirmed = body(confirm_response)
    assert confirmed["status"] == "confirmed"
    return confirmed


def test_a_race_date_change_lifecycle_with_scripted_provider(
    monkeypatch: pytest.MonkeyPatch, provide: Callable[..., Scripted]
) -> None:
    set_clock(monkeypatch, NOW)
    alice, alice_api = prepare_athlete("alice@example.com")
    bob, bob_api = prepare_athlete("bob@example.com")
    initial_race_date = MONDAY + timedelta(weeks=5, days=6)
    moved_race_date = MONDAY + timedelta(weeks=7, days=6)

    alice_goal_id = create_main_race(alice_api, initial_race_date)
    create_main_race(bob_api, initial_race_date, title="Bob 10k")

    v1 = generate_and_confirm(alice, alice_api, provide)
    bob_v1 = generate_and_confirm(bob, bob_api, provide)

    assert body(alice_api.call("GET", REASSESSMENT_URL)) == {
        "confirmed_plan_id": v1["id"],
        "reasons": [],
        "deviation_weeks": [],
    }

    # Moving the A race immediately triggers the reassessment hint for Alice only.
    patch_response = alice_api.call(
        "PATCH",
        f"{GOALS_URL}{alice_goal_id}/",
        {"target_date": moved_race_date.isoformat()},
    )
    assert patch_response.status_code == HTTPStatus.OK

    expected_hint = {
        "confirmed_plan_id": v1["id"],
        "reasons": ["goals_changed"],
        "deviation_weeks": [],
    }
    assert body(alice_api.call("GET", REASSESSMENT_URL)) == expected_hint
    assert body(bob_api.call("GET", REASSESSMENT_URL)) == {
        "confirmed_plan_id": bob_v1["id"],
        "reasons": [],
        "deviation_weeks": [],
    }

    # Explicitly asking for a change drafts against the new skeleton without changing v1.
    updated_skeleton = skeleton_for(alice)
    assert len(updated_skeleton.weeks) == len(v1["weeks"]) + 2
    scripted = provide(following(updated_skeleton, rationale="Extended for later race."))
    change_response = alice_api.call(
        "POST",
        plan_url(v1["id"], "change/"),
        {"request": "Move the taper out two weeks for the new race date."},
    )
    assert change_response.status_code == HTTPStatus.CREATED
    v2 = body(change_response)
    assert (v2["status"], v2["parent"], len(v2["weeks"])) == (
        "draft",
        v1["id"],
        len(updated_skeleton.weeks),
    )
    sent = sent_payload(scripted)
    assert sent["races"][0]["date"] == moved_race_date.isoformat()
    assert sent["change_request"] == "Move the taper out two weeks for the new race date."
    assert len(sent["current_plan"]["weeks"]) == len(v1["weeks"])

    # Drafting or discarding never clears the confirmed plan's hint.
    assert body(alice_api.call("GET", REASSESSMENT_URL)) == expected_hint
    discard_response = alice_api.call("POST", plan_url(v2["id"], "discard/"))
    assert discard_response.status_code == HTTPStatus.OK
    assert body(alice_api.call("GET", REASSESSMENT_URL)) == expected_hint

    # Only confirming a current replacement clears the hint and supersedes v1.
    provide(following(updated_skeleton, rationale="Confirmed later race season."))
    v3_response = alice_api.call(
        "POST",
        plan_url(v1["id"], "change/"),
        {"request": "Adjust the build and taper for the later A race."},
    )
    assert v3_response.status_code == HTTPStatus.CREATED
    v3 = body(v3_response)
    assert body(alice_api.call("GET", REASSESSMENT_URL)) == expected_hint

    confirm_response = alice_api.call("POST", plan_url(v3["id"], "confirm/"))
    assert confirm_response.status_code == HTTPStatus.OK
    assert body(alice_api.call("GET", REASSESSMENT_URL)) == {
        "confirmed_plan_id": v3["id"],
        "reasons": [],
        "deviation_weeks": [],
    }

    # The superseded v1 keeps its original frame and content intact.
    v1_after = body(alice_api.call("GET", plan_url(v1["id"])))
    assert v1_after["status"] == "superseded"
    assert len(v1_after["weeks"]) == len(v1["weeks"])


def test_confirming_an_outdated_replacement_retains_the_goal_change_hint(
    monkeypatch: pytest.MonkeyPatch, provide: Callable[..., Scripted]
) -> None:
    set_clock(monkeypatch, NOW)
    alice, alice_api = prepare_athlete("alice@example.com")
    race_id = create_main_race(alice_api, MONDAY + timedelta(weeks=5, days=6))
    v1 = generate_and_confirm(alice, alice_api, provide)

    first_move = MONDAY + timedelta(weeks=6, days=6)
    second_move = MONDAY + timedelta(weeks=8, days=6)
    assert (
        alice_api.call(
            "PATCH", f"{GOALS_URL}{race_id}/", {"target_date": first_move.isoformat()}
        ).status_code
        == HTTPStatus.OK
    )

    provide(following(skeleton_for(alice), rationale="First adjustment."))
    v2_response = alice_api.call(
        "POST", plan_url(v1["id"], "change/"), {"request": "Shift race by one week."}
    )
    assert v2_response.status_code == HTTPStatus.CREATED
    v2 = body(v2_response)

    # Another goal change before confirmation leaves v2 outdated even once confirmed.
    assert (
        alice_api.call(
            "PATCH", f"{GOALS_URL}{race_id}/", {"target_date": second_move.isoformat()}
        ).status_code
        == HTTPStatus.OK
    )
    assert alice_api.call("POST", plan_url(v2["id"], "confirm/")).status_code == HTTPStatus.OK
    assert body(alice_api.call("GET", REASSESSMENT_URL)) == {
        "confirmed_plan_id": v2["id"],
        "reasons": ["goals_changed"],
        "deviation_weeks": [],
    }


def test_three_weak_completed_weeks_lifecycle_with_scripted_provider(
    monkeypatch: pytest.MonkeyPatch, provide: Callable[..., Scripted]
) -> None:
    set_clock(monkeypatch, NOW)
    alice, alice_api = prepare_athlete("alice@example.com")
    bob, bob_api = prepare_athlete("bob@example.com")
    race_date = MONDAY + timedelta(weeks=10, days=6)
    create_main_race(alice_api, race_date, title="Spring Half")
    create_main_race(bob_api, race_date, title="Bob Half")

    v1 = generate_and_confirm(alice, alice_api, provide)
    bob_v1 = generate_and_confirm(bob, bob_api, provide)

    # Three consecutive completed weeks strictly after confirmation, each at 50% of planned.
    evidence_weeks = tuple(MONDAY + timedelta(weeks=offset) for offset in (1, 2, 3))
    for monday in evidence_weeks:
        make_plan(alice, monday, workouts=1)
        make_activity(alice, f"{monday}T12:00", timer_seconds=1800)
        make_plan(bob, monday, workouts=1)
        make_activity(bob, f"{monday}T12:00", timer_seconds=3600)

    check_now = NOW + timedelta(weeks=4)
    set_clock(monkeypatch, check_now)

    # Viewing Week review and reassessment is read-only and never drafts automatically.
    versions_before = SeasonPlanVersion.objects.for_user(alice).count()
    with (
        patch("coach.services.call", side_effect=AssertionError("Unexpected coach call")),
        patch("coach.services.provider_for", side_effect=AssertionError("Unexpected provider")),
        patch(
            "integrations.intervals.IntervalsClient.__init__",
            side_effect=AssertionError("Unexpected Intervals call"),
        ),
    ):
        weeks_response = alice_api.call("GET", REVIEW_WEEKS_URL)
        assert weeks_response.status_code == HTTPStatus.OK
        review_response = alice_api.call("GET", f"{REVIEW_WEEKS_URL}{evidence_weeks[-1]}/")
        assert review_response.status_code == HTTPStatus.OK
        reassessment_response = alice_api.call("GET", REASSESSMENT_URL)
        assert reassessment_response.status_code == HTTPStatus.OK
        bob_reassessment = bob_api.call("GET", REASSESSMENT_URL)
        assert bob_reassessment.status_code == HTTPStatus.OK

    expected_proposal = {
        "confirmed_plan_id": v1["id"],
        "reasons": ["training_deviation"],
        "deviation_weeks": [week.isoformat() for week in evidence_weeks],
    }
    assert body(reassessment_response) == expected_proposal
    assert body(bob_reassessment) == {
        "confirmed_plan_id": bob_v1["id"],
        "reasons": [],
        "deviation_weeks": [],
    }
    assert SeasonPlanVersion.objects.for_user(alice).count() == versions_before

    # Explicit change request drafts an adjustment, keeping the proposal until confirmed.
    current_skeleton = skeleton_for(alice)
    scripted = provide(following(current_skeleton, rationale="Adjusted after three light weeks."))
    change_response = alice_api.call(
        "POST",
        plan_url(v1["id"], "change/"),
        {"request": "Lower the upcoming build volume after three light weeks."},
    )
    assert change_response.status_code == HTTPStatus.CREATED
    v2 = body(change_response)
    assert (v2["status"], v2["parent"]) == ("draft", v1["id"])
    sent = sent_payload(scripted)
    assert sent["change_request"] == "Lower the upcoming build volume after three light weeks."
    assert body(alice_api.call("GET", REASSESSMENT_URL)) == expected_proposal

    # Confirming the adjustment replaces v1 and resets the three-week window.
    confirm_response = alice_api.call("POST", plan_url(v2["id"], "confirm/"))
    assert confirm_response.status_code == HTTPStatus.OK
    assert body(alice_api.call("GET", REASSESSMENT_URL)) == {
        "confirmed_plan_id": v2["id"],
        "reasons": [],
        "deviation_weeks": [],
    }
    assert body(alice_api.call("GET", plan_url(v1["id"])))["status"] == "superseded"
