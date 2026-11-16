"""What each sport is for the user: the rows of ``SportPreference`` as plain values.

One query however many sports there are (at most four rows). A sport without a row, or a row
without anything in it, says nothing and is not in the result.
"""

from accounts.models import User

from .models import SPORTS, SportPreference


def sport_preferences(user: User) -> list[tuple[str, str | None, int | None, int | None]]:
    """``(sport, role, sessions_min, sessions_max)`` for every sport the user said something
    about, in the order of ``SPORTS``; ``None`` for what they did not say."""
    rows = {
        sport: (role or None, low, high)
        for sport, role, low, high in SportPreference.objects.for_user(user).values_list(
            "sport", "role", "sessions_min", "sessions_max"
        )
    }
    return [
        (sport, *rows[sport])
        for sport in SPORTS
        if sport in rows and any(value is not None for value in rows[sport])
    ]
