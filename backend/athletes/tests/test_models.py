import math
import time
from datetime import date, timedelta
from typing import Any

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from accounts.models import User
from athletes import models
from athletes.models import (
    BEST_TIME_FROM,
    BIRTH_YEAR_MIN,
    MIN_AGE,
    RESTING_HR_MAX,
    RESTING_HR_MIN,
    RULES,
    TRAINING_YEARS_MAX,
    WEIGHT_MAX,
    WEIGHT_MIN,
    YEARS_SPORTS,
    AthleteProfile,
    BestTime,
    Equipment,
    ThresholdValue,
)

pytestmark = pytest.mark.django_db

Sport = ThresholdValue.Sport
Metric = ThresholdValue.Metric
Source = ThresholdValue.Source


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def threshold(
    owner: User,
    *,
    sport: str = Sport.RIDE,
    metric: str = Metric.FTP,
    source: str = Source.MANUAL,
    value: float = 250,
    **fields: Any,
) -> ThresholdValue:
    return ThresholdValue.objects.create(
        owner=owner, sport=sport, metric=metric, source=source, value=value, **fields
    )


class TestProfile:
    def test_a_user_has_one_profile(self, alice: User) -> None:
        AthleteProfile.objects.create(owner=alice)

        with pytest.raises(IntegrityError), transaction.atomic():
            AthleteProfile.objects.create(owner=alice)

        assert AthleteProfile.objects.count() == 1

    def test_every_user_can_have_their_own(self, alice: User, bob: User) -> None:
        AthleteProfile.objects.create(owner=alice)
        AthleteProfile.objects.create(owner=bob)

        assert AthleteProfile.objects.count() == 2

    def test_a_new_profile_is_empty(self, alice: User) -> None:
        profile = AthleteProfile.objects.create(owner=alice)

        assert profile.timezone == ""
        assert profile.intervals_synced_at is None
        profile.full_clean(exclude=["owner"])

    def test_for_user_shows_only_the_own_profile(self, alice: User, bob: User) -> None:
        mine = AthleteProfile.objects.create(owner=alice)
        AthleteProfile.objects.create(owner=bob)

        assert list(AthleteProfile.objects.for_user(alice)) == [mine]

    def test_anonymous_users_see_nothing(self, alice: User) -> None:
        AthleteProfile.objects.create(owner=alice)

        assert not AthleteProfile.objects.for_user(AnonymousUser()).exists()

    def test_deleting_the_user_deletes_the_profile(self, alice: User, bob: User) -> None:
        AthleteProfile.objects.create(owner=alice)
        theirs = AthleteProfile.objects.create(owner=bob)

        alice.delete()

        assert list(AthleteProfile.objects.all()) == [theirs]

    @pytest.mark.parametrize("name", ["Europe/Berlin", "UTC", "America/Argentina/Buenos_Aires", ""])
    def test_valid_time_zones_are_accepted(self, alice: User, name: str) -> None:
        AthleteProfile(owner=alice, timezone=name).full_clean(exclude=["owner"])

    @pytest.mark.parametrize(
        "name",
        [
            "Mars/Olympus_Mons",
            "europe/berlin",  # the database is case sensitive
            " UTC",
            "UTC\n",
            "Europe",  # a directory of the database, not a zone
            "../../etc/passwd",
            "/etc/passwd",
            "Europe/Berlin/../Paris",
            "localtime",
            "posixrules",
            "posix/Europe/Berlin",
            "right/Europe/Berlin",
            "Factory",
            "+01:00",
            "CET-1",
            "x" * 65,
            "\x00",
        ],
    )
    def test_anything_else_is_refused(self, alice: User, name: str) -> None:
        profile = AthleteProfile(owner=alice, timezone=name)

        with pytest.raises(ValidationError) as raised:
            profile.full_clean(exclude=["owner"])

        assert "timezone" in raised.value.message_dict

    def test_the_check_does_not_depend_on_the_operating_system(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A host whose zone directory holds extra names (``localtime``, ``posix/…``) must not
        make them valid, and one that lacks the database must not make real zones invalid."""
        import zoneinfo

        monkeypatch.setattr(
            zoneinfo,
            "available_timezones",
            lambda: {"localtime", "posixrules", "posix/Europe/Berlin", "Mars/Base"},
        )
        models._time_zones.cache_clear()
        try:
            for name in ("localtime", "posixrules", "posix/Europe/Berlin", "Mars/Base"):
                with pytest.raises(ValidationError):
                    AthleteProfile(owner=alice, timezone=name).full_clean(exclude=["owner"])
            AthleteProfile(owner=alice, timezone="Europe/Berlin").full_clean(exclude=["owner"])
        finally:
            models._time_zones.cache_clear()

    def test_every_name_of_the_package_is_accepted_except_the_placeholder(self) -> None:
        from importlib import resources

        names = resources.files("tzdata").joinpath("zones").read_text().split()
        accepted = [name for name in names if name in models._time_zones()]

        assert set(names) - set(accepted) == {"Factory"}
        assert len(accepted) > 500

    def test_the_error_says_what_to_enter(self, alice: User) -> None:
        with pytest.raises(ValidationError) as raised:
            AthleteProfile(owner=alice, timezone="Nowhere").full_clean(exclude=["owner"])

        assert "Europe/Berlin" in raised.value.message_dict["timezone"][0]


def refused(owner: User, field: str, **fields: Any) -> None:
    with pytest.raises(ValidationError) as raised:
        AthleteProfile(owner=owner, **fields).full_clean(exclude=["owner"])
    assert field in raised.value.message_dict, raised.value.message_dict


def rejected_by_database(owner: User, **fields: Any) -> str:
    with pytest.raises(IntegrityError) as raised, transaction.atomic():
        AthleteProfile.objects.create(owner=owner, **fields)
    return str(raised.value)


class TestBodyAndTrainingData:
    LATEST = date.today().year - MIN_AGE

    def test_a_new_profile_has_none_of_it(self, alice: User) -> None:
        profile = AthleteProfile.objects.create(owner=alice)

        assert profile.birth_year is None
        assert profile.weight_kg is None
        assert profile.resting_hr is None
        assert [getattr(profile, f"years_{sport}") for sport in YEARS_SPORTS] == [None] * 4
        assert (profile.sex, profile.strength_experience) == ("", "")
        assert profile.strength_equipment == []
        assert profile.equipment == []

    def test_a_full_set_is_valid(self, alice: User) -> None:
        AthleteProfile(
            owner=alice,
            birth_year=1985,
            sex="female",
            weight_kg=61.5,
            resting_hr=48,
            years_running=12,
            years_cycling=3,
            years_swimming=0,
            years_strength=1,
            strength_experience="beginner",
            strength_equipment=["gym", "dumbbells"],
        ).full_clean(exclude=["owner"])

    @pytest.mark.parametrize("year", [BIRTH_YEAR_MIN, 1985, LATEST])
    def test_plausible_birth_years_are_valid(self, alice: User, year: int) -> None:
        AthleteProfile(owner=alice, birth_year=year).full_clean(exclude=["owner"])

    @pytest.mark.parametrize("year", [BIRTH_YEAR_MIN - 1, 0, LATEST + 1, 3000])
    def test_other_birth_years_are_refused(self, alice: User, year: int) -> None:
        refused(alice, "birth_year", birth_year=year)

    @pytest.mark.parametrize("sex", ["female", "male", "other", ""])
    def test_the_known_values_for_sex_are_valid(self, alice: User, sex: str) -> None:
        AthleteProfile(owner=alice, sex=sex).full_clean(exclude=["owner"])

    @pytest.mark.parametrize("sex", ["f", "Female", "unknown", " male"])
    def test_other_values_for_sex_are_refused(self, alice: User, sex: str) -> None:
        refused(alice, "sex", sex=sex)

    @pytest.mark.parametrize("weight", [WEIGHT_MIN, 61.5, WEIGHT_MAX])
    def test_plausible_weights_are_valid(self, alice: User, weight: float) -> None:
        AthleteProfile(owner=alice, weight_kg=weight).full_clean(exclude=["owner"])

    @pytest.mark.parametrize(
        "weight", [0, WEIGHT_MIN - 0.1, WEIGHT_MAX + 0.1, -60, math.nan, math.inf, True]
    )
    def test_other_weights_are_refused(self, alice: User, weight: Any) -> None:
        refused(alice, "weight_kg", weight_kg=weight)

    @pytest.mark.parametrize("rate", [RESTING_HR_MIN, 48, RESTING_HR_MAX])
    def test_plausible_resting_heart_rates_are_valid(self, alice: User, rate: int) -> None:
        AthleteProfile(owner=alice, resting_hr=rate).full_clean(exclude=["owner"])

    @pytest.mark.parametrize("rate", [0, RESTING_HR_MIN - 1, RESTING_HR_MAX + 1, 250])
    def test_other_resting_heart_rates_are_refused(self, alice: User, rate: int) -> None:
        refused(alice, "resting_hr", resting_hr=rate)

    @pytest.mark.parametrize("sport", YEARS_SPORTS)
    @pytest.mark.parametrize("years", [0, 5, TRAINING_YEARS_MAX])
    def test_years_inside_the_range_are_valid(self, alice: User, sport: str, years: int) -> None:
        AthleteProfile(owner=alice, **{f"years_{sport}": years}).full_clean(exclude=["owner"])

    @pytest.mark.parametrize("sport", YEARS_SPORTS)
    def test_years_above_the_range_are_refused(self, alice: User, sport: str) -> None:
        refused(alice, f"years_{sport}", **{f"years_{sport}": TRAINING_YEARS_MAX + 1})

    @pytest.mark.parametrize("value", ["beginner", "advanced", ""])
    def test_the_known_strength_experience_is_valid(self, alice: User, value: str) -> None:
        AthleteProfile(owner=alice, strength_experience=value).full_clean(exclude=["owner"])

    @pytest.mark.parametrize("value", ["expert", "Beginner", "none"])
    def test_other_strength_experience_is_refused(self, alice: User, value: str) -> None:
        refused(alice, "strength_experience", strength_experience=value)

    @pytest.mark.parametrize(
        "equipment", [[], ["gym"], ["dumbbells", "home"], ["gym", "home", "dumbbells"]]
    )
    def test_the_known_equipment_is_valid(self, alice: User, equipment: list[str]) -> None:
        AthleteProfile(owner=alice, strength_equipment=equipment).full_clean(exclude=["owner"])

    @pytest.mark.parametrize(
        "equipment",
        [["barbell"], ["gym", "gym"], ["Gym"], "gym", {"gym": True}, [1], [None], None, 5],
    )
    def test_other_equipment_is_refused(self, alice: User, equipment: Any) -> None:
        refused(alice, "strength_equipment", strength_equipment=equipment)

    def test_the_equipment_comes_in_the_order_of_the_choices(self, alice: User) -> None:
        profile = AthleteProfile.objects.create(
            owner=alice, strength_equipment=["dumbbells", "gym"]
        )

        assert profile.equipment == [Equipment.GYM, Equipment.DUMBBELLS]

    def test_unusable_stored_equipment_counts_as_none(self, alice: User) -> None:
        assert AthleteProfile(owner=alice, strength_equipment="gym").equipment == []

    @pytest.mark.parametrize(
        ("fields", "name"),
        [
            ({"birth_year": 1899}, "athletes_birth_year_plausible"),
            ({"sex": "x"}, "athletes_sex_known"),
            ({"weight_kg": 24.9}, "athletes_weight_in_range"),
            ({"weight_kg": 300.1}, "athletes_weight_in_range"),
            ({"resting_hr": 24}, "athletes_resting_hr_in_range"),
            ({"resting_hr": 121}, "athletes_resting_hr_in_range"),
            ({"years_running": 81}, "athletes_years_running_in_range"),
            ({"years_cycling": 81}, "athletes_years_cycling_in_range"),
            ({"years_swimming": 81}, "athletes_years_swimming_in_range"),
            ({"years_strength": 81}, "athletes_years_strength_in_range"),
            ({"strength_experience": "x"}, "athletes_strength_experience_known"),
        ],
    )
    def test_the_database_refuses_what_is_out_of_range(
        self, alice: User, fields: dict[str, Any], name: str
    ) -> None:
        assert name in rejected_by_database(alice, **fields)


class TestOwnership:
    def test_the_same_source_holds_one_value_per_threshold(self, alice: User) -> None:
        threshold(alice)

        with pytest.raises(IntegrityError), transaction.atomic():
            threshold(alice, value=260)

        assert ThresholdValue.objects.count() == 1

    def test_every_source_may_hold_its_own_value(self, alice: User) -> None:
        for source in Source.values:
            threshold(alice, source=source)

        assert ThresholdValue.objects.count() == 3

    def test_other_sports_and_metrics_are_other_thresholds(self, alice: User) -> None:
        threshold(alice, sport=Sport.RIDE, metric=Metric.LTHR, value=165)
        threshold(alice, sport=Sport.RUN, metric=Metric.LTHR, value=170)
        threshold(alice, sport=Sport.RIDE, metric=Metric.MAX_HR, value=190)

        assert ThresholdValue.objects.count() == 3

    def test_another_user_may_hold_the_same_threshold(self, alice: User, bob: User) -> None:
        threshold(alice)
        threshold(bob)

        assert ThresholdValue.objects.count() == 2

    def test_for_user_shows_only_the_own_values(self, alice: User, bob: User) -> None:
        mine = threshold(alice)
        threshold(bob)

        assert list(ThresholdValue.objects.for_user(alice)) == [mine]

    def test_anonymous_users_see_nothing(self, alice: User) -> None:
        threshold(alice)

        assert not ThresholdValue.objects.for_user(AnonymousUser()).exists()

    def test_deleting_the_user_deletes_the_values_and_only_theirs(
        self, alice: User, bob: User
    ) -> None:
        threshold(alice)
        theirs = threshold(bob)

        alice.delete()

        assert list(ThresholdValue.objects.all()) == [theirs]


class TestValidation:
    def clean(self, owner: User, **fields: Any) -> None:
        values: dict[str, Any] = {
            "sport": Sport.RIDE,
            "metric": Metric.FTP,
            "source": Source.MANUAL,
            "value": 250,
        } | fields
        ThresholdValue(owner=owner, **values).full_clean(exclude=["owner"])

    def test_the_rules_are_exactly_these(self) -> None:
        """Written out on purpose: the range tests below read their bounds from ``RULES``."""
        assert {key: (r.minimum, r.maximum, r.unit) for key, r in RULES.items()} == {
            ("ride", "ftp"): (30, 2000, "W"),
            ("ride", "lthr"): (30, 250, "bpm"),
            ("ride", "max_hr"): (30, 250, "bpm"),
            ("run", "threshold_pace"): (120, 1200, "s/km"),
            ("run", "lthr"): (30, 250, "bpm"),
            ("run", "max_hr"): (30, 250, "bpm"),
        }

    @pytest.mark.parametrize(
        ("sport", "metric", "value"),
        [
            (Sport.RIDE, Metric.FTP, 250),
            (Sport.RIDE, Metric.LTHR, 165.5),
            (Sport.RIDE, Metric.MAX_HR, 190),
            (Sport.RUN, Metric.THRESHOLD_PACE, 300),
            (Sport.RUN, Metric.LTHR, 170),
            (Sport.RUN, Metric.MAX_HR, 188),
        ],
    )
    def test_typical_values_are_accepted(
        self, alice: User, sport: str, metric: str, value: float
    ) -> None:
        self.clean(alice, sport=sport, metric=metric, value=value)

    @pytest.mark.parametrize(
        ("sport", "metric"),
        [
            (Sport.RUN, Metric.FTP),
            (Sport.RIDE, Metric.THRESHOLD_PACE),
        ],
    )
    def test_a_metric_that_does_not_fit_the_sport_is_refused(
        self, alice: User, sport: str, metric: str
    ) -> None:
        with pytest.raises(ValidationError) as raised:
            self.clean(alice, sport=sport, metric=metric, value=250)

        assert "metric" in raised.value.message_dict

    @pytest.mark.parametrize(
        ("sport", "metric", "minimum", "maximum"),
        [(sport, metric, rule.minimum, rule.maximum) for (sport, metric), rule in RULES.items()],
    )
    def test_the_ends_of_the_range_are_accepted_and_just_beyond_is_not(
        self, alice: User, sport: str, metric: str, minimum: float, maximum: float
    ) -> None:
        self.clean(alice, sport=sport, metric=metric, value=minimum)
        self.clean(alice, sport=sport, metric=metric, value=maximum)
        for value in (minimum - 0.1, maximum + 0.1, 0, -5):
            with pytest.raises(ValidationError) as raised:
                self.clean(alice, sport=sport, metric=metric, value=value)
            assert "value" in raised.value.message_dict

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_values_that_are_no_numbers_are_refused(self, alice: User, value: float) -> None:
        with pytest.raises(ValidationError) as raised:
            self.clean(alice, value=value)

        assert raised.value.message_dict["value"] == ["Enter a number."]

    def test_the_error_names_the_range_and_the_unit(self, alice: User) -> None:
        with pytest.raises(ValidationError) as raised:
            self.clean(alice, value=5000)

        assert raised.value.message_dict["value"] == ["Enter a value between 30 and 2000 W."]

    @pytest.mark.parametrize(
        "field", [("sport", "swim"), ("metric", "vo2max"), ("source", "coach")]
    )
    def test_unknown_choices_are_refused(self, alice: User, field: tuple[str, str]) -> None:
        name, value = field

        with pytest.raises(ValidationError) as raised:
            self.clean(alice, **{name: value})

        assert name in raised.value.message_dict

    def test_the_basis_is_optional_and_short(self, alice: User) -> None:
        self.clean(alice, basis="")
        self.clean(alice, basis="x" * 200)
        with pytest.raises(ValidationError):
            self.clean(alice, basis="x" * 201)


class TestDatabase:
    """The rules must hold even where ``clean()`` is not called."""

    @pytest.mark.parametrize("value", [0, -1, -250.5])
    def test_a_value_that_is_not_positive_is_refused(self, alice: User, value: float) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            threshold(alice, value=value)

        assert not ThresholdValue.objects.exists()

    @pytest.mark.parametrize(
        ("sport", "metric"), [(Sport.RUN, Metric.FTP), (Sport.RIDE, Metric.THRESHOLD_PACE)]
    )
    def test_a_metric_that_does_not_fit_the_sport_is_refused(
        self, alice: User, sport: str, metric: str
    ) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            threshold(alice, sport=sport, metric=metric)

        assert not ThresholdValue.objects.exists()


class TestValues:
    def test_updated_at_moves_when_the_value_is_saved_again(self, alice: User) -> None:
        stored = threshold(alice)
        first = stored.updated_at

        time.sleep(0.01)
        stored.value = 260
        stored.save()
        stored.refresh_from_db()

        assert stored.updated_at > first

    def test_the_basis_is_kept(self, alice: User) -> None:
        stored = threshold(alice, source=Source.ESTIMATED, basis="Highest value in two activities")

        stored.refresh_from_db()

        assert stored.basis == "Highest value in two activities"

    def test_text_does_not_contain_the_value(self, alice: User) -> None:
        stored = threshold(alice, value=263.5)

        assert "263" not in str(stored)
        assert str(alice.pk) in str(stored)


class TestBestTimes:
    RACE_DAY = date.today() - timedelta(days=30)

    def best(self, **fields: Any) -> dict[str, Any]:
        return {"distance": "5k", "seconds": 20 * 60, "date": self.RACE_DAY, **fields}

    def check(self, owner: User, **fields: Any) -> None:
        BestTime(owner=owner, **self.best(**fields)).full_clean(exclude=["owner"])

    def refused(self, owner: User, field: str, **fields: Any) -> None:
        with pytest.raises(ValidationError) as raised:
            self.check(owner, **fields)
        assert field in raised.value.message_dict, raised.value.message_dict

    @pytest.mark.parametrize(
        ("distance", "seconds"),
        [("5k", 1200), ("10k", 2500), ("half_marathon", 5700), ("marathon", 12000)],
    )
    def test_a_plausible_time_over_every_distance_is_valid(
        self, alice: User, distance: str, seconds: int
    ) -> None:
        self.check(alice, distance=distance, seconds=seconds)

    @pytest.mark.parametrize("distance", ["", "3k", "5K", "ultra", "5k "])
    def test_an_unknown_distance_is_refused(self, alice: User, distance: str) -> None:
        self.refused(alice, "distance", distance=distance)

    @pytest.mark.parametrize("seconds", [1, 300, 5 * 3600, 100000])
    def test_a_time_that_no_runner_has_is_refused(self, alice: User, seconds: int) -> None:
        # 5 km in 5 minutes is a typo, and so is 5 km in more than five hours
        self.refused(alice, "seconds", seconds=seconds)

    def test_the_message_asks_to_check_the_time(self, alice: User) -> None:
        with pytest.raises(ValidationError) as raised:
            self.check(alice, seconds=300)

        assert raised.value.message_dict["seconds"] == [
            "That time is not plausible for this distance. Check it."
        ]

    def test_today_is_valid_and_tomorrow_is_not(self, alice: User) -> None:
        self.check(alice, date=date.today())
        self.refused(alice, "date", date=date.today() + timedelta(days=1))

    def test_the_first_day_is_valid_and_the_day_before_is_not(self, alice: User) -> None:
        self.check(alice, date=BEST_TIME_FROM)
        self.refused(alice, "date", date=BEST_TIME_FROM - timedelta(days=1))

    def test_one_time_per_distance_and_user(self, alice: User, bob: User) -> None:
        BestTime.objects.create(owner=alice, **self.best())
        BestTime.objects.create(owner=alice, **self.best(distance="10k", seconds=2500))
        BestTime.objects.create(owner=bob, **self.best())

        with pytest.raises(IntegrityError), transaction.atomic():
            BestTime.objects.create(owner=alice, **self.best(seconds=1100))

        assert BestTime.objects.count() == 3

    @pytest.mark.parametrize(
        ("fields", "name"),
        [
            ({"distance": "3k"}, "athletes_best_time_distance_known"),
            ({"date": date(1899, 12, 31)}, "athletes_best_time_date_plausible"),
        ],
    )
    def test_the_database_refuses_what_is_out_of_range(
        self, alice: User, fields: dict[str, Any], name: str
    ) -> None:
        with pytest.raises(IntegrityError) as raised, transaction.atomic():
            BestTime.objects.create(owner=alice, **self.best(**fields))

        assert name in str(raised.value)

    def test_the_database_refuses_no_time(self, alice: User) -> None:
        with pytest.raises(IntegrityError) as raised, transaction.atomic():
            BestTime.objects.create(owner=alice, **self.best(seconds=0))

        assert "athletes_best_time_seconds_positive" in str(raised.value)

    def test_the_text_names_the_distance_and_the_user_only(self, alice: User) -> None:
        assert str(BestTime(owner=alice, **self.best())) == f"5k best time of user {alice.pk}"

    def test_a_time_belongs_to_its_user(self, alice: User, bob: User) -> None:
        mine = BestTime.objects.create(owner=alice, **self.best())
        BestTime.objects.create(owner=bob, **self.best())

        assert list(BestTime.objects.for_user(alice)) == [mine]

    def test_deleting_the_user_deletes_the_times(self, alice: User) -> None:
        BestTime.objects.create(owner=alice, **self.best())

        alice.delete()

        assert not BestTime.objects.exists()
