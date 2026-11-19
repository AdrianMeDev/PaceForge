"""One place to note an illness as an absence, scoped to the user.

``note_illness`` either stores a new illness period or extends an overlapping or adjacent one, so
that a repeated report does not pile up periods. Nothing is stored when the user is at the limit.
"""

from datetime import date, timedelta

from accounts.models import User

from .models import UnavailablePeriod
from .serializers import MAX_PERIODS


def note_illness(user: User, start: date, end: date) -> UnavailablePeriod | None:
    """Store ``start`` to ``end`` (both included) as an illness of ``user``.

    An overlapping or adjacent illness period of the user is extended to cover the days instead;
    the model's ``clean`` checks the dates and the length. Returns the stored or extended period,
    or ``None`` when the user already has ``MAX_PERIODS`` periods and none of them covers the days.
    """
    periods = UnavailablePeriod.objects.for_user(user)
    existing = periods.filter(kind=UnavailablePeriod.Kind.ILLNESS).order_by("start_date")
    for period in existing:
        # Adjacent counts as touching: the day before the start and the day after the end.
        one_day = timedelta(days=1)
        if period.start_date <= end + one_day and start <= period.end_date + one_day:
            period.start_date = min(period.start_date, start)
            period.end_date = max(period.end_date, end)
            period.full_clean()
            period.save()
            return period
    if periods.count() >= MAX_PERIODS:
        return None
    period = UnavailablePeriod(
        owner=user, kind=UnavailablePeriod.Kind.ILLNESS, start_date=start, end_date=end
    )
    period.full_clean()
    period.save()
    return period
