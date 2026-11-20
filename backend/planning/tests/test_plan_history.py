"""Historical weekly plans retain their stored contents across direct ORM writes."""

from datetime import timedelta
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from accounts.models import User
from accounts.services.deletion import delete_account
from planning.models import WeeklyPlan

from .test_workout_scope import MONDAY

pytestmark = pytest.mark.django_db
FROZEN = ["confirmed", "superseded", "discarded"]


@pytest.fixture
def plan() -> WeeklyPlan:
    owner = User.objects.create_user("history@example.com")
    parent = WeeklyPlan.objects.create(owner=owner, week_start=MONDAY)
    return WeeklyPlan.objects.create(
        owner=owner,
        week_start=MONDAY,
        version=3,
        parent=parent,
        reason="Original reason",
        rationale="Original rationale",
        note="Original note",
    )


def freeze(plan: WeeklyPlan, status: str) -> None:
    # Deliberately leave the caller's instance in its cached draft state.
    WeeklyPlan.objects.filter(pk=plan.pk).update(
        status=status, confirmed_at=timezone.now() if status != "discarded" else None
    )


def check_deferred() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


@pytest.mark.parametrize("status", FROZEN)
@pytest.mark.parametrize("method", ["save", "update"])
@pytest.mark.parametrize(
    "field",
    [
        "owner_id",
        "week_start",
        "version",
        "parent_id",
        "reason",
        "rationale",
        "note",
        "created_at",
        "confirmed_at",
        "status",
    ],
)
def test_history_rejects_changes(plan: WeeklyPlan, status: str, method: str, field: str) -> None:
    other = User.objects.create_user("other@example.com")
    parent = WeeklyPlan.objects.create(owner=plan.owner, week_start=MONDAY, version=2)
    freeze(plan, status)
    before = WeeklyPlan.objects.filter(pk=plan.pk).values().get()
    changes: dict[str, Any] = {
        "owner_id": other.pk,
        "week_start": MONDAY + timedelta(weeks=1),
        "version": 4,
        "parent_id": parent.pk,
        "reason": "Changed",
        "rationale": "Changed",
        "note": "Changed",
        "created_at": timezone.now() + timedelta(days=1),
        "confirmed_at": timezone.now() + timedelta(days=1),
        "status": "draft",
    }
    plan.refresh_from_db()
    with pytest.raises(IntegrityError, match="planning_weekly_plan_history"), transaction.atomic():
        if method == "save":
            setattr(plan, field, changes[field])
            plan.save()
        else:
            WeeklyPlan.objects.filter(pk=plan.pk).update(**{field: changes[field]})
    assert WeeklyPlan.objects.filter(pk=plan.pk).values().get() == before


@pytest.mark.parametrize("status", FROZEN)
def test_a_stale_draft_cannot_overwrite_history(plan: WeeklyPlan, status: str) -> None:
    freeze(plan, status)
    with pytest.raises(IntegrityError, match="planning_weekly_plan_history"), transaction.atomic():
        plan.save()


@pytest.mark.parametrize("method", ["save", "update"])
@pytest.mark.parametrize("field", [None, "reason", "rationale", "note", "confirmed_at"])
def test_supersession_changes_only_status(plan: WeeklyPlan, method: str, field: str | None) -> None:
    freeze(plan, "confirmed")
    plan.refresh_from_db()
    before = WeeklyPlan.objects.filter(pk=plan.pk).values().get()
    changes: dict[str, Any] = {"status": "superseded"}
    if field is not None:
        changes[field] = (
            timezone.now() + timedelta(days=1) if field == "confirmed_at" else "Changed"
        )

    def write() -> None:
        if method == "save":
            for name, value in changes.items():
                setattr(plan, name, value)
            plan.save()
        else:
            WeeklyPlan.objects.filter(pk=plan.pk).update(**changes)

    if field is None:
        write()
        assert WeeklyPlan.objects.filter(pk=plan.pk).values().get() == {
            **before,
            "status": "superseded",
        }
    else:
        with (
            pytest.raises(IntegrityError, match="planning_weekly_plan_history"),
            transaction.atomic(),
        ):
            write()
        assert WeeklyPlan.objects.filter(pk=plan.pk).values().get() == before


@pytest.mark.parametrize(
    ("status", "target"),
    [
        ("confirmed", "discarded"),
        ("superseded", "confirmed"),
        ("superseded", "discarded"),
        ("discarded", "confirmed"),
        ("discarded", "superseded"),
    ],
)
def test_terminal_history_cannot_change_status(plan: WeeklyPlan, status: str, target: str) -> None:
    freeze(plan, status)
    with pytest.raises(IntegrityError, match="planning_weekly_plan_history"), transaction.atomic():
        WeeklyPlan.objects.filter(pk=plan.pk).update(
            status=target, confirmed_at=timezone.now() if target != "discarded" else None
        )


@pytest.mark.parametrize("status", FROZEN)
def test_unchanged_history_can_be_saved(plan: WeeklyPlan, status: str) -> None:
    freeze(plan, status)
    plan.refresh_from_db()
    plan.save()


def test_mixed_batch_rolls_back_draft_changes(plan: WeeklyPlan) -> None:
    draft = WeeklyPlan.objects.create(owner=plan.owner, week_start=MONDAY, version=4)
    freeze(plan, "confirmed")
    with pytest.raises(IntegrityError, match="planning_weekly_plan_history"), transaction.atomic():
        WeeklyPlan.objects.filter(pk__in=[plan.pk, draft.pk]).update(note="Changed")
    draft.refresh_from_db()
    assert draft.note == ""


@pytest.mark.parametrize("status", FROZEN)
@pytest.mark.parametrize("delete_parent", [False, True])
def test_parent_clearing_requires_actual_deletion(
    plan: WeeklyPlan, status: str, delete_parent: bool
) -> None:
    freeze(plan, status)
    assert plan.parent_id is not None
    parent = WeeklyPlan.objects.get(pk=plan.parent_id)
    if delete_parent:
        with transaction.atomic():
            parent.delete()
            check_deferred()
        plan.refresh_from_db()
        assert plan.parent_id is None
    else:
        with (
            pytest.raises(IntegrityError, match="planning_weekly_plan_history"),
            transaction.atomic(),
        ):
            WeeklyPlan.objects.filter(pk=plan.pk).update(parent=None)
            check_deferred()
        plan.refresh_from_db()
        assert plan.parent_id == parent.pk


def test_draft_contents_remain_editable(plan: WeeklyPlan) -> None:
    plan.note = "Edited"
    plan.save()
    WeeklyPlan.objects.filter(pk=plan.pk).update(rationale="Edited too", parent=None)
    plan.refresh_from_db()
    assert (plan.note, plan.rationale, plan.parent_id) == ("Edited", "Edited too", None)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("status", FROZEN)
def test_account_deletion_removes_linked_history(plan: WeeklyPlan, status: str) -> None:
    freeze(plan, status)
    owner = plan.owner
    owner.set_password("history-test-password")
    owner.save(update_fields=["password"])
    other = User.objects.create_user("survivor@example.com")
    survivor = WeeklyPlan.objects.create(owner=other, week_start=MONDAY)
    owner_id = owner.pk

    delete_account(owner, password="history-test-password", confirmation=owner.email)

    assert not User.objects.filter(pk=owner_id).exists()
    assert not WeeklyPlan.objects.filter(owner_id=owner_id).exists()
    assert WeeklyPlan.objects.filter(pk=survivor.pk).exists()
