import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import DateField, ExpressionWrapper, F, Q

from core.models import OwnedModel

from .intensity import (
    DEFAULT_LEVEL,
    LIMIT_NAMES,
    LIMIT_RANGES,
    IntensityLevel,
    Limits,
    effective_limits,
    limit_problems,
)

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

# The parts of the day a session can be in, earliest first. The same values as
# ``planning.schema.Slot`` (a test keeps the two in step).
SLOTS: tuple[str, ...] = ("morning", "afternoon", "evening")


def default_slots() -> list[str]:
    """Every part of the day: what a weekday offers until the user says otherwise."""
    return list(SLOTS)


class AvailabilitySettings(OwnedModel):
    """What a user says about their training time apart from the weekdays. One per user.

    The weekly budget caps what the weekdays add up to; empty means no cap. The typical week is what
    the athlete calls a normal week of training, in minutes (empty: not given): a reference for the
    planning after a break, never a limit on what the weekdays offer. The sports are the ones the
    athlete wants in a plan (empty: none chosen, which means all of them) and ``stretching`` says
    whether stretching may be added to sessions. The limitations are free text and are never
    interpreted here.

    The intensity level sets the limits of the planning rules (``availability.intensity``); each of
    the four own limits replaces the level's value when it is set (empty: the level's value).
    """

    weekly_budget_minutes = models.PositiveIntegerField(null=True, blank=True)
    typical_weekly_minutes = models.PositiveIntegerField(null=True, blank=True)
    sports = models.JSONField(default=list, blank=True)
    stretching = models.BooleanField(default=False)
    limitations = models.CharField(max_length=LIMITATIONS_MAX, blank=True)
    intensity_level = models.CharField(
        max_length=20, choices=IntensityLevel.choices, default=DEFAULT_LEVEL
    )
    max_hard_days = models.PositiveSmallIntegerField(null=True, blank=True)
    progression_warning_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    progression_error_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    easy_share_percent = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(intensity_level__in=IntensityLevel.values),
                name="availability_intensity_level_known",
            ),
            *(
                models.CheckConstraint(
                    condition=Q(**{f"{name}__isnull": True})
                    | Q(**{f"{name}__gte": low, f"{name}__lte": high}),
                    name=f"availability_{name}_in_range",
                )
                for name, (low, high) in LIMIT_RANGES.items()
            ),
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
        if self.intensity_level in IntensityLevel.values:
            errors.update(limit_problems(self.intensity_level, self.own_limits))
        if errors:
            raise ValidationError(errors)

    @property
    def own_limits(self) -> dict[str, int | None]:
        """The own values of the limits by name, ``None`` where the level's value counts."""
        return {name: getattr(self, name) for name in LIMIT_NAMES}

    @property
    def limits(self) -> Limits:
        """The limits of the planning rules: the level's with the own values in their place."""
        return effective_limits(self.intensity_level, self.own_limits)

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


def effective_slots(stored: object) -> list[str]:
    """``stored`` (what a weekday row holds, or nothing) as the parts of the day that are open:
    the stored ones in the order of ``SLOTS``, and all of them if there is nothing usable."""
    if isinstance(stored, list) and stored:
        return [slot for slot in SLOTS if slot in stored]
    return default_slots()


class WeekdayMinutes(OwnedModel):
    """What a user can do on one weekday: the minutes, whether two sessions are allowed and in
    which parts of the day. No row for a weekday means no time, with two sessions allowed and every
    part of the day open (so that nothing changes for a user who never chose)."""

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
    double_allowed = models.BooleanField(default=True)
    slots = models.JSONField(default=default_slots, blank=True)

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
        slots = self.slots
        if not (
            isinstance(slots, list)
            and slots
            and all(isinstance(slot, str) and slot in SLOTS for slot in slots)
            and len(set(slots)) == len(slots)
        ):
            raise ValidationError(
                {"slots": "Use at least one of morning, afternoon and evening, each at most once."}
            )

    @property
    def open_slots(self) -> list[str]:
        """The parts of the day open on this weekday, in the order of ``SLOTS``."""
        return effective_slots(self.slots)


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
