import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from core.models import OwnedModel

from .schema import RATIONALE_MAX

REASON_MAX = 200
# The change request of the athlete that a version was made from: their own words, as text.
REQUEST_MAX = 500


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
    # What the athlete asked for if the coach made this version of another one; free text, shown as
    # text and only ever sent to the coach as data.
    request = models.CharField(max_length=REQUEST_MAX, blank=True)
    rationale = models.CharField(max_length=RATIONALE_MAX, blank=True)
    weeks = models.JSONField(default=list, blank=True)
    skeleton = models.JSONField(default=dict, blank=True)
    sports = models.JSONField(default=list, blank=True)
    # The versioned inputs captured before drafting. Null means the baseline is unknown.
    input_snapshot = models.JSONField(null=True, blank=True, default=None)
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
        if self.input_snapshot is not None and not isinstance(self.input_snapshot, dict):
            errors["input_snapshot"] = "The input snapshot is an object or unknown."
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Historical plans retain their content and metadata. Only confirmed -> superseded
        # and parent removal on deletion are allowed; the database checks deletion at commit.
        if not self._state.adding:
            stored = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list(
                    "status",
                    "parent_id",
                    "owner_id",
                    "version",
                    "created_at",
                    "confirmed_at",
                    "reason",
                    "request",
                    "rationale",
                    "weeks",
                    "skeleton",
                    "sports",
                    "input_snapshot",
                )
                .first()
            )
            now = (
                self.owner_id,
                self.version,
                self.created_at,
                self.confirmed_at,
                self.reason,
                self.request,
                self.rationale,
                self.weeks,
                self.skeleton,
                self.sports,
                self.input_snapshot,
            )
            if (
                stored is not None
                and stored[0] != self.Status.DRAFT
                and (
                    stored[2:] != now
                    or not (
                        self.status == stored[0]
                        or (
                            stored[0] == self.Status.CONFIRMED
                            and self.status == self.Status.SUPERSEDED
                        )
                    )
                    or (self.parent_id != stored[1] and self.parent_id is not None)
                )
            ):
                raise ValidationError(
                    "The content of a plan that is not a draft cannot be changed."
                )
        super().save(*args, **kwargs)
