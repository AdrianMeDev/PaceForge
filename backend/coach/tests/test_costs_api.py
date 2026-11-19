import json
from datetime import UTC, datetime
from decimal import Decimal
from http import HTTPStatus
from typing import Any

import pytest

from accounts.models import User
from accounts.tests.conftest import AuthApi
from coach import pricing
from coach.models import MAX_MODEL_PRICES, AIModelPrice, AIProviderConfiguration, AIUsageRecord

from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

COSTS = "/api/coach/costs/"
PRICES = "/api/coach/costs/prices/"
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
MODEL = "claude-sonnet-5-5"


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pricing, "_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def body(response: Any) -> Any:
    return json.loads(response.content)


def put(api: AuthApi, **fields: Any) -> Any:
    data: dict[str, Any] = {
        "model": MODEL,
        "input_per_million": 3,
        "output_per_million": 15,
        **fields,
    }
    return api.call("PUT", PRICES, data)


def make_price(owner: User, model: str = MODEL, **fields: Any) -> AIModelPrice:
    data: dict[str, Any] = {
        "input_per_million": Decimal(3),
        "output_per_million": Decimal(15),
        **fields,
    }
    return AIModelPrice.objects.create(owner=owner, model=model, **data)


def make_call(owner: User, model: str = MODEL, **fields: Any) -> None:
    data: dict[str, Any] = {
        "provider": "anthropic",
        "purpose": "check",
        "outcome": "success",
        "input_tokens": 1_000_000,
        "output_tokens": 100_000,
        **fields,
    }
    record = AIUsageRecord.objects.create(owner=owner, model=model, **data)
    AIUsageRecord.objects.filter(pk=record.pk).update(created_at=NOW)


class TestAccess:
    @pytest.mark.parametrize(
        ("method", "url"),
        [("GET", COSTS), ("PUT", PRICES), ("DELETE", f"{PRICES}1/")],
    )
    def test_anonymous_visitors_are_refused(self, method: str, url: str) -> None:
        response = AuthApi().call(method, url, {})

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert not AIModelPrice.objects.exists()

    @pytest.mark.parametrize("method", ["PUT", "DELETE"])
    def test_a_request_without_the_csrf_token_is_refused(self, alice: User, method: str) -> None:
        price = make_price(alice)
        api = signed_in(alice)

        response = api.client.generic(
            method,
            f"{PRICES}{price.pk}/" if method == "DELETE" else PRICES,
            data=json.dumps({"model": "m", "input_per_million": 1, "output_per_million": 1}),
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert AIModelPrice.objects.get(pk=price.pk).input_per_million == Decimal(3)

    @pytest.mark.parametrize(
        ("method", "url"),
        [
            ("POST", COSTS),
            ("PUT", COSTS),
            ("DELETE", COSTS),
            ("GET", PRICES),
            ("POST", PRICES),
            ("DELETE", PRICES),
            ("GET", f"{PRICES}1/"),
            ("PUT", f"{PRICES}1/"),
        ],
    )
    def test_other_methods_are_not_allowed(self, alice: User, method: str, url: str) -> None:
        response = signed_in(alice).call(method, url, {})

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED


class TestReadingTheCosts:
    def test_a_new_user_has_neither_prices_nor_months(self, alice: User) -> None:
        response = signed_in(alice).call("GET", COSTS)

        assert response.status_code == HTTPStatus.OK
        assert body(response) == {"prices": [], "months": []}

    def test_without_a_price_there_is_no_cost(self, alice: User) -> None:
        make_call(alice)

        (month,) = body(signed_in(alice).call("GET", COSTS))["months"]

        assert month["month"] == "2026-11"
        assert month["calls"] == 1
        assert month["input_tokens"] == 1_000_000
        assert month["cost"] is None
        assert month["unpriced_models"] == [MODEL]

    def test_with_a_price_the_cost_is_exact(self, alice: User) -> None:
        make_price(alice)
        make_call(alice)

        (month,) = body(signed_in(alice).call("GET", COSTS))["months"]

        assert month["cost"] == "4.5000"
        assert month["unpriced_models"] == []

    def test_a_model_without_a_price_is_named(self, alice: User) -> None:
        make_price(alice)
        make_call(alice)
        make_call(alice, model="other")

        (month,) = body(signed_in(alice).call("GET", COSTS))["months"]

        assert month["calls"] == 2
        assert month["cost"] == "4.5000"
        assert month["unpriced_models"] == ["other"]

    def test_the_prices_are_listed_by_model(self, alice: User) -> None:
        make_price(alice, "b-model", cached_per_million=Decimal("0.3"))
        first = make_price(alice, "a-model")

        prices = body(signed_in(alice).call("GET", COSTS))["prices"]

        assert prices == [
            {
                "id": first.pk,
                "model": "a-model",
                "input_per_million": "3.0000",
                "output_per_million": "15.0000",
                "cached_per_million": None,
            },
            {
                "id": prices[1]["id"],
                "model": "b-model",
                "input_per_million": "3.0000",
                "output_per_million": "15.0000",
                "cached_per_million": "0.3000",
            },
        ]

    def test_another_users_prices_and_calls_are_not_shown(self, alice: User, bob: User) -> None:
        make_price(bob)
        make_call(bob)

        assert body(signed_in(alice).call("GET", COSTS)) == {"prices": [], "months": []}


class TestSettingAPrice:
    def test_a_price_is_created_and_the_state_returned(self, alice: User) -> None:
        make_call(alice)

        response = put(signed_in(alice), cached_per_million=0.3)

        assert response.status_code == HTTPStatus.OK
        answer = body(response)
        assert [p["model"] for p in answer["prices"]] == [MODEL]
        assert answer["prices"][0]["cached_per_million"] == "0.3000"
        assert answer["months"][0]["cost"] == "4.5000"
        price = AIModelPrice.objects.get(owner=alice)
        assert (price.input_per_million, price.output_per_million) == (Decimal(3), Decimal(15))

    def test_a_known_model_is_replaced(self, alice: User) -> None:
        old = make_price(alice, cached_per_million=Decimal(1))

        response = put(signed_in(alice), input_per_million=1.25, output_per_million=0)

        assert response.status_code == HTTPStatus.OK
        price = AIModelPrice.objects.get(owner=alice)
        assert price.pk == old.pk
        assert price.input_per_million == Decimal("1.25")
        assert price.output_per_million == Decimal(0)
        assert price.cached_per_million is None

    @pytest.mark.parametrize("value", [0, 0.0, 1, 0.0001, 12.5, 999999.9999])
    def test_numbers_inside_the_range_are_accepted(self, alice: User, value: float) -> None:
        assert put(signed_in(alice), input_per_million=value).status_code == HTTPStatus.OK

    @pytest.mark.parametrize(
        "value",
        [
            "3",
            "3.5",
            True,
            False,
            [3],
            {"a": 3},
            -1,
            -0.0001,
            1000000,
            999999.99991,
            0.00001,
            1.23456,
        ],
    )
    @pytest.mark.parametrize("field", ["input_per_million", "output_per_million"])
    def test_other_values_are_refused(self, alice: User, field: str, value: Any) -> None:
        response = put(signed_in(alice), **{field: value})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert field in body(response)
        assert not AIModelPrice.objects.exists()

    @pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
    def test_not_a_number_is_refused(self, alice: User, value: str) -> None:
        api = signed_in(alice)
        # JSON has no NaN, but Python's parser would take it.
        raw = f'{{"model": "m", "input_per_million": {value}, "output_per_million": 1}}'

        response = api.client.generic(
            "PUT",
            PRICES,
            data=raw,
            content_type="application/json",
            headers={"X-CSRFToken": api.client.cookies["csrftoken"].value},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert not AIModelPrice.objects.exists()

    def test_the_cached_price_is_checked_too(self, alice: User) -> None:
        for value in ("1", True, -1, 1.00001):
            response = put(signed_in(alice), cached_per_million=value)

            assert response.status_code == HTTPStatus.BAD_REQUEST
            assert "cached_per_million" in body(response)
        assert not AIModelPrice.objects.exists()

    def test_a_null_cached_price_means_none(self, alice: User) -> None:
        make_price(alice, cached_per_million=Decimal(1))

        assert put(signed_in(alice), cached_per_million=None).status_code == HTTPStatus.OK
        assert AIModelPrice.objects.get(owner=alice).cached_per_million is None

    @pytest.mark.parametrize("field", ["model", "input_per_million", "output_per_million"])
    def test_a_missing_field_is_refused(self, alice: User, field: str) -> None:
        data = {"model": "m", "input_per_million": 1, "output_per_million": 1}
        del data[field]

        response = signed_in(alice).call("PUT", PRICES, data)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert field in body(response)

    @pytest.mark.parametrize("model", [3, None, "", "  ", "-bad", "a b", "x" * 101])
    def test_a_bad_model_name_is_refused(self, alice: User, model: Any) -> None:
        response = put(signed_in(alice), model=model)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "model" in body(response)
        assert not AIModelPrice.objects.exists()

    def test_the_limit_stops_a_new_model_but_not_a_known_one(self, alice: User) -> None:
        AIModelPrice.objects.bulk_create(
            AIModelPrice(
                owner=alice,
                model=f"m{number}",
                input_per_million=Decimal(1),
                output_per_million=Decimal(1),
            )
            for number in range(MAX_MODEL_PRICES)
        )
        api = signed_in(alice)

        refused = put(api, model="one-too-many")
        known = put(api, model="m0", input_per_million=2)

        assert refused.status_code == HTTPStatus.BAD_REQUEST
        assert "model" in body(refused)
        assert known.status_code == HTTPStatus.OK
        assert AIModelPrice.objects.filter(owner=alice).count() == MAX_MODEL_PRICES

    def test_the_limit_is_per_user(self, alice: User, bob: User) -> None:
        AIModelPrice.objects.bulk_create(
            AIModelPrice(
                owner=bob,
                model=f"m{number}",
                input_per_million=Decimal(1),
                output_per_million=Decimal(1),
            )
            for number in range(MAX_MODEL_PRICES)
        )

        assert put(signed_in(alice)).status_code == HTTPStatus.OK

    def test_the_same_model_of_two_users_does_not_clash(self, alice: User, bob: User) -> None:
        make_price(bob, input_per_million=Decimal(9))

        assert put(signed_in(alice)).status_code == HTTPStatus.OK

        assert AIModelPrice.objects.get(owner=bob).input_per_million == Decimal(9)
        assert AIModelPrice.objects.get(owner=alice).input_per_million == Decimal(3)

    def test_the_provider_status_is_left_alone(self, alice: User) -> None:
        AIProviderConfiguration.objects.create(
            owner=alice,
            provider="anthropic",
            model=MODEL,
            api_key="sk-ant-test-0123456789-abcdefghij",
            status="connected",
        )
        api = signed_in(alice)
        price = body(put(api))["prices"][0]

        api.call("DELETE", f"{PRICES}{price['id']}/")

        assert AIProviderConfiguration.objects.get(owner=alice).status == "connected"


class TestDeletingAPrice:
    def test_a_price_is_deleted(self, alice: User) -> None:
        price = make_price(alice)

        response = signed_in(alice).call("DELETE", f"{PRICES}{price.pk}/")

        assert response.status_code == HTTPStatus.NO_CONTENT
        assert not AIModelPrice.objects.exists()

    def test_an_unknown_id_is_not_found(self, alice: User) -> None:
        response = signed_in(alice).call("DELETE", f"{PRICES}999999/")

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_deleting_twice_is_not_found_the_second_time(self, alice: User) -> None:
        price = make_price(alice)
        api = signed_in(alice)

        api.call("DELETE", f"{PRICES}{price.pk}/")

        assert api.call("DELETE", f"{PRICES}{price.pk}/").status_code == HTTPStatus.NOT_FOUND

    def test_another_users_price_is_not_found_and_stays(self, alice: User, bob: User) -> None:
        price = make_price(bob)

        response = signed_in(alice).call("DELETE", f"{PRICES}{price.pk}/")

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert AIModelPrice.objects.filter(pk=price.pk).exists()

    def test_the_answer_for_a_foreign_and_an_unknown_id_is_the_same(
        self, alice: User, bob: User
    ) -> None:
        foreign = make_price(bob)
        api = signed_in(alice)

        assert body(api.call("DELETE", f"{PRICES}{foreign.pk}/")) == body(
            api.call("DELETE", f"{PRICES}999999/")
        )
