"""Season history stays frozen through instance, queryset and bulk writes."""

from datetime import timedelta
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from accounts.models import User
from accounts.services.deletion import delete_account
from season import services
from season.models import SeasonPlanVersion

from .test_services import draft

pytestmark = pytest.mark.django_db
FROZEN = ["confirmed", "superseded", "discarded"]
METHODS = ["save", "update", "bulk_update"]


@pytest.fixture
def plan() -> SeasonPlanVersion:
    owner = User.objects.create_user("history@example.com")
    parent = draft(owner)
    return draft(owner, parent=parent.pk, reason="Original reason", request="Original request")


def freeze(plan: SeasonPlanVersion, status: str) -> None:
    # Keep the caller's cached draft state to exercise stale instances too.
    SeasonPlanVersion.objects.filter(pk=plan.pk).update(
        status=status, confirmed_at=timezone.now() if status != "discarded" else None
    )


def write(plan: SeasonPlanVersion, method: str, changes: dict[str, Any]) -> None:
    if method == "update":
        SeasonPlanVersion.objects.filter(pk=plan.pk).update(**changes)
    else:
        for field, value in changes.items():
            setattr(plan, field, value)
        if method == "save":
            plan.save()
        else:
            SeasonPlanVersion.objects.bulk_update([plan], list(changes))


def check_deferred() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


@pytest.mark.parametrize("status", FROZEN)
@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize(
    "field",
    [
        "owner_id",
        "version",
        "parent_id",
        "reason",
        "request",
        "rationale",
        "weeks",
        "skeleton",
        "sports",
        "input_snapshot",
        "created_at",
        "confirmed_at",
        "status",
    ],
)
def test_history_rejects_changes(
    plan: SeasonPlanVersion, status: str, method: str, field: str
) -> None:
    other = User.objects.create_user("other@example.com")
    parent = draft(plan.owner)
    changes: dict[str, Any] = {
        "owner_id": other.pk,
        "version": 4,
        "parent_id": parent.pk,
        "reason": "Changed",
        "request": "Changed",
        "rationale": "Changed",
        "weeks": [],
        "skeleton": {},
        "sports": [],
        "input_snapshot": {"changed": True},
        "created_at": timezone.now() + timedelta(days=1),
        "confirmed_at": timezone.now() + timedelta(days=1),
        "status": "draft",
    }
    freeze(plan, status)
    plan.refresh_from_db()
    before = SeasonPlanVersion.objects.filter(pk=plan.pk).values().get()
    error = ValidationError if method == "save" else IntegrityError
    message = "cannot be changed" if method == "save" else "season_plan_history"
    with pytest.raises(error, match=message), transaction.atomic():
        write(plan, method, {field: changes[field]})
    assert SeasonPlanVersion.objects.filter(pk=plan.pk).values().get() == before


@pytest.mark.parametrize("status", FROZEN)
def test_a_stale_draft_cannot_overwrite_history(plan: SeasonPlanVersion, status: str) -> None:
    freeze(plan, status)
    with pytest.raises(ValidationError, match="cannot be changed"):
        plan.save()


@pytest.mark.parametrize("status", FROZEN)
@pytest.mark.parametrize("method", METHODS)
def test_unchanged_history_can_be_saved(plan: SeasonPlanVersion, status: str, method: str) -> None:
    freeze(plan, status)
    plan.refresh_from_db()
    write(plan, method, {"reason": plan.reason})


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("change_content", [False, True])
def test_supersession_changes_only_status(
    plan: SeasonPlanVersion, method: str, change_content: bool
) -> None:
    freeze(plan, "confirmed")
    plan.refresh_from_db()
    before = SeasonPlanVersion.objects.filter(pk=plan.pk).values().get()
    changes = {"status": "superseded"}
    if change_content:
        changes["reason"] = "Changed"
        error = ValidationError if method == "save" else IntegrityError
        with pytest.raises(error), transaction.atomic():
            write(plan, method, changes)
        assert SeasonPlanVersion.objects.filter(pk=plan.pk).values().get() == before
    else:
        write(plan, method, changes)
        assert SeasonPlanVersion.objects.filter(pk=plan.pk).values().get() == {
            **before,
            "status": "superseded",
        }


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
@pytest.mark.parametrize("method", METHODS)
def test_terminal_history_cannot_change_status(
    plan: SeasonPlanVersion, status: str, target: str, method: str
) -> None:
    freeze(plan, status)
    plan.refresh_from_db()
    error = ValidationError if method == "save" else IntegrityError
    with pytest.raises(error), transaction.atomic():
        write(
            plan,
            method,
            {"status": target, "confirmed_at": timezone.now() if target != "discarded" else None},
        )


@pytest.mark.parametrize("status", FROZEN)
@pytest.mark.parametrize("method", METHODS)
def test_historical_parent_cannot_be_cleared(
    plan: SeasonPlanVersion, status: str, method: str
) -> None:
    freeze(plan, status)
    plan.refresh_from_db()
    parent_id = plan.parent_id
    with pytest.raises(IntegrityError, match="season_plan_history"), transaction.atomic():
        write(plan, method, {"parent_id": None})
        check_deferred()
    plan.refresh_from_db()
    assert plan.parent_id == parent_id


@pytest.mark.parametrize("status", FROZEN)
def test_parent_deletion_can_clear_the_link(plan: SeasonPlanVersion, status: str) -> None:
    freeze(plan, status)
    assert plan.parent is not None
    with transaction.atomic():
        plan.parent.delete()
        check_deferred()
    plan.refresh_from_db()
    assert plan.parent_id is None


@pytest.mark.parametrize("method", METHODS)
def test_drafts_remain_editable(plan: SeasonPlanVersion, method: str) -> None:
    write(plan, method, {"reason": "Changed", "parent_id": None, "input_snapshot": {}})
    plan.refresh_from_db()
    assert (plan.reason, plan.parent_id, plan.input_snapshot) == ("Changed", None, {})


@pytest.mark.parametrize("method", ["update", "bulk_update"])
def test_mixed_batch_rolls_back_draft_changes(plan: SeasonPlanVersion, method: str) -> None:
    editable = draft(plan.owner)
    freeze(plan, "confirmed")
    with pytest.raises(IntegrityError, match="season_plan_history"), transaction.atomic():
        if method == "update":
            SeasonPlanVersion.objects.filter(pk__in=[plan.pk, editable.pk]).update(reason="Changed")
        else:
            plan.reason = editable.reason = "Changed"
            SeasonPlanVersion.objects.bulk_update([plan, editable], ["reason"])
    editable.refresh_from_db()
    assert editable.reason == ""


def test_confirm_restore_and_discard_preserve_history(plan: SeasonPlanVersion) -> None:
    owner = plan.owner
    first = services.confirm(owner, plan.pk)
    before = SeasonPlanVersion.objects.filter(pk=first.pk).values().get()
    second = services.confirm(owner, draft(owner, parent=first.pk).pk)
    assert SeasonPlanVersion.objects.filter(pk=first.pk).values().get() == {
        **before,
        "status": "superseded",
    }
    restored = services.restore(owner, first.pk)
    assert restored.pk != first.pk
    assert restored.status == "draft"
    assert restored.parent_id == first.pk
    assert restored.weeks == first.weeks
    discarded = services.discard(owner, restored.pk)
    discarded_before = SeasonPlanVersion.objects.filter(pk=discarded.pk).values().get()
    restored_again = services.restore(owner, discarded.pk)
    assert restored_again.status == "draft"
    assert restored_again.parent_id == discarded.pk
    assert SeasonPlanVersion.objects.filter(pk=discarded.pk).values().get() == discarded_before
    second.refresh_from_db()
    assert second.status == "confirmed"


@pytest.mark.django_db(transaction=True)
def test_account_deletion_removes_superseded_chain(plan: SeasonPlanVersion) -> None:
    owner = plan.owner
    owner.set_password("history-test-password")
    owner.save(update_fields=["password"])
    services.confirm(owner, plan.pk)
    services.confirm(owner, draft(owner, parent=plan.pk).pk)
    other = User.objects.create_user("survivor@example.com")
    survivor = draft(other)
    owner_id = owner.pk

    delete_account(owner, password="history-test-password", confirmation=owner.email)

    assert not User.objects.filter(pk=owner_id).exists()
    assert not SeasonPlanVersion.objects.filter(owner_id=owner_id).exists()
    assert SeasonPlanVersion.objects.filter(pk=survivor.pk).exists()
