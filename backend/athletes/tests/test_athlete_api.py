import base64
import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from typing import Any

import pytest
from django.db import connection
from django.utils import timezone

from accounts.models import User
from accounts.tests.conftest import AuthApi
from athletes import best_times
from athletes.models import MIN_AGE, TRAINING_YEARS_MAX, AthleteProfile, BestTime, ThresholdValue
from athletes.serializers import EQUIPMENT_CHOICE, NOTHING_TO_CHANGE, TRAINING_YEARS
from integrations.models import ProviderConnection
from integrations.tests.fake_intervals import FakeIntervals

from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

URL = "/api/athlete/"
BODY_FIELDS = (
    "birth_year", "sex", "weight_kg", "resting_hr", "training_years", "strength_experience",
    "strength_equipment",
)  # fmt: skip
FTP = f"{URL}thresholds/ride/ftp/"
SYNC = f"{URL}sync/"
SETTINGS_PATH = "/api/v1/athlete/0/sport-settings"
KEY = "k3y-0123456789-abcdefghij"
Source = ThresholdValue.Source


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def body(response: Any) -> Any:
    return json.loads(response.content)


def numbers_in(data: Any) -> Iterator[float]:
    """Every JSON number in ``data`` at any depth. Text, booleans and ``null`` are not numbers."""
    if isinstance(data, bool):
        return
    if isinstance(data, int | float):
        yield data
    elif isinstance(data, dict):
        for value in data.values():
            yield from numbers_in(value)
    elif isinstance(data, list):
        for value in data:
            yield from numbers_in(value)


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
            ("POST", SYNC),
        ],
    )
    def test_anonymous_visitors_are_refused(self, method: str, url: str) -> None:
        response = AuthApi().call(method, url, {"value": 250, "timezone": "UTC"})

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert not ThresholdValue.objects.exists()
        assert not AthleteProfile.objects.exists()

    @pytest.mark.parametrize(
        ("method", "url"), [("PATCH", URL), ("PUT", FTP), ("DELETE", FTP), ("POST", SYNC)]
    )
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

    def test_the_body_and_training_data_is_empty(self, alice: User) -> None:
        data = body(signed_in(alice).call("GET", URL))

        assert {name: data[name] for name in BODY_FIELDS} == {
            "birth_year": None,
            "sex": None,
            "weight_kg": None,
            "resting_hr": None,
            "training_years": {
                "running": None,
                "cycling": None,
                "swimming": None,
                "strength": None,
            },
            "strength_experience": None,
            "strength_equipment": [],
        }

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


class TestBodyAndTrainingData:
    LATEST = date.today().year - MIN_AGE

    def patch(self, owner: User, data: Any) -> Any:
        return signed_in(owner).call("PATCH", URL, data)

    def test_every_field_is_saved_and_shown(self, alice: User) -> None:
        api = signed_in(alice)
        data = {
            "birth_year": 1985,
            "sex": "female",
            "weight_kg": 61.5,
            "resting_hr": 48,
            "training_years": {"running": 12, "cycling": 3, "swimming": 0, "strength": 1},
            "strength_experience": "beginner",
            "strength_equipment": ["dumbbells", "gym"],
        }

        response = api.call("PATCH", URL, data)

        assert response.status_code == HTTPStatus.OK
        shown = {name: body(response)[name] for name in BODY_FIELDS}
        assert shown == data | {"strength_equipment": ["gym", "dumbbells"]}
        assert {name: body(api.call("GET", URL))[name] for name in BODY_FIELDS} == shown

    def test_only_the_fields_sent_change(self, alice: User) -> None:
        api = signed_in(alice)
        api.call("PATCH", URL, {"timezone": "UTC", "birth_year": 1985, "resting_hr": 48})

        response = api.call("PATCH", URL, {"weight_kg": 70})

        data = body(response)
        assert (data["timezone"], data["birth_year"], data["resting_hr"]) == ("UTC", 1985, 48)
        assert data["weight_kg"] == 70

    def test_null_clears_a_field(self, alice: User) -> None:
        api = signed_in(alice)
        api.call(
            "PATCH",
            URL,
            {
                "birth_year": 1985,
                "sex": "male",
                "weight_kg": 70,
                "resting_hr": 50,
                "strength_experience": "advanced",
            },
        )

        response = api.call(
            "PATCH",
            URL,
            {
                "birth_year": None,
                "sex": None,
                "weight_kg": None,
                "resting_hr": None,
                "strength_experience": None,
            },
        )

        data = body(response)
        cleared = ("birth_year", "sex", "weight_kg", "resting_hr", "strength_experience")
        assert [data[name] for name in cleared] == [None] * 5
        profile = AthleteProfile.objects.get()
        assert (profile.sex, profile.strength_experience) == ("", "")

    def test_the_years_of_one_sport_change_and_the_others_stay(self, alice: User) -> None:
        api = signed_in(alice)
        api.call("PATCH", URL, {"training_years": {"running": 12, "cycling": 3}})

        response = api.call("PATCH", URL, {"training_years": {"cycling": None, "swimming": 2}})

        assert body(response)["training_years"] == {
            "running": 12,
            "cycling": None,
            "swimming": 2,
            "strength": None,
        }

    def test_the_equipment_can_be_emptied(self, alice: User) -> None:
        api = signed_in(alice)
        api.call("PATCH", URL, {"strength_equipment": ["gym"]})

        response = api.call("PATCH", URL, {"strength_equipment": []})

        assert body(response)["strength_equipment"] == []

    def test_a_field_can_be_saved_without_a_time_zone(self, alice: User) -> None:
        response = self.patch(alice, {"birth_year": 1985})

        assert response.status_code == HTTPStatus.OK
        assert body(response)["timezone"] == ""
        assert AthleteProfile.objects.count() == 1

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("birth_year", 1899),
            ("birth_year", LATEST + 1),
            ("birth_year", "1985"),
            ("birth_year", 1985.5),
            ("birth_year", True),
            ("sex", "x"),
            ("sex", "Female"),
            ("sex", 5),
            ("weight_kg", 24),
            ("weight_kg", 301),
            ("weight_kg", "70"),
            ("weight_kg", True),
            ("resting_hr", 24),
            ("resting_hr", 121),
            ("resting_hr", 48.5),
            ("resting_hr", "48"),
            ("strength_experience", "expert"),
            ("strength_experience", 1),
            ("training_years", {"running": TRAINING_YEARS_MAX + 1}),
            ("training_years", {"running": -1}),
            ("training_years", {"running": "5"}),
            ("training_years", {"running": 1.5}),
            ("training_years", {"running": True}),
            ("training_years", {"golf": 5}),
            ("training_years", [5]),
            ("training_years", 5),
            ("training_years", None),
            ("strength_equipment", ["barbell"]),
            ("strength_equipment", ["gym", "gym"]),
            ("strength_equipment", "gym"),
            ("strength_equipment", None),
        ],
    )
    def test_a_field_that_is_not_usable_is_refused_and_changes_nothing(
        self, alice: User, field: str, value: Any
    ) -> None:
        api = signed_in(alice)
        api.call("PATCH", URL, {"birth_year": 1985})
        # a valid field next to it, which must not be saved either
        other = "weight_kg" if field == "resting_hr" else "resting_hr"

        response = api.call("PATCH", URL, {field: value, other: 70 if other == "weight_kg" else 50})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert set(body(response)) == {field}
        profile = AthleteProfile.objects.get()
        assert (profile.birth_year, profile.resting_hr, profile.weight_kg) == (1985, None, None)

    def test_a_refusal_for_a_new_user_leaves_no_profile(self, alice: User) -> None:
        self.patch(alice, {"weight_kg": 5})

        assert not AthleteProfile.objects.exists()

    def test_the_messages_say_what_is_allowed(self, alice: User) -> None:
        assert body(self.patch(alice, {"weight_kg": 5})) == {
            "weight_kg": ["Enter a weight between 25 and 300 kg."]
        }
        assert body(self.patch(alice, {"resting_hr": 5})) == {
            "resting_hr": ["Enter a resting heart rate between 25 and 120 bpm."]
        }
        assert body(self.patch(alice, {"training_years": {"golf": 1}})) == {
            "training_years": [TRAINING_YEARS]
        }
        assert body(self.patch(alice, {"strength_equipment": ["x"]})) == {
            "strength_equipment": [EQUIPMENT_CHOICE]
        }
        assert EQUIPMENT_CHOICE == "Choose any of: gym, home, dumbbells, or none."

    def test_every_problem_of_a_kind_is_named_at_once(self, alice: User) -> None:
        wrong_type = self.patch(alice, {"sex": "x", "birth_year": "1985", "weight_kg": 5})
        out_of_range = self.patch(alice, {"weight_kg": 5, "resting_hr": 5, "birth_year": 1800})

        assert set(body(wrong_type)) == {"sex", "birth_year"}
        assert set(body(out_of_range)) == {"weight_kg", "resting_hr", "birth_year"}

    def test_a_body_with_nothing_to_change_is_refused(self, alice: User) -> None:
        response = self.patch(alice, {})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"non_field_errors": [NOTHING_TO_CHANGE]}
        assert not AthleteProfile.objects.exists()

    def test_the_data_of_another_user_is_not_shown_or_changed(self, alice: User, bob: User) -> None:
        self.patch(bob, {"birth_year": 1970, "weight_kg": 88.5, "resting_hr": 61})

        self.patch(alice, {"resting_hr": 45})

        shown = body(signed_in(alice).call("GET", URL))
        assert (shown["birth_year"], shown["weight_kg"], shown["resting_hr"]) == (None, None, 45)
        assert AthleteProfile.objects.get(owner=bob).resting_hr == 61


class TestBestTimes:
    DAY = date(2026, 11, 16)

    @pytest.fixture(autouse=True)
    def _fixed_day(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(best_times, "_today", lambda: self.DAY)

    def url(self, distance: str) -> str:
        return f"{URL}best-times/{distance}/"

    def day(self, ago: int) -> str:
        return (self.DAY - timedelta(days=ago)).isoformat()

    def test_a_new_user_has_none(self, alice: User) -> None:
        data = body(signed_in(alice).call("GET", URL))

        assert data["best_times"] == {
            "5k": None,
            "10k": None,
            "half_marathon": None,
            "marathon": None,
        }
        assert data["vdot"] is None

    def test_a_time_is_saved_and_shown_with_its_vdot(self, alice: User) -> None:
        api = signed_in(alice)

        response = put(api, self.url("5k"), {"seconds": 1197, "date": self.day(10)})

        assert response.status_code == HTTPStatus.OK
        data = body(response)
        assert data["best_times"]["5k"] == {
            "seconds": 1197,
            "date": self.day(10),
            "vdot": 50.0,
            "recent": True,
            "counts": True,
        }
        assert data["best_times"]["10k"] is None
        assert data["vdot"] == {"value": 50.0, "distance": "5k", "date": self.day(10)}
        assert BestTime.objects.get().owner == alice

    def test_the_threshold_pace_and_the_zones_follow_from_it(self, alice: User) -> None:
        api = signed_in(alice)

        data = body(put(api, self.url("5k"), {"seconds": 1197, "date": self.day(10)}))

        pace = data["sports"]["run"]["thresholds"]["threshold_pace"]
        assert pace["effective"]["source"] == "best_time"
        assert divmod(round(pace["effective"]["value"]), 60) == (4, 15)
        assert pace["effective"]["basis"] == f"VDOT 50.0 from your 5 km on {self.day(10)}"
        assert data["sports"]["run"]["zones"]["pace"]["basis"] == "threshold_pace"

    def test_a_typed_pace_counts_before_it_and_the_time_is_still_listed(self, alice: User) -> None:
        api = signed_in(alice)
        put(api, f"{URL}thresholds/run/threshold_pace/", {"value": 300})

        data = body(put(api, self.url("5k"), {"seconds": 1197, "date": self.day(10)}))

        pace = data["sports"]["run"]["thresholds"]["threshold_pace"]
        assert pace["effective"]["source"] == "manual"
        assert [c["source"] for c in pace["candidates"]] == ["manual", "best_time"]

    def test_a_second_time_for_the_distance_replaces_the_first(self, alice: User) -> None:
        api = signed_in(alice)
        put(api, self.url("5k"), {"seconds": 1300, "date": self.day(100)})

        data = body(put(api, self.url("5k"), {"seconds": 1197, "date": self.day(10)}))

        assert BestTime.objects.count() == 1
        assert data["best_times"]["5k"]["seconds"] == 1197

    def test_the_newest_race_counts_and_an_old_one_says_so(self, alice: User) -> None:
        api = signed_in(alice)
        put(api, self.url("10k"), {"seconds": 2481, "date": self.day(400)})
        data = body(put(api, self.url("5k"), {"seconds": 1500, "date": self.day(30)}))

        assert data["best_times"]["10k"]["recent"] is False
        assert data["best_times"]["10k"]["counts"] is False
        assert data["best_times"]["5k"]["counts"] is True
        assert data["vdot"]["distance"] == "5k"

    def test_with_only_an_old_time_nothing_counts(self, alice: User) -> None:
        data = body(put(signed_in(alice), self.url("5k"), {"seconds": 1197, "date": self.day(400)}))

        assert data["vdot"] is None
        assert data["sports"]["run"]["thresholds"]["threshold_pace"]["effective"] is None

    def test_a_time_is_removed_and_removing_it_again_is_fine(self, alice: User) -> None:
        api = signed_in(alice)
        put(api, self.url("5k"), {"seconds": 1197, "date": self.day(10)})

        first = api.call("DELETE", self.url("5k"))
        second = api.call("DELETE", self.url("5k"))

        assert (first.status_code, second.status_code) == (HTTPStatus.OK, HTTPStatus.OK)
        assert body(second)["best_times"]["5k"] is None
        assert not BestTime.objects.exists()

    def test_removing_a_time_removes_only_that_one(self, alice: User) -> None:
        api = signed_in(alice)
        put(api, self.url("5k"), {"seconds": 1197, "date": self.day(10)})
        put(api, self.url("10k"), {"seconds": 2481, "date": self.day(20)})

        api.call("DELETE", self.url("5k"))

        assert list(BestTime.objects.values_list("distance", flat=True)) == ["10k"]

    @pytest.mark.parametrize("distance", ["3k", "5K", "ultra", "marathon "])
    @pytest.mark.parametrize("method", ["PUT", "DELETE"])
    def test_an_unknown_distance_is_a_404(self, alice: User, distance: str, method: str) -> None:
        response = signed_in(alice).call(
            method, self.url(distance), {"seconds": 1197, "date": self.day(10)}
        )

        assert response.status_code == HTTPStatus.NOT_FOUND

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"seconds": 1197}, "date"),
            ({"date": "2026-10-01"}, "seconds"),
            ({"seconds": "1197", "date": "2026-10-01"}, "seconds"),
            ({"seconds": 1197.5, "date": "2026-10-01"}, "seconds"),
            ({"seconds": True, "date": "2026-10-01"}, "seconds"),
            ({"seconds": 0, "date": "2026-10-01"}, "seconds"),
            ({"seconds": -5, "date": "2026-10-01"}, "seconds"),
            ({"seconds": None, "date": "2026-10-01"}, "seconds"),
            ({"seconds": 1197, "date": "01.10.2026"}, "date"),
            ({"seconds": 1197, "date": "2026-13-45"}, "date"),
            ({"seconds": 1197, "date": 20261001}, "date"),
            ({"seconds": 1197, "date": None}, "date"),
            ({"seconds": 300, "date": "2026-10-01"}, "seconds"),
            ({"seconds": 100000, "date": "2026-10-01"}, "seconds"),
            ({"seconds": 1197, "date": "2999-01-01"}, "date"),
            ({"seconds": 1197, "date": "1899-12-31"}, "date"),
        ],
    )
    def test_a_time_that_is_not_usable_is_refused_and_saves_nothing(
        self, alice: User, payload: Any, field: str
    ) -> None:
        response = put(signed_in(alice), self.url("5k"), payload)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert field in body(response)
        assert not BestTime.objects.exists()

    @pytest.mark.parametrize("payload", [[1197], "1197", 1197, None, [], ""])
    def test_a_body_of_the_wrong_type_is_a_400_and_never_a_500(
        self, alice: User, payload: Any
    ) -> None:
        assert put(signed_in(alice), self.url("5k"), payload).status_code == HTTPStatus.BAD_REQUEST

    def test_a_refusal_keeps_the_earlier_time(self, alice: User) -> None:
        api = signed_in(alice)
        put(api, self.url("5k"), {"seconds": 1197, "date": self.day(10)})

        put(api, self.url("5k"), {"seconds": 300, "date": self.day(10)})

        assert BestTime.objects.get().seconds == 1197

    def test_the_messages_say_what_is_wrong(self, alice: User) -> None:
        assert body(
            put(signed_in(alice), self.url("5k"), {"seconds": 300, "date": "2026-10-01"})
        ) == {"seconds": ["That time is not plausible for this distance. Check it."]}

    def test_only_the_own_times_are_seen_changed_or_removed(self, alice: User, bob: User) -> None:
        put(signed_in(bob), self.url("5k"), {"seconds": 1197, "date": self.day(10)})

        mine = body(put(signed_in(alice), self.url("5k"), {"seconds": 1500, "date": self.day(5)}))
        signed_in(alice).call("DELETE", self.url("10k"))

        assert mine["best_times"]["5k"]["seconds"] == 1500
        assert BestTime.objects.get(owner=bob).seconds == 1197
        assert body(signed_in(alice).call("GET", URL))["best_times"]["10k"] is None

    @pytest.mark.parametrize("method", ["PUT", "DELETE"])
    def test_anonymous_visitors_are_refused(self, method: str) -> None:
        response = AuthApi().call(method, self.url("5k"), {"seconds": 1197, "date": "2026-10-01"})

        assert response.status_code == HTTPStatus.FORBIDDEN

    @pytest.mark.parametrize("method", ["GET", "PATCH", "POST"])
    def test_other_methods_are_not_allowed(self, alice: User, method: str) -> None:
        response = signed_in(alice).call(method, self.url("5k"), {})

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED

    def test_the_vdot_of_another_user_is_not_in_the_answer(self, alice: User, bob: User) -> None:
        put(signed_in(bob), self.url("5k"), {"seconds": 1197, "date": self.day(10)})

        data = body(signed_in(alice).call("GET", URL))

        assert data["vdot"] is None
        assert data["sports"]["run"]["thresholds"]["threshold_pace"]["candidates"] == []


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


def connect(owner: User, key: str = KEY) -> ProviderConnection:
    return ProviderConnection.objects.create(
        owner=owner, provider="intervals_icu", api_key=key, athlete_id="i1"
    )


def settings_answer(fake: FakeIntervals, *entries: object) -> None:
    fake.bodies[SETTINGS_PATH] = json.dumps(list(entries)).encode()


def typical(fake: FakeIntervals) -> None:
    settings_answer(
        fake,
        {"types": ["Ride", "VirtualRide"], "ftp": 262, "lthr": 165, "max_hr": 190},
        {"types": ["Run"], "lthr": 170, "max_hr": 188, "threshold_pace": 10 / 3},
    )


class TestSync:
    def test_it_reads_the_values_and_answers_with_the_whole_profile(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        typical(fake)

        response = signed_in(alice).call("POST", SYNC)

        assert response.status_code == HTTPStatus.OK
        data = body(response)
        found = effective(data, "ride", "ftp")
        assert (found["value"], found["source"]) == (262, "intervals")
        assert found["basis"] == "Read from your Intervals.icu sport settings"
        assert effective(data, "run", "threshold_pace")["value"] == 300
        assert data["intervals"]["connected"] is True
        assert data["intervals"]["synced_at"].endswith("Z")
        assert data["sports"]["ride"]["zones"]["power"]["basis"] == "ftp"
        assert data["sports"]["run"]["zones"]["pace"]["basis"] == "threshold_pace"
        assert body(signed_in(alice).call("GET", URL)) == data

    def test_a_typed_value_still_counts_and_intervals_is_a_candidate(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        typical(fake)
        api = signed_in(alice)
        put(api, FTP, {"value": 255})

        data = body(api.call("POST", SYNC))

        threshold = data["sports"]["ride"]["thresholds"]["ftp"]
        assert [(c["source"], c["value"]) for c in threshold["candidates"]] == [
            ("manual", 255),
            ("intervals", 262),
        ]
        assert threshold["effective"]["source"] == "manual"

    def test_without_a_connection_it_is_a_404_and_nothing_is_asked(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        response = signed_in(alice).call("POST", SYNC)

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response) == {"detail": "Not connected."}
        assert fake.requests == []
        assert not ThresholdValue.objects.exists()
        assert not AthleteProfile.objects.exists()

    @pytest.mark.parametrize("status", [401, 403])
    def test_a_key_that_is_refused_is_a_409_and_the_connection_needs_attention(
        self, fake: FakeIntervals, alice: User, status: int
    ) -> None:
        connection = connect(alice)
        fake.status = status
        api = signed_in(alice)

        response = api.call("POST", SYNC)

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response) == {
            "detail": "Intervals.icu did not accept the stored API key. "
            "Enter it again on the Connections page."
        }
        assert ProviderConnection.objects.defer("api_key").get(pk=connection.pk).status == "invalid"
        assert body(api.call("GET", URL))["intervals"]["connected"] is False
        assert not ThresholdValue.objects.exists()

    @pytest.mark.parametrize("status", [429, 500, 503])
    def test_an_unreachable_service_is_a_503_with_the_usual_text(
        self, fake: FakeIntervals, alice: User, status: int
    ) -> None:
        connection = connect(alice)
        fake.status = status

        response = signed_in(alice).call("POST", SYNC)

        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert body(response) == {
            "detail": "Intervals.icu cannot be reached right now. Please try again later."
        }
        assert (
            ProviderConnection.objects.defer("api_key").get(pk=connection.pk).status == "connected"
        )
        assert not ThresholdValue.objects.exists()

    def test_an_odd_answer_is_a_502_with_the_usual_text(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        fake.bodies[SETTINGS_PATH] = b'{"not": "a list"}'

        response = signed_in(alice).call("POST", SYNC)

        assert response.status_code == HTTPStatus.BAD_GATEWAY
        assert body(response) == {
            "detail": "Intervals.icu answered in an unexpected way. Please try again later."
        }

    def test_the_eleventh_call_within_a_minute_is_throttled_and_never_asks(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        typical(fake)
        api = signed_in(alice)
        for _ in range(10):
            assert api.call("POST", SYNC).status_code == HTTPStatus.OK

        response = api.call("POST", SYNC)

        assert response.status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert "Retry-After" in response.headers
        assert len(fake.requests) == 10

    def test_it_shares_the_counter_with_connecting_and_checking(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        typical(fake)
        api = signed_in(alice)
        for _ in range(5):
            api.call("POST", SYNC)
            api.call("POST", "/api/integrations/intervals/check/")

        assert api.call("POST", SYNC).status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert api.call("POST", "/api/integrations/intervals/check/").status_code == (
            HTTPStatus.TOO_MANY_REQUESTS
        )

    def test_another_user_is_not_throttled(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        connect(alice)
        connect(bob)
        typical(fake)
        alices = signed_in(alice)
        for _ in range(11):
            alices.call("POST", SYNC)

        assert signed_in(bob).call("POST", SYNC).status_code == HTTPStatus.OK

    def test_it_uses_only_the_key_and_the_values_of_the_user_who_asks(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        connect(alice, "alice-key-0123456789")
        connect(bob, "bob-key-0123456789")
        typical(fake)

        data = body(signed_in(alice).call("POST", SYNC))

        [request] = fake.requests
        expected = base64.b64encode(b"API_KEY:alice-key-0123456789").decode()
        assert request["headers"]["Authorization"] == f"Basic {expected}"
        assert not ThresholdValue.objects.filter(owner=bob).exists()
        assert effective(body(signed_in(bob).call("GET", URL)), "ride", "ftp") is None
        assert effective(data, "ride", "ftp")["source"] == "intervals"

    def test_a_get_is_not_allowed(self, alice: User) -> None:
        assert signed_in(alice).call("GET", SYNC).status_code == HTTPStatus.METHOD_NOT_ALLOWED

    def test_neither_the_key_nor_other_users_data_is_in_any_answer(
        self, fake: FakeIntervals, alice: User, bob: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Bob's value is looked for among the numbers of the answers, not as text: answers carry
        # timestamps, and a number written as text turns up in those by chance (microseconds such
        # as ".877042"). The clock below makes it do so on purpose, so that this test cannot flake.
        bobs_value = 877
        connect(alice, "alice-key-0123456789")
        hold(bob, Source.INTERVALS, "ftp", bobs_value)
        typical(fake)
        assert bobs_value in numbers_in(body(signed_in(bob).call("GET", URL)))  # it is findable
        api = signed_in(alice)
        monkeypatch.setattr(
            timezone, "now", lambda: datetime(2026, 11, 13, 12, 31, 10, 877000, UTC)
        )

        texts = [api.call("POST", SYNC).content.decode(), api.call("GET", URL).content.decode()]
        fake.status = 401
        texts.append(api.call("POST", SYNC).content.decode())

        assert any(str(bobs_value) in text for text in texts)  # the clock does what it should
        for text in texts:
            assert "alice-key-0123456789" not in text
            assert bobs_value not in numbers_in(json.loads(text))


def test_numbers_in_finds_numbers_at_any_depth_and_nothing_else() -> None:
    data = {"a": [1, {"b": 2.5, "c": [3]}], "d": "4", "e": True, "f": None, "g": {"h": -5}}

    assert sorted(numbers_in(data)) == [-5, 1, 2.5, 3]
    assert list(numbers_in(7)) == [7]
    assert list(numbers_in("7")) == []
    assert list(numbers_in(False)) == []
