"""Storing the season plans of a user, reading them back, confirming and discarding them.

A plan is stored as a draft with the skeleton it was made for. Reading it back goes through the
strict parser again, so what comes out is always valid. A plan is checked against the skeleton it
was made for, not against the one of today (which has moved on by the time it is confirmed). A
plan with errors is stored as it is, so that the athlete sees what is wrong, and cannot be
confirmed. Nothing here calls the coach: see ``season.generation``.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import User
from planning.schema import Sport
from planning.validation import Report

from .models import REASON_MAX, SeasonPlanVersion
from .rules import SeasonContext, validate_season
from .schema import SeasonPlan, parse_season_plan, to_json
from .storage import skeleton_data, skeleton_from_data

Status = SeasonPlanVersion.Status


class PlanNotFound(Exception):
    """The user has no plan with this id."""


class PlanStateError(Exception):
    """The plan is not in a state that allows this: only a draft can be confirmed or discarded."""


class PlanNotRestorable(Exception):
    """Only a version that was replaced or discarded can be restored."""


class PlanNotConfirmable(Exception):
    """The plan has errors and cannot be confirmed. ``report`` says which."""

    def __init__(self, report: Report) -> None:
        super().__init__("The plan has errors and cannot be confirmed.")
        self.report = report


@dataclass(frozen=True)
class StoredSeason:
    """A stored plan with what it was made for."""

    plan: SeasonPlan
    context: SeasonContext


def _now() -> datetime:
    return timezone.now()


def save_draft(
    user: User,
    plan: SeasonPlan,
    context: SeasonContext,
    reason: str = "",
    parent: UUID | None = None,
) -> SeasonPlanVersion:
    """Store ``plan`` as the next version of the season plan of ``user``, as a draft, with the
    skeleton and the sports it was made for.

    ``parent`` is the version it replaces; ``reason`` is a short plain line saying why. Nothing is
    stored if anything goes wrong. The plan is stored as it is, even if the checks have things to
    say about it."""
    reason = _clean_reason(reason)
    if parent is not None:
        get(user, parent)  # it must be one of the user's own
    for attempt in (1, 2):
        try:
            with transaction.atomic():
                return _store(user, plan, context, reason, parent)
        except IntegrityError:
            # Another request took the version number first; the next round counts again.
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def get(user: User, plan_id: UUID) -> SeasonPlanVersion:
    found = SeasonPlanVersion.objects.for_user(user).filter(pk=plan_id).first()
    if found is None:
        raise PlanNotFound
    return found


def list_versions(user: User) -> list[SeasonPlanVersion]:
    """Every version of the user, the newest first."""
    return list(SeasonPlanVersion.objects.for_user(user).order_by("-version"))


def load(user: User, plan_id: UUID) -> StoredSeason:
    """The stored plan and what it was made for, through the strict parser again."""
    return read(get(user, plan_id))


def read(stored: SeasonPlanVersion) -> StoredSeason:
    plan = parse_season_plan({"rationale": stored.rationale, "weeks": stored.weeks})
    sports = frozenset(Sport(sport) for sport in stored.sports)
    return StoredSeason(plan, SeasonContext(skeleton_from_data(stored.skeleton), sports))


def validate(user: User, plan_id: UUID) -> Report:
    """The report of the stored plan against the skeleton it was made for."""
    loaded = load(user, plan_id)
    return validate_season(loaded.plan, loaded.context)


def confirm(user: User, plan_id: UUID) -> SeasonPlanVersion:
    """Confirm a draft. The plan is checked again; with any error it is refused
    (``PlanNotConfirmable``) and nothing changes. The version that was confirmed before becomes
    ``superseded``. Only a draft can be confirmed (``PlanStateError``)."""
    with transaction.atomic():
        plan = _lock(user, plan_id)
        if plan.status != Status.DRAFT:
            raise PlanStateError
        loaded = read(plan)
        report = validate_season(loaded.plan, loaded.context)
        if not report.valid:
            raise PlanNotConfirmable(report)
        SeasonPlanVersion.objects.for_user(user).filter(status=Status.CONFIRMED).update(
            status=Status.SUPERSEDED
        )
        plan.status = Status.CONFIRMED
        plan.confirmed_at = _now()
        plan.save(update_fields=["status", "confirmed_at"])
        return plan


def discard(user: User, plan_id: UUID) -> SeasonPlanVersion:
    """Throw a draft away. Only a draft can be discarded (``PlanStateError``)."""
    with transaction.atomic():
        plan = _lock(user, plan_id)
        if plan.status != Status.DRAFT:
            raise PlanStateError
        plan.status = Status.DISCARDED
        plan.save(update_fields=["status"])
        return plan


def restore(user: User, plan_id: UUID) -> SeasonPlanVersion:
    """Bring back a version that was replaced or discarded, as the next version: a draft with the
    same weeks and rationale, ``parent`` the version it was restored from and a ``reason`` that says
    so. It keeps the skeleton and the sports the old version was made for (a copy is read and
    checked against what it was made for, as the original was); it is confirmed like any other
    draft. The old version is not touched.

    Raises ``PlanNotFound`` and ``PlanNotRestorable``; in each case nothing is stored.
    """
    old = get(user, plan_id)
    if old.status not in (Status.SUPERSEDED, Status.DISCARDED):
        raise PlanNotRestorable
    loaded = read(old)
    return save_draft(
        user,
        loaded.plan,
        loaded.context,
        reason=f"Restored from version {old.version}",
        parent=old.pk,
    )


def _lock(user: User, plan_id: UUID) -> SeasonPlanVersion:
    """Lock every version of the user, so that two confirmations queue up instead of both finding
    the place free, and return the plan as it is now."""
    versions = list(SeasonPlanVersion.objects.for_user(user).select_for_update().order_by("pk"))
    for plan in versions:
        if plan.pk == plan_id:
            return plan
    raise PlanNotFound


def _store(
    user: User,
    plan: SeasonPlan,
    context: SeasonContext,
    reason: str,
    parent: UUID | None,
) -> SeasonPlanVersion:
    last = (
        SeasonPlanVersion.objects.for_user(user)
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
    )
    data = to_json(plan)
    return SeasonPlanVersion.objects.create(
        owner=user,
        version=(last or 0) + 1,
        parent_id=parent,
        reason=reason,
        rationale=data["rationale"],
        weeks=data["weeks"],
        skeleton=skeleton_data(context.skeleton),
        sports=[sport.value for sport in Sport if sport in context.sports],
    )


def _clean_reason(reason: str) -> str:
    text = reason.strip()
    if len(text) > REASON_MAX:
        raise ValidationError({"reason": f"Use at most {REASON_MAX} characters."})
    if not text.isprintable():
        raise ValidationError({"reason": "A reason is one line of plain text."})
    return text
