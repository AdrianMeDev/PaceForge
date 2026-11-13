"""Reading a user's thresholds from their Intervals.icu sport settings.

Only the user's own connection and key are used, and only rows with the source ``intervals`` are
written: a value the user typed in, or an estimate, is never touched.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from integrations import services as integrations
from integrations.intervals import SportSettings

from .models import AthleteProfile, ThresholdValue
from .thresholds import whole_number

BASIS = "Read from your Intervals.icu sport settings"
METRICS = ("ftp", "lthr", "max_hr", "threshold_pace")


def sync_from_intervals(user: User) -> None:
    """Replace the user's Intervals.icu values by what Intervals.icu says now.

    A value that Intervals.icu no longer has, or that is outside what a person can do, is
    removed. Raises ``NotConnectedError`` and the errors of the client (``InvalidKeyError``,
    ``IntervalsUnavailableError``, ``UnexpectedResponseError``); in each case nothing is changed,
    and the time of the last sync stays as it was.
    """
    found = integrations.with_client(user, lambda client: client.get_sport_settings())
    wanted = _usable_values(user, found)

    with transaction.atomic():
        profile, _ = AthleteProfile.objects.get_or_create(owner=user)
        # Two syncs of the same user wait for each other instead of racing.
        profile = AthleteProfile.objects.select_for_update().get(pk=profile.pk)
        stored = {
            (row.sport, row.metric): row
            for row in ThresholdValue.objects.for_user(user).filter(
                source=ThresholdValue.Source.INTERVALS
            )
        }
        for key, row in stored.items():
            if key not in wanted:
                row.delete()
        for (sport, metric), value in wanted.items():
            current = stored.get((sport, metric))
            if current is not None and current.value == value and current.basis == BASIS:
                continue  # unchanged: keep the time it was last changed
            ThresholdValue.objects.update_or_create(
                owner=user,
                sport=sport,
                metric=metric,
                source=ThresholdValue.Source.INTERVALS,
                defaults={"value": value, "basis": BASIS},
            )
        profile.intervals_synced_at = timezone.now()
        profile.save(update_fields=["intervals_synced_at"])


def _usable_values(user: User, found: list[SportSettings]) -> dict[tuple[str, str], float]:
    wanted: dict[tuple[str, str], float] = {}
    for settings in found:
        for metric in METRICS:
            value = getattr(settings, metric)
            if value is None:
                continue
            try:
                wanted[(settings.sport, metric)] = whole_number(
                    user, settings.sport, metric, ThresholdValue.Source.INTERVALS, value
                )
            except ValidationError:
                continue  # outside the range of a person, or no such threshold for the sport
    return wanted
