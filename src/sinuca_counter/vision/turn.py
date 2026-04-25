"""Detects when motion has subsided long enough to call the turn over."""

from __future__ import annotations

from .events import TurnEnded
from .tracker import BallTracker


class TurnEndDetector:
    """Watches aggregate ball speed and emits :class:`TurnEnded` after a settle."""

    def __init__(
        self,
        tracker: BallTracker,
        *,
        speed_threshold: float = 1.5,
        settle_frames: int = 45,  # ≈ 1.5s at 30fps
    ) -> None:
        self._tracker = tracker
        self._speed_threshold = speed_threshold
        self._settle_frames = settle_frames
        self._still_for = 0
        self._was_moving = False
        self._pocketed_this_turn = 0

    def note_pocket(self) -> None:
        self._pocketed_this_turn += 1

    def evaluate(self, t_ms: int) -> list[TurnEnded]:
        agg_speed = sum(t.speed for t in self._tracker.visible_tracks())
        if agg_speed > self._speed_threshold:
            self._was_moving = True
            self._still_for = 0
            return []
        self._still_for += 1
        if not self._was_moving:
            return []
        if self._still_for < self._settle_frames:
            return []
        # Settled. Emit and reset.
        event = TurnEnded(
            pocketed_this_turn=self._pocketed_this_turn,
            t_ms=t_ms,
        )
        self._was_moving = False
        self._still_for = 0
        self._pocketed_this_turn = 0
        return [event]


__all__ = ["TurnEndDetector"]
