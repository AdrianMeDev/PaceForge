from datetime import UTC, datetime
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from accounts.models import User
from season.models import REASON_MAX, REQUEST_MAX, SeasonPlanVersion

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
Status = SeasonPlanVersion.Status


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def make(owner: User, version: int = 1, **fields: Any) -> SeasonPlanVersion:
    return SeasonPlanVersion.objects.create(owner=owner, version=version, **fields)


def confirmed(owner: User, version: int = 1, **fields: Any) -> SeasonPlanVersion:
    return make(owner, version, status=Status.CONFIRMED, confirmed_at=NOW, **fields)


class TestTheDefaults:
    def test_a_new_plan_is_an_empty_draft_of_version_one(self, alice: User) -> None:
        plan = SeasonPlanVersion.objects.create(owner=alice)

        assert (plan.version, plan.status, plan.parent, plan.confirmed_at) == (
            1,
            "draft",
            None,
            None,
        )
        assert (plan.weeks, plan.skeleton, plan.sports) == ([], {}, [])
        assert plan.pk.version == 7

    def test_the_newest_version_comes_first(self, alice: User) -> None:
        make(alice, 1)
        make(alice, 3)
        make(alice, 2)

        assert list(
            SeasonPlanVersion.objects.for_user(alice).values_list("version", flat=True)
        ) == [3, 2, 1]

    def test_a_new_plan_has_no_request_and_the_limit_is_five_hundred(self, alice: User) -> None:
        assert make(alice).request == ""
        assert REQUEST_MAX == 500

    def test_the_text_names_the_user_and_the_version_only(self, alice: User) -> None:
        plan = make(alice, 4, reason="SECRET reason", request="SECRET request", rationale="SECRET")

        assert str(plan) == f"Season plan of user {alice.pk} (v4)"


class TestOwnership:
    def test_versions_are_counted_per_user(self, alice: User, bob: User) -> None:
        make(alice, 1)
        make(bob, 1)

        assert SeasonPlanVersion.objects.count() == 2

    def test_a_version_is_unique_per_user(self, alice: User) -> None:
        make(alice, 1)

        with pytest.raises(IntegrityError), transaction.atomic():
            make(alice, 1)

    def test_for_user_shows_only_the_own_plans(self, alice: User, bob: User) -> None:
        mine = make(alice)
        make(bob)

        assert list(SeasonPlanVersion.objects.for_user(alice)) == [mine]

    def test_deleting_the_user_deletes_the_plans(self, alice: User, bob: User) -> None:
        make(alice)
        make(bob)

        alice.delete()

        assert SeasonPlanVersion.objects.count() == 1


class TestTheDatabaseRules:
    def test_a_version_starts_at_one(self, alice: User) -> None:
        with pytest.raises(IntegrityError, match="season_version_from_one"), transaction.atomic():
            make(alice, 0)

    def test_at_most_one_plan_is_confirmed_per_user(self, alice: User, bob: User) -> None:
        confirmed(alice, 1)
        confirmed(bob, 1)

        with (
            pytest.raises(IntegrityError, match="season_one_confirmed_per_owner"),
            transaction.atomic(),
        ):
            confirmed(alice, 2)

    def test_a_superseded_plan_does_not_count_against_that(self, alice: User) -> None:
        make(alice, 1, status=Status.SUPERSEDED, confirmed_at=NOW)

        confirmed(alice, 2)

    @pytest.mark.parametrize("status", [Status.CONFIRMED, Status.SUPERSEDED])
    def test_a_confirmed_or_superseded_plan_has_a_time_of_confirming(
        self, alice: User, status: str
    ) -> None:
        with (
            pytest.raises(IntegrityError, match="season_confirmed_at_matches_status"),
            transaction.atomic(),
        ):
            make(alice, 1, status=status)

    @pytest.mark.parametrize("status", [Status.DRAFT, Status.DISCARDED])
    def test_a_draft_or_discarded_plan_has_none(self, alice: User, status: str) -> None:
        with (
            pytest.raises(IntegrityError, match="season_confirmed_at_matches_status"),
            transaction.atomic(),
        ):
            make(alice, 1, status=status, confirmed_at=NOW)

    def test_a_plan_is_not_its_own_parent(self, alice: User) -> None:
        plan = make(alice)

        with pytest.raises(IntegrityError, match="season_not_its_own_parent"), transaction.atomic():
            SeasonPlanVersion.objects.filter(pk=plan.pk).update(parent=plan)

    def test_deleting_the_parent_keeps_the_plan(self, alice: User) -> None:
        old = make(alice, 1)
        new = make(alice, 2, parent=old)

        old.delete()

        new.refresh_from_db()
        assert new.parent is None


class TestClean:
    def test_a_valid_plan_is_valid(self, alice: User) -> None:
        make(alice).full_clean(exclude=["owner"])

    def test_a_version_replaces_an_older_one_of_the_same_user(self, alice: User, bob: User) -> None:
        old = make(alice, 2)
        bobs = make(bob, 1)

        for parent, version, field in (
            (old, 2, "version"),
            (old, 1, "version"),
            (bobs, 5, "parent"),
        ):
            plan = SeasonPlanVersion(owner=alice, version=version, parent=parent)
            with pytest.raises(ValidationError) as raised:
                plan.full_clean(exclude=["owner"])
            assert field in raised.value.message_dict

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("weeks", {}),
            ("weeks", "x"),
            ("skeleton", []),
            ("skeleton", "x"),
            ("sports", {}),
            ("sports", 5),
        ],
    )
    def test_the_json_has_its_shape(self, alice: User, field: str, value: Any) -> None:
        plan = SeasonPlanVersion(owner=alice, **{field: value})

        with pytest.raises(ValidationError) as raised:
            plan.full_clean(exclude=["owner"])

        assert field in raised.value.message_dict

    def test_the_reason_has_a_limit(self, alice: User) -> None:
        plan = SeasonPlanVersion(owner=alice, reason="x" * (REASON_MAX + 1))

        with pytest.raises(ValidationError) as raised:
            plan.full_clean(exclude=["owner"])

        assert "reason" in raised.value.message_dict


class TestAPlanThatIsNoDraftAnyMore:
    def test_a_draft_can_be_changed(self, alice: User) -> None:
        plan = make(alice, weeks=[])

        plan.weeks = [{"x": 1}]
        plan.reason = "Changed"
        plan.save()

        plan.refresh_from_db()
        assert (plan.weeks, plan.reason) == ([{"x": 1}], "Changed")

    @pytest.mark.parametrize("status", [Status.CONFIRMED, Status.SUPERSEDED])
    @pytest.mark.parametrize(
        "field", ["weeks", "skeleton", "sports", "reason", "request", "rationale"]
    )
    def test_its_content_cannot_be_changed(self, alice: User, status: str, field: str) -> None:
        plan = make(alice, status=status, confirmed_at=NOW)
        value: Any = (
            {"x": 1} if field == "skeleton" else ([1] if field in ("weeks", "sports") else "x")
        )

        setattr(plan, field, value)

        with pytest.raises(ValidationError, match="cannot be changed"):
            plan.save()
        plan.refresh_from_db()
        assert getattr(plan, field) != value

    def test_its_status_can_move(self, alice: User) -> None:
        plan = confirmed(alice)

        plan.status = Status.SUPERSEDED
        plan.save(update_fields=["status"])

        plan.refresh_from_db()
        assert plan.status == "superseded"

    def test_a_discarded_plan_is_a_record_too(self, alice: User) -> None:
        plan = make(alice, status=Status.DISCARDED)

        plan.weeks = [1]

        with pytest.raises(ValidationError, match="cannot be changed"):
            plan.save()
