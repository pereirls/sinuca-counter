"""Rules engine — pure Python state machine for billiards scoring.

The rules engine never sees frames. It receives structured events
(:class:`BallPocketed`, :class:`TurnEnded`, :class:`ManualAdjustment`,
:class:`Undo`) and produces an updated :class:`ScoreState`.

Future modalities (snooker, English pool) plug in by implementing
:class:`RuleSet` without touching any other layer.
"""

from .base import RuleSet
from .brazilian import BrazilianRules
from .events import (
    BallPocketed,
    GameEvent,
    ManualAdjustment,
    TurnEnded,
    Undo,
    VisionEvent,
)
from .state import BallColor, ScoreState

__all__ = [
    "BallColor",
    "BallPocketed",
    "BrazilianRules",
    "GameEvent",
    "ManualAdjustment",
    "RuleSet",
    "ScoreState",
    "TurnEnded",
    "Undo",
    "VisionEvent",
]
