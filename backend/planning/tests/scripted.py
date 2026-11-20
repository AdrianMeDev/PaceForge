from collections.abc import Callable
from typing import Any

from coach.providers.base import Completion, Deadline, Message


class Scripted:
    """A provider that answers from a list, and remembers what it was asked."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, list[Message], int]] = []
        self.json_outputs: list[bool] = []
        self.deadlines: list[Deadline | None] = []
        self.before_answer: Callable[[], None] | None = None

    def complete(
        self,
        system: str,
        messages: Any,
        max_tokens: int,
        json_output: bool = False,
        deadline: Deadline | None = None,
    ) -> Completion:
        self.calls.append((system, list(messages), max_tokens))
        self.json_outputs.append(json_output)
        self.deadlines.append(deadline)
        if self.before_answer:
            self.before_answer()
            self.before_answer = None
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, str):
            return Completion(reply, 100, 50)
        assert isinstance(reply, Completion)
        return reply
