"""Revision edges remain ordered even when model validation is bypassed."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from queue import Queue
from time import monotonic, sleep

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import F

from accounts.models import User
from planning.models import WeeklyPlan

MONDAY = date(2027, 7, 12)
pytestmark = pytest.mark.django_db


@pytest.fixture
def plans() -> tuple[WeeklyPlan, WeeklyPlan, User]:
    owner = User.objects.create_user("alice@example.com")
    other = User.objects.create_user("bob@example.com")
    parent = WeeklyPlan.objects.create(owner=owner, week_start=MONDAY, version=3)
    child = WeeklyPlan.objects.create(owner=owner, week_start=MONDAY, version=5)
    return parent, child, other


@pytest.mark.parametrize("kind", ["owner", "week", "version"])
@pytest.mark.parametrize("method", ["save", "bulk_create", "update", "bulk_update"])
def test_invalid_child_edges_roll_back(
    plans: tuple[WeeklyPlan, WeeklyPlan, User], kind: str, method: str
) -> None:
    parent, child, other = plans
    child.parent = parent
    if kind == "owner":
        child.owner = other
    elif kind == "week":
        child.week_start += timedelta(weeks=1)
    else:
        child.version = 1
    with pytest.raises(IntegrityError, match="planning_revision_ancestry"), transaction.atomic():
        if method == "save":
            child.save()
        elif method == "bulk_create":
            child.pk = WeeklyPlan().pk
            WeeklyPlan.objects.bulk_create(
                [WeeklyPlan(owner=parent.owner, week_start=MONDAY, version=9), child]
            )
        elif method == "bulk_update":
            WeeklyPlan.objects.bulk_update([child], ["parent", "owner", "week_start", "version"])
        else:
            WeeklyPlan.objects.filter(pk=child.pk).update(
                parent=parent, owner=child.owner, week_start=child.week_start, version=child.version
            )
    assert WeeklyPlan.objects.count() == 2
    stored = WeeklyPlan.objects.get(version=5)
    assert (stored.parent_id, stored.owner_id, stored.week_start) == (None, parent.owner_id, MONDAY)


@pytest.mark.parametrize("end", ["parent", "child"])
@pytest.mark.parametrize("kind", ["owner", "week", "version"])
@pytest.mark.parametrize("method", ["save", "update"])
def test_edits_to_either_end_cannot_invalidate_an_existing_edge(
    plans: tuple[WeeklyPlan, WeeklyPlan, User], end: str, kind: str, method: str
) -> None:
    parent, child, other = plans
    child.parent = parent
    child.save()
    row = parent if end == "parent" else child
    changes = {
        "owner_id": other.pk,
        "week_start": MONDAY + timedelta(weeks=1),
        "version": 7 if end == "parent" else 1,
    }
    field = {"owner": "owner_id", "week": "week_start", "version": "version"}[kind]
    with pytest.raises(IntegrityError, match="planning_revision_ancestry"), transaction.atomic():
        if method == "update":
            WeeklyPlan.objects.filter(pk=row.pk).update(**{field: changes[field]})
        else:
            setattr(row, field, changes[field])
            row.save()
    row.refresh_from_db()
    assert (row.owner_id, row.week_start, row.version) == (
        parent.owner_id,
        MONDAY,
        3 if end == "parent" else 5,
    )


@pytest.mark.parametrize("size", [2, 3])
@pytest.mark.parametrize("method", ["save", "bulk_create", "bulk_update"])
def test_cycles_are_rejected_including_a_single_statement(
    plans: tuple[WeeklyPlan, WeeklyPlan, User], size: int, method: str
) -> None:
    parent, child, _ = plans
    rows = [parent, child]
    if size == 3:
        rows.append(WeeklyPlan.objects.create(owner=parent.owner, week_start=MONDAY, version=7))
    if method == "save":
        for previous, row in zip(rows, rows[1:], strict=False):
            row.parent = previous
            row.save()
        rows[0].parent = rows[-1]
    else:
        if method == "bulk_create":
            WeeklyPlan.objects.all().delete()
        for index, row in enumerate(rows):
            row.parent = rows[index - 1]
    with pytest.raises(IntegrityError, match="planning_revision_ancestry"), transaction.atomic():
        if method == "save":
            rows[0].save()
        elif method == "bulk_create":
            WeeklyPlan.objects.bulk_create(rows)
        else:
            WeeklyPlan.objects.bulk_update(rows, ["parent"])
    if method == "bulk_create":
        assert not WeeklyPlan.objects.exists()
    else:
        rows[0].refresh_from_db()
        assert rows[0].parent_id is None


def test_reassigning_parent_id_to_a_descendant_cannot_create_a_cycle(
    plans: tuple[WeeklyPlan, WeeklyPlan, User],
) -> None:
    root, child, _ = plans
    child.parent = root
    child.save()
    descendant = WeeklyPlan.objects.create(
        owner=root.owner, week_start=MONDAY, version=7, parent=child
    )
    # The deferred FK allows the root's ID to be temporarily unassigned.
    with pytest.raises(IntegrityError, match="planning_revision_ancestry"), transaction.atomic():
        WeeklyPlan.objects.filter(pk=root.pk).update(id=WeeklyPlan().pk)
        WeeklyPlan.objects.filter(pk=descendant.pk).update(id=root.pk)
    assert WeeklyPlan.objects.get(pk=root.pk).parent_id is None
    assert WeeklyPlan.objects.get(pk=child.pk).parent_id == root.pk
    assert WeeklyPlan.objects.get(pk=descendant.pk).parent_id == child.pk


def test_valid_branches_skipped_versions_and_parent_deletion(
    plans: tuple[WeeklyPlan, WeeklyPlan, User],
) -> None:
    root, branch, _ = plans
    branch.parent = root
    branch.save()
    sibling = WeeklyPlan(owner=root.owner, week_start=MONDAY, version=12, parent=root)
    descendant = WeeklyPlan(owner=root.owner, week_start=MONDAY, version=20, parent=sibling)
    # Child comes first to exercise statement-final visibility of inserted parents.
    WeeklyPlan.objects.bulk_create([descendant, sibling])
    WeeklyPlan.objects.update(version=F("version") + 30)
    root.delete()
    branch.refresh_from_db()
    sibling.refresh_from_db()
    descendant.refresh_from_db()
    assert branch.parent_id is None
    assert sibling.parent_id is None
    assert descendant.parent_id == sibling.pk
    assert descendant.version == 50


def test_joint_owner_and_week_change_checks_final_statement_state(
    plans: tuple[WeeklyPlan, WeeklyPlan, User],
) -> None:
    parent, child, other = plans
    child.parent = parent
    child.save()
    WeeklyPlan.objects.update(owner=other, week_start=MONDAY + timedelta(weeks=1))
    child.refresh_from_db()
    parent.refresh_from_db()
    assert child.owner_id == parent.owner_id == other.pk
    assert child.week_start == parent.week_start == MONDAY + timedelta(weeks=1)


def wait_until_blocked(pid: int) -> None:
    deadline = monotonic() + 10
    while monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT cardinality(pg_blocking_pids(%s))", [pid])
            if cursor.fetchone()[0]:
                return
        sleep(0.01)
    pytest.fail("The concurrent revision write did not wait for the parent row lock")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("kind", ["owner", "week", "version"])
@pytest.mark.parametrize("method", ["insert", "update"])
def test_missing_parent_cannot_be_supplied_by_a_conflicting_transaction(
    plans: tuple[WeeklyPlan, WeeklyPlan, User], kind: str, method: str
) -> None:
    root, child, other = plans
    parent = WeeklyPlan(owner=root.owner, week_start=MONDAY, version=1)
    if kind == "owner":
        parent.owner = other
    elif kind == "week":
        parent.week_start += timedelta(weeks=1)
    else:
        parent.version = 7

    def insert_parent() -> None:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '15s'")
            with transaction.atomic():
                parent.save(force_insert=True)
        finally:
            connection.close()

    rejected = False
    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            # A savepoint lets the outer transaction remain open after rejection.
            # Without the guard this write succeeds, and the deferred FK accepts
            # the conflicting parent committed by the other transaction below.
            try:
                with transaction.atomic():
                    if method == "insert":
                        WeeklyPlan.objects.create(
                            owner=root.owner, week_start=MONDAY, version=6, parent_id=parent.pk
                        )
                    else:
                        WeeklyPlan.objects.filter(pk=child.pk).update(parent_id=parent.pk)
            except IntegrityError as error:
                assert "planning_revision_ancestry" in str(error)
                rejected = True
            pool.submit(insert_parent).result(timeout=20)
    assert rejected, "The child write accepted a parent invisible to its ancestry check"
    assert WeeklyPlan.objects.filter(pk=parent.pk).exists()
    assert not WeeklyPlan.objects.filter(parent_id=parent.pk).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("first", ["parent", "child"])
@pytest.mark.parametrize("kind", ["owner", "week", "version", "existing_edge"])
@pytest.mark.parametrize("method", ["insert", "update"])
def test_conflicting_transactions_cannot_commit_invalid_edges(
    plans: tuple[WeeklyPlan, WeeklyPlan, User], first: str, kind: str, method: str
) -> None:
    parent, child, other = plans
    if kind == "existing_edge":
        child.parent = parent
        child.save()
    changes_by_kind: dict[str, dict[str, object]] = {
        "owner": {"owner_id": other.pk},
        "week": {"week_start": MONDAY + timedelta(weeks=1)},
        "version": {"version": 7},
        "existing_edge": {"version": 4},
    }
    changes = changes_by_kind[kind]
    pids: Queue[int] = Queue()

    def write(which: str) -> None:
        if which == "parent":
            WeeklyPlan.objects.filter(pk=parent.pk).update(**changes)
        elif kind == "existing_edge":
            WeeklyPlan.objects.filter(pk=child.pk).update(version=2)
        elif method == "insert":
            WeeklyPlan.objects.create(
                owner=parent.owner, week_start=MONDAY, version=6, parent=parent
            )
        else:
            WeeklyPlan.objects.filter(pk=child.pk).update(parent=parent)

    # For the existing-edge race both edits must be valid individually:
    # parent 3 -> 4, child 5 -> 2 would already be invalid, so start parent at 1.
    if kind == "existing_edge":
        WeeklyPlan.objects.filter(pk=parent.pk).update(version=1)

    def concurrent_write() -> str:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '15s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids.put(cursor.fetchone()[0])
            with transaction.atomic():
                write("child" if first == "parent" else "parent")
            return "accepted"
        except IntegrityError as error:
            assert "planning_revision_ancestry" in str(error)
            return "rejected"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            write(first)
            future = pool.submit(concurrent_write)
            wait_until_blocked(pids.get(timeout=10))
        assert future.result(timeout=20) == "rejected"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM planning_weeklyplan c "
            "JOIN planning_weeklyplan p ON p.id = c.parent_id "
            "WHERE c.owner_id <> p.owner_id OR c.week_start <> p.week_start "
            "OR c.version <= p.version"
        )
        assert cursor.fetchone()[0] == 0
