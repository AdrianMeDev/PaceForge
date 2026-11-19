"""Input checks and the shape of what the AI provider API answers.

The answer is built by hand from the user's own values. The key is never part of it, not even in
part: the API says whether one is stored and nothing more.
"""

import math
from decimal import Decimal
from typing import Any

from django.conf import settings
from rest_framework import serializers

from accounts.models import User
from core.encryption import DecryptionError
from goals.serializers import TextField

from . import pricing, services
from .models import BASE_URL_MAX, KEY_MAX, MODEL_MAX, PRICE_MAX, AIProviderConfiguration

PRICE_PLACES = 4


class ProviderInput(serializers.Serializer[Any]):
    """What may be sent to set up the provider. Strict: text is text, nothing is guessed."""

    provider = serializers.ChoiceField(choices=AIProviderConfiguration.Provider.choices)
    model = TextField(max_length=MODEL_MAX)
    # The model for the plan of the whole season; absent or empty: the normal model.
    season_model = TextField(max_length=MODEL_MAX, allow_blank=True, required=False)
    # Likewise for the weekly plan and for the coach chat.
    week_model = TextField(max_length=MODEL_MAX, allow_blank=True, required=False)
    chat_model = TextField(max_length=MODEL_MAX, allow_blank=True, required=False)
    base_url = TextField(max_length=BASE_URL_MAX, allow_blank=True, required=False)
    # Absent: keep the stored key (while provider and address stay). Empty: no key.
    api_key = TextField(max_length=KEY_MAX, allow_blank=True, required=False)


class PriceField(serializers.Field[Decimal, Any, Any, Any]):
    """A price per million tokens: a JSON number from 0 to ``PRICE_MAX`` with at most four
    decimal places. Text that looks like a number and true/false are not prices."""

    default_error_messages = {
        "invalid": "Enter a price as a number.",
        "range": f"Enter a price from 0 to {PRICE_MAX}.",
        "places": f"Use at most {PRICE_PLACES} decimal places.",
    }

    def to_internal_value(self, data: Any) -> Decimal:
        if isinstance(data, bool) or not isinstance(data, int | float):
            self.fail("invalid")
        if isinstance(data, float) and not math.isfinite(data):
            self.fail("invalid")
        value = Decimal(data) if isinstance(data, int) else Decimal(repr(data))
        if not Decimal(0) <= value <= PRICE_MAX:
            self.fail("range")
        if value != value.quantize(Decimal(1).scaleb(-PRICE_PLACES)):
            self.fail("places")
        return value

    def to_representation(self, value: Decimal) -> str:
        return format(value, "f")


class ModelPriceInput(serializers.Serializer[Any]):
    """What may be sent to set the price of one model. Absent or null cached price: none."""

    model = TextField(max_length=MODEL_MAX)
    input_per_million = PriceField()
    output_per_million = PriceField()
    cached_per_million = PriceField(allow_null=True, required=False)


def provider_state(user: User) -> dict[str, Any]:
    """The user's provider setup, the operator's allowed addresses and the recent usage."""
    configuration = services.get_configuration(user)
    usage = services.usage_summary(user)
    state: dict[str, Any] = {
        "configured": configuration is not None,
        "provider": None,
        "model": "",
        "season_model": "",
        "week_model": "",
        "chat_model": "",
        "base_url": None,
        "has_key": False,
        "status": None,
        "last_checked_at": None,
        "last_success_at": None,
        "allowed_base_urls": list(settings.AI_ALLOWED_BASE_URLS),
        "usage": {
            "calls": usage.calls,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_read_tokens": usage.cache_read_tokens,
            "cache_write_tokens": usage.cache_write_tokens,
            "days": usage.days,
        },
    }
    if configuration is not None:
        timestamp = serializers.DateTimeField()
        state.update(
            provider=configuration.provider,
            model=configuration.model,
            season_model=configuration.season_model,
            week_model=configuration.week_model,
            chat_model=configuration.chat_model,
            base_url=configuration.base_url or None,
            has_key=_has_key(configuration),
            status=configuration.status,
            last_checked_at=_time(timestamp, configuration.last_checked_at),
            last_success_at=_time(timestamp, configuration.last_success_at),
        )
    return state


def _has_key(configuration: AIProviderConfiguration) -> bool:
    try:
        return bool(configuration.api_key)
    except DecryptionError:
        return False  # a key that cannot be read is as good as none


def _time(field: serializers.DateTimeField, value: Any) -> Any:
    return None if value is None else field.to_representation(value)


def costs_state(user: User) -> dict[str, Any]:
    """The user's own prices and their calls and costs per month, newest month first."""
    price_field = PriceField()
    cost_places = Decimal(1).scaleb(-PRICE_PLACES)
    return {
        "prices": [
            {
                "id": price.pk,
                "model": price.model,
                "input_per_million": price_field.to_representation(price.input_per_million),
                "output_per_million": price_field.to_representation(price.output_per_million),
                "cached_per_million": (
                    None
                    if price.cached_per_million is None
                    else price_field.to_representation(price.cached_per_million)
                ),
            }
            for price in pricing.list_prices(user)
        ],
        "months": [
            {
                "month": usage.month,
                "calls": usage.calls,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read_tokens": usage.cache_read_tokens,
                "cache_write_tokens": usage.cache_write_tokens,
                "cost": (
                    None
                    if usage.cost is None
                    else price_field.to_representation(usage.cost.quantize(cost_places))
                ),
                "unpriced_models": usage.unpriced_models,
            }
            for usage in pricing.monthly_usage(user)
        ],
    }
