import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

from core.fields import EncryptedTextField
from core.models import OwnedModel

MODEL_MAX = 100
BASE_URL_MAX = 200
# Names such as claude-sonnet-5-5, gpt-4o, llama3.1:8b or org/model-name.
# \Z, not $: a $ also matches in front of a trailing line break.
MODEL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]*\Z"
# A key travels in an HTTP header: visible ASCII only, no spaces, no line breaks.
KEY_MAX = 500
KEY_PATTERN = re.compile(r"[\x21-\x7e]+")


class AIProviderConfiguration(OwnedModel):
    """The AI provider a user has chosen, with their own key and model. One per user.

    ``api_key`` is stored encrypted, cannot be edited through forms (``editable=False``) and must
    never be part of a serializer, a log line or an error message; the API only tells whether a
    key exists. Django skips the validation of non-editable fields, so ``clean()`` checks it.

    ``base_url`` is only for OpenAI-compatible endpoints and must be one of the addresses the
    operator allows (``AI_ALLOWED_BASE_URLS``): users must not point the server at arbitrary
    internal addresses.
    """

    class Provider(models.TextChoices):
        ANTHROPIC = "anthropic", "Anthropic"
        OPENAI_COMPATIBLE = "openai_compatible", "OpenAI-compatible"

    class Status(models.TextChoices):
        UNTESTED = "untested", "Not checked yet"
        CONNECTED = "connected", "Connected"
        INVALID = "invalid", "Key refused"  # the provider refused the key at the last call
        UNAVAILABLE = "unavailable", "Unavailable"  # the provider could not be reached

    provider = models.CharField(max_length=30, choices=Provider.choices)
    model = models.CharField(
        max_length=MODEL_MAX, validators=[RegexValidator(MODEL_PATTERN, "Enter a model name.")]
    )
    # The model for the plan of the whole season, a task that may call for a stronger one. Empty:
    # the normal model. Same provider, same key.
    season_model = models.CharField(
        max_length=MODEL_MAX,
        blank=True,
        validators=[RegexValidator(MODEL_PATTERN, "Enter a model name.")],
    )
    api_key = EncryptedTextField(editable=False)
    base_url = models.CharField(max_length=BASE_URL_MAX, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNTESTED)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner"], name="coach_one_provider_per_owner"),
            models.CheckConstraint(condition=~Q(model=""), name="coach_model_not_empty"),
            models.CheckConstraint(
                condition=~Q(provider="anthropic") | Q(base_url=""),
                name="coach_anthropic_has_no_base_url",
            ),
            models.CheckConstraint(
                condition=~Q(provider="openai_compatible") | ~Q(base_url=""),
                name="coach_compatible_has_base_url",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_provider_display()} configuration of user {self.owner_id}"

    def model_for(self, purpose: str) -> str:
        """The model that does ``purpose``: the season model for the season plan if one is set, the
        normal model for everything else."""
        if purpose == AIUsageRecord.Purpose.SEASON_PLAN and self.season_model:
            return self.season_model
        return self.model

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.provider == self.Provider.ANTHROPIC:
            if self.base_url:
                errors["base_url"] = "Anthropic needs no address."
            if not self.api_key:
                errors["api_key"] = "Anthropic needs a key."
        elif self.provider == self.Provider.OPENAI_COMPATIBLE:
            if not self.base_url:
                errors["base_url"] = "Choose the address of the endpoint."
            elif self.base_url not in settings.AI_ALLOWED_BASE_URLS:
                errors["base_url"] = "This address is not allowed on this server."
        if self.api_key and (
            len(self.api_key) > KEY_MAX or not KEY_PATTERN.fullmatch(self.api_key)
        ):
            errors["api_key"] = (
                "A key has no spaces or special characters and at most 500 characters."
            )
        if errors:
            raise ValidationError(errors)


class AIUsageRecord(OwnedModel):
    """One request to a user's AI provider, for the user's own overview.

    Only the facts of the call are kept: who, which provider and model, what for, how it ended
    and how many tokens were counted. Never the prompt, the answer or an error text from the
    provider: they can hold training data, notes and keys.
    """

    class Purpose(models.TextChoices):
        CHECK = "check", "Connection check"
        WEEKLY_PLAN = "weekly_plan", "Weekly plan"
        WEEK_REVIEW = "week_review", "Week review"
        SEASON_PLAN = "season_plan", "Season plan"
        CHAT = "chat", "Coach chat"

    class Outcome(models.TextChoices):
        SUCCESS = "success", "Success"
        INVALID_KEY = "invalid_key", "Key refused"
        RATE_LIMITED = "rate_limited", "Rate limited"
        UNAVAILABLE = "unavailable", "Unavailable"
        UNEXPECTED = "unexpected", "Unexpected answer"

    provider = models.CharField(max_length=30, choices=AIProviderConfiguration.Provider.choices)
    # What was used at the time; the configuration may be changed or removed later.
    model = models.CharField(max_length=MODEL_MAX)
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    # Counted by the provider; ``None`` where it did not say.
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    # The parts of the input that were read from and written to the provider's prompt cache (part
    # of ``input_tokens``, not on top of it); ``None`` where the provider did not say.
    cache_read_tokens = models.PositiveIntegerField(null=True, blank=True)
    cache_write_tokens = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["owner", "created_at"], name="coach_usage_owner_time")]

    def __str__(self) -> str:
        return f"{self.purpose} call of user {self.owner_id} ({self.outcome})"
