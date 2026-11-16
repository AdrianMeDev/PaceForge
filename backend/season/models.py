import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from core.models import OwnedModel

from .schema import RATIONALE_MAX

REASON_MAX = 200


class SeasonPlanVersion(OwnedModel):
    """One version of the season plan of one user: what the coach filled into the weeks of the
    skeleton.

    A plan is never changed once it is confirmed: a new draft is a new version, which may point to
    the one it replaces (``parent``) and says why (``reason``). At most one version is confirmed at
    a time; the one it replaces becomes ``superseded``.

    ``weeks`` is the list of weeks in the format of ``season.schema`` and ``skeleton`` the skeleton
    the plan was made for, as the API tells it; ``sports`` are the sports the athlete had chosen
    then. They are kept so that the plan stays readable and can be checked against what it was made
    for when goals, time or the week change. Both are read back through the strict parser. The
    ``rationale`` and the reasons of the weeks are free text of the coach, shown as text only.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONFIRMED = "confirmed", "Confirmed"
        SUPERSEDED = "superseded", "Superseded"
        DISCARDED = "discarded", "Discarded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    # The version this one replaces. If that is deleted the link is lost, the plan stays.
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="revisions"
    )
    reason = models.CharField(max_length=REASON_MAX, blank=True)
    rationale = models.CharField(max_length=RATIONALE_MAX, blank=True)
    weeks = models.JSONField(default=list, blank=True)
    skeleton = models.JSONField(default=dict, blank=True)
    sports = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Set when the plan is confirmed and kept when it is superseded; empty for drafts.
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.CheckConstraint(condition=Q(version__gte=1), name="season_version_from_one"),
            models.UniqueConstraint(fields=["owner", "version"], name="season_one_per_version"),
            models.UniqueConstraint(
                fields=["owner"],
                condition=Q(status="confirmed"),
                name="season_one_confirmed_per_owner",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status__in=["confirmed", "superseded"], confirmed_at__isnull=False)
                    | Q(status__in=["draft", "discarded"], confirmed_at__isnull=True)
                ),
                name="season_confirmed_at_matches_status",
            ),
            models.CheckConstraint(condition=~Q(parent=F("id")), name="season_not_its_own_parent"),
        ]

    def __str__(self) -> str:
        # No reason or rationale: they are free text and have no business in logs.
        return f"Season plan of user {self.owner_id} (v{self.version})"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        parent = self.parent if self.parent_id is not None else None
        if parent is not None:
            if parent.owner_id != self.owner_id:
                errors["parent"] = "A version replaces a version of the same user."
            elif self.version is not None and self.version <= parent.version:
                errors["version"] = "A version must be newer than the one it replaces."
        if not isinstance(self.weeks, list):
            errors["weeks"] = "The weeks are a list."
        if not isinstance(self.skeleton, dict):
            errors["skeleton"] = "The skeleton is an object."
        if not isinstance(self.sports, list):
            errors["sports"] = "The sports are a list."
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        # A plan that is no draft any more is a record of what was agreed: only its status and its
        # time of confirming move (a change is a new version).
        if not self._state.adding:
            stored = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("status", "reason", "rationale", "weeks", "skeleton", "sports")
                .first()
            )
            now = (self.reason, self.rationale, self.weeks, self.skeleton, self.sports)
            if stored is not None and stored[0] != self.Status.DRAFT and stored[1:] != now:
                raise ValidationError(
                    "The content of a plan that is not a draft cannot be changed."
                )
        super().save(*args, **kwargs)
