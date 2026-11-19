from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import ValidationError

from accounts.models import User
from athletes.models import AthleteProfile
from coach import pricing
from coach.models import MAX_MODEL_PRICES, PRICE_MAX, AIModelPrice, AIUsageRecord

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pricing, "_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def price(**fields: Any) -> AIModelPrice:
    data: dict[str, Any] = {
        "model": "m",
        "input_per_million": Decimal(3),
        "output_per_million": Decimal(15),
        **fields,
    }
    return AIModelPrice(**data)


def add(owner: User, at: datetime, **fields: Any) -> None:
    data: dict[str, Any] = {
        "provider": "anthropic",
        "model": "m",
        "purpose": "check",
        "outcome": "success",
        "input_tokens": 1_000_000,
        "output_tokens": 100_000,
        **fields,
    }
    record = AIUsageRecord.objects.create(owner=owner, **data)
    AIUsageRecord.objects.filter(pk=record.pk).update(created_at=at)


def at(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


class TestTheCostOfACall:
    def test_input_and_output_are_charged_per_million(self) -> None:
        assert pricing.cost_of(price(), 1_000_000, 100_000) == Decimal("4.5")

    def test_the_result_is_an_exact_decimal(self) -> None:
        found = pricing.cost_of(price(input_per_million=Decimal("0.1")), 3, 0)

        assert found == Decimal("0.0000003")

    def test_cached_tokens_use_the_cached_price(self) -> None:
        found = pricing.cost_of(price(cached_per_million=Decimal("0.3")), 1_000_000, 0, 600_000)

        assert found == Decimal("1.2") + Decimal("0.18")

    def test_without_a_cached_price_the_input_price_applies(self) -> None:
        assert pricing.cost_of(price(), 1_000_000, 0, 600_000) == Decimal(3)

    def test_a_cached_price_of_zero_is_not_a_missing_one(self) -> None:
        found = pricing.cost_of(price(cached_per_million=Decimal(0)), 1_000_000, 0, 1_000_000)

        assert found == Decimal(0)

    def test_unknown_token_counts_are_zero(self) -> None:
        assert pricing.cost_of(price(), None, None, None) == Decimal(0)
        assert pricing.cost_of(price(), None, 1_000_000, 5) == Decimal(15)

    def test_zero_prices_cost_nothing(self) -> None:
        free = price(input_per_million=Decimal(0), output_per_million=Decimal(0))

        assert pricing.cost_of(free, 1_000_000, 1_000_000, 10) == Decimal(0)

    def test_more_cached_than_input_is_capped_at_the_input(self) -> None:
        found = pricing.cost_of(price(cached_per_million=Decimal(1)), 100, 0, 500)

        assert found == Decimal(100) / Decimal(1_000_000)


class TestThePrices:
    def test_save_creates_and_then_replaces(self, alice: User) -> None:
        pricing.save_price(alice, "m", Decimal(1), Decimal(2))
        pricing.save_price(alice, "m", Decimal(3), Decimal(4), Decimal(1))

        [found] = pricing.list_prices(alice)
        assert (found.input_per_million, found.output_per_million) == (3, 4)
        assert found.cached_per_million == 1

    def test_the_list_is_sorted_by_model_and_own(self, alice: User, bob: User) -> None:
        pricing.save_price(alice, "b", Decimal(1), Decimal(1))
        pricing.save_price(alice, "a", Decimal(1), Decimal(1))
        pricing.save_price(bob, "c", Decimal(1), Decimal(1))

        assert [p.model for p in pricing.list_prices(alice)] == ["a", "b"]

    @pytest.mark.parametrize(
        ("model", "input_price"),
        [("not a model", Decimal(1)), ("m", Decimal(-1)), ("m", PRICE_MAX + 1)],
    )
    def test_bad_values_are_refused(self, alice: User, model: str, input_price: Decimal) -> None:
        with pytest.raises(ValidationError):
            pricing.save_price(alice, model, input_price, Decimal(1))

        assert not AIModelPrice.objects.exists()

    def test_the_number_of_prices_is_limited_but_a_change_is_not(self, alice: User) -> None:
        for number in range(MAX_MODEL_PRICES):
            pricing.save_price(alice, f"m{number}", Decimal(1), Decimal(1))

        with pytest.raises(pricing.PriceLimitError):
            pricing.save_price(alice, "one-more", Decimal(1), Decimal(1))
        pricing.save_price(alice, "m0", Decimal(2), Decimal(2))

    def test_delete_removes_only_the_own_price(self, alice: User, bob: User) -> None:
        pricing.save_price(alice, "m", Decimal(1), Decimal(1))
        pricing.save_price(bob, "m", Decimal(1), Decimal(1))

        assert pricing.delete_price(alice, "m") is True
        assert pricing.delete_price(alice, "m") is False
        assert pricing.list_prices(alice) == []
        assert len(pricing.list_prices(bob)) == 1


class TestTheMonthlyUsage:
    def test_nothing_gives_no_months(self, alice: User) -> None:
        assert pricing.monthly_usage(alice) == []

    def test_months_come_newest_first_with_their_totals(self, alice: User) -> None:
        pricing.save_price(alice, "m", Decimal(3), Decimal(15), Decimal(1))
        add(alice, at(2026, 9, 30))
        add(alice, at(2026, 11, 2), cache_read_tokens=500_000, cache_write_tokens=7)
        add(alice, at(2026, 11, 3), input_tokens=None, output_tokens=None)

        [november, september] = pricing.monthly_usage(alice)

        assert (november.month, september.month) == ("2026-11", "2026-09")
        assert november.calls == 2
        assert (november.input_tokens, november.output_tokens) == (1_000_000, 100_000)
        assert (november.cache_read_tokens, november.cache_write_tokens) == (500_000, 7)
        assert november.cost == Decimal("1.5") + Decimal("0.5") + Decimal("1.5")
        assert november.unpriced_models == []
        assert september.cost == Decimal("4.5")

    def test_a_model_without_a_price_is_named_and_left_out_of_the_cost(self, alice: User) -> None:
        pricing.save_price(alice, "m", Decimal(3), Decimal(15))
        add(alice, at(2026, 11, 2))
        add(alice, at(2026, 11, 3), model="zeta")
        add(alice, at(2026, 11, 4), model="alpha")

        [november] = pricing.monthly_usage(alice)

        assert november.calls == 3
        assert november.cost == Decimal("4.5")
        assert november.unpriced_models == ["alpha", "zeta"]

    def test_a_month_with_only_unpriced_models_has_no_cost(self, alice: User) -> None:
        add(alice, at(2026, 11, 2))

        [november] = pricing.monthly_usage(alice)

        assert november.cost is None
        assert november.unpriced_models == ["m"]

    def test_a_month_with_only_zero_prices_costs_zero_not_nothing(self, alice: User) -> None:
        pricing.save_price(alice, "m", Decimal(0), Decimal(0))
        add(alice, at(2026, 11, 2))

        assert pricing.monthly_usage(alice)[0].cost == Decimal(0)

    def test_only_the_last_twelve_months_count(self, alice: User) -> None:
        add(alice, at(2025, 12, 1, 0))  # the first month that counts
        add(alice, at(2025, 11, 30, 23))

        assert [m.month for m in pricing.monthly_usage(alice)] == ["2025-12"]

    def test_the_month_is_the_one_in_the_users_time_zone(self, alice: User) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="Pacific/Auckland")
        add(alice, at(2026, 10, 31, 12))  # 01:00 on 1 November in Auckland (UTC+13)

        assert [m.month for m in pricing.monthly_usage(alice)] == ["2026-11"]

    def test_the_default_time_zone_is_utc(self, alice: User) -> None:
        add(alice, at(2026, 10, 31, 23))

        assert [m.month for m in pricing.monthly_usage(alice)] == ["2026-10"]

    def test_the_window_starts_at_the_local_start_of_the_month(self, alice: User) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="America/Los_Angeles")
        add(alice, datetime(2025, 12, 1, 8, 30, tzinfo=UTC))  # 00:30 on 1 December there: in
        add(alice, datetime(2025, 12, 1, 7, 30, tzinfo=UTC))  # 23:30 on 30 November there: out

        found = pricing.monthly_usage(alice)

        assert [(m.month, m.calls) for m in found] == [("2025-12", 1)]

    def test_other_users_calls_and_prices_are_ignored(self, alice: User, bob: User) -> None:
        pricing.save_price(bob, "m", Decimal(3), Decimal(15))
        add(bob, at(2026, 11, 2))
        add(alice, at(2026, 11, 2))

        [november] = pricing.monthly_usage(alice)

        assert november.calls == 1
        assert november.cost is None
        assert november.unpriced_models == ["m"]
