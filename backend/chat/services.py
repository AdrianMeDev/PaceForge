"""The conversation with the coach: what the athlete writes, what the coach answers and the draft
that may come of it.

``send`` asks the coach (``chat.prompt``: the data, the last messages and the new one), reads the
answer strictly, lets the code do the actions on the named week (or the first week in the briefing)
(``chat.actions``) and stores the result as a **new draft** of that week, which the athlete reads,
confirms or discards on the Week plan page. Nothing is confirmed or sent anywhere from here.

A message of the athlete is only stored together with its answer, so a failed request leaves
nothing behind to show again. If the coach does not give a usable answer, even after being told
what was wrong once, the athlete's message is kept with a fixed answer that says so. No database
transaction is held while the provider answers (a call can take a minute). What is stored of a
call at ``coach`` is the usage record (facts, never text).
"""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User
from availability.absences import note_illness
from coach import services as coach
from coach.models import AIUsageRecord
from coach.providers.base import Message
from goals.services import today_of
from planning import services as plans
from planning.generation import plannable_weeks
from planning.models import WeeklyPlan
from planning.schema import Problem, WeekPlan

from .actions import OTHER_WEEK_PROBLEM, ActionFormatError, MarkSick, apply, read_actions
from .briefing import build_briefing
from .models import USER_TEXT_MAX, ChatMessage
from .prompt import SYSTEM_PROMPT, AnswerNotUsable, extract_answer, first_message, repair_message

# How many of the last messages the coach is told with each request.
HISTORY_TOLD = 10
# The most the coach may write (tokens): a reply and a few actions.
CHAT_MAX_TOKENS = 2_000
# One try and one repair.
ATTEMPTS = 2
# The reason of a draft that came from the chat (shown on the Week plan page).
REASON = "Changed in the chat"
# Fixed note appended when the athlete reports a fever.
DOCTOR_HINT = (
    "Because you have a fever, do not train until it has been gone for a full day, "
    "and see a doctor if it lasts or gets worse."
)
# What the athlete is told when no usable answer came of the request.
NOT_USABLE = (
    "I could not turn that into a change of your plan. Please try again, "
    "or change the plan yourself on the Week plan page."
)
# What the athlete is told when the coach still tried to change more than one week at once.
ONE_WEEK_ONLY = (
    "I can only change one week at a time. Please tell me which week to change first, "
    "then ask for the next one."
)


@dataclass(frozen=True)
class Sent:
    """What ``send`` stored: the message of the athlete and the answer of the coach."""

    athlete: ChatMessage
    coach: ChatMessage


def clean_text(text: str) -> str:
    """The message of the athlete, trimmed. Raises ``ValidationError`` if it is empty, longer than
    ``USER_TEXT_MAX`` or has characters that are invisible or reorder text (line breaks are
    fine)."""
    stripped = text.strip()
    if stripped == "":
        raise ValidationError("Write a message.")
    if len(stripped) > USER_TEXT_MAX:
        raise ValidationError(f"Use at most {USER_TEXT_MAX} characters.")
    if any(
        unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"} and char not in "\n\t"
        for char in stripped
    ):
        raise ValidationError("The message must not contain control characters.")
    return stripped


def history(user: User) -> list[ChatMessage]:
    """The whole conversation, oldest first."""
    return list(ChatMessage.objects.for_user(user).select_related("plan", "season_plan"))


def clear(user: User) -> int:
    """Delete the conversation of ``user`` (not the drafts that came of it). Returns how many
    messages were deleted."""
    deleted, _ = ChatMessage.objects.for_user(user).delete()
    return deleted


def send(user: User, text: str) -> Sent:
    """Ask the coach of ``user`` with ``text`` and store the exchange.

    Raises ``ValidationError`` for a message that cannot be used (before anything else is looked
    at), ``coach.services.NotConfiguredError`` (no provider chosen) and the errors of the provider
    (``coach.providers.base.ProviderError``) if it could not be reached or refused; in each case
    nothing is stored.
    """
    text = clean_text(text)
    today = today_of(user)
    stored_plans = _plans_to_change(user)
    loaded = [plans.load(user, row.pk) for row in stored_plans]
    available = list(zip(stored_plans, loaded, strict=True))
    told = [
        ("athlete" if message.role == ChatMessage.Role.USER else "coach", message.text)
        for message in ChatMessage.objects.for_user(user).order_by("-created_at", "-id")[
            :HISTORY_TOLD
        ]
    ][::-1]
    messages = [first_message(build_briefing(user, loaded), told, text)]
    problems: tuple[Problem, ...] = ()
    for attempt in range(1, ATTEMPTS + 1):
        completion = coach.call(
            user,
            AIUsageRecord.Purpose.CHAT,
            SYSTEM_PROMPT,
            messages,
            CHAT_MAX_TOKENS,
            json_output=True,
        )
        if completion.truncated:
            problems = (Problem("", "The answer was cut off before its end; make it shorter."),)
        else:
            try:
                reply, parent, changed, changes, sick = _understand(
                    completion.text, available, today
                )
            except (AnswerNotUsable, ActionFormatError) as error:
                problems = error.problems
            else:
                return _store(user, text, reply, parent, changed, changes, sick, today)
        if attempt < ATTEMPTS:
            answer = completion.text if completion.text.strip() else "(no answer)"
            messages = [messages[0], Message("assistant", answer), repair_message(problems)]
    fallback = ONE_WEEK_ONLY if _names_other_week(problems) else NOT_USABLE
    return _store(user, text, fallback, None, None, (), None, today)


def _names_other_week(problems: Sequence[Problem]) -> bool:
    return any(problem.message == OTHER_WEEK_PROBLEM for problem in problems)


def _understand(
    answer: str,
    available: Sequence[tuple[WeeklyPlan, WeekPlan]],
    today: date,
) -> tuple[str, WeeklyPlan | None, WeekPlan | None, tuple[str, ...], MarkSick | None]:
    """The reply, the parent plan, the changed plan, what changed and any illness action; ``None``
    and no changes if the coach proposed nothing, or nothing that makes a difference."""
    found = extract_answer(answer)
    stored, plan = _pick_week(found.week, available, today)
    if not found.actions:
        return found.reply, None, None, (), None
    others = [other for _, other in available if other.week_start != plan.week_start]
    actions = read_actions(found.actions, plan, today, other_weeks=others)
    sick = next((action for action in actions if isinstance(action, MarkSick)), None)
    changed, changes = apply(plan, actions, today)
    if changed == plan:
        return found.reply, None, None, (), sick
    return found.reply, stored, changed, changes, sick


def _pick_week(
    wanted: date | None,
    available: Sequence[tuple[WeeklyPlan, WeekPlan]],
    today: date,
) -> tuple[WeeklyPlan | None, WeekPlan]:
    if wanted is None:
        return available[0] if available else (None, WeekPlan(_this_week(today), ()))
    for row, plan in available:
        if plan.week_start == wanted:
            return row, plan
    raise AnswerNotUsable((Problem("week", "This week is not in the weeks that can be changed."),))


def _store(
    user: User,
    text: str,
    reply: str,
    parent: WeeklyPlan | None,
    changed: WeekPlan | None,
    changes: tuple[str, ...],
    sick: MarkSick | None,
    today: date,
) -> Sent:
    draft: WeeklyPlan | None = None
    if parent is not None and changed is not None:
        draft = plans.save_draft(user, changed, reason=REASON, parent=parent.pk)
    if sick is not None and sick.fever:
        reply = f"{reply}\n\n{DOCTOR_HINT}"
    with transaction.atomic():
        stored_changes = list(changes) if draft else []
        if sick is not None:
            end = today + timedelta(days=sick.days - 1)
            period = note_illness(user, today, end)
            if period is not None:
                span = (
                    today.isoformat()
                    if sick.days == 1
                    else f"{today.isoformat()} to {end.isoformat()}"
                )
                stored_changes.append(f"Illness noted as an absence ({span})")
        athlete = ChatMessage.objects.create(owner=user, role=ChatMessage.Role.USER, text=text)
        answered = ChatMessage.objects.create(
            owner=user,
            role=ChatMessage.Role.COACH,
            text=reply,
            plan=draft,
            changes=stored_changes,
        )
    return Sent(athlete, answered)


def _this_week(today: date) -> date:
    return today - timedelta(days=today.weekday())


def _plans_to_change(user: User) -> list[WeeklyPlan]:
    """The newest draft or confirmed version of every plannable week that has one, in order."""
    mondays = plannable_weeks(user)
    rows = (
        WeeklyPlan.objects.for_user(user)
        .filter(
            week_start__in=mondays,
            status__in=[WeeklyPlan.Status.DRAFT, WeeklyPlan.Status.CONFIRMED],
        )
        .order_by("week_start", "-version")
    )
    newest: dict[date, WeeklyPlan] = {}
    for row in rows:
        newest.setdefault(row.week_start, row)
    return [newest[monday] for monday in mondays if monday in newest]
