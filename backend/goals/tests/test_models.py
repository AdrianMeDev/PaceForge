import math
import time
from datetime import date
from typing import Any

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from accounts.models import User
from goals.models import DISTANCE_MAX, NOTES_MAX, TARGET_TIME_MAX, TARGET_TIME_MIN, TITLE_MAX, Goal

pytestmark = pytest.mark.django_db

RACE_DAY = date(2027, 9, 26)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def race(**fields: Any) -> dict[str, Any]:
    return {
        "kind": "race",
        "title": "Berlin Marathon",
        "target_date": RACE_DAY,
        "discipline": "running",
        **fields,
    }


def threshold(**fields: Any) -> dict[str, Any]:
    return {
        "kind": "threshold",
        "title": "Raise my FTP",
        "metric": "ftp",
        "target_value": 280,
        **fields,
    }


def general(**fields: Any) -> dict[str, Any]:
    return {"kind": "general", "title": "Build endurance", **fields}


def make(owner: User, **fields: Any) -> Goal:
    return Goal.objects.create(owner=owner, **(race() | fields))


def check(owner: User, **fields: Any) -> None:
    Goal(owner=owner, **fields).full_clean(exclude=["owner"])


def refused(owner: User, field: str, **fields: Any) -> None:
    with pytest.raises(ValidationError) as raised:
        check(owner, **fields)
    assert field in raised.value.message_dict, raised.value.message_dict


class TestKinds:
    @pytest.mark.parametrize(
        "fields",
        [
            race(),
            race(distance_m=42195, target_time_seconds=13500),
            race(discipline="triathlon", distance_m=226000, target_time_seconds=40000),
            threshold(),
            threshold(metric="threshold_pace", target_value=300, target_date=RACE_DAY),
            general(),
            general(target_date=RACE_DAY, notes="strength as a supplement"),
        ],
    )
    def test_a_complete_goal_is_valid(self, alice: User, fields: dict[str, Any]) -> None:
        check(alice, **fields)

    def test_defaults_are_secondary_and_active(self, alice: User) -> None:
        goal = make(alice)

        assert (goal.priority, goal.status) == ("secondary", "active")

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"target_date": None}, "target_date"),
            ({"discipline": ""}, "discipline"),
            ({"discipline": "rowing"}, "discipline"),
            ({"metric": "ftp"}, "metric"),
            ({"target_value": 280}, "target_value"),
        ],
    )
    def test_a_race_needs_its_own_fields_and_no_others(
        self, alice: User, changes: dict[str, Any], field: str
    ) -> None:
        refused(alice, field, **race(**changes))

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"metric": ""}, "metric"),
            ({"metric": "lthr"}, "metric"),
            ({"target_value": None}, "target_value"),
            ({"discipline": "running"}, "discipline"),
            ({"distance_m": 5000}, "distance_m"),
            ({"target_time_seconds": 3600}, "target_time_seconds"),
        ],
    )
    def test_a_threshold_goal_needs_its_own_fields_and_no_others(
        self, alice: User, changes: dict[str, Any], field: str
    ) -> None:
        refused(alice, field, **threshold(**changes))

    @pytest.mark.parametrize(
        "changes",
        [
            {"discipline": "running"},
            {"distance_m": 5000},
            {"target_time_seconds": 3600},
            {"metric": "ftp"},
            {"target_value": 250},
        ],
    )
    def test_a_general_goal_has_only_a_title_notes_and_perhaps_a_date(
        self, alice: User, changes: dict[str, Any]
    ) -> None:
        refused(alice, next(iter(changes)), **general(**changes))

    @pytest.mark.parametrize(
        ("field", "value"), [("kind", "dream"), ("priority", "urgent"), ("status", "paused")]
    )
    def test_unknown_choices_are_refused(self, alice: User, field: str, value: str) -> None:
        refused(alice, field, **race(**{field: value}))


class TestThePreparationRace:
    def test_a_race_can_be_a_preparation_race(self, alice: User) -> None:
        check(alice, **race(priority="preparation"))

    @pytest.mark.parametrize("fields", [threshold(), general()])
    def test_another_kind_cannot(self, alice: User, fields: dict[str, Any]) -> None:
        refused(alice, "priority", **fields | {"priority": "preparation"})

    def test_the_message_says_why(self, alice: User) -> None:
        with pytest.raises(ValidationError) as raised:
            check(alice, **general(priority="preparation"))

        assert raised.value.message_dict["priority"] == ["Only a race can be a preparation race."]

    @pytest.mark.parametrize("fields", [threshold(), general()])
    def test_the_database_refuses_it_for_another_kind(
        self, alice: User, fields: dict[str, Any]
    ) -> None:
        with pytest.raises(IntegrityError, match="goals_preparation_is_a_race"):
            with transaction.atomic():
                Goal.objects.create(owner=alice, **fields | {"priority": "preparation"})

    def test_a_race_is_stored_as_one(self, alice: User) -> None:
        assert make(alice, priority="preparation").priority == "preparation"

    def test_it_is_no_main_goal_so_any_number_can_be_active(self, alice: User) -> None:
        make(alice, priority="main")
        make(alice, priority="preparation")
        make(alice, priority="preparation")

        assert Goal.objects.filter(priority="preparation").count() == 2

    def test_the_choices_are_main_secondary_and_preparation(self) -> None:
        assert Goal.Priority.values == ["main", "secondary", "preparation"]


class TestRanges:
    @pytest.mark.parametrize(
        ("metric", "value"),
        [("ftp", 30), ("ftp", 2000), ("threshold_pace", 120), ("threshold_pace", 1200)],
    )
    def test_the_ends_of_the_threshold_ranges_are_valid(
        self, alice: User, metric: str, value: float
    ) -> None:
        check(alice, **threshold(metric=metric, target_value=value))

    @pytest.mark.parametrize(
        ("metric", "value"),
        [
            ("ftp", 29.9),
            ("ftp", 2000.1),
            ("ftp", 0),
            ("ftp", -5),
            ("threshold_pace", 119.9),
            ("threshold_pace", 1200.1),
            ("ftp", math.nan),
            ("ftp", math.inf),
        ],
    )
    def test_a_target_outside_the_range_of_its_metric_is_refused(
        self, alice: User, metric: str, value: float
    ) -> None:
        refused(alice, "target_value", **threshold(metric=metric, target_value=value))

    def test_the_message_names_the_range_and_the_unit(self, alice: User) -> None:
        with pytest.raises(ValidationError) as raised:
            check(alice, **threshold(metric="threshold_pace", target_value=60))

        assert raised.value.message_dict["target_value"] == [
            "Enter a value between 120 and 1200 s/km."
        ]

    @pytest.mark.parametrize("seconds", [TARGET_TIME_MIN, 13500, TARGET_TIME_MAX])
    def test_target_times_in_range_are_valid(self, alice: User, seconds: int) -> None:
        check(alice, **race(target_time_seconds=seconds))

    @pytest.mark.parametrize("seconds", [0, 59, TARGET_TIME_MAX + 1])
    def test_target_times_outside_the_range_are_refused(self, alice: User, seconds: int) -> None:
        refused(alice, "target_time_seconds", **race(target_time_seconds=seconds))

    @pytest.mark.parametrize("metres", [0.1, 5000, 42195, 226000, DISTANCE_MAX])
    def test_distances_in_range_are_valid(self, alice: User, metres: float) -> None:
        check(alice, **race(distance_m=metres))

    @pytest.mark.parametrize("metres", [0, -1, DISTANCE_MAX + 1, math.nan, math.inf])
    def test_distances_outside_the_range_are_refused(self, alice: User, metres: float) -> None:
        refused(alice, "distance_m", **race(distance_m=metres))


class TestTheLimits:
    """Written out on purpose: the other tests read the limits from the module."""

    def test_the_limits_are_these(self) -> None:
        assert (TARGET_TIME_MIN, TARGET_TIME_MAX) == (60, 360_000)
        assert DISTANCE_MAX == 1_000_000
        assert (TITLE_MAX, NOTES_MAX) == (100, 1000)

    @pytest.mark.parametrize("flag", [True, False])
    def test_a_boolean_is_no_number_even_when_clean_is_called_directly(
        self, alice: User, flag: bool
    ) -> None:
        with pytest.raises(ValidationError) as raised:
            Goal(owner=alice, **race(distance_m=flag)).clean()

        assert "distance_m" in raised.value.message_dict


class TestText:
    @pytest.mark.parametrize("title", ["", "   ", "\t\n"])
    def test_a_title_must_say_something(self, alice: User, title: str) -> None:
        refused(alice, "title", **race(title=title))

    def test_the_length_of_the_title_is_limited(self, alice: User) -> None:
        check(alice, **race(title="x" * TITLE_MAX))
        refused(alice, "title", **race(title="x" * (TITLE_MAX + 1)))

    def test_the_length_of_the_notes_is_limited(self, alice: User) -> None:
        check(alice, **race(notes="x" * NOTES_MAX))
        refused(alice, "notes", **race(notes="x" * (NOTES_MAX + 1)))

    def test_notes_may_be_empty(self, alice: User) -> None:
        check(alice, **race(notes=""))

    def test_text_does_not_contain_the_title(self, alice: User) -> None:
        goal = make(alice, title="My secret plan")

        assert "secret" not in str(goal)
        assert str(alice.pk) in str(goal)


class TestMainGoal:
    def main(self, owner: User, **fields: Any) -> Goal:
        return make(owner, priority="main", **fields)

    def test_a_second_active_main_goal_is_refused_by_the_database(self, alice: User) -> None:
        self.main(alice)

        with pytest.raises(IntegrityError), transaction.atomic():
            self.main(alice, title="Another")

        assert Goal.objects.count() == 1

    def test_the_check_before_saving_reports_it_too(self, alice: User) -> None:
        self.main(alice)

        with pytest.raises(ValidationError) as raised:
            Goal(owner=alice, priority="main", **race()).full_clean()  # the owner is part of it

        assert "goals_one_active_main_goal" in str(raised.value)

    def test_any_number_of_secondary_goals_is_fine(self, alice: User) -> None:
        self.main(alice)
        for n in range(3):
            make(alice, title=f"Secondary {n}")

        assert Goal.objects.count() == 4

    @pytest.mark.parametrize("status", ["achieved", "dropped"])
    def test_a_finished_main_goal_does_not_block_a_new_one(self, alice: User, status: str) -> None:
        self.main(alice, status=status)

        self.main(alice, title="The next one")

        assert Goal.objects.count() == 2

    def test_a_finished_main_goal_cannot_come_back_while_another_is_active(
        self, alice: User
    ) -> None:
        old = self.main(alice, status="achieved")
        self.main(alice, title="The next one")

        old.status = "active"
        with pytest.raises(IntegrityError), transaction.atomic():
            old.save()

    def test_a_secondary_goal_cannot_become_main_while_there_is_one(self, alice: User) -> None:
        self.main(alice)
        other = make(alice, title="Other")

        other.priority = "main"
        with pytest.raises(IntegrityError), transaction.atomic():
            other.save()

    def test_every_user_has_their_own_main_goal(self, alice: User, bob: User) -> None:
        self.main(alice)
        self.main(bob)

        assert Goal.objects.filter(priority="main").count() == 2


class TestDatabase:
    """The rules that make a goal complete hold even where ``clean()`` is not called."""

    @pytest.mark.parametrize(
        "changes",
        [
            {"target_date": None},
            {"discipline": ""},
        ],
    )
    def test_an_incomplete_race_is_refused(self, alice: User, changes: dict[str, Any]) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            Goal.objects.create(owner=alice, **race(**changes))

    @pytest.mark.parametrize("changes", [{"metric": ""}, {"target_value": None}])
    def test_an_incomplete_threshold_goal_is_refused(
        self, alice: User, changes: dict[str, Any]
    ) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            Goal.objects.create(owner=alice, **threshold(**changes))

    @pytest.mark.parametrize(
        "changes",
        [
            {"title": ""},
            {"distance_m": 0},
            {"distance_m": -5},
            {"distance_m": DISTANCE_MAX + 1},
            {"target_time_seconds": 59},
            {"target_time_seconds": TARGET_TIME_MAX + 1},
        ],
    )
    def test_numbers_and_titles_out_of_range_are_refused(
        self, alice: User, changes: dict[str, Any]
    ) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            Goal.objects.create(owner=alice, **race(**changes))

    @pytest.mark.parametrize("value", [0, -5])
    def test_a_target_value_that_is_not_positive_is_refused(
        self, alice: User, value: float
    ) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            Goal.objects.create(owner=alice, **threshold(target_value=value))

    def test_a_general_goal_needs_nothing_but_a_title(self, alice: User) -> None:
        Goal.objects.create(owner=alice, **general())

        assert Goal.objects.count() == 1


class TestOwnership:
    def test_for_user_shows_only_the_own_goals(self, alice: User, bob: User) -> None:
        mine, _ = make(alice), make(bob)

        assert list(Goal.objects.for_user(alice)) == [mine]

    def test_anonymous_users_see_nothing(self, alice: User) -> None:
        make(alice)

        assert not Goal.objects.for_user(AnonymousUser()).exists()

    def test_deleting_the_user_deletes_the_goals_and_only_theirs(
        self, alice: User, bob: User
    ) -> None:
        make(alice)
        theirs = make(bob)

        alice.delete()

        assert list(Goal.objects.all()) == [theirs]

    def test_ids_are_uuids_and_creation_times_are_set(self, alice: User) -> None:
        goal = make(alice)

        assert goal.pk.version == 7
        assert goal.created_at is not None

    def test_updated_at_moves_when_the_goal_is_saved_again(self, alice: User) -> None:
        goal = make(alice)
        first = goal.updated_at

        time.sleep(0.01)
        goal.status = "achieved"
        goal.save()
        goal.refresh_from_db()

        assert goal.updated_at > first
        assert goal.created_at <= goal.updated_at
