from datetime import date, timedelta
from typing import Any

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from accounts.models import User
from availability.intensity import LEVEL_LIMITS, LIMIT_NAMES, IntensityLevel, Limits
from availability.models import (
    DAY_MINUTES_MAX,
    LIMITATIONS_MAX,
    NOTE_MAX,
    PERIOD_MAX_DAYS,
    SLOTS,
    SPORTS,
    WEEK_MINUTES_MAX,
    AvailabilitySettings,
    BodyPart,
    Limitation,
    LimitationStatus,
    UnavailablePeriod,
    WeekdayMinutes,
    effective_slots,
    effective_sports,
)
from planning import schema

pytestmark = pytest.mark.django_db

DAY = date(2027, 7, 12)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def period(**fields: Any) -> dict[str, Any]:
    return {"kind": "vacation", "start_date": DAY, "end_date": DAY + timedelta(days=13), **fields}


def check(model: type[Any], owner: User, **fields: Any) -> None:
    model(owner=owner, **fields).full_clean(exclude=["owner"])


def refused(model: type[Any], owner: User, field: str, **fields: Any) -> None:
    with pytest.raises(ValidationError) as raised:
        check(model, owner, **fields)
    assert field in raised.value.message_dict, raised.value.message_dict


def rejected_by_database(model: type[Any], **fields: Any) -> str:
    with pytest.raises(IntegrityError) as raised, transaction.atomic():
        model.objects.create(**fields)
    return str(raised.value)


class TestLimits:
    def test_the_limits_are_the_ones_the_documentation_names(self) -> None:
        # Written out on purpose: the other tests read the constants and would follow a change.
        assert DAY_MINUTES_MAX == 1440
        assert WEEK_MINUTES_MAX == 10080
        assert LIMITATIONS_MAX == 1000
        assert NOTE_MAX == 200
        assert PERIOD_MAX_DAYS == 366


class TestIntensity:
    def test_the_default_is_normal_without_own_limits(self, alice: User) -> None:
        settings = AvailabilitySettings.objects.create(owner=alice)

        assert settings.intensity_level == IntensityLevel.NORMAL
        assert settings.own_limits == dict.fromkeys(LIMIT_NAMES)
        assert settings.limits == LEVEL_LIMITS[IntensityLevel.NORMAL]

    def test_own_limits_replace_the_levels(self, alice: User) -> None:
        settings = AvailabilitySettings.objects.create(
            owner=alice, intensity_level="relaxed", max_hard_days=2, easy_share_percent=70
        )

        assert settings.limits == Limits(2, 115, 130, 70)

    @pytest.mark.parametrize(
        "fields",
        [
            {"intensity_level": "intensive"},
            {"max_hard_days": 0},
            {"max_hard_days": 4},
            {"progression_warning_percent": 100, "progression_error_percent": 300},
            {"easy_share_percent": 50},
            {"easy_share_percent": 100},
        ],
    )
    def test_valid_settings(self, alice: User, fields: dict[str, Any]) -> None:
        check(AvailabilitySettings, alice, **fields)

    @pytest.mark.parametrize(
        ("field", "fields"),
        [
            ("intensity_level", {"intensity_level": "brutal"}),
            ("max_hard_days", {"max_hard_days": 5}),
            ("progression_warning_percent", {"progression_warning_percent": 99}),
            ("progression_error_percent", {"progression_error_percent": 301}),
            ("easy_share_percent", {"easy_share_percent": 49}),
            # the warning must stay below the error, the level's or an own one
            ("progression_warning_percent", {"progression_warning_percent": 140}),
            (
                "progression_error_percent",
                {"progression_warning_percent": 160, "progression_error_percent": 150},
            ),
        ],
    )
    def test_unusable_settings_are_refused(
        self, alice: User, field: str, fields: dict[str, Any]
    ) -> None:
        refused(AvailabilitySettings, alice, field, **fields)

    @pytest.mark.parametrize(
        "fields",
        [
            {"intensity_level": "brutal"},
            {"max_hard_days": 5},
            {"progression_warning_percent": 99},
            {"progression_warning_percent": 201},
            {"progression_error_percent": 99},
            {"progression_error_percent": 301},
            {"easy_share_percent": 49},
            {"easy_share_percent": 101},
        ],
    )
    def test_the_database_refuses_what_is_out_of_range(
        self, alice: User, fields: dict[str, Any]
    ) -> None:
        assert "availability_" in rejected_by_database(AvailabilitySettings, owner=alice, **fields)


class TestSlots:
    def test_they_are_the_parts_of_the_day_of_the_week_plan_in_the_same_order(self) -> None:
        # availability does not import planning; this keeps the two lists in step
        assert SLOTS == tuple(slot.value for slot in schema.Slot)


class TestSports:
    def test_they_are_the_sports_of_the_week_plan_in_the_same_order(self) -> None:
        # availability does not import planning; this keeps the two lists in step
        assert SPORTS == tuple(sport.value for sport in schema.Sport)

    @pytest.mark.parametrize(
        "sports",
        [[], ["running"], ["cycling", "strength"], ["strength", "running"], list(SPORTS)],
    )
    def test_valid_choices(self, alice: User, sports: list[str]) -> None:
        check(AvailabilitySettings, alice, sports=sports)

    @pytest.mark.parametrize(
        "sports",
        [
            ["golf"],
            ["running", "running"],
            ["Running"],
            "running",
            {"running": True},
            [1],
            [None],
            [["running"]],
            ["running", "golf"],
            5,
            True,
        ],
    )
    def test_unusable_choices_are_refused(self, alice: User, sports: Any) -> None:
        refused(AvailabilitySettings, alice, "sports", sports=sports)

    def test_the_defaults_are_no_choice_and_no_stretching(self, alice: User) -> None:
        settings = AvailabilitySettings.objects.create(owner=alice)

        assert settings.sports == []
        assert settings.stretching is False
        assert settings.share_limitations_text is False

    def test_none_chosen_means_all_of_them(self, alice: User) -> None:
        settings = AvailabilitySettings.objects.create(owner=alice)

        assert settings.chosen_sports == list(SPORTS)

    def test_the_chosen_sports_come_in_the_order_of_the_list(self, alice: User) -> None:
        settings = AvailabilitySettings.objects.create(owner=alice, sports=["strength", "running"])

        assert settings.chosen_sports == ["running", "strength"]

    @pytest.mark.parametrize(
        ("stored", "expected"),
        [
            (None, list(SPORTS)),
            ([], list(SPORTS)),
            (["cycling"], ["cycling"]),
            (["strength", "cycling"], ["cycling", "strength"]),
            ("running", list(SPORTS)),
            ({"a": 1}, list(SPORTS)),
            (5, list(SPORTS)),
            (["golf"], []),
        ],
    )
    def test_the_effective_sports(self, stored: Any, expected: list[str]) -> None:
        assert effective_sports(stored) == expected


class TestSettings:
    @pytest.mark.parametrize(
        "fields",
        [
            {},
            {"weekly_budget_minutes": 0},
            {"weekly_budget_minutes": 360},
            {"weekly_budget_minutes": WEEK_MINUTES_MAX},
            {"typical_weekly_minutes": 0},
            {"typical_weekly_minutes": 420},
            {"typical_weekly_minutes": WEEK_MINUTES_MAX},
            {"limitations": "Knee: no running on consecutive days"},
            {"limitations": "x" * LIMITATIONS_MAX},
        ],
    )
    def test_valid_settings(self, alice: User, fields: dict[str, Any]) -> None:
        check(AvailabilitySettings, alice, **fields)

    def test_defaults_are_no_budget_and_no_limitations(self, alice: User) -> None:
        settings = AvailabilitySettings.objects.create(owner=alice)

        assert settings.weekly_budget_minutes is None
        assert settings.typical_weekly_minutes is None
        assert settings.limitations == ""

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("weekly_budget_minutes", WEEK_MINUTES_MAX + 1),
            ("weekly_budget_minutes", -1),
            ("typical_weekly_minutes", WEEK_MINUTES_MAX + 1),
            ("typical_weekly_minutes", -1),
            ("limitations", "x" * (LIMITATIONS_MAX + 1)),
        ],
    )
    def test_out_of_range_values_are_refused(self, alice: User, field: str, value: Any) -> None:
        refused(AvailabilitySettings, alice, field, **{field: value})

    def test_the_database_refuses_a_budget_above_a_week(self, alice: User) -> None:
        message = rejected_by_database(
            AvailabilitySettings, owner=alice, weekly_budget_minutes=WEEK_MINUTES_MAX + 1
        )

        assert "availability_budget_in_range" in message

    def test_the_database_refuses_a_typical_week_above_a_week(self, alice: User) -> None:
        message = rejected_by_database(
            AvailabilitySettings, owner=alice, typical_weekly_minutes=WEEK_MINUTES_MAX + 1
        )

        assert "availability_typical_week_in_range" in message

    def test_both_numbers_are_named_when_both_are_too_big(self, alice: User) -> None:
        settings = AvailabilitySettings(
            owner=alice,
            weekly_budget_minutes=WEEK_MINUTES_MAX + 1,
            typical_weekly_minutes=WEEK_MINUTES_MAX + 1,
        )

        with pytest.raises(ValidationError) as raised:
            settings.full_clean(exclude=["owner"])

        assert {"weekly_budget_minutes", "typical_weekly_minutes"} <= set(raised.value.message_dict)

    def test_a_user_has_one_settings_row(self, alice: User, bob: User) -> None:
        AvailabilitySettings.objects.create(owner=alice)
        AvailabilitySettings.objects.create(owner=bob)

        message = rejected_by_database(AvailabilitySettings, owner=alice)

        assert "availability_one_settings_per_owner" in message

    def test_the_text_does_not_show_the_limitations(self, alice: User) -> None:
        settings = AvailabilitySettings.objects.create(owner=alice, limitations="secret knee")

        assert "secret" not in str(settings)
        assert str(alice.pk) in str(settings)


class TestWeekdays:
    @pytest.mark.parametrize("weekday", range(7))
    def test_every_weekday_is_valid(self, alice: User, weekday: int) -> None:
        check(WeekdayMinutes, alice, weekday=weekday, minutes=60)

    @pytest.mark.parametrize("minutes", [0, 1, 90, DAY_MINUTES_MAX])
    def test_valid_minutes(self, alice: User, minutes: int) -> None:
        check(WeekdayMinutes, alice, weekday=0, minutes=minutes)

    @pytest.mark.parametrize("weekday", [-1, 7, 12])
    def test_a_day_that_is_no_weekday_is_refused(self, alice: User, weekday: int) -> None:
        refused(WeekdayMinutes, alice, "weekday", weekday=weekday, minutes=60)

    @pytest.mark.parametrize("minutes", [-1, DAY_MINUTES_MAX + 1, 5000])
    def test_more_than_a_day_is_refused(self, alice: User, minutes: int) -> None:
        refused(WeekdayMinutes, alice, "minutes", weekday=0, minutes=minutes)

    def test_the_database_refuses_more_than_a_day(self, alice: User) -> None:
        message = rejected_by_database(
            WeekdayMinutes, owner=alice, weekday=0, minutes=DAY_MINUTES_MAX + 1
        )

        assert "availability_minutes_in_range" in message

    def test_the_database_refuses_a_day_that_is_no_weekday(self, alice: User) -> None:
        message = rejected_by_database(WeekdayMinutes, owner=alice, weekday=7, minutes=60)

        assert "availability_weekday_in_range" in message

    def test_a_weekday_is_stored_once_per_user(self, alice: User, bob: User) -> None:
        WeekdayMinutes.objects.create(owner=alice, weekday=2, minutes=60)
        WeekdayMinutes.objects.create(owner=bob, weekday=2, minutes=30)

        message = rejected_by_database(WeekdayMinutes, owner=alice, weekday=2, minutes=90)

        assert "availability_one_per_day" in message

    def test_minutes_default_to_none(self, alice: User) -> None:
        assert WeekdayMinutes.objects.create(owner=alice, weekday=0).minutes == 0

    def test_the_defaults_are_two_sessions_and_every_part_of_the_day(self, alice: User) -> None:
        row = WeekdayMinutes.objects.create(owner=alice, weekday=0)

        assert row.double_allowed is True
        assert row.slots == ["morning", "afternoon", "evening"]
        assert row.open_slots == list(SLOTS)

    def test_the_default_list_is_not_shared_between_rows(self, alice: User) -> None:
        first = WeekdayMinutes(owner=alice, weekday=0)
        second = WeekdayMinutes(owner=alice, weekday=1)

        first.slots.append("dawn")

        assert second.slots == list(SLOTS)

    @pytest.mark.parametrize("double_allowed", [True, False])
    def test_a_weekday_can_forbid_or_allow_two_sessions(
        self, alice: User, double_allowed: bool
    ) -> None:
        check(WeekdayMinutes, alice, weekday=0, minutes=60, double_allowed=double_allowed)

    @pytest.mark.parametrize(
        "slots",
        [
            ["morning"],
            ["evening"],
            ["morning", "evening"],
            ["evening", "morning"],
            list(SLOTS),
        ],
    )
    def test_valid_time_windows(self, alice: User, slots: list[str]) -> None:
        check(WeekdayMinutes, alice, weekday=0, minutes=60, slots=slots)

    @pytest.mark.parametrize(
        "slots",
        [
            [],
            ["noon"],
            ["Morning"],
            ["morning", "morning"],
            ["morning", "noon"],
            "morning",
            {"morning": True},
            [1],
            [None],
            [["morning"]],
            None,
            5,
            True,
        ],
    )
    def test_unusable_time_windows_are_refused(self, alice: User, slots: Any) -> None:
        refused(WeekdayMinutes, alice, "slots", weekday=0, minutes=60, slots=slots)

    @pytest.mark.parametrize(
        ("stored", "expected"),
        [
            (None, list(SLOTS)),
            ([], list(SLOTS)),
            (["evening"], ["evening"]),
            (["evening", "morning"], ["morning", "evening"]),
            ("morning", list(SLOTS)),
            ({"a": 1}, list(SLOTS)),
            (5, list(SLOTS)),
            (["noon"], []),
        ],
    )
    def test_the_effective_slots(self, stored: Any, expected: list[str]) -> None:
        assert effective_slots(stored) == expected

    def test_the_open_slots_come_in_the_order_of_the_day(self, alice: User) -> None:
        row = WeekdayMinutes.objects.create(owner=alice, weekday=0, slots=["evening", "morning"])

        assert row.open_slots == ["morning", "evening"]

    def test_the_text_names_the_day(self, alice: User) -> None:
        text = str(WeekdayMinutes(owner=alice, weekday=4, minutes=60))

        assert text.startswith("Friday")
        assert str(alice.pk) in text


class TestLimitations:
    def test_every_body_part_is_valid(self, alice: User) -> None:
        for part in BodyPart:
            check(Limitation, alice, body_part=part.value)

    def test_the_body_parts_are_the_agreed_ones(self) -> None:
        assert BodyPart.values == [
            "foot",
            "ankle",
            "achilles",
            "calf",
            "shin",
            "knee",
            "thigh",
            "hip",
            "back",
            "shoulder",
            "other",
        ]

    @pytest.mark.parametrize("part", ["", "elbow", "Knee", "KNEE", "knee "])
    def test_an_unknown_body_part_is_refused(self, alice: User, part: str) -> None:
        refused(Limitation, alice, "body_part", body_part=part)

    @pytest.mark.parametrize("status", ["current", "healed"])
    def test_both_statuses_are_valid(self, alice: User, status: str) -> None:
        check(Limitation, alice, body_part="knee", status=status)

    @pytest.mark.parametrize("status", ["", "chronic", "Current"])
    def test_an_unknown_status_is_refused(self, alice: User, status: str) -> None:
        refused(Limitation, alice, "status", body_part="knee", status=status)

    @pytest.mark.parametrize("sports", [[], ["running"], ["strength", "running"], list(SPORTS)])
    def test_valid_sports(self, alice: User, sports: list[str]) -> None:
        check(Limitation, alice, body_part="knee", sports=sports)

    @pytest.mark.parametrize(
        "sports",
        [
            ["golf"],
            ["running", "running"],
            ["Running"],
            "running",
            {"running": True},
            [1],
            [None],
            [["running"]],
            None,
            5,
            True,
        ],
    )
    def test_unusable_sports_are_refused(self, alice: User, sports: Any) -> None:
        refused(Limitation, alice, "sports", body_part="knee", sports=sports)

    def test_the_defaults_are_current_and_no_particular_sport(self, alice: User) -> None:
        entry = Limitation.objects.create(owner=alice, body_part="knee")

        assert entry.status == LimitationStatus.CURRENT
        assert entry.sports == []
        assert entry.affected_sports == []

    def test_the_affected_sports_come_in_the_order_of_the_sports(self, alice: User) -> None:
        entry = Limitation.objects.create(
            owner=alice, body_part="knee", sports=["strength", "running"]
        )

        assert entry.affected_sports == ["running", "strength"]

    def test_the_id_is_time_ordered_so_that_the_newest_has_the_highest(self, alice: User) -> None:
        first = Limitation.objects.create(owner=alice, body_part="knee")
        second = Limitation.objects.create(owner=alice, body_part="back")

        assert first.pk < second.pk

    def test_the_database_refuses_an_unknown_body_part(self, alice: User) -> None:
        message = rejected_by_database(Limitation, owner=alice, body_part="elbow")

        assert "availability_limitation_body_part_known" in message

    def test_the_database_refuses_an_unknown_status(self, alice: User) -> None:
        message = rejected_by_database(Limitation, owner=alice, body_part="knee", status="x")

        assert "availability_limitation_status_known" in message

    def test_the_text_names_the_body_part_and_the_user_only(self, alice: User) -> None:
        text = str(Limitation(owner=alice, body_part="achilles", sports=["running"]))

        assert text == f"achilles limitation of user {alice.pk}"

    def test_an_entry_belongs_to_its_user(self, alice: User, bob: User) -> None:
        mine = Limitation.objects.create(owner=alice, body_part="knee")
        Limitation.objects.create(owner=bob, body_part="back")

        assert list(Limitation.objects.for_user(alice)) == [mine]
        assert not Limitation.objects.for_user(AnonymousUser()).exists()

    def test_deleting_the_user_deletes_the_entries(self, alice: User) -> None:
        Limitation.objects.create(owner=alice, body_part="knee")

        alice.delete()

        assert Limitation.objects.count() == 0


class TestPeriods:
    @pytest.mark.parametrize("kind", ["vacation", "illness", "other"])
    def test_every_kind_is_valid(self, alice: User, kind: str) -> None:
        check(UnavailablePeriod, alice, **period(kind=kind))

    def test_a_single_day_is_a_period(self, alice: User) -> None:
        check(UnavailablePeriod, alice, **period(end_date=DAY))

    def test_a_note_is_optional_and_limited(self, alice: User) -> None:
        check(UnavailablePeriod, alice, **period(note=""))
        check(UnavailablePeriod, alice, **period(note="x" * NOTE_MAX))
        refused(UnavailablePeriod, alice, "note", **period(note="x" * (NOTE_MAX + 1)))

    @pytest.mark.parametrize("kind", ["", "holiday", "VACATION"])
    def test_an_unknown_kind_is_refused(self, alice: User, kind: str) -> None:
        refused(UnavailablePeriod, alice, "kind", **period(kind=kind))

    def test_the_end_cannot_be_before_the_start(self, alice: User) -> None:
        refused(UnavailablePeriod, alice, "end_date", **period(end_date=DAY - timedelta(days=1)))

    def test_a_period_may_last_366_days_but_not_more(self, alice: User) -> None:
        check(
            UnavailablePeriod,
            alice,
            **period(end_date=DAY + timedelta(days=PERIOD_MAX_DAYS - 1)),
        )
        refused(
            UnavailablePeriod,
            alice,
            "end_date",
            **period(end_date=DAY + timedelta(days=PERIOD_MAX_DAYS)),
        )

    def test_dates_are_required(self, alice: User) -> None:
        refused(UnavailablePeriod, alice, "start_date", **period(start_date=None))
        refused(UnavailablePeriod, alice, "end_date", **period(end_date=None))

    def test_the_database_refuses_an_end_before_the_start(self, alice: User) -> None:
        message = rejected_by_database(
            UnavailablePeriod,
            owner=alice,
            **period(end_date=DAY - timedelta(days=1)),
        )

        assert "availability_period_ends_late" in message

    def test_the_database_enforces_the_longest_period_to_the_day(self, alice: User) -> None:
        UnavailablePeriod.objects.create(
            owner=alice, **period(end_date=DAY + timedelta(days=PERIOD_MAX_DAYS - 1))
        )

        message = rejected_by_database(
            UnavailablePeriod,
            owner=alice,
            **period(end_date=DAY + timedelta(days=PERIOD_MAX_DAYS)),
        )

        assert "availability_period_not_too_long" in message

    def test_periods_may_overlap(self, alice: User) -> None:
        UnavailablePeriod.objects.create(owner=alice, **period())
        UnavailablePeriod.objects.create(owner=alice, **period(kind="illness", end_date=DAY))

        assert UnavailablePeriod.objects.for_user(alice).count() == 2

    def test_the_id_is_not_a_counter(self, alice: User) -> None:
        first = UnavailablePeriod.objects.create(owner=alice, **period())
        second = UnavailablePeriod.objects.create(owner=alice, **period())

        assert first.pk != second.pk
        assert first.pk.version == 7

    def test_the_text_does_not_show_the_note(self, alice: User) -> None:
        text = str(UnavailablePeriod(owner=alice, **period(note="secret diagnosis")))

        assert "secret" not in text
        assert "vacation" in text
        assert str(alice.pk) in text


class TestOwnership:
    def test_for_user_shows_only_the_own_rows(self, alice: User, bob: User) -> None:
        mine = UnavailablePeriod.objects.create(owner=alice, **period())
        UnavailablePeriod.objects.create(owner=bob, **period())
        my_day = WeekdayMinutes.objects.create(owner=alice, weekday=0, minutes=60)
        WeekdayMinutes.objects.create(owner=bob, weekday=0, minutes=30)
        my_settings = AvailabilitySettings.objects.create(owner=alice)
        AvailabilitySettings.objects.create(owner=bob)

        assert list(UnavailablePeriod.objects.for_user(alice)) == [mine]
        assert list(WeekdayMinutes.objects.for_user(alice)) == [my_day]
        assert list(AvailabilitySettings.objects.for_user(alice)) == [my_settings]

    def test_an_anonymous_user_owns_nothing(self, alice: User) -> None:
        UnavailablePeriod.objects.create(owner=alice, **period())
        WeekdayMinutes.objects.create(owner=alice, weekday=0, minutes=60)
        AvailabilitySettings.objects.create(owner=alice)

        anonymous = AnonymousUser()

        assert not UnavailablePeriod.objects.for_user(anonymous).exists()
        assert not WeekdayMinutes.objects.for_user(anonymous).exists()
        assert not AvailabilitySettings.objects.for_user(anonymous).exists()

    def test_deleting_a_user_deletes_their_rows(self, alice: User, bob: User) -> None:
        UnavailablePeriod.objects.create(owner=alice, **period())
        WeekdayMinutes.objects.create(owner=alice, weekday=0, minutes=60)
        AvailabilitySettings.objects.create(owner=alice)
        UnavailablePeriod.objects.create(owner=bob, **period())

        alice.delete()

        assert UnavailablePeriod.objects.count() == 1
        assert WeekdayMinutes.objects.count() == 0
        assert AvailabilitySettings.objects.count() == 0
