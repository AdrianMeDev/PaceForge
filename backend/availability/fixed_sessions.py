"""The fixed appointments of a user as plain values.

One query however many entries there are.
"""

from accounts.models import User

from .models import SLOTS, SPORTS, FixedSession


def fixed_sessions(user: User) -> list[tuple[int, str, int, str | None]]:
    """``(weekday, sport, minutes, slot)`` of every entry, by weekday, then by part of the day (no
    part first), then by the order of ``SPORTS``; ``None`` for no part of the day."""
    rows = FixedSession.objects.for_user(user).values_list("weekday", "sport", "minutes", "slot")
    return sorted(
        ((weekday, sport, minutes, slot or None) for weekday, sport, minutes, slot in rows),
        key=lambda row: (row[0], SLOTS.index(row[3]) + 1 if row[3] else 0, SPORTS.index(row[1])),
    )
