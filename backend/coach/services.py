"""Calling a user's AI provider, and keeping the books on it.

Every function acts on the configuration of the user it is given and on nothing else. The stored
key is decrypted only where a call needs it. The network call never runs inside a database
transaction. What is recorded about a call is in ``AIUsageRecord``: facts, never text.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, QuerySet, Sum
from django.utils import timezone

from accounts.models import User
from core.encryption import DecryptionError

from .models import AIProviderConfiguration, AIUsageRecord
from .providers import provider_for
from .providers.base import (
    Completion,
    InvalidKeyError,
    Message,
    ProviderUnavailableError,
    RateLimitedError,
    UnexpectedResponseError,
)

# What the connection check sends: nothing of the user's, and a tiny answer is enough.
CHECK_PROMPT = "Reply with the single word: ok"
CHECK_MAX_TOKENS = 16
USAGE_DAYS = 30

Status = AIProviderConfiguration.Status
Outcome = AIUsageRecord.Outcome


class NotConfiguredError(Exception):
    """The user has not chosen an AI provider."""


@dataclass(frozen=True)
class UsageSummary:
    calls: int
    input_tokens: int
    output_tokens: int
    days: int


def _now() -> datetime:
    return timezone.now()


def _own(user: User) -> QuerySet[AIProviderConfiguration]:
    # The key stays encrypted (not even loaded) unless a caller asks for it.
    return AIProviderConfiguration.objects.for_user(user).defer("api_key")


def get_configuration(user: User) -> AIProviderConfiguration | None:
    return _own(user).first()


def save_configuration(
    user: User, *, provider: str, model: str, base_url: str, api_key: str | None
) -> AIProviderConfiguration:
    """Create or change the user's configuration.

    ``api_key`` is the new key, ``""`` for none, or ``None`` for "keep the stored one". A stored
    key is only kept while provider and address stay the same: it must never be sent to a
    place the user did not give it for. Anything that changes what is called (provider, model,
    address, key) sets the status back to ``untested`` and forgets the times of the last check.

    Raises Django's ``ValidationError`` (by field) and saves nothing if the result is not valid.
    """
    for attempt in (1, 2):
        try:
            with transaction.atomic():
                return _save(user, provider, model, base_url, api_key)
        except IntegrityError:
            # A second request created the row first; the next round changes that one.
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def _save(
    user: User, provider: str, model: str, base_url: str, api_key: str | None
) -> AIProviderConfiguration:
    existing = _own(user).select_for_update().first()
    configuration = existing or AIProviderConfiguration(owner=user)
    same_target = existing is not None and (existing.provider, existing.base_url) == (
        provider,
        base_url,
    )
    key_written = api_key is not None or not same_target
    if api_key is not None:
        configuration.api_key = api_key
    elif not same_target:
        configuration.api_key = ""
    else:
        try:
            configuration.api_key  # noqa: B018 - decrypts: is the stored key still usable?
        except DecryptionError:
            configuration.api_key = ""
            key_written = True

    changed = (
        existing is None
        or key_written
        or (existing.provider, existing.model, existing.base_url) != (provider, model, base_url)
    )
    configuration.provider = provider
    configuration.model = model
    configuration.base_url = base_url
    # Not ``full_clean``: its constraint check would repeat every message of ``clean``.
    errors = _problems(configuration)
    if errors:
        raise ValidationError(errors)

    if changed:
        configuration.status = Status.UNTESTED
        configuration.last_checked_at = None
        configuration.last_success_at = None
    if existing is None:
        configuration.save()
    else:
        fields = ["provider", "model", "base_url"]
        if key_written:
            fields.append("api_key")
        if changed:
            fields += ["status", "last_checked_at", "last_success_at"]
        configuration.save(update_fields=fields)
    return configuration


def _problems(configuration: AIProviderConfiguration) -> dict[str, list[str]]:
    """The messages of the field checks and of ``clean`` by field, empty if all is well."""
    found: dict[str, list[str]] = {}
    for check_it in (
        lambda: configuration.clean_fields(exclude=["owner", "api_key"]),
        configuration.clean,
    ):
        try:
            check_it()
        except ValidationError as error:
            for name, messages in error.message_dict.items():
                found.setdefault(name, []).extend(messages)
    return found


def remove_configuration(user: User) -> None:
    """Remove the configuration and with it the key. The usage records stay."""
    AIProviderConfiguration.objects.for_user(user).delete()


def call(
    user: User,
    purpose: AIUsageRecord.Purpose,
    system: str,
    messages: Sequence[Message],
    max_tokens: int,
) -> Completion:
    """Ask the user's own provider, and record the call.

    Raises ``NotConfiguredError`` if there is no configuration, ``EndpointNotAllowedError`` if the
    operator has taken the address off the list (nothing is sent, nothing is recorded), and the
    errors of the provider otherwise. A call that reached the provider is recorded whatever
    came of it; the status of the configuration follows what was learned:

    - success: ``connected``;
    - key refused, or the stored key cannot be decrypted: ``invalid``;
    - provider not reachable or broken: ``unavailable``;
    - rate limited or an answer that makes no sense: the status stays (the key may well be fine,
      and a wrong model name is not an outage); only the time of the check moves.
    """
    configuration = _own(user).first()
    if configuration is None:
        raise NotConfiguredError
    try:
        provider = provider_for(configuration)
    except DecryptionError:
        _finish(user, configuration, purpose, Outcome.INVALID_KEY, None, Status.INVALID)
        raise InvalidKeyError("The stored key is not usable.") from None
    # EndpointNotAllowedError passes through: no call was made, so there is nothing to record.
    try:
        completion = provider.complete(system, messages, max_tokens)
    except InvalidKeyError:
        _finish(user, configuration, purpose, Outcome.INVALID_KEY, None, Status.INVALID)
        raise
    except RateLimitedError:
        _finish(user, configuration, purpose, Outcome.RATE_LIMITED, None, None)
        raise
    except ProviderUnavailableError:
        _finish(user, configuration, purpose, Outcome.UNAVAILABLE, None, Status.UNAVAILABLE)
        raise
    except UnexpectedResponseError:
        _finish(user, configuration, purpose, Outcome.UNEXPECTED, None, None)
        raise
    _finish(user, configuration, purpose, Outcome.SUCCESS, completion, Status.CONNECTED)
    return completion


def check(user: User) -> AIProviderConfiguration:
    """Send the fixed check prompt and return the configuration as it is afterwards.

    The errors of ``call`` are raised; the status has been updated either way.
    """
    call(
        user,
        AIUsageRecord.Purpose.CHECK,
        "",
        [Message("user", CHECK_PROMPT)],
        CHECK_MAX_TOKENS,
    )
    configuration = get_configuration(user)
    if configuration is None:  # removed while the check ran
        raise NotConfiguredError
    return configuration


def usage_summary(user: User, days: int = USAGE_DAYS) -> UsageSummary:
    """The user's own calls of the last ``days`` days, failed ones included."""
    since = _now() - timedelta(days=days)
    totals = (
        AIUsageRecord.objects.for_user(user)
        .filter(created_at__gte=since)
        .aggregate(calls=Count("id"), input=Sum("input_tokens"), output=Sum("output_tokens"))
    )
    return UsageSummary(
        calls=totals["calls"],
        input_tokens=totals["input"] or 0,
        output_tokens=totals["output"] or 0,
        days=days,
    )


def _finish(
    user: User,
    configuration: AIProviderConfiguration,
    purpose: AIUsageRecord.Purpose,
    outcome: AIUsageRecord.Outcome,
    completion: Completion | None,
    status: AIProviderConfiguration.Status | None,
) -> None:
    now = _now()
    with transaction.atomic():
        AIUsageRecord.objects.create(
            owner=user,
            provider=configuration.provider,
            model=configuration.model,
            purpose=purpose,
            outcome=outcome,
            input_tokens=completion.input_tokens if completion else None,
            output_tokens=completion.output_tokens if completion else None,
        )
        changes: dict[str, object] = {"last_checked_at": now}
        if status is not None:
            changes["status"] = status
        if outcome == Outcome.SUCCESS:
            changes["last_success_at"] = now
        # An update of single columns: the key is not read back, not re-encrypted, and a
        # configuration removed during the call is not brought back.
        AIProviderConfiguration.objects.for_user(user).filter(pk=configuration.pk).update(**changes)
