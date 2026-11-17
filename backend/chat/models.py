import uuid

from django.db import models
from django.db.models import Q
from django.db.models.functions import Length
from django.db.models.lookups import LessThanOrEqual

from core.models import OwnedModel
from planning.models import WeeklyPlan

# The longest message of the athlete that is kept, and the longest answer of the coach.
USER_TEXT_MAX = 2_000
COACH_TEXT_MAX = 5_000


class ChatMessage(OwnedModel):
    """One message of the conversation between an athlete and their coach.

    ``text`` is free text (the athlete's own, or the coach's answer): shown as text and never
    interpreted. A message of the coach that changed a plan says which draft it made (``plan``) and
    what the code changed in it (``changes``, fixed sentences made by the code, never the words of
    the coach); if the draft is deleted the message stays and only the link is lost. Only the
    athlete sees their messages, and they can delete the whole conversation.
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
    changes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(role__in=["user", "coach"]), name="chat_role_known"),
            models.CheckConstraint(
                # Only the coach changes a plan.
                condition=Q(role="coach") | (Q(plan__isnull=True) & Q(changes=[])),
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
