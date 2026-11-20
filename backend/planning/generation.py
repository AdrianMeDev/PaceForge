"""Drafting a week with the user's own coach.

``generate`` builds the briefing, asks the coach, reads the answer through the strict parser,
checks the plan with the rules and stores it as a draft. If the answer cannot be read, or the plan
has errors, the coach gets the problems once and may try again; nothing more is asked. The best
plan wins: an unreadable second answer does not throw away a readable first one.

No database transaction is held while the provider answers (a call can take a minute). The plan
is checked against what the user can do *after* the answer came in, as that is what confirming
will check too. A plan with training-rule errors is still stored as a draft, so that the user
sees what is wrong; it cannot be confirmed. Out-of-week workouts must be repaired before storage.
What is stored of a call is the usage record of ``coach.services``
(facts, never text).
"""

from dataclasses import dataclass
from datetime import date, timedelta

from accounts.models import User
from coach import services as coach
from coach.models import AIUsageRecord
from coach.providers.base import Message, ProviderError
from goals.services import today_of

from . import services
from .briefing import build_briefing
from .context import build_context
from .models import WeeklyPlan
from .prompt import SYSTEM_PROMPT, extract_plan, first_message, repair_message
from .schema import PlanFormatError, Problem, WeekPlan
from .validation import Report, validate_week

# The current week and this many weeks after it can be planned.
WEEKS_AHEAD = 4
# The most the coach may write for one plan (tokens). A plan at every limit of the format would
# need more; an answer that is cut off is not used.
PLAN_MAX_TOKENS = 8000
# One try and one repair.
ATTEMPTS = 2
REASON = "Drafted by the coach"


class WeekNotPlannable(Exception):
    """The week is not one of ``plannable_weeks``."""


class NoTimeAvailable(Exception):
    """The week offers no training time at all: nothing on any day, a weekly budget of 0, or away
    the whole week. There is nothing to plan, so the coach is not asked (and nothing is paid)."""


class PlanNotUsable(Exception):
    """The coach did not give a storable plan, not even after being told what was wrong.
    ``problems`` says what was wrong with the last answer (fixed texts, nothing of the answer)."""

    def __init__(self, problems: tuple[Problem, ...]) -> None:
        super().__init__("The coach did not give a usable plan.")
        self.problems = problems


@dataclass(frozen=True)
class Generated:
    plan: WeeklyPlan
    report: Report


@dataclass(frozen=True)
class _Attempt:
    """What one answer came to: a plan with its report, or the problems that kept it from being
    one."""

    answer: str
    plan: WeekPlan | None
    report: Report | None
    problems: tuple[Problem, ...]

    @property
    def errors(self) -> int:
        return len(self.report.errors) if self.report else 0

    @property
    def sound(self) -> bool:
        return self.plan is not None and self.report is not None and self.report.valid


def plannable_weeks(user: User) -> tuple[date, ...]:
    """The Mondays of the weeks that can be planned: this week and the next ``WEEKS_AHEAD``."""
    today = today_of(user)
    this_week = today - timedelta(days=today.weekday())
    return tuple(this_week + timedelta(weeks=n) for n in range(WEEKS_AHEAD + 1))


def generate(user: User, monday: date, note: str = "") -> Generated:
    """Draft the week that starts on ``monday`` with the coach of ``user``.

    ``note`` is what the athlete wants the coach to know about the week (a trip, a day without
    time, a niggle): at most ``NOTE_MAX`` characters of plain text. It is stored with the draft
    and told to the coach as data, a wish and never an instruction.

    Raises ``django.core.exceptions.ValidationError`` for a note that is too long or not plain
    text (before anything else is looked at), ``WeekNotPlannable``, ``NoTimeAvailable`` (checked
    before anything is sent, so before the provider is even looked at),
    ``coach.services.NotConfiguredError`` (no provider chosen),
    the errors of the provider (``coach.providers.base.ProviderError``) if it could not be
    reached or refused, and ``PlanNotUsable`` if no readable plan came of it.
    """
    note = services.clean_note(note)
    if monday not in plannable_weeks(user):
        raise WeekNotPlannable
    briefing = build_briefing(user, monday, note)
    if briefing["weekly_minutes_available"] == 0:
        raise NoTimeAvailable
    messages = [first_message(briefing)]
    best: _Attempt | None = None
    for attempt_number in range(1, ATTEMPTS + 1):
        try:
            completion = coach.call(
                user,
                AIUsageRecord.Purpose.WEEKLY_PLAN,
                SYSTEM_PROMPT,
                messages,
                PLAN_MAX_TOKENS,
                json_output=True,
            )
        except ProviderError, coach.NotConfiguredError:
            if best is None or best.plan is None:
                raise
            break  # keep what the first answer gave rather than lose it
        attempt = _assess(user, monday, completion.text, completion.truncated)
        # A readable plan beats an unreadable one and fewer errors beat more; a tie goes to the
        # later answer, which has been told what was wrong.
        if best is None or best.plan is None or _no_worse(attempt, best):
            best = attempt
        if attempt.sound or attempt_number == ATTEMPTS:
            break
        errors = attempt.report.errors if attempt.report else ()
        messages = [
            messages[0],
            Message("assistant", attempt.answer if attempt.answer.strip() else "(no answer)"),
            repair_message(attempt.problems, errors),
        ]
    assert best is not None
    if best.plan is None or best.report is None:
        raise PlanNotUsable(best.problems)
    stored = services.save_draft(user, best.plan, reason=REASON, note=note)
    return Generated(stored, best.report)


def _assess(user: User, monday: date, text: str, truncated: bool) -> _Attempt:
    if truncated:
        problem = Problem("", "The answer was cut off before its end; make the plan shorter.")
        return _Attempt(text, None, None, (problem,))
    try:
        plan = services.canonical(extract_plan(text, monday))
    except PlanFormatError as error:
        return _Attempt(text, None, None, error.problems)
    if problems := services.outside_week_problems(plan):
        return _Attempt(text, None, None, problems)
    report = validate_week(plan, build_context(user, monday))
    return _Attempt(text, plan, report, ())


def _no_worse(attempt: _Attempt, best: _Attempt) -> bool:
    return attempt.plan is not None and attempt.errors <= best.errors
