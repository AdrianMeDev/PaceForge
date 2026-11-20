"""Season ancestry is enforced even when model validation is bypassed."""

from collections.abc import Iterator
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models import F

from accounts.models import User
from season.models import SeasonPlanVersion

pytestmark = pytest.mark.django_db
BEFORE = [("season", "0004_season_plan_history")]
AFTER = [("season", "0005_season_revision_ancestry")]


@pytest.fixture
def plans() -> tuple[SeasonPlanVersion, SeasonPlanVersion, User]:
    owner = User.objects.create_user("alice@example.com")
    other = User.objects.create_user("bob@example.com")
    parent = SeasonPlanVersion.objects.create(owner=owner, version=3)
    child = SeasonPlanVersion.objects.create(owner=owner, version=5)
    return parent, child, other


@pytest.mark.parametrize("kind", ["owner", "older", "equal"])
@pytest.mark.parametrize("method", ["create", "save", "bulk_create", "bulk_update", "update"])
def test_invalid_parent_links_roll_back(
    plans: tuple[SeasonPlanVersion, SeasonPlanVersion, User], kind: str, method: str
) -> None:
    parent, child, other = plans
    child.parent = parent
    if kind == "owner":
        child.owner = other
    else:
        child.version = 1 if kind == "older" else parent.version
    # Equal versions of the same athlete also violate the existing unique constraint.
    constraint = "season_one_per_version" if kind == "equal" else "season_revision_ancestry"
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        if method == "create":
            SeasonPlanVersion.objects.create(
                owner=child.owner, version=child.version, parent=parent
            )
        elif method == "save":
            child.save()
        elif method == "bulk_create":
            child.pk = SeasonPlanVersion().pk
            SeasonPlanVersion.objects.bulk_create(
                [SeasonPlanVersion(owner=parent.owner, version=9), child]
            )
        elif method == "bulk_update":
            SeasonPlanVersion.objects.bulk_update([child], ["owner", "version", "parent"])
        else:
            SeasonPlanVersion.objects.filter(pk=child.pk).update(
                owner=child.owner, version=child.version, parent=parent
            )
    assert SeasonPlanVersion.objects.count() == 2
    stored = SeasonPlanVersion.objects.get(owner=parent.owner, version=5)
    assert (stored.parent_id, stored.owner_id, stored.version) == (None, parent.owner_id, 5)


@pytest.mark.parametrize("end", ["parent", "child"])
@pytest.mark.parametrize("field", ["owner", "version"])
@pytest.mark.parametrize("method", ["save", "bulk_update", "update"])
def test_edits_to_either_end_cannot_break_a_link(
    plans: tuple[SeasonPlanVersion, SeasonPlanVersion, User], end: str, field: str, method: str
) -> None:
    parent, child, other = plans
    child.parent = parent
    child.save()
    owner_id = parent.owner_id
    row = parent if end == "parent" else child
    if field == "owner":
        row.owner = other
    else:
        row.version = 7 if end == "parent" else 1
    with pytest.raises(IntegrityError, match="season_revision_ancestry"), transaction.atomic():
        if method == "save":
            row.save()
        elif method == "bulk_update":
            SeasonPlanVersion.objects.bulk_update([row], [field])
        else:
            SeasonPlanVersion.objects.filter(pk=row.pk).update(**{field: getattr(row, field)})
    row.refresh_from_db()
    assert (row.owner_id, row.version) == (owner_id, 3 if end == "parent" else 5)


def test_valid_chain_and_statement_final_changes(
    plans: tuple[SeasonPlanVersion, SeasonPlanVersion, User],
) -> None:
    parent, child, other = plans
    child.parent = parent
    child.save()
    sibling = SeasonPlanVersion(owner=parent.owner, version=9, parent=parent)
    descendant = SeasonPlanVersion(owner=parent.owner, version=12, parent=sibling)
    # The parent may appear later in the same INSERT statement.
    SeasonPlanVersion.objects.bulk_create([descendant, sibling])
    SeasonPlanVersion.objects.update(owner=other, version=F("version") + 20)
    parent.delete()
    child.refresh_from_db()
    sibling.refresh_from_db()
    descendant.refresh_from_db()
    assert child.parent_id is None
    assert sibling.parent_id is None
    assert descendant.parent_id == sibling.pk
    assert descendant.version == 32
    assert descendant.owner_id == other.pk


@pytest.mark.parametrize("method", ["bulk_create", "bulk_update"])
def test_a_cycle_in_one_statement_is_rejected(
    plans: tuple[SeasonPlanVersion, SeasonPlanVersion, User], method: str
) -> None:
    parent, child, _ = plans
    if method == "bulk_create":
        SeasonPlanVersion.objects.all().delete()
    parent.parent = child
    child.parent = parent
    with pytest.raises(IntegrityError, match="season_revision_ancestry"), transaction.atomic():
        if method == "bulk_create":
            SeasonPlanVersion.objects.bulk_create([parent, child])
        else:
            SeasonPlanVersion.objects.bulk_update([parent, child], ["parent"])


def test_missing_parent_is_rejected_before_deferred_foreign_key(
    plans: tuple[SeasonPlanVersion, SeasonPlanVersion, User],
) -> None:
    _, child, _ = plans
    with pytest.raises(IntegrityError, match="season_revision_ancestry"), transaction.atomic():
        SeasonPlanVersion.objects.filter(pk=child.pk).update(parent_id=SeasonPlanVersion().pk)


@pytest.fixture
def legacy_apps(transactional_db: None) -> Iterator[Any]:
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    executor.migrate(BEFORE)
    apps = executor.loader.project_state(BEFORE).apps
    try:
        yield apps
    finally:
        apps.get_model("season", "SeasonPlanVersion").objects.all().delete()
        MigrationExecutor(connection).migrate(leaves)


@pytest.mark.parametrize("kind", ["owner", "older", "cycle"])
def test_preflight_refuses_existing_bad_links_atomically(legacy_apps: Any, kind: str) -> None:
    owner = legacy_apps.get_model("accounts", "User").objects.create(email="alice@example.com")
    other = legacy_apps.get_model("accounts", "User").objects.create(email="bob@example.com")
    rows = legacy_apps.get_model("season", "SeasonPlanVersion").objects
    parent = rows.create(owner=owner, version=3)
    child = rows.create(
        owner=other if kind == "owner" else owner,
        version=1 if kind == "older" else 5,
        parent=parent,
    )
    if kind == "cycle":
        rows.filter(pk=parent.pk).update(parent=child)
    original = list(rows.order_by("id").values())
    with pytest.raises(IntegrityError, match="invalid existing parent edges"):
        MigrationExecutor(connection).migrate(AFTER)
    assert list(rows.order_by("id").values()) == original
    assert AFTER[0] not in MigrationExecutor(connection).loader.applied_migrations
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_trigger WHERE tgname = 'season_revision_ancestry'")
        assert cursor.fetchone()[0] == 0
        cursor.execute(
            "SELECT count(*) FROM pg_proc WHERE proname = 'season_check_revision_ancestry'"
        )
        assert cursor.fetchone()[0] == 0
    rows.filter(pk=parent.pk).update(parent=None)
    rows.filter(pk=child.pk).update(owner=owner, version=5)
    MigrationExecutor(connection).migrate(AFTER)


def test_migration_preserves_valid_history_and_reverses(legacy_apps: Any) -> None:
    owner = legacy_apps.get_model("accounts", "User").objects.create(email="alice@example.com")
    rows = legacy_apps.get_model("season", "SeasonPlanVersion").objects
    parent = rows.create(owner=owner, version=1)
    child = rows.create(owner=owner, version=3, parent=parent)
    rows.create(owner=owner, version=5, parent=child)
    original = list(rows.order_by("id").values())
    MigrationExecutor(connection).migrate(AFTER)
    assert list(rows.order_by("id").values()) == original
    with pytest.raises(IntegrityError, match="season_revision_ancestry"):
        rows.filter(pk=parent.pk).update(parent=child)
    MigrationExecutor(connection).migrate(BEFORE)
    rows.filter(pk=parent.pk).update(parent=child)
