"""RuleSet protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .events import GameEvent
from .state import ScoreState


@runtime_checkable
class RuleSet(Protocol):
    """Modality-specific rules. Pure: same input → same output, no I/O."""

    @property
    def state(self) -> ScoreState: ...

    def apply(self, event: GameEvent) -> ScoreState:
        """Apply ``event`` and return the new (immutable) :class:`ScoreState`.

        Implementations must NEVER raise on invalid events — they should log a
        warning and return ``self.state`` unchanged.
        """
        ...
