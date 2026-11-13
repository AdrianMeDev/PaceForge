import gzip
import uuid
from typing import Self

from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import OwnedModel


class Activity(OwnedModel):
    """A finished activity with the summary values its source file reports.

    Every measurement may be empty: a value that the file does not contain is never estimated.
    Times are UTC; which local day an activity belongs to needs the user's time zone.
    """

    class Source(models.TextChoices):
        FIT_FILE = "fit_file", "FIT file"
        TCX_FILE = "tcx_file", "TCX file"

    class Sport(models.TextChoices):
        RUNNING = "running"
        CYCLING = "cycling"
        SWIMMING = "swimming"
        STRENGTH = "strength"
        OTHER = "other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    source = models.CharField(max_length=20, choices=Source.choices)
    # SHA-256 (hex) of the uploaded file: the same file cannot be imported twice by one user.
    source_hash = models.CharField(max_length=64)
    sport = models.CharField(max_length=20, choices=Sport.choices)
    # The sport as the file calls it, kept when ``sport`` had to fall back to ``other``.
    source_sport = models.CharField(max_length=50, blank=True)
    start_time = models.DateTimeField()
    elapsed_seconds = models.FloatField(null=True, blank=True)
    timer_seconds = models.FloatField(null=True, blank=True)
    distance_m = models.FloatField(null=True, blank=True)
    avg_heart_rate = models.PositiveSmallIntegerField(null=True, blank=True)
    max_heart_rate = models.PositiveSmallIntegerField(null=True, blank=True)
    avg_power_w = models.PositiveSmallIntegerField(null=True, blank=True)
    total_ascent_m = models.PositiveIntegerField(null=True, blank=True)
    calories = models.PositiveIntegerField(null=True, blank=True)
    manufacturer = models.CharField(max_length=50, blank=True)
    # One entry per lap: start, seconds, distance, heart rates (whatever the file reports).
    laps = models.JSONField(default=list, blank=True)
    # Best power and speed over fixed windows, from the file's time series (see ``efforts``).
    # Empty when not computed yet; ``{}`` when the file has no usable series.
    best_efforts = models.JSONField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "source_hash"], name="activities_one_per_file_and_owner"
            ),
            # The same run exported as FIT and as TCX has the same start and sport.
            models.UniqueConstraint(
                fields=["owner", "start_time", "sport"], name="activities_one_per_start_and_owner"
            ),
            models.CheckConstraint(
                condition=(Q(elapsed_seconds__isnull=True) | Q(elapsed_seconds__gte=0))
                & (Q(timer_seconds__isnull=True) | Q(timer_seconds__gte=0))
                & (Q(distance_m__isnull=True) | Q(distance_m__gte=0)),
                name="activities_measurements_not_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_sport_display()} {self.start_time:%Y-%m-%d %H:%M} (user {self.owner_id})"


class ActivityFile(models.Model):
    """The uploaded file of an activity, gzip-compressed, so later features can read more of it.

    It belongs to its activity and is reached only through it; deleting the activity deletes the
    file. It holds the whole track (GPS included), so it must never be part of an API answer.
    """

    activity = models.OneToOneField(
        Activity, on_delete=models.CASCADE, primary_key=True, related_name="file"
    )
    data = models.BinaryField(editable=False)
    original_size = models.PositiveIntegerField()

    def __str__(self) -> str:
        return f"File of activity {self.activity_id} ({self.original_size} bytes)"

    @classmethod
    def for_activity(cls, activity: Activity, content: bytes) -> Self:
        # ``gzip.compress`` writes no timestamp by default: the bytes depend on the content only.
        return cls(
            activity=activity,
            data=gzip.compress(content, compresslevel=6),
            original_size=len(content),
        )

    def read(self) -> bytes:
        return gzip.decompress(bytes(self.data))
