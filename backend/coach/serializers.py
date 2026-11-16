"""Input checks and the shape of what the AI provider API answers.

The answer is built by hand from the user's own values. The key is never part of it, not even in
part: the API says whether one is stored and nothing more.
"""

from typing import Any

from django.conf import settings
from rest_framework import serializers

from accounts.models import User
from core.encryption import DecryptionError
from goals.serializers import TextField

from . import services
from .models import BASE_URL_MAX, KEY_MAX, MODEL_MAX, AIProviderConfiguration


class ProviderInput(serializers.Serializer[Any]):
    """What may be sent to set up the provider. Strict: text is text, nothing is guessed."""

    provider = serializers.ChoiceField(choices=AIProviderConfiguration.Provider.choices)
    model = TextField(max_length=MODEL_MAX)
    # The model for the plan of the whole season; absent or empty: the normal model.
    season_model = TextField(max_length=MODEL_MAX, allow_blank=True, required=False)
    base_url = TextField(max_length=BASE_URL_MAX, allow_blank=True, required=False)
    # Absent: keep the stored key (while provider and address stay). Empty: no key.
    api_key = TextField(max_length=KEY_MAX, allow_blank=True, required=False)


def provider_state(user: User) -> dict[str, Any]:
    """The user's provider setup, the operator's allowed addresses and the recent usage."""
    configuration = services.get_configuration(user)
    usage = services.usage_summary(user)
    state: dict[str, Any] = {
        "configured": configuration is not None,
        "provider": None,
        "model": "",
        "season_model": "",
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
