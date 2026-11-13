import json
from http import HTTPStatus
from typing import Any

import pytest
from django.db import connection

from accounts.models import User
from accounts.tests.conftest import AuthApi
from athletes.models import AthleteProfile, ThresholdValue
from integrations.models import ProviderConnection

from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

URL = "/api/athlete/"
FTP = f"{URL}thresholds/ride/ftp/"
Source = ThresholdValue.Source


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def body(response: Any) -> Any:
    return json.loads(response.content)


def hold(owner: User, source: str, metric: str, value: float, sport: str = "ride") -> None:
    ThresholdValue.objects.create(
        owner=owner, sport=sport, metric=metric, value=value, source=source, basis=f"via {source}"
    )


def put(api: AuthApi, url: str, data: Any) -> Any:
    return api.call("PUT", url, data)


def effective(data: dict[str, Any], sport: str, metric: str) -> Any:
    return data["sports"][sport]["thresholds"][metric]["effective"]


class TestWhoMayCome:
    @pytest.mark.parametrize(
        ("method", "url"),
        [
            ("GET", URL),
            ("PATCH", URL),
            ("PUT", FTP),
            ("DELETE", FTP),
        ],
    )
    def test_anonymous_visitors_are_refused(self, method: str, url: str) -> None:
        response = AuthApi().call(method, url, {"value": 250, "timezone": "UTC"})

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert not ThresholdValue.objects.exists()
        assert not AthleteProfile.objects.exists()

    @pytest.mark.parametrize(("method", "url"), [("PATCH", URL), ("PUT", FTP), ("DELETE", FTP)])
    def test_a_request_without_the_csrf_token_is_refused(
        self, alice: User, method: str, url: str
    ) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            method,
            url,
            data=json.dumps({"value": 250, "timezone": "UTC"}),
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert not ThresholdValue.objects.exists()
        assert not AthleteProfile.objects.exists()


class TestNewUser:
    def test_the_profile_is_empty(self, alice: User) -> None:
        response = signed_in(alice).call("GET", URL)

        assert response.status_code == HTTPStatus.OK
        data = body(response)
        assert data["timezone"] == ""
        assert data["intervals"] == {"connected": False, "synced_at": None}
        assert set(data["sports"]) == {"ride", "run"}
        assert set(data["sports"]["ride"]["thresholds"]) == {"ftp", "lthr", "max_hr"}
        assert set(data["sports"]["run"]["thresholds"]) == {"threshold_pace", "lthr", "max_hr"}
        for sport in data["sports"].values():
            for threshold in sport["thresholds"].values():
                assert threshold == {"effective": None, "candidates": []}
            assert all(zones is None for zones in sport["zones"].values())
        assert set(data["sports"]["ride"]["zones"]) == {"power", "heart_rate"}
        assert set(data["sports"]["run"]["zones"]) == {"pace", "heart_rate"}

    def test_reading_writes_nothing(self, alice: User) -> None:
        signed_in(alice).call("GET", URL)

        assert not AthleteProfile.objects.exists()
        assert not ThresholdValue.objects.exists()


class TestThresholds:
    def test_a_typed_ftp_is_effective_and_gives_the_seven_power_zones(self, alice: User) -> None:
        response = put(signed_in(alice), FTP, {"value": 250})

        assert response.status_code == HTTPStatus.OK
        data = body(response)
        found = effective(data, "ride", "ftp")
        assert (found["value"], found["source"], found["basis"]) == (250, "manual", "")
        assert found["updated_at"].endswith("Z")
        zones = data["sports"]["ride"]["zones"]["power"]
        assert zones["basis"] == "ftp"
        assert len(zones["zones"]) == 7
        assert zones["zones"][0] == {
            "number": 1,
            "name": "Active recovery",
            "lower": None,
            "upper": 138,
            "unit": "W",
        }
        assert zones["zones"][6]["upper"] is None
        assert ThresholdValue.objects.get().owner == alice

    def test_the_answer_is_the_same_when_read_again(self, alice: User) -> None:
        api = signed_in(alice)

        written = body(put(api, FTP, {"value": 250}))

        assert body(api.call("GET", URL)) == written

    def test_the_pace_gives_five_pace_zones(self, alice: User) -> None:
        data = body(put(signed_in(alice), f"{URL}thresholds/run/threshold_pace/", {"value": 300}))

        zones = data["sports"]["run"]["zones"]["pace"]["zones"]
        assert [(zone["lower"], zone["upper"]) for zone in zones] == [
            (387, None),
            (342, 387),
            (318, 342),
            (297, 318),
            (None, 297),
        ]

    def test_heart_rate_zones_follow_the_threshold_else_the_maximum(self, alice: User) -> None:
        api = signed_in(alice)

        only_max = body(put(api, f"{URL}thresholds/ride/max_hr/", {"value": 190}))
        both = body(put(api, f"{URL}thresholds/ride/lthr/", {"value": 165}))

        assert only_max["sports"]["ride"]["zones"]["heart_rate"]["basis"] == "max_hr"
        assert both["sports"]["ride"]["zones"]["heart_rate"]["basis"] == "lthr"
        assert both["sports"]["run"]["zones"]["heart_rate"] is None

    def test_all_candidates_are_listed_and_the_typed_one_counts(self, alice: User) -> None:
        hold(alice, Source.INTERVALS, "ftp", 262)
        hold(alice, Source.ESTIMATED, "ftp", 241)

        data = body(put(signed_in(alice), FTP, {"value": 255}))

        threshold = data["sports"]["ride"]["thresholds"]["ftp"]
        assert [(c["source"], c["value"]) for c in threshold["candidates"]] == [
            ("manual", 255),
            ("intervals", 262),
            ("estimated", 241),
        ]
        assert threshold["effective"] == threshold["candidates"][0]
        assert threshold["candidates"][1]["basis"] == "via intervals"

    @pytest.mark.parametrize(
        ("others", "expected"),
        [
            ([(Source.INTERVALS, 262), (Source.ESTIMATED, 241)], ("intervals", 262)),
            ([(Source.ESTIMATED, 241)], ("estimated", 241)),
            ([], None),
        ],
    )
    def test_deleting_the_typed_value_falls_back_to_automatic(
        self, alice: User, others: list[tuple[str, float]], expected: tuple[str, float] | None
    ) -> None:
        for source, value in others:
            hold(alice, source, "ftp", value)
        api = signed_in(alice)
        put(api, FTP, {"value": 250})

        response = api.call("DELETE", FTP)

        assert response.status_code == HTTPStatus.OK
        found = effective(body(response), "ride", "ftp")
        assert (found["source"], found["value"]) == expected if expected else found is None
        assert not ThresholdValue.objects.filter(source="manual").exists()
        assert ThresholdValue.objects.count() == len(others)

    def test_deleting_what_is_not_there_is_fine(self, alice: User) -> None:
        response = signed_in(alice).call("DELETE", FTP)

        assert response.status_code == HTTPStatus.OK
        assert effective(body(response), "ride", "ftp") is None

    def test_a_second_value_replaces_the_first(self, alice: User) -> None:
        api = signed_in(alice)
        put(api, FTP, {"value": 250})

        data = body(put(api, FTP, {"value": 260.4}))

        assert effective(data, "ride", "ftp")["value"] == 260
        assert ThresholdValue.objects.count() == 1


class TestRefusals:
    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"value": 29}, "value"),
            ({"value": 2001}, "value"),
            ({"value": 0}, "value"),
            ({"value": -250}, "value"),
            ({"value": "250"}, "value"),
            ({"value": "abc"}, "value"),
            ({"value": True}, "value"),
            ({"value": None}, "value"),
            ({"value": [250]}, "value"),
            ({"value": {"a": 1}}, "value"),
            ({}, "value"),
            ({"val": 250}, "value"),
        ],
    )
    def test_a_value_that_is_no_usable_number_changes_nothing(
        self, alice: User, payload: dict[str, Any], field: str
    ) -> None:
        response = put(signed_in(alice), FTP, payload)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert field in body(response)
        assert not ThresholdValue.objects.exists()

    def test_the_message_names_the_range(self, alice: User) -> None:
        response = put(signed_in(alice), FTP, {"value": 5000})

        assert body(response) == {"value": ["Enter a value between 30 and 2000 W."]}

    @pytest.mark.parametrize("payload", [[250], "250", 250, None, [], "", True])
    def test_a_body_of_the_wrong_type_is_a_400_and_never_a_500(
        self, alice: User, payload: Any
    ) -> None:
        api = signed_in(alice)

        assert put(api, FTP, payload).status_code == HTTPStatus.BAD_REQUEST
        assert api.call("PATCH", URL, payload).status_code == HTTPStatus.BAD_REQUEST
        assert not ThresholdValue.objects.exists()
        assert not AthleteProfile.objects.exists()

    def test_a_body_that_is_no_json_is_a_400(self, alice: User) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            "PUT",
            FTP,
            data=b"{not json",
            content_type="application/json",
            headers={"X-CSRFToken": api._csrf_token()},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST

    @pytest.mark.parametrize(
        "raw", [b'{"value": NaN}', b'{"value": Infinity}', b'{"value": -Infinity}']
    )
    def test_a_literal_that_is_no_json_number_is_a_400(self, alice: User, raw: bytes) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            "PUT",
            FTP,
            data=raw,
            content_type="application/json",
            headers={"X-CSRFToken": api._csrf_token()},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert not ThresholdValue.objects.exists()

    @pytest.mark.parametrize("raw", [b'{"value": 1e999}', b'{"value": -1e999}'])
    def test_a_number_too_large_for_a_float_is_refused_with_the_reason(
        self, alice: User, raw: bytes
    ) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            "PUT",
            FTP,
            data=raw,
            content_type="application/json",
            headers={"X-CSRFToken": api._csrf_token()},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"value": ["A valid number is required."]}
        assert not ThresholdValue.objects.exists()

    def test_a_threshold_above_the_maximum_is_refused_with_the_reason(self, alice: User) -> None:
        api = signed_in(alice)
        put(api, f"{URL}thresholds/ride/max_hr/", {"value": 180})

        response = put(api, f"{URL}thresholds/ride/lthr/", {"value": 185})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"value": ["Cannot be above the maximum heart rate (180 bpm)."]}
        assert ThresholdValue.objects.count() == 1

    def test_a_maximum_below_the_threshold_is_refused_with_the_reason(self, alice: User) -> None:
        api = signed_in(alice)
        put(api, f"{URL}thresholds/ride/lthr/", {"value": 170})

        response = put(api, f"{URL}thresholds/ride/max_hr/", {"value": 165})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "lactate threshold heart rate (170 bpm)" in body(response)["value"][0]

    @pytest.mark.parametrize(
        "path",
        [
            "thresholds/run/ftp/",  # running has no power
            "thresholds/ride/threshold_pace/",  # cycling has no pace
            "thresholds/ride/vo2max/",
            "thresholds/swim/ftp/",
            "thresholds/ride/FTP/",
            "thresholds/ride/ftp%2F../",
            "thresholds/ride/",
        ],
    )
    def test_an_unknown_threshold_is_a_404(self, alice: User, path: str) -> None:
        api = signed_in(alice)

        assert put(api, f"{URL}{path}", {"value": 250}).status_code == HTTPStatus.NOT_FOUND
        assert api.call("DELETE", f"{URL}{path}").status_code == HTTPStatus.NOT_FOUND
        assert not ThresholdValue.objects.exists()

    def test_the_threshold_address_has_no_get(self, alice: User) -> None:
        assert signed_in(alice).call("GET", FTP).status_code == HTTPStatus.METHOD_NOT_ALLOWED

    def test_an_owner_or_user_id_in_the_body_is_ignored(self, alice: User, bob: User) -> None:
        payload = {"value": 250, "owner": str(bob.pk), "owner_id": str(bob.pk), "user": str(bob.pk)}

        response = put(signed_in(alice), FTP, payload)

        assert response.status_code == HTTPStatus.OK
        assert ThresholdValue.objects.get().owner == alice
        assert not ThresholdValue.objects.filter(owner=bob).exists()


class TestTimezone:
    def test_it_is_saved_and_shown(self, alice: User) -> None:
        api = signed_in(alice)

        response = api.call("PATCH", URL, {"timezone": "Europe/Berlin"})

        assert response.status_code == HTTPStatus.OK
        assert body(response)["timezone"] == "Europe/Berlin"
        assert body(api.call("GET", URL))["timezone"] == "Europe/Berlin"
        assert AthleteProfile.objects.get().owner == alice

    def test_it_can_be_cleared(self, alice: User) -> None:
        api = signed_in(alice)
        api.call("PATCH", URL, {"timezone": "UTC"})

        response = api.call("PATCH", URL, {"timezone": ""})

        assert body(response)["timezone"] == ""

    def test_saving_it_twice_keeps_one_profile(self, alice: User) -> None:
        api = signed_in(alice)

        api.call("PATCH", URL, {"timezone": "UTC"})
        api.call("PATCH", URL, {"timezone": "Europe/Berlin"})

        assert AthleteProfile.objects.count() == 1

    @pytest.mark.parametrize(
        "name",
        [
            "Mars/Base",
            "europe/berlin",
            " UTC",
            "UTC ",
            "../etc/passwd",
            "Europe",
            "x" * 65,
            5,
            None,
        ],
    )
    def test_an_invalid_time_zone_changes_nothing(self, alice: User, name: Any) -> None:
        api = signed_in(alice)
        api.call("PATCH", URL, {"timezone": "UTC"})

        response = api.call("PATCH", URL, {"timezone": name})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "timezone" in body(response)
        assert AthleteProfile.objects.get().timezone == "UTC"

    def test_the_time_zone_is_required(self, alice: User) -> None:
        response = signed_in(alice).call("PATCH", URL, {"other": 1})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert not AthleteProfile.objects.exists()

    def test_other_profile_fields_cannot_be_set_this_way(self, alice: User) -> None:
        api = signed_in(alice)

        api.call(
            "PATCH",
            URL,
            {"timezone": "UTC", "intervals_synced_at": "2026-01-01T00:00:00Z", "owner": "x"},
        )

        assert AthleteProfile.objects.get().intervals_synced_at is None


class TestIntervals:
    def connect(self, owner: User, status: str = "connected") -> None:
        ProviderConnection.objects.create(
            owner=owner,
            provider="intervals_icu",
            api_key="a-key-that-must-not-leak",
            athlete_id="i1",
            status=status,
        )

    def test_a_working_connection_shows_as_connected(self, alice: User) -> None:
        self.connect(alice)

        data = body(signed_in(alice).call("GET", URL))

        assert data["intervals"]["connected"] is True

    def test_a_connection_that_needs_attention_does_not(self, alice: User) -> None:
        self.connect(alice, status="invalid")

        assert body(signed_in(alice).call("GET", URL))["intervals"]["connected"] is False

    def test_the_time_of_the_last_sync_is_shown(self, alice: User) -> None:
        from django.utils import timezone

        moment = timezone.now()
        AthleteProfile.objects.create(owner=alice, intervals_synced_at=moment)

        data = body(signed_in(alice).call("GET", URL))

        assert data["intervals"]["synced_at"].endswith("Z")

    def test_the_key_never_appears(self, alice: User) -> None:
        self.connect(alice)

        response = signed_in(alice).call("GET", URL)

        assert b"a-key-that-must-not-leak" not in response.content
        assert b"i1" not in response.content


class TestIsolation:
    def test_each_user_sees_only_their_own_values(self, alice: User, bob: User) -> None:
        alices, bobs = signed_in(alice), signed_in(bob)
        put(alices, FTP, {"value": 250})
        put(bobs, FTP, {"value": 300})
        alices.call("PATCH", URL, {"timezone": "Europe/Berlin"})

        mine, theirs = body(alices.call("GET", URL)), body(bobs.call("GET", URL))

        assert effective(mine, "ride", "ftp")["value"] == 250
        assert effective(theirs, "ride", "ftp")["value"] == 300
        assert mine["timezone"] == "Europe/Berlin"
        assert theirs["timezone"] == ""

    def test_changing_or_deleting_only_touches_the_own_value(self, alice: User, bob: User) -> None:
        alices, bobs = signed_in(alice), signed_in(bob)
        put(bobs, FTP, {"value": 300})

        put(alices, FTP, {"value": 250})
        alices.call("DELETE", FTP)

        assert effective(body(bobs.call("GET", URL)), "ride", "ftp")["value"] == 300

    def test_values_of_other_sources_belong_to_their_user_too(self, alice: User, bob: User) -> None:
        hold(bob, Source.INTERVALS, "ftp", 311)

        data = body(signed_in(alice).call("GET", URL))

        assert effective(data, "ride", "ftp") is None
        assert b"311" not in json.dumps(data).encode()

    def test_an_administrator_sees_only_their_own_values(self, alice: User) -> None:
        boss = make_user("boss@example.com", staff=True)
        put(signed_in(alice), FTP, {"value": 250})

        data = body(signed_in(boss).call("GET", URL))

        assert effective(data, "ride", "ftp") is None

    def test_the_answer_has_no_ids_and_no_owner(self, alice: User, bob: User) -> None:
        api = signed_in(alice)
        put(api, FTP, {"value": 250})
        api.call("PATCH", URL, {"timezone": "UTC"})

        text = api.call("GET", URL).content.decode()

        assert str(alice.pk) not in text
        assert str(bob.pk) not in text
        assert '"id"' not in text
        assert '"owner"' not in text

    def test_the_reading_does_not_run_a_query_per_threshold(
        self, alice: User, django_assert_max_num_queries: Any
    ) -> None:
        for metric, value in (("ftp", 250), ("lthr", 165), ("max_hr", 190)):
            for source in (Source.MANUAL, Source.INTERVALS, Source.ESTIMATED):
                hold(alice, source, metric, value)
        api = signed_in(alice)

        with django_assert_max_num_queries(6):
            api.call("GET", URL)

    def test_the_connection_is_the_only_other_table_read(self, alice: User) -> None:
        api = signed_in(alice)
        api.call("GET", URL)  # warm up: session and user

        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as queries:
            api.call("GET", URL)

        touched = " ".join(q["sql"] for q in queries)
        assert "athletes_thresholdvalue" in touched
        assert "api_key" not in touched
