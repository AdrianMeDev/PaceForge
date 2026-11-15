"""The limitations of a user that count now: the ones that are current, newest first.

Healed entries are a record and nothing else. One query however many entries there are.
"""

from accounts.models import User

from .models import SPORTS, Limitation, LimitationStatus


def current_limitations(user: User) -> list[tuple[str, tuple[str, ...]]]:
    """``(body part, affected sports)`` of every current entry, the newest first. The sports come
    in the order of ``SPORTS``; none means no particular sport."""
    rows = (
        Limitation.objects.for_user(user)
        .filter(status=LimitationStatus.CURRENT)
        .order_by("-id")
        .values_list("body_part", "sports")
    )
    return [
        (
            body_part,
            tuple(sport for sport in SPORTS if isinstance(sports, list) and sport in sports),
        )
        for body_part, sports in rows
    ]
