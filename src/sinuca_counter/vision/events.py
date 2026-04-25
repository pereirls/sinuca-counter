"""Events emitted by the vision pipeline.

Re-exports :class:`BallPocketed` and :class:`TurnEnded` from the rules module
to keep the contract symmetric: whatever the vision pipeline emits is exactly
what the rules engine consumes.
"""

from __future__ import annotations

from dataclasses import dataclass

from sinuca_counter.rules.events import BallPocketed, TurnEnded


@dataclass(frozen=True)
class CalibrationLost:
    """The pipeline can no longer locate the table corners reliably."""

    t_ms: int
    reason: str = ""


@dataclass(frozen=True)
class FrameProcessed:
    """Heartbeat — emitted after each processed frame so observers can tick."""

    t_ms: int
    n_tracks: int


VisionEvent = BallPocketed | TurnEnded | CalibrationLost | FrameProcessed


__all__ = [
    "BallPocketed",
    "CalibrationLost",
    "FrameProcessed",
    "TurnEnded",
    "VisionEvent",
]
