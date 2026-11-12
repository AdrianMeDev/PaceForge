import base64
import json
import logging
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

import pytest

from integrations import intervals
from integrations.intervals import (
    Athlete,
    IntervalsClient,
    IntervalsUnavailableError,
    InvalidKeyError,
    UnexpectedResponseError,
)

from .fake_intervals import FakeIntervals, running

KEY = "k3y-0123456789-abcdefghij"


def client(fake: FakeIntervals, key: str = KEY, **options: float) -> IntervalsClient:
    return IntervalsClient(key, base_url=fake.url, **options)


def everything_printed(error: BaseException) -> str:
    return "".join(traceback.format_exception(error)) + f" {error!s} {error!r}"


class TestTheRequest:
    def test_it_asks_for_the_own_athlete_with_basic_auth_and_the_key(
        self, fake: FakeIntervals
    ) -> None:
        client(fake).get_athlete()

        [request] = fake.requests
        assert request["path"] == "/api/v1/athlete/0"
        expected = base64.b64encode(f"API_KEY:{KEY}".encode()).decode()
        assert request["headers"]["Authorization"] == f"Basic {expected}"
        assert request["headers"]["Accept"] == "application/json"
        assert request["headers"]["User-Agent"] == "PaceForge"

    @pytest.mark.parametrize("key", ["a:b:c", "with space", "line\nbreak", "ümläut-✓", "x" * 500])
    def test_unusual_keys_still_make_a_single_valid_header(
        self, fake: FakeIntervals, key: str
    ) -> None:
        client(fake, key).get_athlete()

        header = fake.requests[0]["headers"]["Authorization"]
        assert header.startswith("Basic ")
        assert base64.b64decode(header.removeprefix("Basic ")).decode() == f"API_KEY:{key}"

    def test_a_trailing_slash_in_the_base_url_is_harmless(self, fake: FakeIntervals) -> None:
        IntervalsClient(KEY, base_url=fake.url + "/").get_athlete()

        assert fake.requests[0]["path"] == "/api/v1/athlete/0"

    def test_the_base_url_comes_from_the_settings_by_default(
        self, fake: FakeIntervals, settings: Any
    ) -> None:
        settings.INTERVALS_API_BASE_URL = fake.url

        IntervalsClient(KEY).get_athlete()

        assert len(fake.requests) == 1

    def test_the_default_points_at_the_real_api(self, settings: Any) -> None:
        assert settings.INTERVALS_API_BASE_URL == "https://intervals.icu/api/v1"

    def test_an_empty_key_is_refused_before_anything_is_sent(self, fake: FakeIntervals) -> None:
        with pytest.raises(ValueError, match="empty"):
            IntervalsClient("", base_url=fake.url)

        assert fake.requests == []

    @pytest.mark.parametrize("url", ["ftp://example.com", "file:///etc/passwd", "intervals.icu"])
    def test_only_http_and_https_base_urls_are_accepted(self, url: str) -> None:
        with pytest.raises(ValueError, match="http"):
            IntervalsClient(KEY, base_url=url)

    def test_the_client_does_not_show_the_key_when_printed(self, fake: FakeIntervals) -> None:
        shown = repr(client(fake))

        assert KEY not in shown
        assert fake.url in shown


class TestTheAnswer:
    def test_it_returns_the_athlete_id_and_nothing_else(self, fake: FakeIntervals) -> None:
        fake.body = json.dumps(
            {"id": "i797177", "email": "someone@example.com", "name": "Someone", "zwift_user_id": 5}
        ).encode()

        athlete = client(fake).get_athlete()

        assert athlete == Athlete(id="i797177")
        assert "someone" not in repr(athlete).lower()

    @pytest.mark.parametrize("athlete_id", ["i1", "123456", "a_b-c", "x" * 50])
    def test_usable_ids_are_accepted(self, fake: FakeIntervals, athlete_id: str) -> None:
        fake.body = json.dumps({"id": athlete_id}).encode()

        assert client(fake).get_athlete().id == athlete_id

    @pytest.mark.parametrize(
        "body",
        [
            b"",
            b"not json",
            b"null",
            b"[]",
            b'"i1"',
            b"{}",
            b'{"id": null}',
            b'{"id": 797177}',
            b'{"id": ""}',
            b'{"id": "has space"}',
            b'{"id": "../../etc"}',
            b'{"id": "<script>"}',
            b'{"id": "' + b"x" * 51 + b'"}',
            b'{"id": "i1",',
        ],
    )
    def test_an_answer_without_a_usable_athlete_is_unexpected(
        self, fake: FakeIntervals, body: bytes
    ) -> None:
        fake.body = body

        with pytest.raises(UnexpectedResponseError):
            client(fake).get_athlete()

    def test_an_answer_that_is_too_large_is_refused(
        self, fake: FakeIntervals, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(intervals, "MAX_RESPONSE_BYTES", 100)
        fake.body = json.dumps({"id": "i1", "padding": "x" * 500}).encode()

        with pytest.raises(UnexpectedResponseError, match="larger"):
            client(fake).get_athlete()

    def test_an_answer_just_below_the_limit_is_read(
        self, fake: FakeIntervals, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake.body = b'{"id": "i1", "p": "' + b"x" * 40 + b'"}'
        monkeypatch.setattr(intervals, "MAX_RESPONSE_BYTES", len(fake.body))

        assert client(fake).get_athlete().id == "i1"


class TestRefusalsAndFailures:
    @pytest.mark.parametrize("status", [401, 403])
    def test_a_refused_key_is_reported_as_invalid(self, fake: FakeIntervals, status: int) -> None:
        fake.status = status
        fake.body = b'{"status": %d, "error": "nope"}' % status

        with pytest.raises(InvalidKeyError):
            client(fake).get_athlete()

    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_a_busy_or_broken_service_is_reported_as_unavailable(
        self, fake: FakeIntervals, status: int
    ) -> None:
        fake.status = status

        with pytest.raises(IntervalsUnavailableError):
            client(fake).get_athlete()

    @pytest.mark.parametrize("status", [400, 404, 405, 410, 422])
    def test_other_statuses_are_unexpected(self, fake: FakeIntervals, status: int) -> None:
        fake.status = status

        with pytest.raises(UnexpectedResponseError, match=str(status)):
            client(fake).get_athlete()

    def test_a_closed_port_is_unavailable(self) -> None:
        with running() as gone:
            url = gone.url
        with pytest.raises(IntervalsUnavailableError):
            IntervalsClient(KEY, base_url=url).get_athlete()

    def test_a_server_that_does_not_answer_in_time_is_unavailable(
        self, fake: FakeIntervals
    ) -> None:
        fake.delay = 1.5

        with pytest.raises(IntervalsUnavailableError):
            client(fake, timeout=0.2).get_athlete()

    def test_an_answer_that_is_cut_off_is_unavailable_even_if_the_part_is_valid_json(
        self, fake: FakeIntervals
    ) -> None:
        fake.body = b'{"id": "i1"}'
        fake.missing_bytes = 50

        with pytest.raises(IntervalsUnavailableError, match="cut off"):
            client(fake).get_athlete()


class TestRedirects:
    def test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else(
        self, fake: FakeIntervals
    ) -> None:
        with running() as elsewhere:
            fake.status = 302
            fake.headers = {"Location": elsewhere.url + "/athlete/0"}

            with pytest.raises(UnexpectedResponseError, match="302"):
                client(fake).get_athlete()

            assert elsewhere.requests == []
        assert len(fake.requests) == 1

    def test_a_redirect_to_another_scheme_is_not_followed_either(self, fake: FakeIntervals) -> None:
        fake.status = 301
        fake.headers = {"Location": "file:///etc/passwd"}

        with pytest.raises(UnexpectedResponseError, match="301"):
            client(fake).get_athlete()


class TestTheKeyStaysSecret:
    @pytest.mark.parametrize(
        ("status", "body"),
        [
            (401, b"{}"),
            (403, b"{}"),
            (429, b"{}"),
            (500, b"{}"),
            (404, b"{}"),
            (302, b"{}"),
            (200, b"not json"),
            (200, b'{"id": 5}'),
            (200, b'{"id": "i1", "echo": "' + KEY.encode() + b'"}'),
        ],
    )
    def test_no_error_shows_the_key(
        self, fake: FakeIntervals, caplog: pytest.LogCaptureFixture, status: int, body: bytes
    ) -> None:
        caplog.set_level(logging.DEBUG)
        fake.status, fake.body = status, body
        fake.headers = {"Location": "http://127.0.0.1:9/"} if status == 302 else {}
        encoded = base64.b64encode(f"API_KEY:{KEY}".encode()).decode()

        try:
            client(fake).get_athlete()
        except intervals.IntervalsError as error:
            shown = everything_printed(error)
            assert KEY not in shown
            assert encoded not in shown

        assert KEY not in caplog.text
        assert encoded not in caplog.text

    def test_a_connection_error_does_not_show_the_key_either(self) -> None:
        with running() as gone:
            url = gone.url
        encoded = base64.b64encode(f"API_KEY:{KEY}".encode()).decode()

        with pytest.raises(IntervalsUnavailableError) as raised:
            IntervalsClient(KEY, base_url=url).get_athlete()

        assert KEY not in everything_printed(raised.value)
        assert encoded not in everything_printed(raised.value)

    def test_an_invalid_base_url_error_does_not_show_the_key(self) -> None:
        with pytest.raises(ValueError) as raised:
            IntervalsClient(KEY, base_url="ftp://example.com")

        assert KEY not in everything_printed(raised.value)


def import_settings(statement: str, **env: str) -> subprocess.CompletedProcess[str]:
    """Imports the settings in a fresh process, without reading the repository's real `.env`."""
    no_dotenv = "import environ; environ.Env.read_env = lambda *a, **k: None; "
    base = {k: v for k, v in os.environ.items() if k != "INTERVALS_API_BASE_URL"}
    return subprocess.run(
        [sys.executable, "-c", no_dotenv + statement],
        env=base | {"DJANGO_SECRET_KEY": "x", "DATABASE_URL": "sqlite:///unused.db"} | env,
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
    )


class TestTheSetting:
    def test_the_default_is_the_real_api(self) -> None:
        result = import_settings(
            "import config.settings as s; print(s.INTERVALS_API_BASE_URL)",
            ENCRYPTION_KEY="srPGFiK_-1uuYQrhJix9QxALddGxwSw-I5bllic4QsY=",
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "https://intervals.icu/api/v1"

    def test_it_can_be_set_for_a_fake_server(self) -> None:
        result = import_settings(
            "import config.settings as s; print(s.INTERVALS_API_BASE_URL)",
            ENCRYPTION_KEY="srPGFiK_-1uuYQrhJix9QxALddGxwSw-I5bllic4QsY=",
            INTERVALS_API_BASE_URL="http://127.0.0.1:9999/api/v1",
        )

        assert result.stdout.strip() == "http://127.0.0.1:9999/api/v1"

    @pytest.mark.parametrize("value", ["ftp://example.com", "file:///etc/passwd", "intervals.icu"])
    def test_other_schemes_stop_django_at_startup(self, value: str) -> None:
        result = import_settings(
            "import config.settings",
            ENCRYPTION_KEY="srPGFiK_-1uuYQrhJix9QxALddGxwSw-I5bllic4QsY=",
            INTERVALS_API_BASE_URL=value,
        )

        assert result.returncode != 0
        assert "INTERVALS_API_BASE_URL" in result.stderr
