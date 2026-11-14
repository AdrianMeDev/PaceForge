"""An in-memory Intervals.icu calendar that stands in for the client of the application."""

from collections.abc import Mapping
from typing import Any

from integrations.intervals import Event

Failure = Exception | None


class Calendar:
    """What Intervals.icu would hold, and the calls made to it."""

    def __init__(self) -> None:
        self.events: dict[int, dict[str, Any]] = {}
        self.calls: list[tuple[str, Any]] = []
        # One entry per upsert, consumed in order: what to raise instead of storing (None: store).
        self.upsert_failures: list[Failure] = []
        self.delete_failures: list[Failure] = []
        self.keys: list[str] = []
        self._next = 100

    def upsert(self, event: Mapping[str, Any]) -> Event:
        self.calls.append(("upsert", event["external_id"]))
        failure = self.upsert_failures.pop(0) if self.upsert_failures else None
        if failure is not None:
            raise failure
        for event_id, stored in self.events.items():
            if stored["external_id"] == event["external_id"]:
                self.events[event_id] = dict(event)
                return Event(event_id, event["external_id"])
        self._next += 1
        self.events[self._next] = dict(event)
        return Event(self._next, event["external_id"])

    def delete(self, event_id: int) -> None:
        self.calls.append(("delete", event_id))
        failure = self.delete_failures.pop(0) if self.delete_failures else None
        if failure is not None:
            raise failure
        self.events.pop(event_id, None)  # one that is gone counts as removed

    def count(self, kind: str) -> int:
        return sum(1 for call, _ in self.calls if call == kind)


class FakeClient:
    def __init__(self, calendar: Calendar, key: str) -> None:
        self._calendar = calendar
        calendar.keys.append(key)

    def upsert_event(self, event: Mapping[str, Any]) -> Event:
        return self._calendar.upsert(event)

    def delete_event(self, event_id: int) -> None:
        self._calendar.delete(event_id)
