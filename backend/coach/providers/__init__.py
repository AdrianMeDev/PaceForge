"""The AI providers behind one interface (``base.CoachProvider``), one module per API format."""

from typing import TYPE_CHECKING

from .anthropic import AnthropicProvider
from .base import CoachProvider
from .openai_compatible import OpenAICompatibleProvider

if TYPE_CHECKING:
    from coach.models import AIProviderConfiguration


def provider_for(
    configuration: AIProviderConfiguration, model: str | None = None, effort: str = ""
) -> CoachProvider:
    """The adapter for a user's configuration, for ``model`` if one is given and else for the
    normal model, with ``effort`` (Anthropic only; empty: none is sent). Raises
    ``EndpointNotAllowedError`` before any network call if an OpenAI-compatible address is no
    longer on the operator's list."""
    from coach.models import AIProviderConfiguration

    kind = AIProviderConfiguration.Provider
    model = model or configuration.model
    if configuration.provider == kind.ANTHROPIC:
        return AnthropicProvider(configuration.api_key, model, effort=effort)
    if configuration.provider == kind.OPENAI_COMPATIBLE:
        return OpenAICompatibleProvider(configuration.base_url, model, configuration.api_key)
    raise ValueError("Unknown provider.")
