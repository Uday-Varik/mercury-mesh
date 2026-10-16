"""Inter-agent message bus.

Every agent (manager, sourcing, voice workers, learning loop) communicates
ONLY through this bus, using the event catalog in agents/models.py.
That keeps the agents decoupled: v1 runs in-process with asyncio; later the
same interface can be backed by Redis pub/sub so voice workers run on
separate machines.

Delivery is best-effort fan-out: a crashing subscriber never takes down
the bus or the other agents.
"""
from __future__ import annotations

import asyncio
import inspect
from collections import defaultdict
from typing import Awaitable, Callable, Union

from .models import Event

Handler = Callable[[Event], Union[Awaitable[None], None]]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._history: list[Event] = []

    def subscribe(self, event_type: str, handler: Handler) -> Callable[[], None]:
        """Subscribe to an event type ('*' = all). Returns an unsubscribe fn."""
        self._subs[event_type].append(handler)

        def _unsub() -> None:
            try:
                self._subs[event_type].remove(handler)
            except ValueError:
                pass

        return _unsub

    async def publish(self, event: Event) -> None:
        self._history.append(event)
        handlers = list(self._subs.get(event.type, [])) + list(self._subs.get("*", []))
        pending = []
        for h in handlers:
            try:
                res = h(event)
                if inspect.isawaitable(res):
                    pending.append(res)
            except Exception:
                continue  # broken subscriber must not kill the bus
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def history(self, event_type: str | None = None) -> list[Event]:
        if event_type is None:
            return list(self._history)
        return [e for e in self._history if e.type == event_type]
