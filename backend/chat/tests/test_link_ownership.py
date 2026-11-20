"""Every write path keeps a message and its linked plans with the same athlete."""

from collections.abc import Iterator
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from accounts.models import User
from accounts.services.deletion import delete_account
from chat.models import ChatMessage
from chat.services import clear
from planning.models import WeeklyPlan
from season.models import SeasonPlanVersion

pytestmark = pytest.mark.django_db
GUARD = "chat_message_plan_owner"
BEFORE = [("chat", "0002_chatmessage_season_plan")]
AFTER = [("chat", "0003_message_plan_owner")]


@pytest.fixture
def links(alice: User, bob: User) -> dict[str, Any]:
    return {
        "plan": WeeklyPlan.objects.create(owner=alice, week_start="2026-11-09"),
        # Distinct week/version avoid uniqueness conflicts on owner changes.
        "other_plan": WeeklyPlan.objects.create(owner=bob, week_start="2026-11-16"),
        "season_plan": SeasonPlanVersion.objects.create(owner=alice),
        "other_season_plan": SeasonPlanVersion.objects.create(owner=bob, version=2),
    }


@pytest.mark.parametrize("field", ["plan", "season_plan"])
@pytest.mark.parametrize("method", ["create", "save", "bulk_create", "bulk_update", "update"])
@pytest.mark.parametrize("reverse", [False, True])
def test_cross_owner_links_are_refused_atomically(
    links: dict[str, Any], field: str, method: str, reverse: bool
) -> None:
    mine, theirs = links[field], links[f"other_{field}"]
    if reverse:
        mine, theirs = theirs, mine
    fields = {"owner_id": mine.owner_id, "role": "coach", "text": "Changed", field: mine}
    if method in ("create", "bulk_create"):
        with pytest.raises(IntegrityError, match=GUARD), transaction.atomic():
            if method == "create":
                ChatMessage.objects.create(**{**fields, field: theirs})
            else:
                ChatMessage.objects.bulk_create(
                    [ChatMessage(**fields), ChatMessage(**{**fields, field: theirs})]
                )
        assert not ChatMessage.objects.exists()
    else:
        row = ChatMessage.objects.create(**fields)
        with pytest.raises(IntegrityError, match=GUARD), transaction.atomic():
            if method == "update":
                ChatMessage.objects.filter(pk=row.pk).update(**{field: theirs})
            else:
                setattr(row, field, theirs)
                if method == "save":
                    row.save()
                else:
                    ChatMessage.objects.bulk_update([row], [field])
        row.refresh_from_db()
        assert getattr(row, f"{field}_id") == mine.pk


@pytest.mark.parametrize("field", ["plan", "season_plan"])
@pytest.mark.parametrize("side", ["message", "plan"])
@pytest.mark.parametrize("method", ["save", "bulk_update", "update"])
def test_owner_changes_cannot_strand_messages(
    links: dict[str, Any], field: str, side: str, method: str
) -> None:
    plan = links[field]
    message = ChatMessage.objects.create(
        owner_id=plan.owner_id, role="coach", text="Changed", **{field: plan}
    )
    row: Any = message if side == "message" else plan
    original_owner = row.owner_id
    with pytest.raises(IntegrityError, match=GUARD), transaction.atomic():
        if method == "update":
            type(row).objects.filter(pk=row.pk).update(owner_id=links[f"other_{field}"].owner_id)
        else:
            row.owner_id = links[f"other_{field}"].owner_id
            if method == "save":
                row.save()
            else:
                type(row).objects.bulk_update([row], ["owner"])
    row.refresh_from_db()
    assert row.owner_id == original_owner


def test_clean_reports_both_links_and_accepts_same_owner_or_null(links: dict[str, Any]) -> None:
    message = ChatMessage(
        owner_id=links["plan"].owner_id,
        role="coach",
        text="Changed",
        plan=links["other_plan"],
        season_plan=links["other_season_plan"],
    )
    with pytest.raises(ValidationError) as error:
        message.clean()
    assert set(error.value.message_dict) == {"plan", "season_plan"}
    message.plan, message.season_plan = links["plan"], links["season_plan"]
    message.clean()
    message.plan = message.season_plan = None
    message.clean()


def test_draft_deletion_clears_each_link_and_reset_keeps_plans(links: dict[str, Any]) -> None:
    plan, season = links["plan"], links["season_plan"]
    message = ChatMessage.objects.create(
        owner=plan.owner, role="coach", text="Changed", plan=plan, season_plan=season, changes=["x"]
    )
    plan.delete()
    message.refresh_from_db()
    assert message.plan_id is None and message.season_plan_id == season.pk
    season.delete()
    message.refresh_from_db()
    assert message.season_plan_id is None and message.changes == ["x"]
    other_plan, other_season = links["other_plan"], links["other_season_plan"]
    other = ChatMessage.objects.create(
        owner=other_plan.owner,
        role="coach",
        text="Other",
        plan=other_plan,
        season_plan=other_season,
    )
    assert clear(message.owner) == 1
    assert list(ChatMessage.objects.all()) == [other]
    assert clear(other.owner) == 1
    assert WeeklyPlan.objects.filter(pk=other_plan.pk).exists()
    assert SeasonPlanVersion.objects.filter(pk=other_season.pk).exists()


def test_delete_account_with_linked_messages(links: dict[str, Any], transactional_db: None) -> None:
    plan = links["plan"]
    owner = plan.owner
    owner.set_password("chat-test-password")
    owner.save()
    ChatMessage.objects.create(
        owner=owner, role="coach", text="Changed", plan=plan, season_plan=links["season_plan"]
    )
    survivor = ChatMessage.objects.create(
        owner=links["other_plan"].owner,
        role="coach",
        text="Other",
        plan=links["other_plan"],
        season_plan=links["other_season_plan"],
    )
    owner_id = owner.pk
    delete_account(owner, password="chat-test-password", confirmation=owner.email)
    assert not User.objects.filter(pk=owner_id).exists()
    assert not WeeklyPlan.objects.filter(owner_id=owner_id).exists()
    assert not SeasonPlanVersion.objects.filter(owner_id=owner_id).exists()
    assert list(ChatMessage.objects.all()) == [survivor]


@pytest.fixture
def legacy_apps(transactional_db: None) -> Iterator[Any]:
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    executor.migrate(BEFORE)
    apps = executor.loader.project_state(leaves).apps
    try:
        yield apps
    finally:
        apps.get_model("chat", "ChatMessage").objects.all().delete()
        MigrationExecutor(connection).migrate(leaves)


@pytest.mark.parametrize("field", ["plan", "season_plan"])
def test_preflight_refuses_invalid_existing_links(legacy_apps: Any, field: str) -> None:
    apps = legacy_apps
    users = apps.get_model("accounts", "User").objects
    owner = users.create(email="alice@example.com")
    other = users.create(email="bob@example.com")
    plan = apps.get_model("planning", "WeeklyPlan").objects.create(
        owner=other if field == "plan" else owner, week_start="2026-11-09"
    )
    season = apps.get_model("season", "SeasonPlanVersion").objects.create(
        owner=other if field == "season_plan" else owner
    )
    messages = apps.get_model("chat", "ChatMessage").objects
    row = messages.create(owner=owner, role="coach", text="Changed", plan=plan, season_plan=season)
    original = list(messages.values())
    with pytest.raises(IntegrityError, match="invalid existing message links"):
        MigrationExecutor(connection).migrate(AFTER)
    assert list(messages.values()) == original
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname IN "
            "('chat_message_plan_owner', 'chat_plan_message_owner', "
            "'chat_season_plan_message_owner')"
        )
        assert cursor.fetchone()[0] == 0
    assert AFTER[0] not in MigrationExecutor(connection).loader.applied_migrations
    setattr(row, field, None)
    row.save()
    MigrationExecutor(connection).migrate(AFTER)
    row.refresh_from_db()
    assert getattr(row, f"{field}_id") is None
    # Reversal removes all guards and permits the old invalid link again.
    MigrationExecutor(connection).migrate(BEFORE)
    messages.filter(pk=row.pk).update(**{field: plan if field == "plan" else season})
