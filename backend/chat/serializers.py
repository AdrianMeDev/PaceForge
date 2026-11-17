"""The shape of what the chat API answers: the messages as text, and what the code changed.

``changes`` are sentences made by the code (``chat.actions``), never the words of the coach; the
text of a message is the athlete's own or the coach's and is only ever shown as text.
"""

from typing import Any

from rest_framework import serializers

from .models import ChatMessage

_TIME = serializers.DateTimeField()


def message_data(message: ChatMessage) -> dict[str, Any]:
    plan = message.plan
    return {
        "id": str(message.id),
        "role": message.role,
        "text": message.text,
        "created_at": _TIME.to_representation(message.created_at),
        "changes": list(message.changes),
        "plan": None
        if plan is None
        else {"id": str(plan.pk), "week_start": plan.week_start.isoformat()},
    }


def messages_data(messages: list[ChatMessage]) -> dict[str, Any]:
    return {"messages": [message_data(message) for message in messages]}
