"""Filling the season with the user's own coach.

``generate`` works out the skeleton, builds the briefing, asks the coach, reads the answer through
the strict parser, checks the plan against the skeleton and stores it as a draft. If the answer
cannot be read, or the plan has errors, the coach is told the problems and may try again, up to
``ATTEMPTS`` answers in all. The best plan wins: an unreadable later answer does not throw away a
readable earlier one, and a plan with fewer errors beats one with more.

No database transaction is held while the provider answers (a call can take a minute). A plan
with errors is still stored as a draft, so that the user sees what is wrong; it cannot be
confirmed. What is stored of a call is the usage record of ``coach.services`` (facts, never text).
"""

from dataclasses import dataclass

from accounts.models import User
from coach import services as coach
from coach.models import AIUsageRecord
from coach.providers.base import Message, ProviderError
from goals.services import today_of
from planning.prompt import repair_message
from planning.schema import PlanFormatError, Problem, Sport
from planning.validation import Report

from . import services
from .briefing import build_briefing
from .inputs import skeleton_for
from .models import SeasonPlanVersion
from .prompt import SEASON_MAX_TOKENS, SYSTEM_PROMPT, extract_plan, first_message
from .rules import SeasonContext, validate_season
from .schema import SeasonPlan

# The answers the coach may give for one season: one try and two repairs.
ATTEMPTS = 3
REASON = "Drafted by the coach"


class NothingToPlan(Exception):
    """No week of the skeleton offers any training time at all, so there is nothing to fill. The
    coach is not asked (and nothing is paid)."""


class PlanNotUsable(Exception):
    """The coach did not give a readable plan, not even after being told what was wrong.
    ``problems`` says what was wrong with the last answer (fixed texts, nothing of the answer)."""

    def __init__(self, problems: tuple[Problem, ...]) -> None:
        super().__init__("The coach did not give a usable plan.")
        self.problems = problems


@dataclass(frozen=True)
class Generated:
    plan: SeasonPlanVersion
    report: Report


@dataclass(frozen=True)
class _Attempt:
    """What one answer came to: a plan with its report, or the problems that kept it from being
    one."""

    answer: str
    plan: SeasonPlan | None
    report: Report | None
    problems: tuple[Problem, ...]

    @property
    def errors(self) -> int:
        return len(self.report.errors) if self.report else 0

    @property
    def sound(self) -> bool:
        return self.plan is not None and self.report is not None and self.report.valid


def generate(user: User) -> Generated:
    """Fill the season of ``user`` with their coach.

    Raises ``NothingToPlan`` (checked before anything is sent, so before the provider is even
    looked at), ``coach.services.NotConfiguredError`` (no provider chosen), the errors of the
    provider (``coach.providers.base.ProviderError``) if it could not be reached or refused, and
    ``PlanNotUsable`` if no readable plan came of it.
    """
    skeleton = skeleton_for(user)
    if not any(week.capacity_minutes for week in skeleton.weeks):
        raise NothingToPlan
    briefing = build_briefing(user, today_of(user), skeleton)
    context = SeasonContext(skeleton, frozenset(Sport(sport) for sport in briefing["sports"]))
    messages = [first_message(briefing)]
    best: _Attempt | None = None
    for attempt_number in range(1, ATTEMPTS + 1):
        try:
            completion = coach.call(
                user,
                AIUsageRecord.Purpose.SEASON_PLAN,
                SYSTEM_PROMPT,
                messages,
                SEASON_MAX_TOKENS,
                json_output=True,
            )
        except ProviderError, coach.NotConfiguredError:
            if best is None or best.plan is None:
                raise
            break  # keep what an earlier answer gave rather than lose it
        attempt = _assess(context, completion.text, completion.truncated)
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
    stored = services.save_draft(user, best.plan, context, reason=REASON)
    return Generated(stored, best.report)


def _assess(context: SeasonContext, text: str, truncated: bool) -> _Attempt:
    if truncated:
        problem = Problem("", "The answer was cut off before its end; make the plan shorter.")
        return _Attempt(text, None, None, (problem,))
    try:
        plan = extract_plan(text)
    except PlanFormatError as error:
        return _Attempt(text, None, None, error.problems)
    return _Attempt(text, plan, validate_season(plan, context), ())


def _no_worse(attempt: _Attempt, best: _Attempt) -> bool:
    return attempt.plan is not None and attempt.errors <= best.errors
