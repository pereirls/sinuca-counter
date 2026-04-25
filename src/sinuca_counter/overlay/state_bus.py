"""Pub/sub bus for ScoreState updates.

Decouples the rules engine from the WebSocket layer: the engine pushes a new
:class:`ScoreState` and any subscriber (typically WebSocket connections) gets
notified. The bus is asyncio-based and thread-safe via the supplied loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sinuca_counter.rules.state import ScoreState


class StateBus:
    """Holds the latest :class:`ScoreState` and broadcasts updates."""

    def __init__(self, initial: ScoreState | None = None) -> None:
        self._state: ScoreState = initial or ScoreState()
        self._subscribers: set[asyncio.Queue[ScoreState]] = set()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> ScoreState:
        return self._state

    async def publish(self, state: ScoreState) -> None:
        async with self._lock:
            self._state = state
            stale: list[asyncio.Queue[ScoreState]] = []
            for queue in self._subscribers:
                try:
                    queue.put_nowait(state)
                except asyncio.QueueFull:
                    stale.append(queue)
            for queue in stale:
                self._subscribers.discard(queue)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[ScoreState]]:
        queue: asyncio.Queue[ScoreState] = asyncio.Queue(maxsize=64)
        async with self._lock:
            self._subscribers.add(queue)
            queue.put_nowait(self._state)
        try:
            yield queue
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    def subscriber_count(self) -> int:
        return len(self._subscribers)


def state_to_payload(state: ScoreState) -> dict[str, Any]:
    return state.to_dict()


__all__ = ["StateBus", "state_to_payload"]
