import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import DateField, ExpressionWrapper, F, Q

from core.models import OwnedModel

# A day has 1440 minutes and a week 10080.
DAY_MINUTES_MAX = 1440
WEEK_MINUTES_MAX = 7 * DAY_MINUTES_MAX
LIMITATIONS_MAX = 1000
NOTE_MAX = 200
# The longest period of absence: a year (and a leap day).
PERIOD_MAX_DAYS = 366


class AvailabilitySettings(OwnedModel):
    """What a user says about their training time apart from the weekdays. One per user.

    The weekly budget caps what the weekdays add up to; empty means no cap. The limitations are
    free text for the coach and are never interpreted here.
    """

    weekly_budget_minutes = models.PositiveIntegerField(null=True, blank=True)
    limitations = models.CharField(max_length=LIMITATIONS_MAX, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner"], name="availability_one_settings_per_owner"),
            models.CheckConstraint(
                condition=Q(weekly_budget_minutes__isnull=True)
                | Q(weekly_budget_minutes__lte=WEEK_MINUTES_MAX),
                name="availability_budget_in_range",
            ),
        ]

    def __str__(self) -> str:
        # No limitations: they are free text from the user and have no business in logs.
        return f"Availability settings of user {self.owner_id}"

    def clean(self) -> None:
        super().clean()
        budget = self.weekly_budget_minutes
        if budget is not None and budget > WEEK_MINUTES_MAX:
            raise ValidationError(
                {"weekly_budget_minutes": f"Enter at most {WEEK_MINUTES_MAX} minutes (a week)."}
            )


class WeekdayMinutes(OwnedModel):
    """The minutes a user can train on one weekday. No row for a weekday means no time."""

    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    minutes = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "weekday"], name="availability_one_per_day"),
            models.CheckConstraint(
                condition=Q(weekday__gte=0, weekday__lte=6), name="availability_weekday_in_range"
            ),
            models.CheckConstraint(
                condition=Q(minutes__lte=DAY_MINUTES_MAX), name="availability_minutes_in_range"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_weekday_display()} of user {self.owner_id}"

    def clean(self) -> None:
        super().clean()
        if self.minutes is not None and self.minutes > DAY_MINUTES_MAX:
            raise ValidationError({"minutes": f"Enter at most {DAY_MINUTES_MAX} minutes (a day)."})


class UnavailablePeriod(OwnedModel):
    """Days on which a user cannot train: vacation, illness or something else.

    Both dates belong to the period. Periods may overlap; a day inside any of them offers no time.
    """

    class Kind(models.TextChoices):
        VACATION = "vacation", "Vacation"
        ILLNESS = "illness", "Illness"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    note = models.CharField(max_length=NOTE_MAX, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")), name="availability_period_ends_late"
            ),
            models.CheckConstraint(
                condition=Q(
                    end_date__lte=ExpressionWrapper(
                        F("start_date") + timedelta(days=PERIOD_MAX_DAYS - 1),
                        output_field=DateField(),
                    )
                ),
                name="availability_period_not_too_long",
            ),
        ]

    def __str__(self) -> str:
        # No note: it is free text from the user and has no business in logs and admin lists.
        return f"{self.kind} period of user {self.owner_id}"

    def clean(self) -> None:
        super().clean()
        if self.start_date is None or self.end_date is None:
            return  # the field checks have already said so
        if self.end_date < self.start_date:
            raise ValidationError({"end_date": "The end cannot be before the start."})
        if (self.end_date - self.start_date).days >= PERIOD_MAX_DAYS:
            raise ValidationError(
                {"end_date": f"A period can last at most {PERIOD_MAX_DAYS} days."}
            )
