"""The AI providers behind one interface (``base.CoachProvider``), one module per API format."""

from typing import TYPE_CHECKING

from .anthropic import AnthropicProvider
from .base import CoachProvider
from .openai_compatible import OpenAICompatibleProvider

if TYPE_CHECKING:
    from coach.models import AIProviderConfiguration


def provider_for(configuration: AIProviderConfiguration) -> CoachProvider:
    """The adapter for a user's configuration. Raises ``EndpointNotAllowedError`` before any
    network call if an OpenAI-compatible address is no longer on the operator's list."""
    from coach.models import AIProviderConfiguration

    kind = AIProviderConfiguration.Provider
    if configuration.provider == kind.ANTHROPIC:
        return AnthropicProvider(configuration.api_key, configuration.model)
    if configuration.provider == kind.OPENAI_COMPATIBLE:
        return OpenAICompatibleProvider(
            configuration.base_url, configuration.model, configuration.api_key
        )
    raise ValueError("Unknown provider.")
