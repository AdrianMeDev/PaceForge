import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Length
from django.db.models.lookups import LessThanOrEqual

from core.models import OwnedModel
from planning.models import WeeklyPlan
from season.models import SeasonPlanVersion

# The longest message of the athlete that is kept, and the longest answer of the coach.
USER_TEXT_MAX = 2_000
COACH_TEXT_MAX = 5_000


class ChatMessage(OwnedModel):
    """One message of the conversation between an athlete and their coach.

    ``text`` is free text (the athlete's own, or the coach's answer): shown as text and never
    interpreted. A message of the coach that changed a plan says which draft it made (``plan``, a
    week; ``season_plan``, the season) and what the code changed in it (``changes``, fixed
    sentences made by the code, never the words of the coach); if the draft is deleted the message
    stays and only the link is lost. Only the athlete sees their messages, and they can delete the
    whole conversation.
    """

    class Role(models.TextChoices):
        USER = "user", "Athlete"
        COACH = "coach", "Coach"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    role = models.CharField(max_length=10, choices=Role.choices)
    text = models.CharField(max_length=COACH_TEXT_MAX)
    plan = models.ForeignKey(
        WeeklyPlan,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="chat_messages",
    )
    # The version of the season plan the coach made; the link is lost if that is deleted.
    season_plan = models.ForeignKey(
        SeasonPlanVersion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="chat_messages",
    )
    changes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(role__in=["user", "coach"]), name="chat_role_known"),
            models.CheckConstraint(
                # Only the coach changes a plan.
                condition=Q(role="coach")
                | (Q(plan__isnull=True) & Q(season_plan__isnull=True) & Q(changes=[])),
                name="chat_only_the_coach_changes_a_plan",
            ),
            models.CheckConstraint(
                condition=Q(role="coach") | Q(LessThanOrEqual(Length("text"), USER_TEXT_MAX)),
                name="chat_user_text_length",
            ),
        ]
        indexes = [models.Index(fields=["owner", "created_at"], name="chat_owner_time")]

    def __str__(self) -> str:
        return f"{self.role} message of user {self.owner_id}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.owner_id is not None:
            plan = self.plan
            if plan is not None and plan.owner_id != self.owner_id:
                errors["plan"] = "A message links a weekly plan of the same user."
            season_plan = self.season_plan
            if season_plan is not None and season_plan.owner_id != self.owner_id:
                errors["season_plan"] = "A message links a season plan of the same user."
        if errors:
            raise ValidationError(errors)
