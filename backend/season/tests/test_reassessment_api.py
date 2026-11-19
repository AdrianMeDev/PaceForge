import json
from http import HTTPStatus
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from accounts.tests.conftest import AuthApi
from athletes.models import BestTime, ThresholdValue
from availability.models import AvailabilitySettings, UnavailablePeriod, WeekdayMinutes
from goals import services as goal_services
from goals.models import Goal
from season import services
from season.models import SeasonPlanVersion

from .conftest import make_user, signed_in
from .test_reassessment import MONDAY, NOW, confirmed, draft, race, train

pytestmark = pytest.mark.django_db

URL = "/api/season/reassessment/"


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    user = make_user("alice@example.com")
    train(user)
    return user


def test_authentication_is_required() -> None:
    assert AuthApi().call("GET", URL).status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_write_methods_are_refused(alice: User, method: str) -> None:
    assert signed_in(alice).call(method, URL, {}).status_code == HTTPStatus.METHOD_NOT_ALLOWED


def test_no_confirmed_plan_returns_an_explicit_empty_answer(alice: User) -> None:
    draft(alice)
    response = signed_in(alice).call("GET", URL)

    assert response.status_code == HTTPStatus.OK
    assert json.loads(response.content) == {
        "confirmed_plan_id": None,
        "reasons": [],
        "deviation_weeks": [],
    }


def test_response_names_the_confirmed_plan_and_only_stable_reason_codes(alice: User) -> None:
    plan = confirmed(alice)
    race(alice)
    ThresholdValue.objects.create(
        owner=alice, sport="ride", metric="ftp", source="manual", value=250
    )
    BestTime.objects.create(owner=alice, distance="5k", seconds=1200, date=MONDAY)
    WeekdayMinutes.objects.for_user(alice).update(minutes=120)

    response = signed_in(alice).call("GET", URL)

    assert response.status_code == HTTPStatus.OK
    assert json.loads(response.content) == {
        "confirmed_plan_id": str(plan.pk),
        "reasons": ["goals_changed", "ftp_changed", "best_times_changed", "training_time_changed"],
        "deviation_weeks": [],
    }


def test_endpoint_tracks_the_confirmed_version_through_the_lifecycle(alice: User) -> None:
    plan = confirmed(alice)
    race(alice)
    api = signed_in(alice)
    hint = {"confirmed_plan_id": str(plan.pk), "reasons": ["goals_changed"], "deviation_weeks": []}
    replacement = draft(alice)
    assert json.loads(api.call("GET", URL).content) == hint
    services.discard(alice, replacement.pk)
    assert json.loads(api.call("GET", URL).content) == hint
    replacement = confirmed(alice)
    assert json.loads(api.call("GET", URL).content) == {
        "confirmed_plan_id": str(replacement.pk),
        "reasons": [],
        "deviation_weeks": [],
    }


def test_get_only_reads_and_makes_no_external_calls(alice: User) -> None:
    plan = confirmed(alice)
    race(alice)
    before = list(SeasonPlanVersion.objects.values())
    api = signed_in(alice)
    with (
        patch("coach.services.call", side_effect=AssertionError("Unexpected coach call")),
        patch("coach.services.provider_for", side_effect=AssertionError("Unexpected provider")),
        patch(
            "integrations.intervals.IntervalsClient.__init__",
            side_effect=AssertionError("Unexpected Intervals call"),
        ),
        CaptureQueriesContext(connection) as queries,
    ):
        first = api.call("GET", URL)
        second = api.call("GET", URL)

    assert first.status_code == second.status_code == HTTPStatus.OK
    assert (
        json.loads(first.content)
        == json.loads(second.content)
        == {"confirmed_plan_id": str(plan.pk), "reasons": ["goals_changed"], "deviation_weeks": []}
    )
    assert queries.captured_queries
    assert all(query["sql"].lstrip().upper().startswith("SELECT") for query in queries)
    assert list(SeasonPlanVersion.objects.values()) == before
    assert not AvailabilitySettings.objects.exists()


def test_missing_inputs_are_not_created_on_get(alice: User) -> None:
    confirmed(alice)
    response = signed_in(alice).call("GET", URL)

    assert response.status_code == HTTPStatus.OK
    assert not AvailabilitySettings.objects.exists()
    assert not ThresholdValue.objects.exists()
    assert not BestTime.objects.exists()


def test_another_users_confirmed_plan_is_never_returned(alice: User) -> None:
    bob = make_user("bob@example.com")
    train(bob)
    confirmed(bob)
    race(bob)
    draft(alice)
    api = signed_in(alice)

    for path in (URL, f"{URL}?owner={bob.pk}", f"{URL}?user_id={bob.pk}"):
        response = api.call("GET", path)
        assert response.status_code == HTTPStatus.OK
        assert json.loads(response.content) == {
            "confirmed_plan_id": None,
            "reasons": [],
            "deviation_weeks": [],
        }


def test_all_comparison_inputs_and_capacities_are_isolated(alice: User) -> None:
    plan = confirmed(alice)
    bob = make_user("bob@example.com")
    train(bob)
    bob_plan = confirmed(bob)
    race(bob)
    ThresholdValue.objects.create(owner=bob, sport="ride", metric="ftp", source="manual", value=300)
    BestTime.objects.create(owner=bob, distance="5k", seconds=1200, date=MONDAY)
    AvailabilitySettings.objects.create(
        owner=bob, typical_weekly_minutes=300, weekly_budget_minutes=0
    )
    WeekdayMinutes.objects.for_user(bob).update(minutes=0)
    UnavailablePeriod.objects.create(owner=bob, kind="vacation", start_date=MONDAY, end_date=MONDAY)
    alice_api, bob_api = signed_in(alice), signed_in(bob)

    assert json.loads(alice_api.call("GET", f"{URL}?owner={bob.pk}").content) == {
        "confirmed_plan_id": str(plan.pk),
        "reasons": [],
        "deviation_weeks": [],
    }
    assert json.loads(bob_api.call("GET", URL).content) == {
        "confirmed_plan_id": str(bob_plan.pk),
        "reasons": ["goals_changed", "ftp_changed", "best_times_changed", "training_time_changed"],
        "deviation_weeks": [],
    }
    Goal.objects.for_user(bob).delete()
    assert json.loads(alice_api.call("GET", URL).content)["reasons"] == []
