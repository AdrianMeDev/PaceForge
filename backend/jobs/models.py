"""What the background jobs may do for one user, and what they did when they ran.

Every job works on the data of exactly one user. ``JobSettings`` says which jobs that user lets
run; a user without a row has every job on. ``JobRun`` is the log: one row per attempt, with a
fixed outcome and, when a run did not simply succeed, one of a handful of fixed codes. Neither row
ever holds a word from the coach or from Intervals.icu: counts are numbers only.
"""

import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import OwnedModel

# The longest note a code may be: codes are short fixed words, never free text.
CODE_MAX = 40


class Job(models.TextChoices):
    """The jobs that run on their own, in the order they run for one user."""

    SYNC = "sync", "Sync activities"
    WEEK_REVIEW = "week_review", "Week review"
    WEEK_DRAFT = "week_draft", "Draft next week"


class Outcome(models.TextChoices):
    """How an attempt ended. ``done``: it did its work; ``skipped``: it rightly did nothing;
    ``failed``: it could not do its work and will be tried again."""

    DONE = "done", "Done"
    SKIPPED = "skipped", "Skipped"
    FAILED = "failed", "Failed"


class Code(models.TextChoices):
    """The fixed words that say why a run was skipped or failed. A short hint for the athlete and
    for the operator, never a message from the coach or from another service."""

    # Sync.
    NOT_CONNECTED = "not_connected", "No Intervals.icu connection"
    INVALID_KEY = "invalid_key", "The Intervals.icu key was refused"
    INTERVALS_UNAVAILABLE = "intervals_unavailable", "Intervals.icu did not answer"
    # Review and draft.
    NO_COACH = "no_coach", "No coach configured"
    PROVIDER_ERROR = "provider_error", "The coach did not answer"
    PLAN_NOT_USABLE = "plan_not_usable", "The plan did not pass the checks"
    COMMENT_NOT_USABLE = "comment_not_usable", "The comment was not usable"
    NO_TIME = "no_time", "No training time known"
    NOTHING_TO_REVIEW = "nothing_to_review", "Nothing to review"
    ALREADY_PLANNED = "already_planned", "Next week is already planned"
    # Anything else: an error the code did not expect, never with the error text.
    UNEXPECTED = "unexpected", "Unexpected error"


class JobSettings(OwnedModel):
    """Which jobs the user lets PaceForge run for them: at most one row per user, and a user
    without a row has all of them on. Turning a job off only stops it from starting; nothing it
    already did is undone."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    sync = models.BooleanField(default=True)
    week_review = models.BooleanField(default=True)
    week_draft = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner"], name="jobs_one_settings_per_user"),
        ]

    def __str__(self) -> str:
        return f"Job settings of user {self.owner_id}"

    def allows(self, job: Job | str) -> bool:
        """Whether the user lets ``job`` run."""
        by_job = {
            Job.SYNC: self.sync,
            Job.WEEK_REVIEW: self.week_review,
            Job.WEEK_DRAFT: self.week_draft,
        }
        return by_job[Job(job)]


class JobRun(OwnedModel):
    """One attempt of one job for one user.

    ``week_start`` is the Monday of the week the job was about, empty for a job that is about no
    week. ``started_at`` and ``finished_at`` are the ends of the attempt. ``counts`` holds small
    numbers only (for example how many activities were new); nothing else is stored, so a run can
    never leak the text of a coach answer or of Intervals.icu.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    job = models.CharField(max_length=20, choices=Job.choices)
    week_start = models.DateField(null=True, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(default=timezone.now)
    outcome = models.CharField(max_length=10, choices=Outcome.choices)
    code = models.CharField(max_length=CODE_MAX, blank=True)
    counts = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(job__in=list(Job.values)), name="jobs_run_job_known"
            ),
            models.CheckConstraint(
                condition=Q(outcome__in=list(Outcome.values)), name="jobs_run_outcome_known"
            ),
            models.CheckConstraint(
                # A run that succeeded needs no explanation; the others need one word.
                condition=Q(outcome=Outcome.DONE, code="") | ~Q(code=""),
                name="jobs_run_code_when_not_done",
            ),
            models.CheckConstraint(
                condition=Q(week_start__isnull=True) | Q(week_start__iso_week_day=1),
                name="jobs_run_week_is_a_monday",
            ),
        ]
        indexes = [models.Index(fields=["owner", "job", "week_start"], name="jobs_run_owner_job")]

    def __str__(self) -> str:
        return f"{self.job} run of user {self.owner_id}: {self.outcome} {self.code}".strip()
