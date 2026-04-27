"""Playback control for video sources.

Lets the operator pause/resume, seek and change playback speed of the
underlying video while the vision worker is running. Designed so commands
can be issued from the asyncio thread (HTTP handlers) and consumed from
the vision worker thread without races.

The split is intentional:

* :class:`PlaybackController` is the threadsafe shared state — commands
  go in via setters, the worker pulls them out and reports back its
  position.
* :class:`PlaybackBus` is an asyncio pub/sub for streaming snapshots to
  the browser. It mirrors the ``StateBus`` design but carries playback
  info instead of score state.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

# Guard rails: keep speed in a sane range so a frantic UI request can't
# starve the loop or overflow time math.
MIN_SPEED = 0.25
MAX_SPEED = 8.0


@dataclass(frozen=True)
class PlaybackState:
    """Immutable snapshot of the playback state, broadcast to clients."""

    paused: bool = False
    speed: float = 1.0
    current_time_ms: int = 0
    duration_ms: int = 0
    has_video: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "paused": self.paused,
            "speed": self.speed,
            "current_time_ms": self.current_time_ms,
            "duration_ms": self.duration_ms,
            "has_video": self.has_video,
        }


class PlaybackController:
    """Thread-safe shared state between HTTP handlers and the vision worker."""

    def __init__(self, *, has_video: bool, duration_ms: int = 0) -> None:
        self._lock = threading.Lock()
        self._paused = False
        self._speed = 1.0
        self._current_time_ms = 0
        self._duration_ms = max(0, duration_ms)
        self._has_video = has_video
        # Pending seek request, in milliseconds. The worker reads this
        # at the top of each iteration and, if non-None, seeks the source
        # before processing the next frame.
        self._pending_seek_ms: int | None = None

    # -- HTTP handler side -------------------------------------------------

    def set_paused(self, paused: bool) -> PlaybackState:
        with self._lock:
            self._paused = paused
            return self._snapshot_locked()

    def set_speed(self, speed: float) -> PlaybackState:
        clamped = max(MIN_SPEED, min(MAX_SPEED, speed))
        with self._lock:
            self._speed = clamped
            return self._snapshot_locked()

    def request_seek(self, ms: int) -> PlaybackState:
        with self._lock:
            target = max(0, ms)
            if self._duration_ms > 0:
                target = min(target, self._duration_ms)
            self._pending_seek_ms = target
            # Update reported position immediately so the UI is responsive
            # even if the worker is mid-frame.
            self._current_time_ms = target
            return self._snapshot_locked()

    # -- worker side -------------------------------------------------------

    def consume_seek(self) -> int | None:
        """Return any pending seek request, clearing it. Worker calls this."""

        with self._lock:
            target = self._pending_seek_ms
            self._pending_seek_ms = None
            return target

    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def speed(self) -> float:
        with self._lock:
            return self._speed

    def report_position(self, ms: int) -> None:
        with self._lock:
            self._current_time_ms = max(0, ms)

    # -- read helpers ------------------------------------------------------

    def snapshot(self) -> PlaybackState:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> PlaybackState:
        return PlaybackState(
            paused=self._paused,
            speed=self._speed,
            current_time_ms=self._current_time_ms,
            duration_ms=self._duration_ms,
            has_video=self._has_video,
        )


class PlaybackBus:
    """asyncio pub/sub for :class:`PlaybackState`. Mirrors :class:`StateBus`."""

    def __init__(self, initial: PlaybackState | None = None) -> None:
        self._state = initial or PlaybackState()
        self._subscribers: set[asyncio.Queue[PlaybackState]] = set()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> PlaybackState:
        return self._state

    async def publish(self, state: PlaybackState) -> None:
        async with self._lock:
            self._state = state
            stale: list[asyncio.Queue[PlaybackState]] = []
            for queue in self._subscribers:
                try:
                    queue.put_nowait(state)
                except asyncio.QueueFull:
                    stale.append(queue)
            for queue in stale:
                self._subscribers.discard(queue)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[PlaybackState]]:
        queue: asyncio.Queue[PlaybackState] = asyncio.Queue(maxsize=64)
        async with self._lock:
            self._subscribers.add(queue)
            queue.put_nowait(self._state)
        try:
            yield queue
        finally:
            async with self._lock:
                self._subscribers.discard(queue)


__all__ = [
    "MAX_SPEED",
    "MIN_SPEED",
    "PlaybackBus",
    "PlaybackController",
    "PlaybackState",
]
