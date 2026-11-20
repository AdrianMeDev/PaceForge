"""The deadline that all AI calls of one request share: how it is kept, and what it costs."""

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from accounts.models import User
from coach import services
from coach.models import AIProviderConfiguration, AIUsageRecord
from coach.providers import base
from coach.providers.anthropic import AnthropicProvider
from coach.providers.base import (
    Deadline,
    DeadlineExceededError,
    Message,
    ProviderUnavailableError,
)
from coach.providers.openai_compatible import OpenAICompatibleProvider
from coach.views import provider_problem

from .fake_providers import FakeProvider

KEY = "synthetic-test-token-abcdefghij"
MODEL = "claude-sonnet-5-5"
HELLO = [Message("user", "Hello")]
ANSWER = {
    "content": [{"type": "text", "text": "Hi there"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 12, "output_tokens": 5},
}
COMPATIBLE_ANSWER = {
    "choices": [{"message": {"content": "Hi there"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 12, "completion_tokens": 5},
}
WEEK = AIUsageRecord.Purpose.WEEKLY_PLAN


class TestTheDeadline:
    def test_the_time_left_counts_down_and_never_below_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = [100.0]
        monkeypatch.setattr(base, "clock", lambda: now[0])
        deadline = Deadline.after(30)

        assert deadline.remaining() == 30
        assert not deadline.passed()
        now[0] = 129.5
        assert deadline.remaining() == 0.5
        now[0] = 130.0
        assert deadline.passed()
        now[0] = 500.0
        assert deadline.remaining() == 0.0

    def test_a_request_gets_the_deadline_of_the_setting(
        self, monkeypatch: pytest.MonkeyPatch, settings: Any
    ) -> None:
        monkeypatch.setattr(base, "clock", lambda: 1000.0)
        settings.AI_REQUEST_DEADLINE_SECONDS = 123

        assert services.request_deadline() == Deadline(1123.0)

    @pytest.mark.parametrize(
        ("left", "expected"),
        [(services.MIN_ATTEMPT_SECONDS, True), (services.MIN_ATTEMPT_SECONDS - 0.1, False)],
    )
    def test_another_attempt_needs_a_minute(
        self, monkeypatch: pytest.MonkeyPatch, left: float, expected: bool
    ) -> None:
        monkeypatch.setattr(base, "clock", lambda: 0.0)

        assert services.time_for_another_attempt(Deadline(left)) is expected


class TestAStreamedAnswer:
    def provider(self, fake: FakeProvider, timeout: float = 60) -> AnthropicProvider:
        return AnthropicProvider(KEY, MODEL, base_url=fake.url, timeout=timeout)

    def test_a_model_may_be_quiet_for_longer_than_the_timeout_within_the_deadline(
        self, fake: FakeProvider
    ) -> None:
        fake.reply(ANSWER)
        fake.event_delay = 0.25

        result = self.provider(fake, timeout=0.2).complete(
            "", HELLO, 10, deadline=Deadline.after(10)
        )

        assert result.text == "Hi there"

    def test_a_stream_that_stalls_is_given_up_at_the_deadline(self, fake: FakeProvider) -> None:
        fake.reply(ANSWER)
        fake.event_delay = 3.0
        started = time.monotonic()

        with pytest.raises(DeadlineExceededError):
            self.provider(fake).complete("", HELLO, 10, deadline=Deadline.after(0.4))

        assert time.monotonic() - started < 2.0

    def test_nothing_is_sent_once_the_deadline_has_passed(self, fake: FakeProvider) -> None:
        fake.reply(ANSWER)

        with pytest.raises(DeadlineExceededError):
            self.provider(fake).complete("", HELLO, 10, deadline=Deadline.after(-1))

        assert fake.requests == []

    def test_a_missed_deadline_is_a_kind_of_unavailable_provider(self) -> None:
        assert issubclass(DeadlineExceededError, ProviderUnavailableError)


class TestAPlainAnswer:
    def test_an_answer_that_comes_too_late_is_given_up_at_the_deadline(
        self, fake: FakeProvider, settings: Any
    ) -> None:
        settings.AI_ALLOWED_BASE_URLS = (fake.url,)
        fake.reply(COMPATIBLE_ANSWER)
        fake.delay = 3.0
        started = time.monotonic()

        with pytest.raises(DeadlineExceededError):
            OpenAICompatibleProvider(fake.url, MODEL, KEY).complete(
                "", HELLO, 10, deadline=Deadline.after(0.4)
            )

        assert time.monotonic() - started < 2.0


@pytest.mark.django_db
class TestTheCall:
    @pytest.fixture
    def alice(self) -> User:
        return User.objects.create_user("alice@example.com")

    def configure(self, owner: User) -> AIProviderConfiguration:
        return AIProviderConfiguration.objects.create(
            owner=owner,
            provider="anthropic",
            model=MODEL,
            api_key=KEY,
            status=AIProviderConfiguration.Status.CONNECTED,
        )

    def test_nothing_is_sent_or_recorded_once_the_deadline_has_passed(
        self, alice: User, fake: FakeProvider
    ) -> None:
        self.configure(alice)
        fake.reply(ANSWER)

        with pytest.raises(DeadlineExceededError):
            services.call(alice, WEEK, "system", HELLO, 50, deadline=Deadline.after(-1))

        assert fake.requests == []
        assert not AIUsageRecord.objects.exists()

    def test_a_missed_deadline_is_recorded_but_leaves_the_status(
        self, alice: User, fake: FakeProvider
    ) -> None:
        configuration = self.configure(alice)
        fake.reply(ANSWER)
        fake.event_delay = 3.0

        with pytest.raises(DeadlineExceededError):
            services.call(alice, WEEK, "system", HELLO, 50, deadline=Deadline.after(0.4))

        (record,) = AIUsageRecord.objects.for_user(alice)
        assert record.outcome == AIUsageRecord.Outcome.UNAVAILABLE
        assert record.output_tokens is None
        configuration.refresh_from_db()
        assert configuration.status == AIProviderConfiguration.Status.CONNECTED

    def test_the_answer_to_the_athlete_says_it_was_too_slow(self) -> None:
        response = provider_problem(DeadlineExceededError("The answer did not arrive in time."))

        assert response.status_code == 503
        assert response.data["code"] == "too_slow"
        assert "did not finish in time" in response.data["detail"]


class TestTheSetting:
    @pytest.mark.parametrize(
        "env",
        [
            {"AI_REQUEST_DEADLINE_SECONDS": "0"},
            {"AI_REQUEST_DEADLINE_SECONDS": "-5"},
            {"AI_REQUEST_DEADLINE_SECONDS": "240"},
            {"AI_REQUEST_DEADLINE_SECONDS": "soon"},
            {"GUNICORN_TIMEOUT": "200"},
            {"AI_REQUEST_DEADLINE_SECONDS": "300", "GUNICORN_TIMEOUT": "300"},
        ],
    )
    def test_a_deadline_not_below_the_server_timeout_stops_django(
        self, env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Settings are read at import time, so each case starts a fresh interpreter.
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        result = subprocess.run(
            [sys.executable, "-c", "import config.settings_test"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "AI_REQUEST_DEADLINE_SECONDS" in result.stderr

    def test_a_longer_deadline_with_a_longer_server_timeout_is_fine(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AI_REQUEST_DEADLINE_SECONDS", "270")
        monkeypatch.setenv("GUNICORN_TIMEOUT", "290")
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import config.settings_test as s; print(s.AI_REQUEST_DEADLINE_SECONDS)",
            ],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "270"
