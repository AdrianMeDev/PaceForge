"""The conversation with the coach: what the athlete writes, what the coach answers and the draft
that may come of it.

``send`` asks the coach (``chat.prompt``: the data, the last messages and the new one), reads the
answer strictly, lets the code do the actions on the week that can be changed (``chat.actions``)
and stores the result as a **new draft** of that week, which the athlete reads, confirms or
discards on the Week plan page. Nothing is confirmed or sent anywhere from here.

A message of the athlete is only stored together with its answer, so a failed request leaves
nothing behind to show again. If the coach does not give a usable answer, even after being told
what was wrong once, the athlete's message is kept with a fixed answer that says so. No database
transaction is held while the provider answers (a call can take a minute). What is stored of a
call at ``coach`` is the usage record (facts, never text).
"""

import unicodedata
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

from .actions import ActionFormatError, MarkSick, apply, read_actions
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
    return list(ChatMessage.objects.for_user(user).select_related("plan"))


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
    stored = _plan_to_change(user)
    plan = plans.load(user, stored.pk) if stored else WeekPlan(_this_week(today), ())
    told = [
        ("athlete" if message.role == ChatMessage.Role.USER else "coach", message.text)
        for message in ChatMessage.objects.for_user(user).order_by("-created_at", "-id")[
            :HISTORY_TOLD
        ]
    ][::-1]
    messages = [first_message(build_briefing(user, plan), told, text)]
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
                reply, changed, changes, sick = _understand(completion.text, plan, today)
            except (AnswerNotUsable, ActionFormatError) as error:
                problems = error.problems
            else:
                return _store(user, text, reply, stored, changed, changes, sick, today)
        if attempt < ATTEMPTS:
            answer = completion.text if completion.text.strip() else "(no answer)"
            messages = [messages[0], Message("assistant", answer), repair_message(problems)]
    return _store(user, text, NOT_USABLE, None, None, (), None, today)


def _understand(
    answer: str, plan: WeekPlan, today: date
) -> tuple[str, WeekPlan | None, tuple[str, ...], MarkSick | None]:
    """The reply, the changed plan, what changed and any illness action; ``None`` and no changes if
    the coach proposed nothing, or nothing that makes a difference."""
    found = extract_answer(answer)
    if not found.actions:
        return found.reply, None, (), None
    actions = read_actions(found.actions, plan, today)
    sick = next((action for action in actions if isinstance(action, MarkSick)), None)
    changed, changes = apply(plan, actions, today)
    if changed == plan:
        return found.reply, None, (), sick
    return found.reply, changed, changes, sick


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


def _plan_to_change(user: User) -> WeeklyPlan | None:
    """The plan the chat works on: the newest draft or confirmed version of the first week (this
    one, then the next ones) that has one."""
    for monday in plannable_weeks(user):
        found = (
            WeeklyPlan.objects.for_user(user)
            .filter(
                week_start=monday,
                status__in=[WeeklyPlan.Status.DRAFT, WeeklyPlan.Status.CONFIRMED],
            )
            .order_by("-version")
            .first()
        )
        if found is not None:
            return found
    return None
