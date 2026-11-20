"""Calling a user's AI provider, and keeping the books on it.

Every function acts on the configuration of the user it is given and on nothing else. The stored
key is decrypted only where a call needs it. The network call never runs inside a database
transaction. What is recorded about a call is in ``AIUsageRecord``: facts, never text.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, QuerySet, Sum
from django.utils import timezone

from accounts.models import User
from core.encryption import DecryptionError

from .models import EFFORT_FIELDS, AIProviderConfiguration, AIUsageRecord
from .providers import provider_for
from .providers.base import (
    Completion,
    Deadline,
    DeadlineExceededError,
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
# A repair round is only started with at least this much time left before the deadline: an
# answer that cannot arrive in time is paid for and thrown away.
MIN_ATTEMPT_SECONDS = 60

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
    # Parts of ``input_tokens``: what came from the prompt cache, and what was written to it.
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def _now() -> datetime:
    return timezone.now()


def request_deadline() -> Deadline:
    """The deadline for the calls of one request of the athlete (a plan, a change, a chat answer,
    a review comment), ``AI_REQUEST_DEADLINE_SECONDS`` from now."""
    return Deadline.after(settings.AI_REQUEST_DEADLINE_SECONDS)


def time_for_another_attempt(deadline: Deadline) -> bool:
    """Whether a repair round can still be started before ``deadline``."""
    return deadline.remaining() >= MIN_ATTEMPT_SECONDS


def _own(user: User) -> QuerySet[AIProviderConfiguration]:
    # The key stays encrypted (not even loaded) unless a caller asks for it.
    return AIProviderConfiguration.objects.for_user(user).defer("api_key")


def get_configuration(user: User) -> AIProviderConfiguration | None:
    return _own(user).first()


def save_configuration(
    user: User,
    *,
    provider: str,
    model: str,
    base_url: str,
    api_key: str | None,
    season_model: str = "",
    week_model: str = "",
    chat_model: str = "",
    efforts: Mapping[str, str] | None = None,
) -> AIProviderConfiguration:
    """Create or change the user's configuration.

    ``api_key`` is the new key, ``""`` for none, or ``None`` for "keep the stored one". A stored
    key is only kept while provider and address stay the same: it must never be sent to a
    place the user did not give it for. Anything that changes what is called (provider, model,
    address, key) sets the status back to ``untested`` and forgets the times of the last check.
    ``efforts`` holds the four effort fields (``EFFORT_FIELDS``; a missing one is empty); they
    change how long a model may think, not what is called, so the status stays.

    Raises Django's ``ValidationError`` (by field) and saves nothing if the result is not valid.
    """
    for attempt in (1, 2):
        try:
            with transaction.atomic():
                return _save(
                    user,
                    provider,
                    model,
                    base_url,
                    api_key,
                    season_model,
                    week_model,
                    chat_model,
                    efforts or {},
                )
        except IntegrityError:
            # A second request created the row first; the next round changes that one.
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def _save(
    user: User,
    provider: str,
    model: str,
    base_url: str,
    api_key: str | None,
    season_model: str = "",
    week_model: str = "",
    chat_model: str = "",
    efforts: Mapping[str, str] | None = None,
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
        or (existing.season_model, existing.week_model, existing.chat_model)
        != (season_model, week_model, chat_model)
    )
    configuration.provider = provider
    configuration.model = model
    configuration.season_model = season_model
    configuration.week_model = week_model
    configuration.chat_model = chat_model
    for name in EFFORT_FIELDS:
        setattr(configuration, name, (efforts or {}).get(name, ""))
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
        fields = [
            "provider",
            "model",
            "season_model",
            "week_model",
            "chat_model",
            *EFFORT_FIELDS,
            "base_url",
        ]
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
    json_output: bool = False,
    deadline: Deadline | None = None,
) -> Completion:
    """Ask the user's own provider, and record the call.

    ``json_output`` asks for a JSON object where the provider has a mode for it (the answer is
    read strictly either way); the connection check does not ask, its answer is the word "ok".
    ``deadline`` is when the answer must be there; once it has passed nothing is sent and
    ``DeadlineExceededError`` is raised, and a provider that is still answering then gives up
    with the same error (recorded as ``unavailable``).

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
    if deadline is not None and deadline.passed():
        raise DeadlineExceededError("There was no time left for the answer.")
    try:
        model = configuration.model_for(purpose)
        provider = provider_for(configuration, model, configuration.effort_for(purpose))
    except DecryptionError:
        _finish(user, configuration, purpose, Outcome.INVALID_KEY, None, Status.INVALID)
        raise InvalidKeyError("The stored key is not usable.") from None
    # EndpointNotAllowedError passes through: no call was made, so there is nothing to record.
    try:
        completion = provider.complete(
            system, messages, max_tokens, json_output=json_output, deadline=deadline
        )
    except InvalidKeyError:
        _finish(user, configuration, purpose, Outcome.INVALID_KEY, None, Status.INVALID)
        raise
    except RateLimitedError:
        _finish(user, configuration, purpose, Outcome.RATE_LIMITED, None, None)
        raise
    except DeadlineExceededError:
        # A slow answer is no outage: the provider was there, it only took too long.
        _finish(user, configuration, purpose, Outcome.UNAVAILABLE, None, None)
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
        .aggregate(
            calls=Count("id"),
            input=Sum("input_tokens"),
            output=Sum("output_tokens"),
            cache_read=Sum("cache_read_tokens"),
            cache_write=Sum("cache_write_tokens"),
        )
    )
    return UsageSummary(
        calls=totals["calls"],
        input_tokens=totals["input"] or 0,
        output_tokens=totals["output"] or 0,
        days=days,
        cache_read_tokens=totals["cache_read"] or 0,
        cache_write_tokens=totals["cache_write"] or 0,
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
            model=configuration.model_for(purpose),
            purpose=purpose,
            outcome=outcome,
            input_tokens=completion.input_tokens if completion else None,
            output_tokens=completion.output_tokens if completion else None,
            cache_read_tokens=completion.cache_read_tokens if completion else None,
            cache_write_tokens=completion.cache_write_tokens if completion else None,
        )
        changes: dict[str, object] = {"last_checked_at": now}
        if status is not None:
            changes["status"] = status
        if outcome == Outcome.SUCCESS:
            changes["last_success_at"] = now
        # An update of single columns: the key is not read back, not re-encrypted, and a
        # configuration removed during the call is not brought back.
        AIProviderConfiguration.objects.for_user(user).filter(pk=configuration.pk).update(**changes)
