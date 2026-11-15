import json
from datetime import date, timedelta
from http import HTTPStatus
from typing import Any

import pytest

from accounts.models import User
from accounts.tests.conftest import AuthApi
from availability.capacity import minutes_in_week
from availability.intensity import LIMIT_NAMES, Limits
from availability.models import AvailabilitySettings, WeekdayMinutes

from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

URL = "/api/availability/"
MONDAY = date(2027, 7, 12)
ALL_SPORTS = ["running", "cycling", "swimming", "strength"]
# The intensity of a user who chose nothing: "normal" without own limits, and every level's limits.
LEVEL_LIMITS_ANSWER = {
    "relaxed": {
        "max_hard_days": 1,
        "progression_warning_percent": 115,
        "progression_error_percent": 130,
        "easy_share_percent": 85,
    },
    "normal": {
        "max_hard_days": 2,
        "progression_warning_percent": 120,
        "progression_error_percent": 140,
        "easy_share_percent": 80,
    },
    "intensive": {
        "max_hard_days": 3,
        "progression_warning_percent": 130,
        "progression_error_percent": 150,
        "easy_share_percent": 75,
    },
}
INTENSITY = {
    "intensity_level": "normal",
    "max_hard_days": None,
    "progression_warning_percent": None,
    "progression_error_percent": None,
    "easy_share_percent": None,
    "level_limits": LEVEL_LIMITS_ANSWER,
}
# What a weekday offers until the user says otherwise: two sessions, every part of the day.
DAY_OPTIONS = {
    "double_days": [True] * 7,
    "time_windows": [["morning", "afternoon", "evening"]] * 7,
}
EMPTY = {
    "weekdays": [0] * 7,
    "weekly_budget_minutes": None,
    "typical_weekly_minutes": None,
    "sports": ALL_SPORTS,
    "stretching": False,
    "limitations": "",
    **INTENSITY,
    **DAY_OPTIONS,
}
WEEK = [60, 0, 90, 0, 0, 120, 180]


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def body(response: Any) -> Any:
    return json.loads(response.content)


def read(api: AuthApi) -> Any:
    response = api.call("GET", URL)
    assert response.status_code == HTTPStatus.OK
    return body(response)


def save(api: AuthApi, data: Any) -> Any:
    return api.call("PATCH", URL, data)


def rows() -> tuple[int, int]:
    return WeekdayMinutes.objects.count(), AvailabilitySettings.objects.count()


class TestAccess:
    @pytest.mark.parametrize("method", ["GET", "PATCH"])
    def test_anonymous_visitors_are_refused(self, method: str) -> None:
        response = AuthApi().call(method, URL, {"limitations": "x"})

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert rows() == (0, 0)

    def test_a_request_without_the_csrf_token_is_refused(self, alice: User) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            "PATCH", URL, data=json.dumps({"limitations": "x"}), content_type="application/json"
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert rows() == (0, 0)

    @pytest.mark.parametrize("method", ["PUT", "POST", "DELETE"])
    def test_other_methods_are_not_allowed(self, alice: User, method: str) -> None:
        response = signed_in(alice).call(method, URL, EMPTY)

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
        assert rows() == (0, 0)


class TestReading:
    def test_a_user_who_saved_nothing_gets_zeros_and_no_budget(self, alice: User) -> None:
        assert read(signed_in(alice)) == EMPTY

    def test_reading_writes_nothing(self, alice: User) -> None:
        api = signed_in(alice)

        read(api)
        read(api)

        assert rows() == (0, 0)

    def test_the_answer_has_exactly_these_fields(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "weekly_budget_minutes": 300, "limitations": "Knee"})

        assert set(read(api)) == {
            "weekdays",
            "weekly_budget_minutes",
            "typical_weekly_minutes",
            "sports",
            "stretching",
            "limitations",
            "double_days",
            "time_windows",
            "intensity_level",
            "max_hard_days",
            "progression_warning_percent",
            "progression_error_percent",
            "easy_share_percent",
            "level_limits",
        }

    def test_the_weekdays_come_monday_first_and_missing_ones_are_zero(self, alice: User) -> None:
        WeekdayMinutes.objects.create(owner=alice, weekday=0, minutes=60)
        WeekdayMinutes.objects.create(owner=alice, weekday=6, minutes=180)

        assert read(signed_in(alice))["weekdays"] == [60, 0, 0, 0, 0, 0, 180]

    def test_a_user_sees_only_their_own_data(self, alice: User, bob: User) -> None:
        WeekdayMinutes.objects.create(owner=bob, weekday=0, minutes=500)
        AvailabilitySettings.objects.create(
            owner=bob, weekly_budget_minutes=900, limitations="Bob's back"
        )

        assert read(signed_in(alice)) == EMPTY


class TestSportsAndStretching:
    def test_a_user_who_chose_nothing_gets_all_sports_and_no_stretching(self, alice: User) -> None:
        answer = read(signed_in(alice))

        assert (answer["sports"], answer["stretching"]) == (ALL_SPORTS, False)

    def test_settings_saved_before_the_choice_existed_read_as_all_sports(self, alice: User) -> None:
        AvailabilitySettings.objects.create(owner=alice, weekly_budget_minutes=300)

        assert read(signed_in(alice))["sports"] == ALL_SPORTS

    def test_the_sports_are_chosen_and_kept_in_the_order_of_the_list(self, alice: User) -> None:
        api = signed_in(alice)

        response = save(api, {"sports": ["strength", "cycling"]})

        assert response.status_code == HTTPStatus.OK
        assert body(response)["sports"] == ["cycling", "strength"]
        assert AvailabilitySettings.objects.get().sports == ["cycling", "strength"]
        assert read(api)["sports"] == ["cycling", "strength"]

    def test_all_four_can_be_chosen_explicitly(self, alice: User) -> None:
        response = save(signed_in(alice), {"sports": ALL_SPORTS[::-1]})

        assert body(response)["sports"] == ALL_SPORTS

    def test_the_choice_can_be_changed(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"sports": ["running"]})

        save(api, {"sports": ["swimming", "running"]})

        assert read(api)["sports"] == ["running", "swimming"]

    @pytest.mark.parametrize(
        "sports",
        [[], ["golf"], ["running", "running"], ["Running"], "running", None, [5], {}, True, 3],
    )
    def test_an_unusable_choice_is_refused(self, alice: User, sports: Any) -> None:
        response = save(signed_in(alice), {"sports": sports})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert list(body(response)) == ["sports"]
        assert body(response)["sports"] == [
            "Choose at least one of: running, cycling, swimming, strength."
        ]
        assert rows() == (0, 0)

    @pytest.mark.parametrize("stretching", [True, False])
    def test_stretching_is_switched_on_and_off(self, alice: User, stretching: bool) -> None:
        api = signed_in(alice)

        response = save(api, {"stretching": stretching})

        assert body(response)["stretching"] is stretching
        assert read(api)["stretching"] is stretching

    @pytest.mark.parametrize("stretching", ["true", "false", 1, 0, None, "yes", [], {}, 1.0])
    def test_only_true_and_false_are_stretching(self, alice: User, stretching: Any) -> None:
        response = save(signed_in(alice), {"stretching": stretching})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert list(body(response)) == ["stretching"]
        assert body(response)["stretching"] == ["Send true or false."]
        assert rows() == (0, 0)

    def test_the_sports_alone_leave_the_rest_as_it_was(self, alice: User) -> None:
        api = signed_in(alice)
        save(
            api,
            {
                "weekdays": WEEK,
                "weekly_budget_minutes": 300,
                "typical_weekly_minutes": 360,
                "stretching": True,
                "limitations": "Knee",
            },
        )

        save(api, {"sports": ["running"]})

        assert read(api) == {
            "weekdays": WEEK,
            "weekly_budget_minutes": 300,
            "typical_weekly_minutes": 360,
            "sports": ["running"],
            "stretching": True,
            "limitations": "Knee",
            **INTENSITY,
            **DAY_OPTIONS,
        }

    def test_the_other_settings_leave_the_choice_as_it_was(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"sports": ["cycling"], "stretching": True})

        save(api, {"weekly_budget_minutes": 200, "limitations": "Knee"})

        answer = read(api)
        assert (answer["sports"], answer["stretching"]) == (["cycling"], True)

    def test_the_choice_of_another_user_is_not_seen(self, alice: User, bob: User) -> None:
        AvailabilitySettings.objects.create(owner=bob, sports=["swimming"], stretching=True)

        answer = read(signed_in(alice))

        assert (answer["sports"], answer["stretching"]) == (ALL_SPORTS, False)

    def test_a_refusal_keeps_the_choice(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"sports": ["running"], "stretching": True})

        response = save(api, {"sports": [], "stretching": False})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        answer = read(api)
        assert (answer["sports"], answer["stretching"]) == (["running"], True)

    def test_every_problem_is_named_at_once(self, alice: User) -> None:
        response = save(signed_in(alice), {"sports": [], "stretching": "yes"})

        assert set(body(response)) == {"sports", "stretching"}


class TestIntensity:
    OWN = {
        "max_hard_days": 3,
        "progression_warning_percent": 110,
        "progression_error_percent": 160,
        "easy_share_percent": 70,
    }

    def test_a_new_user_has_normal_without_own_limits(self, alice: User) -> None:
        answer = read(signed_in(alice))

        assert {key: answer[key] for key in INTENSITY} == INTENSITY

    def test_the_level_is_chosen_and_kept(self, alice: User) -> None:
        api = signed_in(alice)

        for level in ("relaxed", "intensive", "normal"):
            assert body(save(api, {"intensity_level": level}))["intensity_level"] == level
            assert read(api)["intensity_level"] == level

    def test_own_limits_are_saved_and_null_gives_the_levels_back(self, alice: User) -> None:
        api = signed_in(alice)

        assert body(save(api, self.OWN)) == {**EMPTY, **self.OWN}
        assert AvailabilitySettings.objects.get(owner=alice).limits == Limits(3, 110, 160, 70)

        save(api, {"progression_warning_percent": None, "easy_share_percent": None})

        settings = AvailabilitySettings.objects.get(owner=alice)
        assert settings.own_limits == {**self.OWN, "progression_warning_percent": None,
                                       "easy_share_percent": None}  # fmt: skip
        assert settings.limits == Limits(3, 120, 160, 80)

    @pytest.mark.parametrize("name", LIMIT_NAMES)
    def test_every_own_limit_alone_leaves_the_rest_as_it_was(self, alice: User, name: str) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "limitations": "Knee", "intensity_level": "intensive"})
        before = read(api)

        save(api, {name: self.OWN[name]})

        assert read(api) == {**before, name: self.OWN[name]}

    def test_the_level_alone_leaves_the_own_limits_as_they_were(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"max_hard_days": 4, "easy_share_percent": 60})

        save(api, {"intensity_level": "relaxed"})

        answer = read(api)
        assert (answer["max_hard_days"], answer["easy_share_percent"]) == (4, 60)

    def test_the_other_settings_leave_the_intensity_as_it_was(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"intensity_level": "relaxed", **self.OWN})

        save(api, {"weekdays": WEEK, "sports": ["running"], "limitations": "Knee"})

        answer = read(api)
        assert answer["intensity_level"] == "relaxed"
        assert {name: answer[name] for name in self.OWN} == self.OWN

    def test_the_ends_of_the_ranges_are_accepted(self, alice: User) -> None:
        api = signed_in(alice)

        for data in (
            {"max_hard_days": 0, "easy_share_percent": 50},
            {"max_hard_days": 4, "easy_share_percent": 100},
            {"progression_warning_percent": 100, "progression_error_percent": 300},
            {"progression_warning_percent": 200, "progression_error_percent": 201},
        ):
            assert save(api, data).status_code == HTTPStatus.OK, data

    @pytest.mark.parametrize(
        ("name", "value", "message"),
        [
            ("max_hard_days", -1, "Enter a whole number of days between 0 and 4."),
            ("max_hard_days", 5, "Enter a whole number of days between 0 and 4."),
            ("max_hard_days", "2", "Enter a whole number of days between 0 and 4."),
            ("max_hard_days", 2.5, "Enter a whole number of days between 0 and 4."),
            ("max_hard_days", True, "Enter a whole number of days between 0 and 4."),
            ("progression_warning_percent", 99, "Enter a whole percent between 100 and 200."),
            ("progression_warning_percent", 201, "Enter a whole percent between 100 and 200."),
            ("progression_error_percent", 301, "Enter a whole percent between 100 and 300."),
            ("easy_share_percent", 49, "Enter a whole percent between 50 and 100."),
            ("easy_share_percent", [80], "Enter a whole percent between 50 and 100."),
        ],
    )
    def test_an_own_limit_out_of_range_is_refused(
        self, alice: User, name: str, value: Any, message: str
    ) -> None:
        response = save(signed_in(alice), {name: value})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {name: [message]}
        assert rows() == (0, 0)

    @pytest.mark.parametrize("level", ["brutal", "Normal", "", None, 1, True, ["normal"]])
    def test_an_unknown_level_is_refused(self, alice: User, level: Any) -> None:
        response = save(signed_in(alice), {"intensity_level": level})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"intensity_level": ["Choose one of: relaxed, normal, intensive."]}
        assert rows() == (0, 0)

    def test_a_warning_at_or_above_the_error_is_refused(self, alice: User) -> None:
        response = save(
            signed_in(alice),
            {"progression_warning_percent": 150, "progression_error_percent": 150},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {
            "progression_error_percent": [
                "The warning limit (150 %) must be below the error limit (150 %)."
            ]
        }
        assert rows() == (0, 0)

    def test_the_order_is_checked_against_what_is_stored(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"progression_warning_percent": 135})  # normal: error 140

        refused = save(api, {"intensity_level": "relaxed"})  # relaxed: error 130

        assert refused.status_code == HTTPStatus.BAD_REQUEST
        assert body(refused) == {
            "progression_warning_percent": [
                "The warning limit (135 %) must be below the error limit (130 %)."
            ]
        }
        assert read(api)["intensity_level"] == "normal"
        # with an own error limit sent along it is fine
        accepted = save(api, {"intensity_level": "relaxed", "progression_error_percent": 160})
        assert accepted.status_code == HTTPStatus.OK

    def test_a_null_that_breaks_the_order_is_refused(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"progression_warning_percent": 145, "progression_error_percent": 160})

        response = save(api, {"progression_error_percent": None})  # normal: error 140

        assert body(response) == {
            "progression_warning_percent": [
                "The warning limit (145 %) must be below the error limit (140 %)."
            ]
        }

    def test_the_stored_values_of_another_user_do_not_count(self, alice: User, bob: User) -> None:
        save(signed_in(bob), {"progression_warning_percent": 135})

        response = save(signed_in(alice), {"intensity_level": "relaxed"})

        assert response.status_code == HTTPStatus.OK
        assert read(signed_in(bob))["intensity_level"] == "normal"


class TestDoubleDaysAndTimeWindows:
    DOUBLE = [True, False, True, True, False, True, True]
    WINDOWS = [
        ["evening"],
        ["morning", "evening"],
        ["morning", "afternoon", "evening"],
        ["afternoon"],
        ["morning"],
        ["morning", "afternoon"],
        ["afternoon", "evening"],
    ]

    def test_a_user_who_chose_nothing_gets_two_sessions_and_every_part_of_the_day(
        self, alice: User
    ) -> None:
        answer = read(signed_in(alice))

        assert answer["double_days"] == [True] * 7
        assert answer["time_windows"] == [["morning", "afternoon", "evening"]] * 7

    def test_they_are_saved_and_read_back(self, alice: User) -> None:
        api = signed_in(alice)

        response = save(api, {"double_days": self.DOUBLE, "time_windows": self.WINDOWS})

        assert response.status_code == HTTPStatus.OK
        assert body(response)["double_days"] == self.DOUBLE
        assert body(response)["time_windows"] == self.WINDOWS
        assert read(api) == body(response)
        assert rows() == (7, 0)

    def test_the_parts_of_a_day_are_stored_in_the_order_of_the_day(self, alice: User) -> None:
        api = signed_in(alice)
        windows = [["evening", "morning"]] + self.WINDOWS[1:]

        save(api, {"time_windows": windows})

        assert read(api)["time_windows"][0] == ["morning", "evening"]

    def test_the_double_days_alone_leave_the_rest_as_it_was(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "time_windows": self.WINDOWS, "limitations": "Knee"})
        before = read(api)

        save(api, {"double_days": self.DOUBLE})

        assert read(api) == {**before, "double_days": self.DOUBLE}

    def test_the_time_windows_alone_leave_the_rest_as_it_was(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "double_days": self.DOUBLE, "limitations": "Knee"})
        before = read(api)

        save(api, {"time_windows": self.WINDOWS})

        assert read(api) == {**before, "time_windows": self.WINDOWS}

    def test_the_weekdays_alone_leave_them_as_they_were(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"double_days": self.DOUBLE, "time_windows": self.WINDOWS})

        save(api, {"weekdays": WEEK})

        answer = read(api)
        assert answer["weekdays"] == WEEK
        assert (answer["double_days"], answer["time_windows"]) == (self.DOUBLE, self.WINDOWS)

    def test_a_day_without_minutes_still_has_them(self, alice: User) -> None:
        api = signed_in(alice)

        save(api, {"double_days": self.DOUBLE})

        assert read(api)["weekdays"] == [0] * 7
        assert minutes_in_week(alice, MONDAY) == 0

    def test_the_other_settings_leave_them_as_they_were(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"double_days": self.DOUBLE, "time_windows": self.WINDOWS})

        save(api, {"weekly_budget_minutes": 300, "sports": ["running"], "stretching": True})

        answer = read(api)
        assert (answer["double_days"], answer["time_windows"]) == (self.DOUBLE, self.WINDOWS)

    def test_the_choice_of_another_user_is_not_seen(self, alice: User, bob: User) -> None:
        save(signed_in(bob), {"double_days": self.DOUBLE, "time_windows": self.WINDOWS})

        answer = read(signed_in(alice))

        assert answer["double_days"] == [True] * 7
        assert answer["time_windows"] == [["morning", "afternoon", "evening"]] * 7

    def test_saving_one_user_leaves_the_other_alone(self, alice: User, bob: User) -> None:
        bob_api = signed_in(bob)
        save(bob_api, {"double_days": self.DOUBLE, "time_windows": self.WINDOWS})

        save(signed_in(alice), {"double_days": [False] * 7})

        assert read(bob_api)["double_days"] == self.DOUBLE

    def test_rows_saved_before_the_choice_existed_read_as_the_defaults(self, alice: User) -> None:
        WeekdayMinutes.objects.create(owner=alice, weekday=2, minutes=90)

        answer = read(signed_in(alice))

        assert answer["weekdays"][2] == 90
        assert answer["double_days"] == [True] * 7
        assert answer["time_windows"][2] == ["morning", "afternoon", "evening"]

    @pytest.mark.parametrize(
        "double_days",
        [
            [True] * 6,
            [True] * 8,
            [],
            "TTTTTTT",
            {"0": True},
            None,
            [1] * 7,
            ["true"] * 7,
            [None] * 7,
            [[True]] * 7,
        ],
    )
    def test_unusable_double_days_are_refused(self, alice: User, double_days: Any) -> None:
        response = save(signed_in(alice), {"double_days": double_days})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {
            "double_days": ["Enter seven values of true or false, Monday first."]
        }
        assert rows() == (0, 0)

    @pytest.mark.parametrize(
        "windows",
        [
            [["morning"]] * 6,
            [["morning"]] * 8,
            [],
            "morning",
            None,
            [[]] * 7,
            [["noon"]] * 7,
            [["Morning"]] * 7,
            [["morning", "morning"]] * 7,
            ["morning"] * 7,
            [[1]] * 7,
            [[None]] * 7,
            [[["morning"]]] * 7,
            [{"morning": True}] * 7,
        ],
    )
    def test_unusable_time_windows_are_refused(self, alice: User, windows: Any) -> None:
        response = save(signed_in(alice), {"time_windows": windows})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {
            "time_windows": [
                "Enter seven lists of parts of the day, Monday first, each with at least one of: "
                "morning, afternoon, evening."
            ]
        }
        assert rows() == (0, 0)

    def test_a_refusal_saves_nothing_of_the_rest(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "double_days": self.DOUBLE})
        before = read(api)

        response = save(api, {"weekdays": [10] * 7, "double_days": self.DOUBLE[:3]})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert read(api) == before

    def test_every_problem_is_named_at_once(self, alice: User) -> None:
        response = save(
            signed_in(alice),
            {"weekdays": [0] * 3, "double_days": [True], "time_windows": [[]]},
        )

        assert set(body(response)) == {"weekdays", "double_days", "time_windows"}


class TestSaving:
    def test_everything_at_once(self, alice: User) -> None:
        api = signed_in(alice)

        response = save(
            api, {"weekdays": WEEK, "weekly_budget_minutes": 300, "limitations": "No running"}
        )

        assert response.status_code == HTTPStatus.OK
        assert body(response) == {
            "weekdays": WEEK,
            "weekly_budget_minutes": 300,
            "typical_weekly_minutes": None,
            "sports": ALL_SPORTS,
            "stretching": False,
            "limitations": "No running",
            **INTENSITY,
            **DAY_OPTIONS,
        }
        assert read(api) == body(response)
        assert rows() == (7, 1)

    def test_the_weekdays_alone_leave_the_rest_as_it_was(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekly_budget_minutes": 300, "limitations": "Knee"})

        save(api, {"weekdays": WEEK})

        assert read(api) == {
            "weekdays": WEEK,
            "weekly_budget_minutes": 300,
            "typical_weekly_minutes": None,
            "sports": ALL_SPORTS,
            "stretching": False,
            "limitations": "Knee",
            **INTENSITY,
            **DAY_OPTIONS,
        }

    def test_the_budget_alone_leaves_the_rest_as_it_was(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "limitations": "Knee"})

        save(api, {"weekly_budget_minutes": 240})

        assert read(api) == {
            "weekdays": WEEK,
            "weekly_budget_minutes": 240,
            "typical_weekly_minutes": None,
            "sports": ALL_SPORTS,
            "stretching": False,
            "limitations": "Knee",
            **INTENSITY,
            **DAY_OPTIONS,
        }

    def test_the_limitations_alone_leave_the_rest_as_it_was(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "weekly_budget_minutes": 300})

        save(api, {"limitations": "Knee"})

        assert read(api) == {
            "weekdays": WEEK,
            "weekly_budget_minutes": 300,
            "typical_weekly_minutes": None,
            "sports": ALL_SPORTS,
            "stretching": False,
            "limitations": "Knee",
            **INTENSITY,
            **DAY_OPTIONS,
        }

    def test_the_typical_week_can_be_set_changed_and_removed(self, alice: User) -> None:
        api = signed_in(alice)

        assert body(save(api, {"typical_weekly_minutes": 360}))["typical_weekly_minutes"] == 360
        assert body(save(api, {"typical_weekly_minutes": 420}))["typical_weekly_minutes"] == 420
        assert body(save(api, {"typical_weekly_minutes": None}))["typical_weekly_minutes"] is None
        assert rows() == (0, 1)

    @pytest.mark.parametrize("minutes", [0, 1, 10080])
    def test_the_limits_of_the_typical_week_are_accepted(self, alice: User, minutes: int) -> None:
        response = save(signed_in(alice), {"typical_weekly_minutes": minutes})

        assert response.status_code == HTTPStatus.OK
        assert body(response)["typical_weekly_minutes"] == minutes

    def test_a_typical_week_of_zero_is_not_the_same_as_none(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"typical_weekly_minutes": 0})

        assert read(api)["typical_weekly_minutes"] == 0

    def test_the_typical_week_alone_leaves_the_rest_as_it_was(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "weekly_budget_minutes": 300, "limitations": "Knee"})

        save(api, {"typical_weekly_minutes": 360})

        assert read(api) == {
            "weekdays": WEEK,
            "weekly_budget_minutes": 300,
            "typical_weekly_minutes": 360,
            "sports": ALL_SPORTS,
            "stretching": False,
            "limitations": "Knee",
            **INTENSITY,
            **DAY_OPTIONS,
        }

    def test_the_other_settings_leave_the_typical_week_as_it_was(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"typical_weekly_minutes": 360})

        save(api, {"weekly_budget_minutes": 200, "limitations": "Knee"})

        assert read(api)["typical_weekly_minutes"] == 360

    def test_it_says_nothing_about_what_the_week_offers(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "typical_weekly_minutes": 5000})

        assert minutes_in_week(alice, MONDAY) == sum(WEEK)

    def test_the_typical_week_of_another_user_is_not_seen(self, alice: User, bob: User) -> None:
        AvailabilitySettings.objects.create(owner=bob, typical_weekly_minutes=900)

        assert read(signed_in(alice))["typical_weekly_minutes"] is None

    def test_a_refusal_keeps_the_typical_week(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"typical_weekly_minutes": 360})

        save(api, {"typical_weekly_minutes": 999999, "weekly_budget_minutes": 100})

        assert read(api)["typical_weekly_minutes"] == 360
        assert read(api)["weekly_budget_minutes"] is None

    def test_null_removes_the_budget(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekly_budget_minutes": 300})

        response = save(api, {"weekly_budget_minutes": None})

        assert body(response)["weekly_budget_minutes"] is None

    def test_a_budget_of_zero_is_a_budget(self, alice: User) -> None:
        response = save(signed_in(alice), {"weekly_budget_minutes": 0})

        assert body(response)["weekly_budget_minutes"] == 0

    def test_an_empty_request_changes_nothing_and_creates_nothing(self, alice: User) -> None:
        response = save(signed_in(alice), {})

        assert response.status_code == HTTPStatus.OK
        assert body(response) == EMPTY
        assert rows() == (0, 0)

    def test_saving_again_updates_instead_of_adding(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "weekly_budget_minutes": 300})

        save(api, {"weekdays": [30] * 7, "weekly_budget_minutes": 100})

        assert rows() == (7, 1)
        assert read(api) == {
            "weekdays": [30] * 7,
            "weekly_budget_minutes": 100,
            "typical_weekly_minutes": None,
            "sports": ALL_SPORTS,
            "stretching": False,
            "limitations": "",
            **INTENSITY,
            **DAY_OPTIONS,
        }

    def test_the_limits_themselves_are_accepted(self, alice: User) -> None:
        response = save(
            signed_in(alice),
            {
                "weekdays": [0, 1440, 0, 0, 0, 0, 0],
                "weekly_budget_minutes": 10080,
                "limitations": "x" * 1000,
            },
        )

        assert response.status_code == HTTPStatus.OK

    def test_the_limitations_are_trimmed_and_may_be_emptied(self, alice: User) -> None:
        api = signed_in(alice)

        assert body(save(api, {"limitations": "  Knee  "}))["limitations"] == "Knee"
        assert body(save(api, {"limitations": ""}))["limitations"] == ""

    def test_the_limitations_are_text_never_markup(self, alice: User) -> None:
        response = save(signed_in(alice), {"limitations": "<b>x</b> & <script>1</script>"})

        assert body(response)["limitations"] == "<b>x</b> & <script>1</script>"
        assert response["Content-Type"] == "application/json"

    def test_other_fields_are_ignored(self, alice: User, bob: User) -> None:
        api = signed_in(alice)

        save(api, {"owner": str(bob.pk), "id": 7, "weekday": 3, "limitations": "Knee"})

        assert AvailabilitySettings.objects.get().owner == alice
        assert not AvailabilitySettings.objects.filter(owner=bob).exists()

    def test_saving_one_user_leaves_the_other_alone(self, alice: User, bob: User) -> None:
        bob_api = signed_in(bob)
        save(bob_api, {"weekdays": [10] * 7, "weekly_budget_minutes": 50, "limitations": "Bob"})

        save(signed_in(alice), {"weekdays": WEEK, "weekly_budget_minutes": 300})

        assert read(bob_api) == {
            "weekdays": [10] * 7,
            "weekly_budget_minutes": 50,
            "typical_weekly_minutes": None,
            "sports": ALL_SPORTS,
            "stretching": False,
            "limitations": "Bob",
            **INTENSITY,
            **DAY_OPTIONS,
        }

    def test_a_failure_while_saving_leaves_the_weekdays_as_they_were(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK})

        def broken(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("disk full")

        monkeypatch.setattr(AvailabilitySettings, "save", broken)
        with pytest.raises(RuntimeError):
            save(api, {"weekdays": [10] * 7, "limitations": "Knee"})
        monkeypatch.undo()

        assert read(api)["weekdays"] == WEEK

    def test_the_capacity_follows_what_was_saved(self, alice: User) -> None:
        api = signed_in(alice)

        save(api, {"weekdays": WEEK})
        assert minutes_in_week(alice, MONDAY) == 450

        save(api, {"weekly_budget_minutes": 200})
        assert minutes_in_week(alice, MONDAY) == 200
        assert minutes_in_week(alice, MONDAY + timedelta(days=7)) == 200


class TestRefusals:
    @pytest.mark.parametrize(
        "weekdays",
        [[0] * 6, [0] * 8, [], "0000000", {"0": 1}, 7, None, [-1, 0, 0, 0, 0, 0, 0],
         [1441, 0, 0, 0, 0, 0, 0], ["60"] * 7, [60.5] * 7, [True] * 7, [None] * 7, [[60]] * 7],
    )  # fmt: skip
    def test_unusable_weekdays_are_refused(self, alice: User, weekdays: Any) -> None:
        response = save(signed_in(alice), {"weekdays": weekdays})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert list(body(response)) == ["weekdays"]
        assert all(isinstance(text, str) for text in body(response)["weekdays"])
        assert rows() == (0, 0)

    @pytest.mark.parametrize("budget", [-1, 10081, "300", 300.5, True, [], {}])
    def test_an_unusable_budget_is_refused(self, alice: User, budget: Any) -> None:
        response = save(signed_in(alice), {"weekly_budget_minutes": budget})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert list(body(response)) == ["weekly_budget_minutes"]
        assert rows() == (0, 0)

    @pytest.mark.parametrize("typical", [-1, 10081, "300", 300.5, True, [], {}])
    def test_an_unusable_typical_week_is_refused(self, alice: User, typical: Any) -> None:
        response = save(signed_in(alice), {"typical_weekly_minutes": typical})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert list(body(response)) == ["typical_weekly_minutes"]
        assert body(response)["typical_weekly_minutes"] == [
            "Enter whole minutes between 0 and 10080."
        ]
        assert rows() == (0, 0)

    @pytest.mark.parametrize("limitations", [5, ["Knee"], None, True, {"a": 1}, "x" * 1001])
    def test_unusable_limitations_are_refused(self, alice: User, limitations: Any) -> None:
        response = save(signed_in(alice), {"limitations": limitations})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert list(body(response)) == ["limitations"]
        assert rows() == (0, 0)

    @pytest.mark.parametrize("data", [[], "text", 5])
    def test_a_body_that_is_no_object_is_refused(self, alice: User, data: Any) -> None:
        response = save(signed_in(alice), data)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert rows() == (0, 0)

    def test_a_json_null_is_refused(self, alice: User) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            "PATCH",
            URL,
            data="null",
            content_type="application/json",
            headers={"X-CSRFToken": api._csrf_token()},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert rows() == (0, 0)

    def test_an_empty_body_is_the_same_as_no_changes(self, alice: User) -> None:
        response = signed_in(alice).call("PATCH", URL, None)

        assert response.status_code == HTTPStatus.OK
        assert body(response) == EMPTY
        assert rows() == (0, 0)

    def test_a_refusal_saves_nothing_of_the_rest(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "weekly_budget_minutes": 300, "limitations": "Knee"})

        response = save(
            api, {"weekdays": [10] * 7, "weekly_budget_minutes": 99, "limitations": "x" * 1001}
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert read(api) == {
            "weekdays": WEEK,
            "weekly_budget_minutes": 300,
            "typical_weekly_minutes": None,
            "sports": ALL_SPORTS,
            "stretching": False,
            "limitations": "Knee",
            **INTENSITY,
            **DAY_OPTIONS,
        }

    def test_every_problem_is_named_at_once(self, alice: User) -> None:
        response = save(
            signed_in(alice),
            {
                "weekdays": [0] * 3,
                "weekly_budget_minutes": -5,
                "typical_weekly_minutes": 10081,
                "limitations": "x" * 1001,
            },
        )

        assert set(body(response)) == {
            "weekdays",
            "weekly_budget_minutes",
            "typical_weekly_minutes",
            "limitations",
        }

    def test_the_messages_say_what_is_allowed(self, alice: User) -> None:
        api = signed_in(alice)

        assert body(save(api, {"weekdays": [1]}))["weekdays"] == [
            "Enter seven numbers of minutes, Monday first."
        ]
        assert body(save(api, {"weekdays": [1441] + [0] * 6}))["weekdays"] == [
            "Enter whole minutes between 0 and 1440 for every day."
        ]
        assert body(save(api, {"weekly_budget_minutes": 10081}))["weekly_budget_minutes"] == [
            "Enter whole minutes between 0 and 10080."
        ]
