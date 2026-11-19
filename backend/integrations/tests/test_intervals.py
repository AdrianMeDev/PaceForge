import base64
import dataclasses
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
    SportSettings,
    UnexpectedResponseError,
)

from .fake_intervals import FakeIntervals, running

KEY = "k3y-0123456789-abcdefghij"


def client(fake: FakeIntervals, key: str = KEY, **options: Any) -> IntervalsClient:
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


class TestRetries:
    def test_retries_429_and_5xx_with_exponential_backoff_until_200(
        self, fake: FakeIntervals
    ) -> None:
        sleeps: list[float] = []
        fake.queue(429)
        fake.queue(500)
        fake.queue(503)
        fake.queue(200, body=b'{"id": "i42"}')

        athlete = client(fake, retry_delays=(1.0, 2.0, 4.0), sleep=sleeps.append).get_athlete()

        assert athlete == Athlete(id="i42")
        assert len(fake.requests) == 4
        assert sleeps == [1.0, 2.0, 4.0]

    def test_retry_after_numeric_header_is_used_and_capped(self, fake: FakeIntervals) -> None:
        sleeps: list[float] = []
        fake.queue(429, headers={"Retry-After": "5"})
        fake.queue(429, headers={"Retry-After": "9999"})
        fake.queue(503, headers={"Retry-After": "2.5"})
        fake.queue(200, body=b'{"id": "i42"}')

        athlete = client(fake, retry_delays=(1.0, 2.0, 4.0), sleep=sleeps.append).get_athlete()

        assert athlete == Athlete(id="i42")
        assert sleeps == [5.0, intervals.MAX_RETRY_AFTER, 2.5]

    @pytest.mark.parametrize(
        "header",
        ["Wed, 21 Oct 2015 07:28:00 GMT", "-5", "soon", ""],
    )
    def test_non_numeric_retry_after_falls_back_to_backoff(
        self, fake: FakeIntervals, header: str
    ) -> None:
        sleeps: list[float] = []
        fake.queue(429, headers={"Retry-After": header})
        fake.queue(200, body=b'{"id": "i1"}')

        athlete = client(fake, retry_delays=(1.5, 3.0), sleep=sleeps.append).get_athlete()

        assert athlete == Athlete(id="i1")
        assert sleeps == [1.5]

    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_exhausting_retries_raises_unavailable_without_leaking_key(
        self, fake: FakeIntervals, status: int
    ) -> None:
        sleeps: list[float] = []
        fake.status = status
        encoded = base64.b64encode(f"API_KEY:{KEY}".encode()).decode()

        with pytest.raises(IntervalsUnavailableError) as raised:
            client(fake, retry_delays=(1.0, 2.0, 4.0), sleep=sleeps.append).get_athlete()

        assert len(fake.requests) == 4
        assert sleeps == [1.0, 2.0, 4.0]
        assert KEY not in everything_printed(raised.value)
        assert encoded not in everything_printed(raised.value)

    @pytest.mark.parametrize("status", [401, 403, 400, 422, 404, 301, 302])
    def test_non_retryable_statuses_are_not_retried(self, fake: FakeIntervals, status: int) -> None:
        sleeps: list[float] = []
        fake.status = status
        if status in {301, 302}:
            fake.headers = {"Location": fake.url}

        with pytest.raises(intervals.IntervalsError):
            client(fake, retry_delays=(1.0, 2.0, 4.0), sleep=sleeps.append).get_athlete()

        assert len(fake.requests) == 1
        assert sleeps == []

    def test_test_settings_use_zero_retry_delays(self, fake: FakeIntervals, settings: Any) -> None:
        sleeps: list[float] = []
        fake.status = 429

        with pytest.raises(IntervalsUnavailableError):
            client(fake, sleep=sleeps.append).get_athlete()

        assert settings.INTERVALS_RETRY_DELAYS == (0.0, 0.0, 0.0)
        assert len(fake.requests) == 4
        assert sleeps == [0.0, 0.0, 0.0]


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


SETTINGS_PATH = "/api/v1/athlete/0/sport-settings"


def settings_body(*entries: object) -> bytes:
    return json.dumps(list(entries)).encode()


def entry(types: object, **fields: object) -> dict[str, object]:
    """One entry as Intervals.icu sends it: the four thresholds among a great many other fields."""
    return {
        "id": 1,
        "athlete_id": "i1",
        "types": types,
        "warmup_time": 600,
        "power_zones": [55, 75, 90, 105, 120, 150, 999],
        "power_zone_names": ["Z1", "Z2"],
        "display": {"color": "#fff", "showLoad": True},
        "created": "2020-01-01T00:00:00",
        "ftp": None,
        "lthr": None,
        "max_hr": None,
        "threshold_pace": None,
        "pace_units": "MINS_KM",
        **fields,
    }


class TestSportSettings:
    def read(self, fake: FakeIntervals, *entries: object) -> list[SportSettings]:
        fake.bodies[SETTINGS_PATH] = settings_body(*entries)
        return client(fake).get_sport_settings()

    def test_it_asks_for_the_own_sport_settings_with_the_key(self, fake: FakeIntervals) -> None:
        self.read(fake)

        [request] = fake.requests
        assert request["path"] == SETTINGS_PATH
        expected = base64.b64encode(f"API_KEY:{KEY}".encode()).decode()
        assert request["headers"]["Authorization"] == f"Basic {expected}"
        assert request["headers"]["Accept"] == "application/json"

    def test_a_typical_answer_gives_cycling_and_running(self, fake: FakeIntervals) -> None:
        result = self.read(
            fake,
            entry(
                ["Ride", "VirtualRide", "MountainBikeRide", "GravelRide"],
                ftp=250,
                lthr=165,
                max_hr=190,
            ),
            entry(["Run", "VirtualRun", "TrailRun"], lthr=170, max_hr=188, threshold_pace=10 / 3),
            entry(["Swim", "OpenWaterSwim"], lthr=150, max_hr=180, threshold_pace=0.9),
            entry(["Other"], lthr=140, max_hr=170),
        )

        assert [settings.sport for settings in result] == ["ride", "run"]
        assert result[0] == SportSettings(
            "ride", ftp=250, lthr=165, max_hr=190, threshold_pace=None
        )
        assert result[1] == SportSettings(
            "run", lthr=170, max_hr=188, threshold_pace=result[1].threshold_pace
        )
        assert result[1].threshold_pace == pytest.approx(300)

    def test_cycling_comes_first_whatever_the_order_of_the_answer(
        self, fake: FakeIntervals
    ) -> None:
        result = self.read(fake, entry(["Run"], lthr=170), entry(["Ride"], ftp=250))

        assert [settings.sport for settings in result] == ["ride", "run"]

    @pytest.mark.parametrize(
        ("types", "sport"),
        [
            (["Ride"], "ride"),
            (["VirtualRide"], "ride"),
            (["Ride", "VirtualRide", "MountainBikeRide", "GravelRide", "TrackRide"], "ride"),
            (["GravelRide", "Ride"], "ride"),
            (["Run"], "run"),
            (["VirtualRun"], "run"),
            (["Run", "VirtualRun", "TrailRun"], "run"),
            (["TrailRun", "Run"], "run"),
        ],
    )
    def test_entries_are_assigned_by_their_sport_types(
        self, fake: FakeIntervals, types: list[str], sport: str
    ) -> None:
        [result] = self.read(fake, entry(types, lthr=160))

        assert (result.sport, result.lthr) == (sport, 160)

    @pytest.mark.parametrize(
        "types",
        [
            ["Swim", "OpenWaterSwim"],
            ["Other"],
            ["WeightTraining"],
            ["TrailRun"],  # only an entry that also has Run or VirtualRun counts as running
            ["MountainBikeRide"],
            ["Ride", "Run"],  # ambiguous
            [],
            None,
            "Ride",
            5,
            [5, None],
            {"Ride": True},
        ],
    )
    def test_all_other_entries_are_dropped(self, fake: FakeIntervals, types: object) -> None:
        assert self.read(fake, entry(types, ftp=250, lthr=165, max_hr=190)) == []

    @pytest.mark.parametrize(
        ("speed", "pace"),
        [
            (10 / 3, 300.0),
            (4, 250.0),
            (2.5, 400.0),
            (1000 / 360, 360.0),
            (20, 50.0),
            (0.1, 10000.0),
        ],
    )
    def test_metres_per_second_become_seconds_per_kilometre(
        self, fake: FakeIntervals, speed: float, pace: float
    ) -> None:
        [result] = self.read(fake, entry(["Run"], threshold_pace=speed))

        assert result.threshold_pace == pytest.approx(pace)

    @pytest.mark.parametrize("speed", [0, -3, 0.09, 20.1, 300, "3.3", True, None, [3], {}])
    def test_a_speed_that_makes_no_sense_is_skipped(
        self, fake: FakeIntervals, speed: object
    ) -> None:
        [result] = self.read(fake, entry(["Run"], threshold_pace=speed, lthr=170))

        assert result.threshold_pace is None
        assert result.lthr == 170

    @pytest.mark.parametrize("field", ["ftp", "lthr", "max_hr"])
    @pytest.mark.parametrize(
        "value", [0, -1, -250.5, "250", "", True, False, None, [250], {"v": 250}]
    )
    def test_a_value_that_is_missing_or_not_a_positive_number_is_skipped(
        self, fake: FakeIntervals, field: str, value: object
    ) -> None:
        [result] = self.read(fake, entry(["Ride"], **{field: value}))

        assert getattr(result, field) is None

    @pytest.mark.parametrize(("field", "limit"), [("ftp", 5000), ("lthr", 300), ("max_hr", 300)])
    def test_absurd_values_are_skipped_and_the_limit_itself_is_kept(
        self, fake: FakeIntervals, field: str, limit: int
    ) -> None:
        [at_limit] = self.read(fake, entry(["Ride"], **{field: limit}))
        [beyond] = self.read(fake, entry(["Ride"], **{field: limit + 1}))

        assert getattr(at_limit, field) == limit
        assert getattr(beyond, field) is None

    def test_numbers_that_are_not_finite_are_skipped(self, fake: FakeIntervals) -> None:
        fake.bodies[SETTINGS_PATH] = (
            b'[{"types": ["Ride"], "ftp": NaN, "lthr": Infinity, "max_hr": -Infinity},'
            b' {"types": ["Run"], "threshold_pace": NaN, "lthr": 1e999}]'
        )

        assert client(fake).get_sport_settings() == [
            SportSettings("ride"),
            SportSettings("run"),
        ]

    def test_one_bad_value_does_not_cost_the_others(self, fake: FakeIntervals) -> None:
        [result] = self.read(fake, entry(["Ride"], ftp="abc", lthr=165, max_hr=-1))

        assert result == SportSettings("ride", lthr=165)

    def test_whole_numbers_and_decimals_are_both_fine(self, fake: FakeIntervals) -> None:
        [result] = self.read(fake, entry(["Ride"], ftp=250, lthr=165.5))

        assert (result.ftp, result.lthr) == (250.0, 165.5)

    def test_a_group_without_any_usable_value_is_still_reported(self, fake: FakeIntervals) -> None:
        assert self.read(fake, entry(["Ride"]), entry(["Run"], lthr=0)) == [
            SportSettings("ride"),
            SportSettings("run"),
        ]

    def test_where_two_entries_claim_a_group_the_first_wins_per_value(
        self, fake: FakeIntervals
    ) -> None:
        result = self.read(
            fake,
            entry(["Ride"], ftp=250),
            entry(["VirtualRide"], ftp=300, lthr=165, max_hr=190),
        )

        assert result == [SportSettings("ride", ftp=250, lthr=165, max_hr=190)]

    def test_entries_that_are_no_objects_are_skipped(self, fake: FakeIntervals) -> None:
        result = self.read(fake, 1, "x", None, [], [["Ride"]], entry(["Ride"], ftp=250))

        assert result == [SportSettings("ride", ftp=250)]

    def test_an_empty_list_is_a_valid_answer(self, fake: FakeIntervals) -> None:
        assert self.read(fake) == []

    @pytest.mark.parametrize(
        "body", [b"{}", b"null", b'"text"', b"5", b'{"types": ["Ride"], "ftp": 777}', b"", b"[1,"]
    )
    def test_an_answer_that_is_no_list_is_unexpected_and_shows_no_value(
        self, fake: FakeIntervals, body: bytes
    ) -> None:
        fake.bodies[SETTINGS_PATH] = body

        with pytest.raises(UnexpectedResponseError) as raised:
            client(fake).get_sport_settings()

        assert "777" not in everything_printed(raised.value)

    def test_only_the_four_thresholds_are_kept(self, fake: FakeIntervals) -> None:
        result = self.read(
            fake, entry(["Ride"], ftp=250, email="someone@example.com", athlete_name="Someone")
        )

        assert [field.name for field in dataclasses.fields(SportSettings)] == [
            "sport",
            "ftp",
            "lthr",
            "max_hr",
            "threshold_pace",
        ]
        assert "someone" not in repr(result).lower()
        assert "Z1" not in repr(result)

    def test_the_result_cannot_be_changed(self, fake: FakeIntervals) -> None:
        [result] = self.read(fake, entry(["Ride"], ftp=250))

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.ftp = 999  # type: ignore[misc]

    def test_it_makes_one_request(self, fake: FakeIntervals) -> None:
        self.read(fake, entry(["Ride"], ftp=250))

        assert len(fake.requests) == 1

    def test_an_answer_that_is_too_large_is_refused(
        self, fake: FakeIntervals, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(intervals, "MAX_RESPONSE_BYTES", 200)
        fake.bodies[SETTINGS_PATH] = settings_body(entry(["Ride"], ftp=250))

        with pytest.raises(UnexpectedResponseError, match="larger"):
            client(fake).get_sport_settings()

    @pytest.mark.parametrize("status", [401, 403])
    def test_a_refused_key_is_reported_as_invalid(self, fake: FakeIntervals, status: int) -> None:
        fake.status = status

        with pytest.raises(InvalidKeyError):
            client(fake).get_sport_settings()

    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_a_busy_or_broken_service_is_reported_as_unavailable(
        self, fake: FakeIntervals, status: int
    ) -> None:
        fake.status = status

        with pytest.raises(IntervalsUnavailableError):
            client(fake).get_sport_settings()

    @pytest.mark.parametrize("status", [400, 404, 405, 422])
    def test_other_statuses_are_unexpected(self, fake: FakeIntervals, status: int) -> None:
        fake.status = status

        with pytest.raises(UnexpectedResponseError, match=str(status)):
            client(fake).get_sport_settings()

    def test_a_closed_port_is_unavailable(self) -> None:
        with running() as gone:
            url = gone.url
        with pytest.raises(IntervalsUnavailableError):
            IntervalsClient(KEY, base_url=url).get_sport_settings()

    def test_a_cut_off_answer_is_unavailable(self, fake: FakeIntervals) -> None:
        fake.bodies[SETTINGS_PATH] = settings_body(entry(["Ride"], ftp=250))
        fake.missing_bytes = 50

        with pytest.raises(IntervalsUnavailableError, match="cut off"):
            client(fake).get_sport_settings()

    def test_a_redirect_is_not_followed(self, fake: FakeIntervals) -> None:
        with running() as elsewhere:
            fake.status = 302
            fake.headers = {"Location": elsewhere.url + "/athlete/0/sport-settings"}

            with pytest.raises(UnexpectedResponseError, match="302"):
                client(fake).get_sport_settings()

            assert elsewhere.requests == []

    @pytest.mark.parametrize("status", [200, 401, 403, 429, 500, 404, 302])
    def test_neither_the_key_nor_a_value_shows_up_in_errors_or_logs(
        self, fake: FakeIntervals, caplog: pytest.LogCaptureFixture, status: int
    ) -> None:
        caplog.set_level(logging.DEBUG)
        fake.status = status
        fake.headers = {"Location": "http://127.0.0.1:9/"} if status == 302 else {}
        fake.bodies[SETTINGS_PATH] = json.dumps(
            {"types": ["Ride"], "ftp": 777, "echo": KEY}
        ).encode()
        encoded = base64.b64encode(f"API_KEY:{KEY}".encode()).decode()

        try:
            client(fake).get_sport_settings()
        except intervals.IntervalsError as error:
            shown = everything_printed(error)
            assert KEY not in shown
            assert encoded not in shown
            assert "777" not in shown

        assert KEY not in caplog.text
        assert encoded not in caplog.text
        assert "777" not in caplog.text

    def test_reading_the_settings_logs_nothing_with_values(
        self, fake: FakeIntervals, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)

        self.read(fake, entry(["Ride"], ftp=777, lthr=166))

        assert "777" not in caplog.text
        assert "166" not in caplog.text
        assert KEY not in caplog.text


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


EVENT = {
    "category": "WORKOUT",
    "type": "Ride",
    "start_date_local": "2027-07-19T07:00:00",
    "name": "Endurance ride",
    "external_id": "paceforge-1",
    "description": "- 1h 138-188w",
}
BULK = "/api/v1/athlete/0/events/bulk?upsert=true"


class TestUpsertEvent:
    def test_it_posts_the_event_as_a_list_with_the_upsert_flag(self, fake: FakeIntervals) -> None:
        fake.body = b'[{"id": 4711, "external_id": "paceforge-1", "name": "Endurance ride"}]'

        stored = client(fake).upsert_event(EVENT)

        (request,) = fake.requests
        assert (request["method"], request["path"]) == ("POST", BULK)
        assert json.loads(request["body"]) == [EVENT]
        assert request["headers"]["Content-Type"] == "application/json"
        assert request["headers"]["Authorization"].startswith("Basic ")
        assert stored == intervals.Event(id=4711, external_id="paceforge-1")

    def test_only_the_id_and_the_external_id_are_kept(self, fake: FakeIntervals) -> None:
        fake.body = (
            b'[{"id": 1, "external_id": "x", "description": "secret", "icu_training_load": 5}]'
        )

        stored = client(fake).upsert_event(EVENT)

        assert dataclasses.asdict(stored) == {"id": 1, "external_id": "x"}

    def test_an_answer_without_an_external_id_is_fine(self, fake: FakeIntervals) -> None:
        fake.body = b'[{"id": 1}]'

        assert client(fake).upsert_event(EVENT) == intervals.Event(id=1, external_id=None)

    @pytest.mark.parametrize(
        "body",
        [
            b"[]",
            b"{}",
            b'{"id": 1}',
            b'[{"id": 1}, {"id": 2}]',
            b'["x"]',
            b'[{"id": "1"}]',
            b'[{"id": true}]',
            b'[{"id": 0}]',
            b'[{"id": -3}]',
            b'[{"id": 1.5}]',
            b'[{"name": "no id"}]',
            b"null",
            b"not json",
        ],
    )
    def test_an_answer_that_is_not_one_event_is_unexpected(
        self, fake: FakeIntervals, body: bytes
    ) -> None:
        fake.body = body

        with pytest.raises(UnexpectedResponseError):
            client(fake).upsert_event(EVENT)

    @pytest.mark.parametrize("status", [400, 422])
    def test_an_event_it_does_not_accept_is_rejected(
        self, fake: FakeIntervals, status: int
    ) -> None:
        fake.status = status
        fake.body = b'{"error": "Cannot parse workout: SECRETMARKER"}'

        with pytest.raises(intervals.RejectedError) as caught:
            client(fake).upsert_event(EVENT)

        assert "SECRETMARKER" not in everything_printed(caught.value)
        assert isinstance(caught.value, UnexpectedResponseError)

    @pytest.mark.parametrize("status", [401, 403])
    def test_a_refused_key_is_reported_as_invalid(self, fake: FakeIntervals, status: int) -> None:
        fake.status = status

        with pytest.raises(InvalidKeyError):
            client(fake).upsert_event(EVENT)

    @pytest.mark.parametrize("status", [429, 500, 503])
    def test_a_busy_service_is_reported_as_unavailable(
        self, fake: FakeIntervals, status: int
    ) -> None:
        fake.status = status

        with pytest.raises(IntervalsUnavailableError):
            client(fake).upsert_event(EVENT)

    def test_a_too_large_answer_is_refused(
        self, fake: FakeIntervals, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake.body = b'[{"id": 1}]'
        monkeypatch.setattr(intervals, "MAX_RESPONSE_BYTES", 5)

        with pytest.raises(UnexpectedResponseError):
            client(fake).upsert_event(EVENT)

    def test_a_redirect_is_not_followed_and_the_event_goes_nowhere_else(
        self, fake: FakeIntervals
    ) -> None:
        with running() as elsewhere:
            fake.status = 307
            fake.headers = {"Location": elsewhere.url}

            with pytest.raises(UnexpectedResponseError):
                client(fake).upsert_event(EVENT)

            assert elsewhere.requests == []

    def test_no_error_shows_the_key_or_the_event(self, fake: FakeIntervals) -> None:
        encoded = base64.b64encode(f"API_KEY:{KEY}".encode()).decode()
        for status in (401, 422, 429, 500, 404, 200):
            fake.status = status
            fake.body = b"not json at all"
            try:
                client(fake).upsert_event(EVENT)
            except intervals.IntervalsError as error:
                shown = everything_printed(error)
                assert KEY not in shown
                assert encoded not in shown
                assert "paceforge-1" not in shown
                assert "Endurance" not in shown


class TestDeleteEvent:
    def test_it_deletes_the_event_with_that_id(self, fake: FakeIntervals) -> None:
        fake.body = b""

        client(fake).delete_event(4711)

        (request,) = fake.requests
        assert (request["method"], request["path"]) == ("DELETE", "/api/v1/athlete/0/events/4711")
        assert request["headers"]["Authorization"].startswith("Basic ")
        assert request["body"] == b""

    def test_an_answer_with_a_body_is_fine_too(self, fake: FakeIntervals) -> None:
        fake.body = b'{"deleted": 1}'

        client(fake).delete_event(1)

    def test_an_event_that_is_gone_counts_as_removed(self, fake: FakeIntervals) -> None:
        fake.status = 404

        client(fake).delete_event(4711)

    @pytest.mark.parametrize("status", [401, 403])
    def test_a_refused_key_is_reported_as_invalid(self, fake: FakeIntervals, status: int) -> None:
        fake.status = status

        with pytest.raises(InvalidKeyError):
            client(fake).delete_event(1)

    @pytest.mark.parametrize("status", [429, 502])
    def test_a_busy_service_is_reported_as_unavailable(
        self, fake: FakeIntervals, status: int
    ) -> None:
        fake.status = status

        with pytest.raises(IntervalsUnavailableError):
            client(fake).delete_event(1)

    def test_other_statuses_are_unexpected(self, fake: FakeIntervals) -> None:
        fake.status = 405

        with pytest.raises(UnexpectedResponseError):
            client(fake).delete_event(1)

    @pytest.mark.parametrize("event_id", [0, -1, True, "1", "1/../../athlete", 1.5, None])
    def test_only_a_positive_whole_number_is_an_id_and_nothing_is_sent(
        self, fake: FakeIntervals, event_id: Any
    ) -> None:
        with pytest.raises(ValueError, match="event id"):
            client(fake).delete_event(event_id)

        assert fake.requests == []

    def test_an_empty_answer_is_only_accepted_where_it_is_expected(
        self, fake: FakeIntervals
    ) -> None:
        fake.body = b""

        with pytest.raises(UnexpectedResponseError):
            client(fake).get_athlete()
