from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection
from django.db.models import QuerySet

from accounts.models import User
from coach import services
from coach.models import AIProviderConfiguration, AIUsageRecord
from coach.providers.base import (
    Completion,
    Deadline,
    EndpointNotAllowedError,
    InvalidKeyError,
    Message,
    ProviderUnavailableError,
    RateLimitedError,
    UnexpectedResponseError,
)
from coach.services import CHECK_PROMPT, NotConfiguredError, UsageSummary

from .fake_providers import FakeProvider, running

pytestmark = pytest.mark.django_db

KEY = "synthetic-test-token-abcdefghij"
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
PROMPT = "A secret prompt about my knee"
ANSWER_TEXT = "A secret answer about training"
ANSWER = {
    "content": [{"type": "text", "text": ANSWER_TEXT}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 12, "output_tokens": 5},
}
CHECK = AIUsageRecord.Purpose.CHECK


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(services, "_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def configure(owner: User, **fields: Any) -> AIProviderConfiguration:
    data: dict[str, Any] = {"provider": "anthropic", "model": "claude-sonnet-5-5", "api_key": KEY}
    return AIProviderConfiguration.objects.create(owner=owner, **(data | fields))


def ask(user: User, text: str = PROMPT) -> Completion:
    return services.call(user, CHECK, "system", [Message("user", text)], 50)


def records(user: User) -> list[AIUsageRecord]:
    return list(AIUsageRecord.objects.for_user(user).order_by("id"))


def reload(config: AIProviderConfiguration) -> AIProviderConfiguration:
    return AIProviderConfiguration.objects.get(pk=config.pk)


def stored_key(pk: int) -> str:
    table = AIProviderConfiguration._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT api_key FROM {table} WHERE id = %s", [pk])
        return str(cursor.fetchone()[0])


class TestASuccessfulCall:
    def test_it_returns_the_answer_and_records_the_facts(
        self, fake: FakeProvider, alice: User
    ) -> None:
        configure(alice)
        fake.reply(ANSWER)

        result = ask(alice)

        assert result == Completion(ANSWER_TEXT, 12, 5, False)
        (record,) = records(alice)
        assert (record.provider, record.model, record.purpose, record.outcome) == (
            "anthropic",
            "claude-sonnet-5-5",
            "check",
            "success",
        )
        assert (record.input_tokens, record.output_tokens) == (12, 5)

    def test_the_cached_tokens_of_the_answer_are_recorded(
        self, fake: FakeProvider, alice: User
    ) -> None:
        usage = {
            "input_tokens": 20,
            "output_tokens": 5,
            "cache_read_input_tokens": 3000,
            "cache_creation_input_tokens": 400,
        }
        fake.reply({**ANSWER, "usage": usage})
        configure(alice)

        ask(alice)

        (record,) = records(alice)
        assert (record.input_tokens, record.cache_read_tokens, record.cache_write_tokens) == (
            3420,
            3000,
            400,
        )

    def test_a_call_without_cache_counts_records_none(
        self, fake: FakeProvider, alice: User
    ) -> None:
        configure(alice)
        fake.reply(ANSWER)

        ask(alice)

        (record,) = records(alice)
        assert (record.cache_read_tokens, record.cache_write_tokens) == (None, None)

    def test_the_status_becomes_connected_and_the_times_are_set(
        self, fake: FakeProvider, alice: User
    ) -> None:
        config = configure(alice)
        fake.reply(ANSWER)

        ask(alice)

        config = reload(config)
        assert config.status == "connected"
        assert config.last_checked_at == NOW
        assert config.last_success_at == NOW

    def test_the_call_uses_the_users_own_key_and_model(
        self, fake: FakeProvider, alice: User, bob: User
    ) -> None:
        configure(bob, api_key="bobs-key-0123456789", model="bobs-model")
        configure(alice)
        fake.reply(ANSWER)

        ask(alice)

        assert fake.requests[0]["headers"]["x-api-key"] == KEY
        assert fake.requests[0]["json"]["model"] == "claude-sonnet-5-5"
        assert records(bob) == []
        assert reload(AIProviderConfiguration.objects.get(owner=bob)).status == "untested"

    def test_unknown_token_counts_stay_unknown(self, fake: FakeProvider, alice: User) -> None:
        configure(alice)
        fake.reply({"content": [{"type": "text", "text": "ok"}]})

        ask(alice)

        (record,) = records(alice)
        assert (record.input_tokens, record.output_tokens) == (None, None)

    def test_the_key_is_not_rewritten(self, fake: FakeProvider, alice: User) -> None:
        config = configure(alice)
        before = stored_key(config.pk)
        fake.reply(ANSWER)

        ask(alice)

        assert stored_key(config.pk) == before

    def test_the_key_is_encrypted_at_rest_and_never_recorded(
        self, fake: FakeProvider, alice: User
    ) -> None:
        config = configure(alice)
        fake.reply(ANSWER)

        ask(alice)

        assert KEY not in stored_key(config.pk)
        assert all(KEY not in str(vars(record)) for record in records(alice))

    def test_neither_prompt_nor_answer_is_kept_anywhere(
        self, fake: FakeProvider, alice: User
    ) -> None:
        config = configure(alice)
        fake.reply(ANSWER)

        ask(alice)

        everything = " ".join(
            str(value) for record in records(alice) for value in vars(record).values()
        )
        everything += " ".join(str(value) for value in vars(reload(config)).values())
        assert "secret" not in everything
        assert PROMPT not in everything
        assert ANSWER_TEXT not in everything

    def test_a_compatible_endpoint_works_the_same_way(
        self, fake: FakeProvider, alice: User, settings: Any
    ) -> None:
        settings.AI_ALLOWED_BASE_URLS = (fake.url + "/v1",)
        configure(
            alice,
            provider="openai_compatible",
            model="llama3.1:8b",
            api_key="",
            base_url=fake.url + "/v1",
        )
        fake.reply(
            {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            }
        )

        ask(alice)

        (record,) = records(alice)
        assert (record.provider, record.model, record.outcome) == (
            "openai_compatible",
            "llama3.1:8b",
            "success",
        )
        assert (record.input_tokens, record.output_tokens) == (3, 1)


SEASON = AIUsageRecord.Purpose.SEASON_PLAN
WEEKLY = AIUsageRecord.Purpose.WEEKLY_PLAN


class TestTheModelOfAPurpose:
    def ask_for(self, user: User, purpose: AIUsageRecord.Purpose) -> Completion:
        return services.call(user, purpose, "system", [Message("user", PROMPT)], 50)

    def test_the_season_plan_uses_the_season_model_if_there_is_one(
        self, fake: FakeProvider, alice: User
    ) -> None:
        configure(alice, season_model="claude-opus-5-5")
        fake.reply(ANSWER)

        self.ask_for(alice, SEASON)

        assert fake.requests[0]["json"]["model"] == "claude-opus-5-5"
        (record,) = records(alice)
        assert (record.model, record.purpose) == ("claude-opus-5-5", "season_plan")

    def test_without_a_season_model_the_normal_model_does_it(
        self, fake: FakeProvider, alice: User
    ) -> None:
        configure(alice)
        fake.reply(ANSWER)

        self.ask_for(alice, SEASON)

        assert fake.requests[0]["json"]["model"] == "claude-sonnet-5-5"
        assert records(alice)[0].model == "claude-sonnet-5-5"

    @pytest.mark.parametrize("purpose", [CHECK, WEEKLY, AIUsageRecord.Purpose.WEEK_REVIEW])
    def test_every_other_purpose_keeps_the_normal_model(
        self, fake: FakeProvider, alice: User, purpose: AIUsageRecord.Purpose
    ) -> None:
        configure(alice, season_model="claude-opus-5-5")
        fake.reply(ANSWER)

        self.ask_for(alice, purpose)

        assert fake.requests[0]["json"]["model"] == "claude-sonnet-5-5"
        assert records(alice)[0].model == "claude-sonnet-5-5"

    def test_the_failed_call_is_recorded_with_the_model_that_was_asked(
        self, fake: FakeProvider, alice: User
    ) -> None:
        configure(alice, season_model="claude-opus-5-5")
        fake.reply({"error": {"message": "x"}}, 500)

        with pytest.raises(ProviderUnavailableError):
            self.ask_for(alice, SEASON)

        assert records(alice)[0].model == "claude-opus-5-5"
        assert records(alice)[0].outcome == "unavailable"

    def test_week_and_chat_use_their_own_models(self, fake: FakeProvider, alice: User) -> None:
        configure(alice, week_model="claude-haiku-5-5", chat_model="claude-opus-5-5")
        fake.reply(ANSWER)
        fake.reply(ANSWER)

        self.ask_for(alice, WEEKLY)
        self.ask_for(alice, AIUsageRecord.Purpose.CHAT)

        assert [r["json"]["model"] for r in fake.requests] == [
            "claude-haiku-5-5",
            "claude-opus-5-5",
        ]
        assert [r.model for r in records(alice)] == ["claude-haiku-5-5", "claude-opus-5-5"]

    @pytest.mark.parametrize("purpose", [CHECK, AIUsageRecord.Purpose.WEEK_REVIEW])
    def test_check_and_review_keep_the_normal_model_with_week_and_chat_models(
        self, fake: FakeProvider, alice: User, purpose: AIUsageRecord.Purpose
    ) -> None:
        configure(alice, week_model="claude-haiku-5-5", chat_model="claude-opus-5-5")
        fake.reply(ANSWER)

        self.ask_for(alice, purpose)

        assert fake.requests[0]["json"]["model"] == "claude-sonnet-5-5"

    def test_the_model_for_is_the_one_of_the_configuration(self, alice: User) -> None:
        config = configure(alice, season_model="m2")

        assert config.model_for(SEASON) == "m2"
        assert config.model_for(WEEKLY) == "claude-sonnet-5-5"


class TestTheSeasonModelInTheSetup:
    def save(self, user: User, **fields: Any) -> AIProviderConfiguration:
        data: dict[str, Any] = {
            "provider": "anthropic",
            "model": "claude-sonnet-5-5",
            "base_url": "",
            "api_key": KEY,
        }
        return services.save_configuration(user, **(data | fields))

    def test_it_is_stored_and_empty_by_default(self, alice: User) -> None:
        assert self.save(alice).season_model == ""
        assert self.save(alice, season_model="claude-opus-5-5").season_model == "claude-opus-5-5"

    def test_it_can_be_taken_away_again(self, alice: User) -> None:
        self.save(alice, season_model="claude-opus-5-5")

        assert self.save(alice, season_model="").season_model == ""

    def test_a_change_of_it_sets_the_status_back(self, alice: User) -> None:
        config = self.save(alice)
        AIProviderConfiguration.objects.filter(pk=config.pk).update(
            status="connected", last_success_at=NOW
        )

        changed = self.save(alice, season_model="claude-opus-5-5")

        assert (changed.status, changed.last_success_at) == ("untested", None)

    def test_the_same_setup_again_keeps_the_status(self, alice: User) -> None:
        config = self.save(alice, season_model="claude-opus-5-5")
        AIProviderConfiguration.objects.filter(pk=config.pk).update(status="connected")

        # no key sent: the stored one is kept, so nothing changes
        again = self.save(alice, season_model="claude-opus-5-5", api_key=None)

        assert again.status == "connected"

    @pytest.mark.parametrize("name", ["-bad", "has space", "x" * 101, "ü"])
    def test_a_name_that_cannot_be_a_model_is_refused(self, alice: User, name: str) -> None:
        with pytest.raises(ValidationError) as raised:
            self.save(alice, season_model=name)

        assert "season_model" in raised.value.message_dict
        assert not AIProviderConfiguration.objects.exists()


class TestTheWeekAndChatModelsInTheSetup:
    def save(self, user: User, **fields: Any) -> AIProviderConfiguration:
        data: dict[str, Any] = {
            "provider": "anthropic",
            "model": "claude-sonnet-5-5",
            "base_url": "",
            "api_key": KEY,
        }
        return services.save_configuration(user, **(data | fields))

    @pytest.mark.parametrize("field", ["week_model", "chat_model"])
    def test_it_is_stored_and_can_be_cleared(self, alice: User, field: str) -> None:
        assert getattr(self.save(alice), field) == ""
        assert getattr(self.save(alice, **{field: "claude-haiku-5-5"}), field) == "claude-haiku-5-5"
        assert getattr(self.save(alice, **{field: ""}), field) == ""

    @pytest.mark.parametrize("field", ["week_model", "chat_model"])
    def test_a_change_sets_the_status_back(self, alice: User, field: str) -> None:
        config = self.save(alice)
        AIProviderConfiguration.objects.filter(pk=config.pk).update(
            status="connected", last_success_at=NOW
        )

        changed = self.save(alice, **{field: "claude-haiku-5-5"})

        assert (changed.status, changed.last_success_at) == ("untested", None)

    def test_the_same_setup_again_keeps_the_status(self, alice: User) -> None:
        config = self.save(alice, week_model="a", chat_model="b")
        AIProviderConfiguration.objects.filter(pk=config.pk).update(status="connected")

        again = self.save(alice, week_model="a", chat_model="b", api_key=None)

        assert again.status == "connected"

    @pytest.mark.parametrize("field", ["week_model", "chat_model"])
    def test_a_name_that_cannot_be_a_model_is_refused(self, alice: User, field: str) -> None:
        with pytest.raises(ValidationError) as raised:
            self.save(alice, **{field: "has space"})

        assert field in raised.value.message_dict
        assert not AIProviderConfiguration.objects.exists()


class TestJsonOutput:
    class Recorder:
        def __init__(self) -> None:
            self.asked: list[bool] = []

        def complete(
            self,
            system: str,
            messages: Any,
            max_tokens: int,
            json_output: bool = False,
            deadline: Deadline | None = None,
        ) -> Completion:
            self.asked.append(json_output)
            return Completion("ok", 1, 1)

    def use(self, monkeypatch: pytest.MonkeyPatch) -> TestJsonOutput.Recorder:
        recorder = self.Recorder()
        monkeypatch.setattr(services, "provider_for", lambda configuration, model=None: recorder)
        return recorder

    def test_a_call_does_not_ask_for_json_unless_told_to(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        configure(alice)
        recorder = self.use(monkeypatch)

        ask(alice)

        assert recorder.asked == [False]

    def test_a_call_can_ask_for_json(self, alice: User, monkeypatch: pytest.MonkeyPatch) -> None:
        configure(alice)
        recorder = self.use(monkeypatch)

        services.call(alice, CHECK, "system", [Message("user", PROMPT)], 50, json_output=True)

        assert recorder.asked == [True]

    def test_the_check_never_asks_for_json(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        configure(alice)
        recorder = self.use(monkeypatch)

        services.check(alice)

        assert recorder.asked == [False]

    def test_it_reaches_a_listed_endpoint_and_only_when_asked(
        self, fake: FakeProvider, alice: User, settings: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from coach.providers import openai_compatible

        monkeypatch.setattr(openai_compatible, "JSON_MODE_HOSTS", frozenset({"127.0.0.1"}))
        settings.AI_ALLOWED_BASE_URLS = (fake.url + "/v1",)
        configure(
            alice,
            provider="openai_compatible",
            model="llama3.1:8b",
            api_key="",
            base_url=fake.url + "/v1",
        )
        fake.reply({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

        services.check(alice)
        services.call(alice, CHECK, "system", [Message("user", PROMPT)], 50, json_output=True)

        check_body, asked_body = (request["json"] for request in fake.requests)
        assert "response_format" not in check_body
        assert asked_body["response_format"] == {"type": "json_object"}


class TestFailures:
    def test_a_refused_key_marks_the_configuration_invalid(
        self, fake: FakeProvider, alice: User
    ) -> None:
        config = configure(alice)
        fake.reply({}, 401)

        with pytest.raises(InvalidKeyError):
            ask(alice)

        config = reload(config)
        assert config.status == "invalid"
        assert config.last_checked_at == NOW
        assert config.last_success_at is None
        (record,) = records(alice)
        assert record.outcome == "invalid_key"
        assert (record.input_tokens, record.output_tokens) == (None, None)

    def test_an_invalid_key_that_works_again_is_connected_again(
        self, fake: FakeProvider, alice: User
    ) -> None:
        config = configure(alice)
        fake.reply({}, 401)
        with pytest.raises(InvalidKeyError):
            ask(alice)

        fake.reply(ANSWER)
        ask(alice)

        assert reload(config).status == "connected"
        assert [r.outcome for r in records(alice)] == ["invalid_key", "success"]

    def test_a_provider_that_is_down_marks_the_configuration_unavailable(
        self, fake: FakeProvider, alice: User
    ) -> None:
        config = configure(alice)
        fake.reply({}, 503)

        with pytest.raises(ProviderUnavailableError):
            ask(alice)

        assert reload(config).status == "unavailable"
        assert records(alice)[0].outcome == "unavailable"

    def test_a_provider_that_cannot_be_reached_is_unavailable_too(
        self, alice: User, settings: Any
    ) -> None:
        with running() as gone:
            settings.ANTHROPIC_API_BASE_URL = gone.url
        config = configure(alice)

        with pytest.raises(ProviderUnavailableError):
            ask(alice)

        assert reload(config).status == "unavailable"

    def test_rate_limiting_keeps_the_status_and_moves_the_time_of_the_check(
        self, fake: FakeProvider, alice: User
    ) -> None:
        config = configure(alice, status="connected")
        fake.headers = {"Retry-After": "30"}
        fake.reply({}, 429)

        with pytest.raises(RateLimitedError) as raised:
            ask(alice)

        assert raised.value.retry_after == 30
        config = reload(config)
        assert config.status == "connected"
        assert config.last_checked_at == NOW
        assert records(alice)[0].outcome == "rate_limited"

    def test_rate_limiting_does_not_make_an_untested_key_connected(
        self, fake: FakeProvider, alice: User
    ) -> None:
        config = configure(alice)
        fake.reply({}, 429)

        with pytest.raises(RateLimitedError):
            ask(alice)

        assert reload(config).status == "untested"

    @pytest.mark.parametrize("status", ["connected", "invalid", "unavailable", "untested"])
    def test_an_unexpected_answer_leaves_the_status_alone(
        self, fake: FakeProvider, alice: User, status: str
    ) -> None:
        config = configure(alice, status=status)
        fake.reply({"error": {"message": "model not found"}}, 404)

        with pytest.raises(UnexpectedResponseError):
            ask(alice)

        config = reload(config)
        assert config.status == status
        assert config.last_checked_at == NOW
        assert config.last_success_at is None
        assert records(alice)[0].outcome == "unexpected"

    def test_a_failure_does_not_touch_an_earlier_success_time(
        self, fake: FakeProvider, alice: User
    ) -> None:
        earlier = NOW - timedelta(days=2)
        config = configure(alice, status="connected", last_success_at=earlier)
        fake.reply({}, 500)

        with pytest.raises(ProviderUnavailableError):
            ask(alice)

        assert reload(config).last_success_at == earlier

    def test_a_key_that_cannot_be_decrypted_counts_as_refused_without_a_call(
        self, fake: FakeProvider, alice: User
    ) -> None:
        config = configure(alice)
        table = AIProviderConfiguration._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET api_key = %s WHERE id = %s", ["enc:v1:garbage", config.pk]
            )

        with pytest.raises(InvalidKeyError) as raised:
            ask(alice)

        assert fake.requests == []
        assert raised.value.__cause__ is None
        assert raised.value.__suppress_context__
        assert reload_without_key(config).status == "invalid"
        assert records(alice)[0].outcome == "invalid_key"

    def test_the_record_and_the_status_are_saved_together_or_not_at_all(
        self, fake: FakeProvider, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        configure(alice)
        fake.reply(ANSWER)

        def broken(*args: Any, **kwargs: Any) -> int:
            raise RuntimeError("database trouble")

        monkeypatch.setattr(QuerySet, "update", broken)
        with pytest.raises(RuntimeError):
            ask(alice)
        monkeypatch.undo()

        assert records(alice) == []

    def test_every_failure_leaves_exactly_one_record(self, fake: FakeProvider, alice: User) -> None:
        configure(alice)
        for status in (401, 429, 500, 404):
            fake.reply({}, status)
            with pytest.raises(Exception):  # noqa: B017 - the kinds are tested above
                ask(alice)

        assert len(records(alice)) == 4


def reload_without_key(config: AIProviderConfiguration) -> AIProviderConfiguration:
    return AIProviderConfiguration.objects.defer("api_key").get(pk=config.pk)


class TestWhatIsNotRecorded:
    def test_without_a_configuration_nothing_is_sent_or_recorded(
        self, fake: FakeProvider, alice: User
    ) -> None:
        with pytest.raises(NotConfiguredError):
            ask(alice)

        assert fake.requests == []
        assert AIUsageRecord.objects.count() == 0

    def test_another_users_configuration_is_never_used(
        self, fake: FakeProvider, alice: User, bob: User
    ) -> None:
        configure(bob)

        with pytest.raises(NotConfiguredError):
            ask(alice)

        assert fake.requests == []
        assert AIUsageRecord.objects.count() == 0

    def test_an_address_the_operator_removed_is_refused_before_any_call(
        self, fake: FakeProvider, alice: User, settings: Any
    ) -> None:
        config = configure(
            alice,
            provider="openai_compatible",
            model="llama3.1:8b",
            api_key="",
            base_url=fake.url + "/v1",
        )
        settings.AI_ALLOWED_BASE_URLS = ()

        with pytest.raises(EndpointNotAllowedError):
            ask(alice)

        assert fake.requests == []
        assert AIUsageRecord.objects.count() == 0
        config = reload(config)
        assert config.status == "untested"
        assert config.last_checked_at is None


class TestAllowlistEnforcement:
    OPENAI_ANSWER = {
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
    }

    def test_approved_self_hosted_endpoint_succeeds_for_call(
        self, alice: User, settings: Any
    ) -> None:
        with running() as approved, running() as unlisted:
            approved_url = approved.url + "/v1"
            settings.AI_ALLOWED_BASE_URLS = (approved_url,)
            configure(
                alice,
                provider="openai_compatible",
                model="llama3.1:8b",
                api_key="",
                base_url=approved_url,
            )
            approved.reply(self.OPENAI_ANSWER)

            result = ask(alice)

            assert result == Completion("ok", 3, 1, False)
            assert len(approved.requests) == 1
            assert approved.requests[0]["raw_path"] == "/v1/chat/completions"
            assert unlisted.requests == []
            assert len(records(alice)) == 1

    def test_approved_self_hosted_endpoint_succeeds_for_check(
        self, alice: User, settings: Any
    ) -> None:
        with running() as approved, running() as unlisted:
            approved_url = approved.url + "/v1"
            settings.AI_ALLOWED_BASE_URLS = (approved_url,)
            configure(
                alice,
                provider="openai_compatible",
                model="llama3.1:8b",
                api_key="",
                base_url=approved_url,
            )
            approved.reply(self.OPENAI_ANSWER)

            config = services.check(alice)

            assert config.status == "connected"
            assert len(approved.requests) == 1
            assert approved.requests[0]["raw_path"] == "/v1/chat/completions"
            assert unlisted.requests == []
            assert len(records(alice)) == 1

    def test_directly_created_unapproved_base_url_is_refused_in_call_and_check(
        self, alice: User, settings: Any
    ) -> None:
        with running() as approved, running() as unlisted:
            settings.AI_ALLOWED_BASE_URLS = (approved.url + "/v1",)
            config = configure(
                alice,
                provider="openai_compatible",
                model="llama3.1:8b",
                api_key="",
                base_url=unlisted.url + "/v1",
            )

            for invoke in (lambda: ask(alice), lambda: services.check(alice)):
                with pytest.raises(EndpointNotAllowedError):
                    invoke()

            assert unlisted.requests == []
            assert approved.requests == []
            assert AIUsageRecord.objects.count() == 0
            config = reload(config)
            assert config.status == "untested"
            assert config.last_checked_at is None

    def test_queryset_updated_unapproved_base_url_is_refused_in_call_and_check(
        self, alice: User, settings: Any
    ) -> None:
        with running() as approved, running() as unlisted:
            settings.AI_ALLOWED_BASE_URLS = (approved.url + "/v1",)
            config = configure(
                alice,
                provider="openai_compatible",
                model="llama3.1:8b",
                api_key="",
                base_url=approved.url + "/v1",
            )
            AIProviderConfiguration.objects.filter(pk=config.pk).update(
                base_url=unlisted.url + "/v1"
            )

            for invoke in (lambda: ask(alice), lambda: services.check(alice)):
                with pytest.raises(EndpointNotAllowedError):
                    invoke()

            assert unlisted.requests == []
            assert approved.requests == []
            assert AIUsageRecord.objects.count() == 0
            config = reload(config)
            assert config.status == "untested"
            assert config.last_checked_at is None

    def test_stale_base_url_removed_from_allowlist_is_refused_in_call_and_check(
        self, alice: User, settings: Any
    ) -> None:
        with running() as approved, running() as stale:
            approved_url = approved.url + "/v1"
            stale_url = stale.url + "/v1"
            settings.AI_ALLOWED_BASE_URLS = (approved_url, stale_url)
            config = configure(
                alice,
                provider="openai_compatible",
                model="llama3.1:8b",
                api_key="",
                base_url=stale_url,
            )
            settings.AI_ALLOWED_BASE_URLS = (approved_url,)

            for invoke in (lambda: ask(alice), lambda: services.check(alice)):
                with pytest.raises(EndpointNotAllowedError):
                    invoke()

            assert stale.requests == []
            assert approved.requests == []
            assert AIUsageRecord.objects.count() == 0
            config = reload(config)
            assert config.status == "untested"
            assert config.last_checked_at is None


class TestTheCheck:
    def test_it_sends_the_fixed_prompt_and_nothing_of_the_user(
        self, fake: FakeProvider, alice: User
    ) -> None:
        configure(alice)
        fake.reply(ANSWER)

        services.check(alice)

        body = fake.requests[0]["json"]
        assert body["messages"] == [{"role": "user", "content": CHECK_PROMPT}]
        assert body["max_tokens"] == 16
        assert "system" not in body
        assert "alice" not in str(body)

    def test_the_prompt_is_the_documented_one(self) -> None:
        assert CHECK_PROMPT == "Reply with the single word: ok"

    def test_it_returns_the_configuration_as_it_is_afterwards(
        self, fake: FakeProvider, alice: User
    ) -> None:
        configure(alice)
        fake.reply(ANSWER)

        config = services.check(alice)

        assert config.status == "connected"
        assert config.last_success_at == NOW
        assert records(alice)[0].purpose == "check"

    def test_a_refused_key_raises_and_the_status_is_invalid(
        self, fake: FakeProvider, alice: User
    ) -> None:
        config = configure(alice)
        fake.reply({}, 401)

        with pytest.raises(InvalidKeyError):
            services.check(alice)

        assert reload(config).status == "invalid"

    def test_a_configuration_removed_while_the_check_runs_is_not_brought_back(
        self, fake: FakeProvider, alice: User
    ) -> None:
        configure(alice)
        fake.reply(ANSWER)
        real_call = services.call

        def call_and_remove(*args: Any, **kwargs: Any) -> Completion:
            result = real_call(*args, **kwargs)
            AIProviderConfiguration.objects.filter(owner=alice).delete()
            return result

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(services, "call", call_and_remove)
            with pytest.raises(NotConfiguredError):
                services.check(alice)

        assert AIProviderConfiguration.objects.count() == 0
        assert len(records(alice)) == 1

    def test_without_a_configuration_there_is_nothing_to_check(self, alice: User) -> None:
        with pytest.raises(NotConfiguredError):
            services.check(alice)

    def test_the_returned_configuration_does_not_load_the_key(
        self, fake: FakeProvider, alice: User
    ) -> None:
        configure(alice)
        fake.reply(ANSWER)

        config = services.check(alice)

        assert "api_key" in config.get_deferred_fields()


class TestTheConfiguration:
    def test_a_user_sees_only_their_own(self, alice: User, bob: User) -> None:
        mine = configure(alice)
        configure(bob)

        assert services.get_configuration(alice) == mine
        assert services.get_configuration(alice) is not None
        found = services.get_configuration(alice)
        assert found is not None and "api_key" in found.get_deferred_fields()

    def test_without_one_there_is_none(self, alice: User, bob: User) -> None:
        configure(bob)

        assert services.get_configuration(alice) is None


class TestTheUsageSummary:
    def add(self, owner: User, age_days: float, **fields: Any) -> None:
        data: dict[str, Any] = {
            "provider": "anthropic",
            "model": "m",
            "purpose": "check",
            "outcome": "success",
            "input_tokens": 10,
            "output_tokens": 4,
            **fields,
        }
        record = AIUsageRecord.objects.create(owner=owner, **data)
        AIUsageRecord.objects.filter(pk=record.pk).update(created_at=NOW - timedelta(days=age_days))

    def test_nothing_gives_zeros(self, alice: User) -> None:
        assert services.usage_summary(alice) == UsageSummary(0, 0, 0, 30)

    def test_calls_and_tokens_are_added_up(self, alice: User) -> None:
        self.add(alice, 1)
        self.add(alice, 5, input_tokens=100, output_tokens=40)

        assert services.usage_summary(alice) == UsageSummary(2, 110, 44, 30)

    def test_the_cached_tokens_are_added_up_and_unknown_ones_count_as_zero(
        self, alice: User
    ) -> None:
        self.add(alice, 1, cache_read_tokens=3000, cache_write_tokens=400)
        self.add(alice, 2, cache_read_tokens=500)
        self.add(alice, 3)

        found = services.usage_summary(alice)

        assert (found.cache_read_tokens, found.cache_write_tokens) == (3500, 400)
        assert found.input_tokens == 30  # the cached part is part of the input, not on top

    def test_the_cached_tokens_of_others_and_of_old_calls_do_not_count(
        self, alice: User, bob: User
    ) -> None:
        self.add(bob, 1, cache_read_tokens=999)
        self.add(alice, 40, cache_read_tokens=999)

        assert services.usage_summary(alice).cache_read_tokens == 0

    def test_failed_calls_count_as_calls_without_tokens(self, alice: User) -> None:
        self.add(alice, 1)
        self.add(alice, 1, outcome="invalid_key", input_tokens=None, output_tokens=None)

        assert services.usage_summary(alice) == UsageSummary(2, 10, 4, 30)

    def test_unknown_token_counts_count_as_zero(self, alice: User) -> None:
        self.add(alice, 1, input_tokens=None, output_tokens=None)

        assert services.usage_summary(alice) == UsageSummary(1, 0, 0, 30)

    def test_the_period_is_thirty_days_and_includes_its_first_moment(self, alice: User) -> None:
        self.add(alice, 29.9)
        self.add(alice, 30)
        self.add(alice, 30.1)
        self.add(alice, 400)

        assert services.usage_summary(alice).calls == 2

    def test_another_period_can_be_asked_for(self, alice: User) -> None:
        self.add(alice, 3)
        self.add(alice, 10)

        assert services.usage_summary(alice, days=7) == UsageSummary(1, 10, 4, 7)
        assert services.usage_summary(alice, days=14).calls == 2

    def test_only_the_own_records_count(self, alice: User, bob: User) -> None:
        self.add(alice, 1)
        self.add(bob, 1, input_tokens=999, output_tokens=999)

        assert services.usage_summary(alice) == UsageSummary(1, 10, 4, 30)

    def test_the_default_is_thirty_days(self) -> None:
        assert services.USAGE_DAYS == 30


class TestSavingTheConfiguration:
    def save(self, user: User, **fields: Any) -> AIProviderConfiguration:
        data: dict[str, Any] = {
            "provider": "anthropic",
            "model": "claude-sonnet-5-5",
            "base_url": "",
            "api_key": KEY,
        }
        return services.save_configuration(user, **(data | fields))

    def test_messages_from_the_field_checks_and_from_clean_are_all_kept(
        self, alice: User, settings: Any
    ) -> None:
        settings.AI_ALLOWED_BASE_URLS = ()
        long_address = "http://localhost/" + "a" * 300

        with pytest.raises(ValidationError) as raised:
            self.save(alice, provider="openai_compatible", base_url=long_address, api_key="")

        messages = raised.value.message_dict["base_url"]
        assert len(messages) == 2
        assert "This address is not allowed on this server." in messages

    def test_a_race_for_the_first_save_is_retried_once(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = services._save
        calls: list[int] = []

        def lose_the_race(*args: Any, **kwargs: Any) -> AIProviderConfiguration:
            calls.append(1)
            if len(calls) == 1:
                raise IntegrityError("coach_one_provider_per_owner")
            return real(*args, **kwargs)

        monkeypatch.setattr(services, "_save", lose_the_race)

        config = self.save(alice)

        assert len(calls) == 2
        assert config.model == "claude-sonnet-5-5"

    def test_a_second_failure_is_not_hidden(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def always(*args: Any, **kwargs: Any) -> AIProviderConfiguration:
            raise IntegrityError("coach_one_provider_per_owner")

        monkeypatch.setattr(services, "_save", always)

        with pytest.raises(IntegrityError):
            self.save(alice)
