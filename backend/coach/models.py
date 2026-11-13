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
        if errors:
            raise ValidationError(errors)
