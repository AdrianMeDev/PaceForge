"""Asking the user's own coach to comment on a week.

``comment_on`` builds the briefing of the week (``reviews.briefing``: numbers only), asks the coach,
reads the answer through the strict reader and stores the comment. If the answer cannot be read the
coach is told what was wrong, once, and may try again; nothing more is asked.

No database transaction is held while the provider answers (a call can take a minute). A comment
that was asked for again replaces the earlier one, but only when a new one could be read: a failed
try leaves the old comment alone. What is stored of a call is the usage record of
``coach.services`` (facts, never text).
"""

from datetime import date, datetime

from django.utils import timezone

from accounts.models import User
from coach import services as coach
from coach.models import AIUsageRecord
from coach.providers.base import Message

from .briefing import build_briefing
from .models import WeekComment
from .prompt import (
    SYSTEM_PROMPT,
    CommentFormatError,
    Problem,
    extract_comment,
    first_message,
    repair_message,
)
from .services import has_anything, week_review

# The most the coach may write for a comment (tokens): the comment is at most 600 characters. An
# answer that is cut off is not used.
COMMENT_MAX_TOKENS = 1000
# One try and one repair.
ATTEMPTS = 2


class NothingToReview(Exception):
    """The week has no confirmed plan, no activity and no feedback: there is nothing to look back
    on, so the coach is not asked (and nothing is paid)."""


class CommentNotUsable(Exception):
    """The coach did not give a readable comment, not even after being told what was wrong.
    ``problems`` says what was wrong with the last answer (fixed texts, nothing of the answer)."""

    def __init__(self, problems: tuple[Problem, ...]) -> None:
        super().__init__("The coach did not give a usable comment.")
        self.problems = problems


def comment_on(user: User, monday: date) -> WeekComment:
    """Ask the coach of ``user`` about the week that starts on ``monday`` and store its comment.

    Raises ``reviews.services.WeekNotReviewable`` and ``NothingToReview`` (both before anything is
    sent, so before the provider is even looked at), ``coach.services.NotConfiguredError`` (no
    provider chosen), the errors of the provider (``coach.providers.base.ProviderError``) if it
    could not be reached or refused, and ``CommentNotUsable`` if no readable comment came of it.
    """
    review = week_review(user, monday)  # raises WeekNotReviewable
    if not has_anything(review):
        raise NothingToReview
    messages = [first_message(build_briefing(review))]
    problems: tuple[Problem, ...] = ()
    for attempt in range(1, ATTEMPTS + 1):
        completion = coach.call(
            user,
            AIUsageRecord.Purpose.WEEK_REVIEW,
            SYSTEM_PROMPT,
            messages,
            COMMENT_MAX_TOKENS,
            json_output=True,
        )
        if completion.truncated:
            problems = (
                Problem("", "The answer was cut off before its end; make the comment shorter."),
            )
        else:
            try:
                found = extract_comment(completion.text)
            except CommentFormatError as error:
                problems = error.problems
            else:
                stored, _ = WeekComment.objects.update_or_create(
                    owner=user,
                    week_start=monday,
                    defaults={
                        "comment": found.text,
                        "next_week": found.next_week,
                        "created_at": _now(),
                    },
                )
                return stored
        if attempt < ATTEMPTS:
            answer = completion.text if completion.text.strip() else "(no answer)"
            messages = [messages[0], Message("assistant", answer), repair_message(problems)]
    raise CommentNotUsable(problems)


def _now() -> datetime:
    return timezone.now()
