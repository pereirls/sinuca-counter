"""Events accepted by :class:`RuleSet` implementations.

These dataclasses are the durable contract between the vision pipeline, the
manual control panel and the rules engine. They are versioned by *addition only*
— never rename or remove a field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .state import BallColor, PlayerId


@dataclass(frozen=True)
class BallPocketed:
    """A ball was pocketed (emitted by the vision pipeline)."""

    color: BallColor
    pocket_id: str
    t_ms: int


@dataclass(frozen=True)
class TurnEnded:
    """The cue ball stopped — the active turn is over."""

    pocketed_this_turn: int
    t_ms: int


@dataclass(frozen=True)
class ManualAdjustment:
    """Operator-driven correction issued from the control panel.

    ``op`` decides which fields are read:

    * ``"adjust"`` uses ``player`` and ``delta``.
    * ``"set_score"`` uses ``p1_score`` and ``p2_score``.
    * ``"swap_turn"`` uses no extra fields.
    * ``"rename"`` uses ``p1_name`` and ``p2_name``.
    * ``"correct_last"`` uses ``color`` (replaces the colour of the most
      recent :class:`BallPocketed`).
    * ``"pause"``, ``"resume"`` toggle the paused flag.
    * ``"reset"`` resets scores while keeping player names.
    * ``"start_match"`` marks the match as started (arms automatic scoring).
    * ``"stop_match"`` disarms automatic scoring (e.g. pause between frames).
    """

    op: Literal[
        "adjust",
        "set_score",
        "swap_turn",
        "rename",
        "correct_last",
        "pause",
        "resume",
        "reset",
        "start_match",
        "stop_match",
    ]
    t_ms: int = 0
    player: PlayerId | None = None
    delta: int | None = None
    p1_score: int | None = None
    p2_score: int | None = None
    p1_name: str | None = None
    p2_name: str | None = None
    color: BallColor | None = None


@dataclass(frozen=True)
class Undo:
    """Undo the last applied event."""

    t_ms: int = 0


VisionEvent = BallPocketed | TurnEnded
GameEvent = BallPocketed | TurnEnded | ManualAdjustment | Undo
