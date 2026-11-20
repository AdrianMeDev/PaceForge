import json
import logging
from http import HTTPStatus
from typing import Any

import pytest
from django.db import connection

from accounts.models import User
from accounts.tests.conftest import AuthApi
from coach.models import AIProviderConfiguration, AIUsageRecord
from coach.views import PROBLEMS

from .conftest import make_user, signed_in
from .fake_providers import FakeProvider, running

pytestmark = pytest.mark.django_db

URL = "/api/coach/provider/"
CHECK = "/api/coach/provider/check/"
KEY = "sk-ant-test-0123456789-abcdefghij"
OTHER_KEY = "sk-ant-other-9876543210-zyxwvutsrq"
MODEL = "claude-sonnet-5-5"
LOCAL_MODEL = "llama3.1:8b"
STATE_FIELDS = {
    "configured",
    "provider",
    "model",
    "season_model",
    "week_model",
    "chat_model",
    "base_url",
    "has_key",
    "status",
    "last_checked_at",
    "last_success_at",
    "allowed_base_urls",
    "usage",
}
ANSWER = {
    "content": [{"type": "text", "text": "ok"}],
    "usage": {"input_tokens": 12, "output_tokens": 5},
}


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


@pytest.fixture
def base(fake: FakeProvider, settings: Any) -> str:
    """The address of the fake server as an operator would list it."""
    address = fake.url + "/v1"
    settings.AI_ALLOWED_BASE_URLS = (address, "https://api.openai.com/v1")
    return address


def body(response: Any) -> Any:
    return json.loads(response.content)


def anthropic(**fields: Any) -> dict[str, Any]:
    return {"provider": "anthropic", "model": MODEL, "api_key": KEY, **fields}


def compatible(base_url: str, **fields: Any) -> dict[str, Any]:
    return {"provider": "openai_compatible", "model": LOCAL_MODEL, "base_url": base_url, **fields}


def save(api: AuthApi, data: Any) -> Any:
    return api.call("PUT", URL, data)


def read(api: AuthApi) -> Any:
    response = api.call("GET", URL)
    assert response.status_code == HTTPStatus.OK
    return body(response)


def stored(owner: User) -> AIProviderConfiguration:
    return AIProviderConfiguration.objects.get(owner=owner)


def stored_raw_key(owner: User) -> str:
    table = AIProviderConfiguration._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT api_key FROM {table} WHERE owner_id = %s", [owner.pk])
        return str(cursor.fetchone()[0])


def make_connected(owner: User, **fields: Any) -> AIProviderConfiguration:
    data: dict[str, Any] = {
        "provider": "anthropic",
        "model": MODEL,
        "api_key": KEY,
        "status": "connected",
    }
    return AIProviderConfiguration.objects.create(owner=owner, **(data | fields))


class TestAccess:
    @pytest.mark.parametrize(
        ("method", "url"),
        [("GET", URL), ("PUT", URL), ("DELETE", URL), ("POST", CHECK)],
    )
    def test_anonymous_visitors_are_refused(self, method: str, url: str) -> None:
        response = AuthApi().call(method, url, anthropic())

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert not AIProviderConfiguration.objects.exists()

    @pytest.mark.parametrize(("method", "url"), [("PUT", URL), ("DELETE", URL), ("POST", CHECK)])
    def test_a_request_without_the_csrf_token_is_refused(
        self, alice: User, method: str, url: str
    ) -> None:
        make_connected(alice)
        api = signed_in(alice)

        response = api.client.generic(
            method, url, data=json.dumps(anthropic()), content_type="application/json"
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert AIProviderConfiguration.objects.count() == 1

    @pytest.mark.parametrize(
        ("method", "url"),
        [("PATCH", URL), ("POST", URL), ("GET", CHECK), ("PUT", CHECK), ("DELETE", CHECK)],
    )
    def test_other_methods_are_not_allowed(self, alice: User, method: str, url: str) -> None:
        response = signed_in(alice).call(method, url, {})

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED


class TestReading:
    def test_a_user_without_a_setup_gets_an_empty_state(self, alice: User) -> None:
        state = read(signed_in(alice))

        assert state == {
            "configured": False,
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
            "allowed_base_urls": [],
            "usage": {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "days": 30,
            },
        }

    def test_reading_writes_nothing(self, alice: User) -> None:
        api = signed_in(alice)

        read(api)
        read(api)

        assert not AIProviderConfiguration.objects.exists()
        assert not AIUsageRecord.objects.exists()

    def test_the_allowed_addresses_are_the_operators(self, alice: User, settings: Any) -> None:
        settings.AI_ALLOWED_BASE_URLS = ("http://localhost:11434/v1", "https://api.openai.com/v1")

        assert read(signed_in(alice))["allowed_base_urls"] == [
            "http://localhost:11434/v1",
            "https://api.openai.com/v1",
        ]

    def test_a_setup_is_shown_without_its_key(self, alice: User) -> None:
        make_connected(alice, status="invalid")
        api = signed_in(alice)

        response = api.call("GET", URL)

        state = body(response)
        assert set(state) == STATE_FIELDS
        assert state["configured"] is True
        assert (state["provider"], state["model"], state["base_url"]) == ("anthropic", MODEL, None)
        assert (state["has_key"], state["status"]) == (True, "invalid")
        assert KEY not in response.content.decode()
        assert "api_key" not in state
        assert "sk-" not in response.content.decode()

    def test_a_compatible_setup_shows_its_address(self, alice: User, base: str) -> None:
        AIProviderConfiguration.objects.create(
            owner=alice, provider="openai_compatible", model=LOCAL_MODEL, api_key="", base_url=base
        )

        state = read(signed_in(alice))

        assert (state["provider"], state["base_url"], state["has_key"]) == (
            "openai_compatible",
            base,
            False,
        )

    def test_the_times_are_shown_as_timestamps(self, alice: User) -> None:
        from datetime import UTC, datetime

        checked = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
        succeeded = datetime(2026, 11, 12, 8, 30, tzinfo=UTC)
        make_connected(alice, last_checked_at=checked, last_success_at=succeeded)

        state = read(signed_in(alice))

        assert state["last_checked_at"] == "2026-11-13T12:00:00Z"
        assert state["last_success_at"] == "2026-11-12T08:30:00Z"

    def test_the_usage_counts_the_own_calls(self, alice: User, bob: User) -> None:
        for owner, tokens in ((alice, 10), (alice, 20), (bob, 999)):
            AIUsageRecord.objects.create(
                owner=owner,
                provider="anthropic",
                model=MODEL,
                purpose="check",
                outcome="success",
                input_tokens=tokens,
                output_tokens=1,
            )

        assert read(signed_in(alice))["usage"] == {
            "calls": 2,
            "input_tokens": 30,
            "output_tokens": 2,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "days": 30,
        }

    def test_the_usage_tells_how_much_of_the_input_came_from_the_cache(
        self, alice: User, bob: User
    ) -> None:
        for owner, read_tokens, written in ((alice, 3000, 0), (alice, 0, 400), (bob, 999, 999)):
            AIUsageRecord.objects.create(
                owner=owner,
                provider="anthropic",
                model=MODEL,
                purpose="weekly_plan",
                outcome="success",
                input_tokens=read_tokens + written + 10,
                output_tokens=1,
                cache_read_tokens=read_tokens,
                cache_write_tokens=written,
            )

        usage = read(signed_in(alice))["usage"]

        assert (usage["cache_read_tokens"], usage["cache_write_tokens"]) == (3000, 400)
        assert usage["input_tokens"] == 3420  # the cached parts are part of it

    def test_a_key_that_cannot_be_read_counts_as_no_key(self, alice: User) -> None:
        config = make_connected(alice)
        table = AIProviderConfiguration._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET api_key = %s WHERE id = %s", ["enc:v1:garbage", config.pk]
            )

        state = read(signed_in(alice))

        assert state["configured"] is True
        assert state["has_key"] is False

    def test_a_user_never_sees_anothers_setup(self, alice: User, bob: User) -> None:
        make_connected(bob, model="bobs-model")

        assert read(signed_in(alice))["configured"] is False


class TestSavingForTheFirstTime:
    def test_anthropic(self, alice: User) -> None:
        response = save(signed_in(alice), anthropic())

        assert response.status_code == HTTPStatus.OK
        state = body(response)
        assert set(state) == STATE_FIELDS
        assert (state["configured"], state["provider"], state["model"]) == (
            True,
            "anthropic",
            MODEL,
        )
        assert (state["base_url"], state["has_key"], state["status"]) == (None, True, "untested")
        assert (state["last_checked_at"], state["last_success_at"]) == (None, None)
        assert stored(alice).api_key == KEY

    def test_the_key_is_stored_encrypted(self, alice: User) -> None:
        save(signed_in(alice), anthropic())

        raw = stored_raw_key(alice)

        assert raw.startswith("enc:v1:")
        assert KEY not in raw

    def test_the_answer_never_holds_the_key(self, alice: User) -> None:
        response = save(signed_in(alice), anthropic())

        assert KEY not in response.content.decode()
        assert "api_key" not in body(response)

    def test_an_openai_compatible_endpoint_without_a_key(self, alice: User, base: str) -> None:
        response = save(signed_in(alice), compatible(base))

        state = body(response)
        assert (state["provider"], state["base_url"], state["has_key"]) == (
            "openai_compatible",
            base,
            False,
        )
        assert stored(alice).api_key == ""

    def test_an_openai_compatible_endpoint_with_a_key(self, alice: User, base: str) -> None:
        response = save(signed_in(alice), compatible(base, api_key=KEY))

        assert body(response)["has_key"] is True
        assert stored(alice).api_key == KEY

    def test_an_empty_address_for_anthropic_is_as_good_as_none(self, alice: User) -> None:
        assert save(signed_in(alice), anthropic(base_url="")).status_code == HTTPStatus.OK

    def test_a_line_break_around_the_model_is_trimmed_away(self, alice: User) -> None:
        save(signed_in(alice), anthropic(model="gpt-4o\n"))

        assert stored(alice).model == "gpt-4o"

    def test_text_is_trimmed(self, alice: User) -> None:
        save(signed_in(alice), anthropic(model=f"  {MODEL}  ", api_key=f"  {KEY}  "))

        config = stored(alice)
        assert (config.model, config.api_key) == (MODEL, KEY)

    def test_what_the_server_decides_cannot_be_sent(self, alice: User, bob: User) -> None:
        response = save(
            signed_in(alice),
            anthropic(
                status="connected",
                last_success_at="2026-01-01T00:00:00Z",
                owner=str(bob.pk),
                id=7,
            ),
        )

        state = body(response)
        assert state["status"] == "untested"
        assert state["last_success_at"] is None
        assert stored(alice).owner == alice
        assert not AIProviderConfiguration.objects.filter(owner=bob).exists()

    def test_no_usage_is_recorded_by_saving(self, alice: User) -> None:
        save(signed_in(alice), anthropic())

        assert not AIUsageRecord.objects.exists()


class TestRefusals:
    @pytest.mark.parametrize(
        ("data", "fields"),
        [
            ({}, {"provider", "model"}),
            ({"model": MODEL, "api_key": KEY}, {"provider"}),
            ({"provider": "anthropic", "api_key": KEY}, {"model"}),
            (anthropic(provider="gemini"), {"provider"}),
            (anthropic(provider=""), {"provider"}),
            (anthropic(model=""), {"model"}),
            (anthropic(model="-gpt"), {"model"}),
            (anthropic(model="gpt\n4o"), {"model"}),
            (anthropic(model="a b"), {"model"}),
            (anthropic(model="m" * 101), {"model"}),
            (anthropic(base_url="http://localhost:11434/v1"), {"base_url"}),
            (anthropic(api_key=""), {"api_key"}),
            (anthropic(api_key="has space"), {"api_key"}),
            (anthropic(api_key="line\nbreak"), {"api_key"}),
            (anthropic(api_key="ünïcode"), {"api_key"}),
            (anthropic(api_key="k" * 501), {"api_key"}),
        ],
    )
    def test_unusable_input_is_refused_by_field(
        self, alice: User, data: dict[str, Any], fields: set[str]
    ) -> None:
        response = save(signed_in(alice), data)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert set(body(response)) == fields
        assert not AIProviderConfiguration.objects.exists()

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("provider", 5),
            ("provider", None),
            ("provider", ["anthropic"]),
            ("model", 5),
            ("model", None),
            ("model", ["m"]),
            ("model", True),
            ("base_url", 5),
            ("base_url", None),
            ("base_url", ["x"]),
            ("api_key", 5),
            ("api_key", None),
            ("api_key", True),
            ("api_key", {"k": "v"}),
        ],
    )
    def test_values_of_the_wrong_type_are_refused(
        self, alice: User, field: str, value: Any
    ) -> None:
        response = save(signed_in(alice), anthropic(**{field: value}))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert field in body(response)
        assert not AIProviderConfiguration.objects.exists()

    @pytest.mark.parametrize("data", [[], "text", 5])
    def test_a_body_that_is_no_object_is_refused(self, alice: User, data: Any) -> None:
        assert save(signed_in(alice), data).status_code == HTTPStatus.BAD_REQUEST

    def test_a_compatible_endpoint_needs_an_address(self, alice: User, base: str) -> None:
        response = save(signed_in(alice), compatible(""))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"base_url": ["Choose the address of the endpoint."]}

    @pytest.mark.parametrize(
        "address",
        [
            "http://169.254.169.254/latest",
            "http://localhost:11434/v1",
            "https://api.openai.com",
            "https://api.openai.com/v1/",
            "https://API.openai.com/v1",
            "http://127.0.0.1:1/v1",
        ],
    )
    def test_an_address_that_is_not_on_the_operators_list_is_refused(
        self, alice: User, base: str, address: str
    ) -> None:
        response = save(signed_in(alice), compatible(address))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"base_url": ["This address is not allowed on this server."]}
        assert not AIProviderConfiguration.objects.exists()

    def test_with_an_empty_list_no_address_is_allowed(self, alice: User, settings: Any) -> None:
        settings.AI_ALLOWED_BASE_URLS = ()

        response = save(signed_in(alice), compatible("https://api.openai.com/v1"))

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_every_problem_is_named_at_once(self, alice: User) -> None:
        response = save(
            signed_in(alice),
            {"provider": "anthropic", "model": "-", "base_url": "http://x.example", "api_key": ""},
        )

        assert set(body(response)) == {"model", "base_url", "api_key"}

    def test_the_messages_say_what_is_wrong_and_hold_no_input(self, alice: User) -> None:
        response = save(signed_in(alice), anthropic(api_key="my secret key"))

        assert body(response) == {
            "api_key": ["A key has no spaces or special characters and at most 500 characters."]
        }
        assert "my secret key" not in response.content.decode()


class TestTheSeasonModel:
    def test_it_is_saved_and_shown(self, alice: User) -> None:
        state = body(save(signed_in(alice), anthropic(season_model="claude-opus-5-5")))

        assert state["season_model"] == "claude-opus-5-5"
        assert stored(alice).season_model == "claude-opus-5-5"
        assert body(signed_in(alice).call("GET", URL))["season_model"] == "claude-opus-5-5"

    def test_it_is_empty_when_it_is_left_out(self, alice: User) -> None:
        state = body(save(signed_in(alice), anthropic()))

        assert state["season_model"] == ""

    def test_leaving_it_out_when_saving_again_takes_it_away(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, anthropic(season_model="claude-opus-5-5"))

        state = body(save(api, {"provider": "anthropic", "model": MODEL}))

        assert state["season_model"] == ""

    @pytest.mark.parametrize("name", ["-bad", "has space", "x" * 101, 5, ["m"], None])
    def test_a_name_that_is_not_one_is_refused_at_its_field(self, alice: User, name: Any) -> None:
        response = save(signed_in(alice), anthropic(season_model=name))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert set(body(response)) == {"season_model"}
        assert not AIProviderConfiguration.objects.exists()


class TestTheWeekAndChatModels:
    @pytest.mark.parametrize("field", ["week_model", "chat_model"])
    def test_it_is_saved_shown_and_cleared(self, alice: User, field: str) -> None:
        api = signed_in(alice)

        state = body(save(api, anthropic(**{field: "claude-haiku-5-5"})))

        assert state[field] == "claude-haiku-5-5"
        assert getattr(stored(alice), field) == "claude-haiku-5-5"
        assert body(api.call("GET", URL))[field] == "claude-haiku-5-5"
        assert body(save(api, anthropic(**{field: ""})))[field] == ""
        assert getattr(stored(alice), field) == ""

    def test_they_are_empty_when_left_out(self, alice: User) -> None:
        state = body(save(signed_in(alice), anthropic()))

        assert (state["week_model"], state["chat_model"]) == ("", "")

    @pytest.mark.parametrize("field", ["week_model", "chat_model"])
    @pytest.mark.parametrize("name", ["-bad", "has space", "x" * 101, 5, ["m"], None])
    def test_a_name_that_is_not_one_is_refused_at_its_field(
        self, alice: User, field: str, name: Any
    ) -> None:
        response = save(signed_in(alice), anthropic(**{field: name}))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert set(body(response)) == {field}
        assert not AIProviderConfiguration.objects.exists()

    def test_the_models_of_another_user_are_not_shown(self, alice: User, bob: User) -> None:
        save(signed_in(bob), anthropic(week_model="bobs-week", chat_model="bobs-chat"))

        state = body(save(signed_in(alice), anthropic()))

        assert (state["week_model"], state["chat_model"]) == ("", "")
        assert stored(bob).week_model == "bobs-week"


class TestChangingTheSetup:
    def test_the_model_changes_and_the_key_is_kept(self, alice: User) -> None:
        make_connected(alice)
        api = signed_in(alice)

        response = save(api, {"provider": "anthropic", "model": "claude-opus-5-5"})

        assert response.status_code == HTTPStatus.OK
        config = stored(alice)
        assert (config.model, config.api_key) == ("claude-opus-5-5", KEY)
        assert body(response)["has_key"] is True

    def test_a_change_sets_the_status_back_and_forgets_the_last_check(self, alice: User) -> None:
        from datetime import UTC, datetime

        moment = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
        make_connected(alice, last_checked_at=moment, last_success_at=moment)

        state = body(save(signed_in(alice), {"provider": "anthropic", "model": "claude-opus-5-5"}))

        assert state["status"] == "untested"
        assert (state["last_checked_at"], state["last_success_at"]) == (None, None)

    def test_saving_the_same_setup_again_keeps_status_and_times(self, alice: User) -> None:
        from datetime import UTC, datetime

        moment = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
        make_connected(alice, last_checked_at=moment, last_success_at=moment)

        state = body(save(signed_in(alice), {"provider": "anthropic", "model": MODEL}))

        assert state["status"] == "connected"
        assert state["last_success_at"] == "2026-11-13T12:00:00Z"
        assert stored(alice).api_key == KEY

    def test_a_new_key_replaces_the_old_one_and_sets_the_status_back(self, alice: User) -> None:
        make_connected(alice)

        state = body(save(signed_in(alice), anthropic(api_key=OTHER_KEY)))

        assert stored(alice).api_key == OTHER_KEY
        assert state["status"] == "untested"

    def test_an_empty_key_is_refused_for_anthropic_and_changes_nothing(self, alice: User) -> None:
        make_connected(alice)

        response = save(signed_in(alice), anthropic(api_key=""))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        config = stored(alice)
        assert (config.api_key, config.status) == (KEY, "connected")

    def test_a_compatible_endpoint_can_drop_its_key(self, alice: User, base: str) -> None:
        AIProviderConfiguration.objects.create(
            owner=alice,
            provider="openai_compatible",
            model=LOCAL_MODEL,
            api_key=KEY,
            base_url=base,
            status="connected",
        )

        state = body(save(signed_in(alice), compatible(base, api_key="")))

        assert state["has_key"] is False
        assert stored(alice).api_key == ""

    def test_the_key_is_not_carried_to_another_provider(self, alice: User, base: str) -> None:
        make_connected(alice)

        state = body(save(signed_in(alice), compatible(base)))

        assert state["has_key"] is False
        assert stored(alice).api_key == ""
        assert stored(alice).provider == "openai_compatible"

    def test_the_key_is_not_carried_to_another_address(self, alice: User, base: str) -> None:
        AIProviderConfiguration.objects.create(
            owner=alice,
            provider="openai_compatible",
            model=LOCAL_MODEL,
            api_key=KEY,
            base_url="https://api.openai.com/v1",
        )

        state = body(save(signed_in(alice), compatible(base)))

        assert state["has_key"] is False
        assert stored(alice).api_key == ""
        assert stored(alice).base_url == base

    def test_the_same_address_keeps_the_key(self, alice: User, base: str) -> None:
        AIProviderConfiguration.objects.create(
            owner=alice, provider="openai_compatible", model=LOCAL_MODEL, api_key=KEY, base_url=base
        )

        save(signed_in(alice), compatible(base, model="qwen2.5:7b"))

        assert stored(alice).api_key == KEY

    def test_going_to_anthropic_without_a_key_is_refused_and_changes_nothing(
        self, alice: User, base: str
    ) -> None:
        AIProviderConfiguration.objects.create(
            owner=alice, provider="openai_compatible", model=LOCAL_MODEL, api_key=KEY, base_url=base
        )

        response = save(signed_in(alice), {"provider": "anthropic", "model": MODEL})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"api_key": ["Anthropic needs a key."]}
        config = stored(alice)
        assert (config.provider, config.api_key) == ("openai_compatible", KEY)

    def test_a_stored_key_that_cannot_be_read_is_not_kept_for_anthropic(self, alice: User) -> None:
        config = make_connected(alice)
        table = AIProviderConfiguration._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET api_key = %s WHERE id = %s", ["enc:v1:garbage", config.pk]
            )

        response = save(signed_in(alice), {"provider": "anthropic", "model": MODEL})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "api_key" in body(response)

    def test_a_stored_key_that_cannot_be_read_is_replaced_by_a_new_one(self, alice: User) -> None:
        config = make_connected(alice)
        table = AIProviderConfiguration._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET api_key = %s WHERE id = %s", ["enc:v1:garbage", config.pk]
            )

        response = save(signed_in(alice), anthropic())

        assert response.status_code == HTTPStatus.OK
        assert stored(alice).api_key == KEY

    def test_a_compatible_endpoint_with_an_unreadable_key_gets_a_clean_slate(
        self, alice: User, base: str
    ) -> None:
        config = AIProviderConfiguration.objects.create(
            owner=alice, provider="openai_compatible", model=LOCAL_MODEL, api_key=KEY, base_url=base
        )
        table = AIProviderConfiguration._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET api_key = %s WHERE id = %s", ["enc:v1:garbage", config.pk]
            )

        state = body(save(signed_in(alice), compatible(base)))

        assert state["has_key"] is False
        assert stored(alice).api_key == ""
        assert state["status"] == "untested"

    def test_a_refused_change_leaves_the_setup_as_it_was(self, alice: User) -> None:
        make_connected(alice)

        response = save(signed_in(alice), {"provider": "anthropic", "model": "-bad"})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        config = stored(alice)
        assert (config.model, config.status, config.api_key) == (MODEL, "connected", KEY)

    def test_there_is_still_only_one_setup_per_user(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, anthropic())
        save(api, anthropic(model="claude-opus-5-5"))
        save(api, anthropic(api_key=OTHER_KEY))

        assert AIProviderConfiguration.objects.filter(owner=alice).count() == 1

    def test_changing_the_setup_keeps_the_usage_records(self, alice: User) -> None:
        make_connected(alice)
        AIUsageRecord.objects.create(
            owner=alice, provider="anthropic", model=MODEL, purpose="check", outcome="success"
        )

        save(signed_in(alice), {"provider": "anthropic", "model": "claude-opus-5-5"})

        assert AIUsageRecord.objects.count() == 1

    def test_one_users_change_leaves_the_other_alone(self, alice: User, bob: User) -> None:
        make_connected(bob)

        save(signed_in(alice), anthropic(api_key=OTHER_KEY))

        config = stored(bob)
        assert (config.api_key, config.status) == (KEY, "connected")


class TestRemoving:
    def test_the_setup_and_its_key_are_removed(self, alice: User) -> None:
        make_connected(alice)
        api = signed_in(alice)

        response = api.call("DELETE", URL)

        assert response.status_code == HTTPStatus.NO_CONTENT
        assert not AIProviderConfiguration.objects.exists()
        assert read(api)["configured"] is False

    def test_the_usage_records_stay(self, alice: User) -> None:
        make_connected(alice)
        AIUsageRecord.objects.create(
            owner=alice, provider="anthropic", model=MODEL, purpose="check", outcome="success"
        )

        signed_in(alice).call("DELETE", URL)

        assert AIUsageRecord.objects.count() == 1

    def test_removing_nothing_is_fine(self, alice: User) -> None:
        assert signed_in(alice).call("DELETE", URL).status_code == HTTPStatus.NO_CONTENT

    def test_another_users_setup_is_not_touched(self, alice: User, bob: User) -> None:
        make_connected(bob)

        signed_in(alice).call("DELETE", URL)

        assert AIProviderConfiguration.objects.filter(owner=bob).exists()


class TestTheCheck:
    def check(self, api: AuthApi) -> Any:
        response = api.call("POST", CHECK)
        assert response.status_code == HTTPStatus.OK, response.content
        return body(response)

    def test_without_a_setup_there_is_nothing_to_check(
        self, alice: User, fake: FakeProvider
    ) -> None:
        response = signed_in(alice).call("POST", CHECK)

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response) == {"detail": "No AI provider is set up."}
        assert fake.requests == []

    def test_a_working_setup_is_connected(self, alice: User, fake: FakeProvider) -> None:
        make_connected(alice, status="untested")
        fake.reply(ANSWER)

        answer = self.check(signed_in(alice))

        assert answer["check"] == {"ok": True, "problem": None, "message": "", "retry_after": None}
        assert set(answer) == STATE_FIELDS | {"check"}
        assert answer["status"] == "connected"
        assert answer["last_checked_at"] is not None
        assert answer["last_success_at"] is not None
        assert answer["usage"]["calls"] == 1
        assert answer["usage"]["input_tokens"] == 12
        assert fake.requests[0]["headers"]["x-api-key"] == KEY

    def test_a_compatible_endpoint_is_checked_too(
        self, alice: User, fake: FakeProvider, base: str
    ) -> None:
        AIProviderConfiguration.objects.create(
            owner=alice, provider="openai_compatible", model=LOCAL_MODEL, api_key="", base_url=base
        )
        fake.reply({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

        answer = self.check(signed_in(alice))

        assert answer["check"]["ok"] is True
        assert answer["status"] == "connected"
        assert fake.requests[0]["raw_path"] == "/v1/chat/completions"

    def test_a_refused_key(self, alice: User, fake: FakeProvider) -> None:
        make_connected(alice, status="untested")
        fake.reply({"error": {"message": f"bad key {KEY}"}}, 401)

        answer = self.check(signed_in(alice))

        assert answer["check"] == {
            "ok": False,
            "problem": "invalid_key",
            "message": PROBLEMS["invalid_key"],
            "retry_after": None,
        }
        assert answer["status"] == "invalid"

    def test_a_provider_that_asks_to_slow_down(self, alice: User, fake: FakeProvider) -> None:
        make_connected(alice)
        fake.headers = {"Retry-After": "30"}
        fake.reply({}, 429)

        answer = self.check(signed_in(alice))

        assert answer["check"]["problem"] == "rate_limited"
        assert answer["check"]["retry_after"] == 30
        assert answer["check"]["message"] == PROBLEMS["rate_limited"]
        assert answer["status"] == "connected"

    def test_a_provider_that_is_down(self, alice: User, fake: FakeProvider) -> None:
        make_connected(alice)
        fake.reply({}, 503)

        answer = self.check(signed_in(alice))

        assert answer["check"]["problem"] == "unavailable"
        assert answer["status"] == "unavailable"

    def test_a_provider_that_cannot_be_reached(self, alice: User, settings: Any) -> None:
        with running() as gone:
            settings.ANTHROPIC_API_BASE_URL = gone.url
        make_connected(alice)

        answer = self.check(signed_in(alice))

        assert answer["check"]["problem"] == "unavailable"

    def test_an_answer_that_makes_no_sense_leaves_the_status(
        self, alice: User, fake: FakeProvider
    ) -> None:
        make_connected(alice)
        fake.reply({"error": {"message": "model not found"}}, 404)

        answer = self.check(signed_in(alice))

        assert answer["check"]["problem"] == "unexpected"
        assert answer["check"]["message"] == PROBLEMS["unexpected"]
        assert answer["status"] == "connected"

    def test_an_address_the_operator_removed_is_refused_without_a_call(
        self, alice: User, fake: FakeProvider, base: str, settings: Any
    ) -> None:
        AIProviderConfiguration.objects.create(
            owner=alice, provider="openai_compatible", model=LOCAL_MODEL, api_key="", base_url=base
        )
        settings.AI_ALLOWED_BASE_URLS = ()

        answer = self.check(signed_in(alice))

        assert answer["check"]["problem"] == "not_allowed"
        assert answer["check"]["message"] == PROBLEMS["not_allowed"]
        assert answer["status"] == "untested"
        assert fake.requests == []
        assert answer["usage"]["calls"] == 0

    def test_a_key_that_cannot_be_read_counts_as_refused(
        self, alice: User, fake: FakeProvider
    ) -> None:
        config = make_connected(alice)
        table = AIProviderConfiguration._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET api_key = %s WHERE id = %s", ["enc:v1:garbage", config.pk]
            )

        answer = self.check(signed_in(alice))

        assert answer["check"]["problem"] == "invalid_key"
        assert answer["status"] == "invalid"
        assert fake.requests == []

    def test_the_messages_are_fixed_texts(self) -> None:
        assert set(PROBLEMS) == {
            "invalid_key",
            "rate_limited",
            "unavailable",
            "too_slow",
            "unexpected",
            "not_allowed",
        }

    def test_a_user_checks_only_their_own_setup(
        self, alice: User, bob: User, fake: FakeProvider
    ) -> None:
        make_connected(bob, api_key=OTHER_KEY)
        make_connected(alice)
        fake.reply(ANSWER)

        self.check(signed_in(alice))

        assert fake.requests[0]["headers"]["x-api-key"] == KEY
        assert stored(bob).last_checked_at is None
        assert not AIUsageRecord.objects.filter(owner=bob).exists()


class TestThrottling:
    def test_the_eleventh_check_within_a_minute_is_throttled(
        self, alice: User, fake: FakeProvider
    ) -> None:
        make_connected(alice)
        fake.reply(ANSWER)
        api = signed_in(alice)

        statuses = [api.call("POST", CHECK).status_code for _ in range(11)]

        assert statuses == [HTTPStatus.OK] * 10 + [HTTPStatus.TOO_MANY_REQUESTS]
        assert len(fake.requests) == 10  # the throttled request never reached the provider

    def test_reading_saving_and_removing_are_not_throttled(self, alice: User) -> None:
        api = signed_in(alice)

        for _ in range(15):
            assert api.call("GET", URL).status_code == HTTPStatus.OK
            assert save(api, anthropic()).status_code == HTTPStatus.OK
        assert api.call("DELETE", URL).status_code == HTTPStatus.NO_CONTENT

    def test_every_user_has_their_own_counter(
        self, alice: User, bob: User, fake: FakeProvider
    ) -> None:
        make_connected(alice)
        make_connected(bob)
        fake.reply(ANSWER)
        alice_api, bob_api = signed_in(alice), signed_in(bob)
        for _ in range(10):
            alice_api.call("POST", CHECK)

        assert alice_api.call("POST", CHECK).status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert bob_api.call("POST", CHECK).status_code == HTTPStatus.OK

    def test_the_ai_checks_do_not_use_up_the_counter_of_the_intervals_connection(
        self, alice: User, fake: FakeProvider
    ) -> None:
        make_connected(alice)
        fake.reply(ANSWER)
        api = signed_in(alice)
        for _ in range(10):
            api.call("POST", CHECK)
        assert api.call("POST", CHECK).status_code == HTTPStatus.TOO_MANY_REQUESTS

        # Not connected is a 404; a used-up counter would be a 429.
        response = api.call("POST", "/api/integrations/intervals/check/")

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_the_rate_is_ten_a_minute(self, settings: Any) -> None:
        assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["coach_check"] == "10/min"


class TestSecrecy:
    """The key must not turn up in any answer or log line."""

    def test_no_answer_and_no_log_line_holds_the_key(
        self, alice: User, fake: FakeProvider, base: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        api = signed_in(alice)
        texts: list[str] = []

        def note(response: Any) -> None:
            texts.append(response.content.decode())

        note(api.call("GET", URL))
        note(save(api, anthropic()))
        note(save(api, anthropic(api_key="has space")))
        note(save(api, anthropic(api_key=OTHER_KEY[:5], model="-bad")))
        for status, data in (
            (200, ANSWER),
            (401, {"e": KEY}),
            (429, {"e": KEY}),
            (500, {}),
            (404, {}),
        ):
            fake.reply(data, status)
            note(api.call("POST", CHECK))
        note(api.call("GET", URL))
        note(save(api, compatible(base, api_key=OTHER_KEY)))
        note(api.call("GET", URL))
        note(api.call("DELETE", URL))

        everything = " ".join(texts) + caplog.text
        assert KEY not in everything
        assert OTHER_KEY not in everything
        assert "sk-ant" not in everything
        assert "has space" not in everything
