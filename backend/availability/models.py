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


class Sport(models.TextChoices):
    """The sports a plan can contain, in the order they are listed and stored. The same values as
    ``planning.schema.Sport`` (a test keeps the two in step)."""

    RUNNING = "running", "Running"
    CYCLING = "cycling", "Cycling"
    SWIMMING = "swimming", "Swimming"
    STRENGTH = "strength", "Strength"


SPORTS: tuple[str, ...] = tuple(Sport.values)


class AvailabilitySettings(OwnedModel):
    """What a user says about their training time apart from the weekdays. One per user.

    The weekly budget caps what the weekdays add up to; empty means no cap. The typical week is what
    the athlete calls a normal week of training, in minutes (empty: not given): a reference for the
    planning after a break, never a limit on what the weekdays offer. The sports are the ones the
    athlete wants in a plan (empty: none chosen, which means all of them) and ``stretching`` says
    whether stretching may be added to sessions. The limitations are free text and are never
    interpreted here.
    """

    weekly_budget_minutes = models.PositiveIntegerField(null=True, blank=True)
    typical_weekly_minutes = models.PositiveIntegerField(null=True, blank=True)
    sports = models.JSONField(default=list, blank=True)
    stretching = models.BooleanField(default=False)
    limitations = models.CharField(max_length=LIMITATIONS_MAX, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner"], name="availability_one_settings_per_owner"),
            models.CheckConstraint(
                condition=Q(weekly_budget_minutes__isnull=True)
                | Q(weekly_budget_minutes__lte=WEEK_MINUTES_MAX),
                name="availability_budget_in_range",
            ),
            models.CheckConstraint(
                condition=Q(typical_weekly_minutes__isnull=True)
                | Q(typical_weekly_minutes__lte=WEEK_MINUTES_MAX),
                name="availability_typical_week_in_range",
            ),
        ]

    def __str__(self) -> str:
        # No limitations: they are free text from the user and have no business in logs.
        return f"Availability settings of user {self.owner_id}"

    def clean(self) -> None:
        super().clean()
        errors = {}
        for name in ("weekly_budget_minutes", "typical_weekly_minutes"):
            minutes = getattr(self, name)
            if minutes is not None and minutes > WEEK_MINUTES_MAX:
                errors[name] = f"Enter at most {WEEK_MINUTES_MAX} minutes (a week)."
        sports = self.sports
        if not (
            isinstance(sports, list)
            and all(isinstance(sport, str) and sport in SPORTS for sport in sports)
            and len(set(sports)) == len(sports)
        ):
            errors["sports"] = "Use each of running, cycling, swimming and strength at most once."
        if errors:
            raise ValidationError(errors)

    @property
    def chosen_sports(self) -> list[str]:
        """The sports of the plan in the order of ``SPORTS``; all of them if none was chosen."""
        return effective_sports(self.sports)


def effective_sports(chosen: object) -> list[str]:
    """``chosen`` (what is stored, or nothing) as the list of sports a plan may use: the chosen
    ones in the order of ``SPORTS``, and all of them if none was chosen."""
    if isinstance(chosen, list) and chosen:
        return [sport for sport in SPORTS if sport in chosen]
    return list(SPORTS)


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
