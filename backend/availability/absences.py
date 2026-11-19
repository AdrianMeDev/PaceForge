"""One place to note an absence of any kind, scoped to the user.

``note_absence`` either stores a new period or extends an overlapping or adjacent period of the
same kind, so that a repeated report does not pile up periods. Nothing is stored when the user is
at the limit. ``note_illness`` is the shortcut for an illness.
"""

from datetime import date, timedelta

from accounts.models import User

from .models import UnavailablePeriod
from .serializers import MAX_PERIODS


def note_absence(
    user: User, start: date, end: date, kind: str = UnavailablePeriod.Kind.ILLNESS
) -> UnavailablePeriod | None:
    """Store ``start`` to ``end`` (both included) as an absence of ``kind`` for ``user``.

    An overlapping or adjacent period of the same kind is extended to cover the days instead; a
    period of another kind is never merged, because the kinds mean different things. The model's
    ``clean`` checks the dates and the length. Returns the stored or extended period, or ``None``
    when the user already has ``MAX_PERIODS`` periods and none of them covers the days.
    """
    periods = UnavailablePeriod.objects.for_user(user)
    existing = periods.filter(kind=kind).order_by("start_date")
    one_day = timedelta(days=1)
    for period in existing:
        # Adjacent counts as touching: the day before the start and the day after the end.
        if period.start_date <= end + one_day and start <= period.end_date + one_day:
            period.start_date = min(period.start_date, start)
            period.end_date = max(period.end_date, end)
            period.full_clean()
            period.save()
            return period
    if periods.count() >= MAX_PERIODS:
        return None
    period = UnavailablePeriod(owner=user, kind=kind, start_date=start, end_date=end)
    period.full_clean()
    period.save()
    return period


def note_illness(user: User, start: date, end: date) -> UnavailablePeriod | None:
    """Store ``start`` to ``end`` (both included) as an illness of ``user``."""
    return note_absence(user, start, end, UnavailablePeriod.Kind.ILLNESS)
