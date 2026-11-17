from typing import Any

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction

from accounts.models import User
from coach.models import BASE_URL_MAX, MODEL_MAX, AIProviderConfiguration, AIUsageRecord
from core.encryption import PREFIX

pytestmark = pytest.mark.django_db

KEY = "sk-test-0123456789-abcdefghij"
LOCAL = "http://localhost:11434/v1"


@pytest.fixture(autouse=True)
def _allowed(settings: Any) -> None:
    settings.AI_ALLOWED_BASE_URLS = (LOCAL, "https://api.openai.com/v1")


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def anthropic(**fields: Any) -> dict[str, Any]:
    return {"provider": "anthropic", "model": "claude-sonnet-5-5", "api_key": KEY, **fields}


def compatible(**fields: Any) -> dict[str, Any]:
    return {
        "provider": "openai_compatible",
        "model": "llama3.1:8b",
        "api_key": "",
        "base_url": LOCAL,
        **fields,
    }


def check(owner: User, **fields: Any) -> None:
    AIProviderConfiguration(owner=owner, **fields).full_clean(exclude=["owner"])


def refused(owner: User, field: str, **fields: Any) -> None:
    with pytest.raises(ValidationError) as raised:
        check(owner, **fields)
    assert field in raised.value.message_dict, raised.value.message_dict


def rejected_by_database(**fields: Any) -> str:
    with pytest.raises(IntegrityError) as raised, transaction.atomic():
        AIProviderConfiguration.objects.create(**fields)
    return str(raised.value)


def stored_key(pk: int) -> str:
    table = AIProviderConfiguration._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT api_key FROM {table} WHERE id = %s", [pk])
        return str(cursor.fetchone()[0])


class TestValidConfigurations:
    @pytest.mark.parametrize(
        "fields",
        [
            anthropic(),
            compatible(),
            compatible(api_key=KEY, base_url="https://api.openai.com/v1", model="gpt-4o"),
            compatible(model="org/model-name_v2.1"),
        ],
    )
    def test_a_complete_configuration_is_valid(self, alice: User, fields: dict[str, Any]) -> None:
        check(alice, **fields)

    def test_the_defaults_are_untested_and_never_called(self, alice: User) -> None:
        config = AIProviderConfiguration.objects.create(owner=alice, **anthropic())

        assert config.status == "untested"
        assert config.last_checked_at is None
        assert config.last_success_at is None

    def test_a_local_endpoint_needs_no_key(self, alice: User) -> None:
        check(alice, **compatible(api_key=""))


class TestLimits:
    def test_the_limits_are_written_out_on_purpose(self) -> None:
        # The other tests read the constants and would follow a change.
        assert MODEL_MAX == 100
        assert BASE_URL_MAX == 200


class TestRules:
    def test_anthropic_needs_a_key(self, alice: User) -> None:
        refused(alice, "api_key", **anthropic(api_key=""))

    def test_anthropic_has_no_address(self, alice: User) -> None:
        refused(alice, "base_url", **anthropic(base_url=LOCAL))

    def test_an_openai_compatible_endpoint_needs_an_address(self, alice: User) -> None:
        refused(alice, "base_url", **compatible(base_url=""))

    def test_the_messages_say_what_is_wrong(self, alice: User) -> None:
        def message(**fields: Any) -> str:
            with pytest.raises(ValidationError) as raised:
                check(alice, **fields)
            return " ".join(raised.value.message_dict["base_url"])

        assert message(**compatible(base_url="")) == "Choose the address of the endpoint."
        assert message(**compatible(base_url="http://x.example")) == (
            "This address is not allowed on this server."
        )
        assert message(**anthropic(base_url=LOCAL)) == "Anthropic needs no address."

    @pytest.mark.parametrize(
        "address",
        [
            "http://169.254.169.254/latest",
            "http://localhost:11434",
            "http://localhost:11434/v1/",
            "http://LOCALHOST:11434/v1",
            "https://api.openai.com",
            "http://localhost:11434/v1?x=1",
            "http://localhost:11435/v1",
        ],
    )
    def test_an_address_that_is_not_on_the_list_is_refused(self, alice: User, address: str) -> None:
        refused(alice, "base_url", **compatible(base_url=address))

    def test_the_list_is_read_when_the_check_runs(self, alice: User, settings: Any) -> None:
        check(alice, **compatible())

        settings.AI_ALLOWED_BASE_URLS = ()

        refused(alice, "base_url", **compatible())

    @pytest.mark.parametrize(
        "model",
        [
            "",
            " ",
            "-gpt",
            ".x",
            "a b",
            "a;b",
            "a\nb",
            "gpt\n",
            "\ngpt",
            "a$b",
            "model<script>",
            "é",
        ],
    )
    def test_a_malformed_model_is_refused(self, alice: User, model: str) -> None:
        refused(alice, "model", **anthropic(model=model))

    def test_the_model_may_have_100_characters_but_not_more(self, alice: User) -> None:
        check(alice, **anthropic(model="m" * MODEL_MAX))
        refused(alice, "model", **anthropic(model="m" * (MODEL_MAX + 1)))

    @pytest.mark.parametrize(
        "key",
        ["has space", " lead", "trail ", "line\nbreak", "tab\there", "ünï", "k\x00", "k" * 501],
    )
    def test_a_key_that_cannot_travel_in_a_header_is_refused(self, alice: User, key: str) -> None:
        refused(alice, "api_key", **anthropic(api_key=key))
        refused(alice, "api_key", **compatible(api_key=key))

    @pytest.mark.parametrize("key", ["k", "sk-ant-api03-AbC_dEf-123", "!~", "k" * 500])
    def test_a_key_of_visible_characters_is_accepted(self, alice: User, key: str) -> None:
        check(alice, **anthropic(api_key=key))

    def test_the_key_limit_is_written_out_on_purpose(self) -> None:
        from coach.models import KEY_MAX

        assert KEY_MAX == 500

    def test_the_address_has_a_length_limit(self, alice: User, settings: Any) -> None:
        long = "http://localhost/" + "a" * BASE_URL_MAX
        settings.AI_ALLOWED_BASE_URLS = (long,)

        refused(alice, "base_url", **compatible(base_url=long))

    @pytest.mark.parametrize(("field", "value"), [("provider", "gemini"), ("status", "broken")])
    def test_unknown_choices_are_refused(self, alice: User, field: str, value: str) -> None:
        refused(alice, field, **anthropic(**{field: value}))


class TestDatabase:
    def test_a_user_has_one_configuration(self, alice: User, bob: User) -> None:
        AIProviderConfiguration.objects.create(owner=alice, **anthropic())
        AIProviderConfiguration.objects.create(owner=bob, **anthropic())

        message = rejected_by_database(owner=alice, **anthropic())

        assert "coach_one_provider_per_owner" in message

    def test_the_model_cannot_be_empty(self, alice: User) -> None:
        message = rejected_by_database(owner=alice, **anthropic(model=""))

        assert "coach_model_not_empty" in message

    def test_anthropic_cannot_have_an_address(self, alice: User) -> None:
        message = rejected_by_database(owner=alice, **anthropic(base_url=LOCAL))

        assert "coach_anthropic_has_no_base_url" in message

    def test_a_compatible_endpoint_cannot_lack_its_address(self, alice: User) -> None:
        message = rejected_by_database(owner=alice, **compatible(base_url=""))

        assert "coach_compatible_has_base_url" in message


class TestTheKey:
    def test_it_is_stored_encrypted_and_read_back(self, alice: User) -> None:
        config = AIProviderConfiguration.objects.create(owner=alice, **anthropic())

        raw = stored_key(config.pk)

        assert raw.startswith(PREFIX)
        assert KEY not in raw
        config.refresh_from_db()
        assert config.api_key == KEY

    def test_the_text_does_not_show_the_key_or_the_model(self, alice: User) -> None:
        config = AIProviderConfiguration.objects.create(owner=alice, **anthropic())

        text = str(config)

        assert KEY not in text
        assert "claude" not in text
        assert str(alice.pk) in text
        assert "Anthropic" in text

    def test_it_is_not_editable_through_forms(self) -> None:
        assert AIProviderConfiguration._meta.get_field("api_key").editable is False


class TestOwnership:
    def test_for_user_shows_only_the_own_configuration(self, alice: User, bob: User) -> None:
        mine = AIProviderConfiguration.objects.create(owner=alice, **anthropic())
        AIProviderConfiguration.objects.create(owner=bob, **anthropic())

        assert list(AIProviderConfiguration.objects.for_user(alice)) == [mine]

    def test_an_anonymous_user_owns_nothing(self, alice: User) -> None:
        AIProviderConfiguration.objects.create(owner=alice, **anthropic())

        assert not AIProviderConfiguration.objects.for_user(AnonymousUser()).exists()

    def test_deleting_the_user_deletes_the_configuration(self, alice: User, bob: User) -> None:
        AIProviderConfiguration.objects.create(owner=alice, **anthropic())
        AIProviderConfiguration.objects.create(owner=bob, **anthropic())

        alice.delete()

        assert AIProviderConfiguration.objects.count() == 1


class TestUsageRecords:
    def record(self, owner: User, **fields: Any) -> AIUsageRecord:
        data: dict[str, Any] = {
            "provider": "anthropic",
            "model": "claude-sonnet-5-5",
            "purpose": "check",
            "outcome": "success",
            **fields,
        }
        return AIUsageRecord.objects.create(owner=owner, **data)

    def test_a_record_holds_only_facts(self) -> None:
        names = {f.name for f in AIUsageRecord._meta.get_fields()}

        # No prompt, no answer, no error text: the fields are listed on purpose.
        assert names == {
            "id",
            "owner",
            "provider",
            "model",
            "purpose",
            "outcome",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "created_at",
        }

    def test_tokens_may_be_unknown(self, alice: User) -> None:
        record = self.record(alice)

        assert (record.input_tokens, record.output_tokens) == (None, None)

    def test_the_cached_tokens_may_be_unknown_too(self, alice: User) -> None:
        record = self.record(alice)

        assert (record.cache_read_tokens, record.cache_write_tokens) == (None, None)

    def test_the_cached_tokens_are_kept(self, alice: User) -> None:
        record = self.record(alice, cache_read_tokens=3000, cache_write_tokens=400)
        record.refresh_from_db()

        assert (record.cache_read_tokens, record.cache_write_tokens) == (3000, 400)

    @pytest.mark.parametrize("field", ["cache_read_tokens", "cache_write_tokens"])
    def test_the_cached_tokens_cannot_be_negative(self, alice: User, field: str) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            self.record(alice, **{field: -1})

    def test_tokens_cannot_be_negative(self, alice: User) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            self.record(alice, input_tokens=-1)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("provider", "gemini"),
            ("purpose", "gossip"),
            ("outcome", "fine"),
        ],
    )
    def test_unknown_choices_are_refused(self, alice: User, field: str, value: str) -> None:
        record = AIUsageRecord(
            owner=alice,
            provider="anthropic",
            model="m",
            purpose="check",
            outcome="success",
        )
        setattr(record, field, value)

        with pytest.raises(ValidationError) as raised:
            record.full_clean(exclude=["owner"])

        assert field in raised.value.message_dict

    def test_the_time_is_set_on_creation(self, alice: User) -> None:
        assert self.record(alice).created_at is not None

    def test_the_text_names_neither_the_model_nor_a_provider_text(self, alice: User) -> None:
        text = str(self.record(alice))

        assert "claude" not in text
        assert str(alice.pk) in text
        assert "check" in text

    def test_for_user_shows_only_the_own_records(self, alice: User, bob: User) -> None:
        mine = self.record(alice)
        self.record(bob)

        assert list(AIUsageRecord.objects.for_user(alice)) == [mine]
        assert not AIUsageRecord.objects.for_user(AnonymousUser()).exists()

    def test_records_survive_the_configuration_and_go_with_the_user(
        self, alice: User, bob: User
    ) -> None:
        AIProviderConfiguration.objects.create(owner=alice, **anthropic())
        self.record(alice)
        self.record(bob)

        AIProviderConfiguration.objects.filter(owner=alice).delete()
        assert AIUsageRecord.objects.filter(owner=alice).count() == 1

        alice.delete()
        assert AIUsageRecord.objects.count() == 1
