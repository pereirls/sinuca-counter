"""ScoreState and BallColor — the public state types."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Literal

PlayerId = Literal["p1", "p2"]


class BallColor(StrEnum):
    """Ball colors recognised by the system.

    The names are stable on the wire (string values used in JSON/log files).
    Future modalities can extend this enum with new members; existing members
    must never be renamed or removed so historical ``.replay.jsonl`` files keep
    parsing.
    """

    BRANCA = "branca"
    AMARELA = "amarela"
    VERMELHA = "vermelha"
    VERDE = "verde"
    MARROM = "marrom"
    AZUL = "azul"
    ROSA = "rosa"
    PRETA_BOLA_7 = "preta_bola_7"


@dataclass(frozen=True)
class TimelineEntry:
    """A single human-readable line for the operator timeline."""

    t_ms: int
    kind: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScoreState:
    """Public, serialisable snapshot of the match state.

    The overlay and control panel render directly from this dictionary. New
    modalities may *add* optional fields (with defaults) but never rename or
    remove existing ones.
    """

    p1_name: str = "P1"
    p2_name: str = "P2"
    p1_score: int = 0
    p2_score: int = 0
    current_player: PlayerId = "p1"
    pocketed_this_turn: int = 0
    balls_remaining: dict[str, int] = field(default_factory=dict)
    paused: bool = False
    detection_status: str = "ok"
    rules_name: str = ""
    timeline: tuple[TimelineEntry, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "p1_name": self.p1_name,
            "p2_name": self.p2_name,
            "p1_score": self.p1_score,
            "p2_score": self.p2_score,
            "current_player": self.current_player,
            "pocketed_this_turn": self.pocketed_this_turn,
            "balls_remaining": dict(self.balls_remaining),
            "paused": self.paused,
            "detection_status": self.detection_status,
            "rules_name": self.rules_name,
            "timeline": [entry.to_dict() for entry in self.timeline],
        }

    def with_changes(self, **kwargs: Any) -> ScoreState:
        """Return a copy with fields replaced (frozen-friendly)."""

        from dataclasses import replace

        return replace(self, **kwargs)
