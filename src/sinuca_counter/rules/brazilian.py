"""Brazilian sinuca rules.

Default scoring follows the snooker-style values widely used in Brazilian
sinuca: amarela=1, vermelha=2, verde=3, marrom=4, azul=5, rosa=6, preta=7.
The black ball ("bolão", :data:`BallColor.PRETA_BOLA_7`) is special: pocketing
it ends the rack. By default it counts +7 to whoever pocketed it last; the
``bolao_premature_penalty`` flag swaps to a stricter variant where pocketing
the bolão while colours remain on the table loses the rack.
"""

from __future__ import annotations

import logging

from .events import (
    BallPocketed,
    GameEvent,
    ManualAdjustment,
    TurnEnded,
    Undo,
)
from .state import BallColor, PlayerId, ScoreState, TimelineEntry

log = logging.getLogger(__name__)

DEFAULT_POINTS: dict[BallColor, int] = {
    BallColor.AMARELA: 1,
    BallColor.VERMELHA: 2,
    BallColor.VERDE: 3,
    BallColor.MARROM: 4,
    BallColor.AZUL: 5,
    BallColor.ROSA: 6,
    BallColor.PRETA_BOLA_7: 7,
}

INITIAL_BALLS: dict[BallColor, int] = dict.fromkeys(DEFAULT_POINTS, 1)

MAX_TIMELINE_ENTRIES = 40


class BrazilianRules:
    """In-memory rules engine for sinuca brasileira."""

    def __init__(
        self,
        p1_name: str = "P1",
        p2_name: str = "P2",
        starting_player: PlayerId = "p1",
        bolao_premature_penalty: bool = False,
    ) -> None:
        self._points = dict(DEFAULT_POINTS)
        self._bolao_premature_penalty = bolao_premature_penalty
        self._state = ScoreState(
            p1_name=p1_name,
            p2_name=p2_name,
            current_player=starting_player,
            balls_remaining=dict(_initial_balls_str()),
            rules_name="brasileira",
        )
        # History of (event, prev_state) for undo. prev_state is the state
        # *before* the event was applied.
        self._history: list[tuple[GameEvent, ScoreState]] = []

    # -- RuleSet protocol --------------------------------------------------

    @property
    def state(self) -> ScoreState:
        return self._state

    def apply(self, event: GameEvent) -> ScoreState:
        try:
            new_state = self._dispatch(event)
        except Exception as exc:  # pragma: no cover - defensive belt-and-braces
            log.warning("rules engine ignored event %r due to %r", event, exc)
            return self._state
        if new_state is None:
            return self._state
        if not isinstance(event, Undo):
            self._history.append((event, self._state))
        self._state = new_state
        return self._state

    # -- dispatch ----------------------------------------------------------

    def _dispatch(self, event: GameEvent) -> ScoreState | None:
        if isinstance(event, BallPocketed):
            return self._on_ball_pocketed(event)
        if isinstance(event, TurnEnded):
            return self._on_turn_ended(event)
        if isinstance(event, ManualAdjustment):
            return self._on_manual(event)
        if isinstance(event, Undo):
            return self._on_undo()
        log.warning("unknown event type %r ignored", type(event).__name__)
        return None

    # -- handlers ----------------------------------------------------------

    def _on_ball_pocketed(self, event: BallPocketed) -> ScoreState | None:
        if self._state.paused:
            log.info("ball %s ignored: rules engine is paused", event.color)
            return None
        balls = dict(self._state.balls_remaining)
        key = event.color.value
        if balls.get(key, 0) <= 0:
            log.warning("ball %s already accounted for; ignoring", key)
            return None
        balls[key] = balls[key] - 1
        points = self._points.get(event.color, 0)
        is_bolao = event.color is BallColor.PRETA_BOLA_7
        coloured_left = sum(v for k, v in balls.items() if k != BallColor.PRETA_BOLA_7.value)
        loses_rack = is_bolao and self._bolao_premature_penalty and coloured_left > 0

        scorer: PlayerId
        if loses_rack:
            scorer = "p2" if self._state.current_player == "p1" else "p1"
        else:
            scorer = self._state.current_player

        p1 = self._state.p1_score
        p2 = self._state.p2_score
        if scorer == "p1":
            p1 += points
        else:
            p2 += points

        timeline = self._push_timeline(
            self._state.timeline,
            TimelineEntry(
                t_ms=event.t_ms,
                kind="ball_pocketed",
                description=(
                    f"{event.color.value} (+{points}) → "
                    f"{self._state.p1_name if scorer == 'p1' else self._state.p2_name}"
                    + (" [bolão prematuro]" if loses_rack else "")
                ),
            ),
        )
        return self._state.with_changes(
            p1_score=p1,
            p2_score=p2,
            balls_remaining=balls,
            pocketed_this_turn=self._state.pocketed_this_turn + 1,
            timeline=timeline,
        )

    def _on_turn_ended(self, event: TurnEnded) -> ScoreState | None:
        if self._state.paused:
            return None
        # Trust the explicit count from the event (spec contract). Fall back to
        # the engine's internal counter only if the vision pipeline didn't send
        # one.
        pocketed = (
            event.pocketed_this_turn
            if event.pocketed_this_turn is not None
            else self._state.pocketed_this_turn
        )
        if pocketed == 0:
            new_player: PlayerId = "p2" if self._state.current_player == "p1" else "p1"
            timeline = self._push_timeline(
                self._state.timeline,
                TimelineEntry(
                    t_ms=event.t_ms,
                    kind="turn_change",
                    description=f"vez passou para "
                    f"{self._state.p2_name if new_player == 'p2' else self._state.p1_name}",
                ),
            )
            return self._state.with_changes(
                current_player=new_player,
                pocketed_this_turn=0,
                timeline=timeline,
            )
        # Player keeps the cue but turn counter resets.
        return self._state.with_changes(pocketed_this_turn=0)

    def _on_manual(self, event: ManualAdjustment) -> ScoreState | None:
        if event.op == "adjust":
            if event.player not in ("p1", "p2") or event.delta is None:
                log.warning("invalid adjust event: %r", event)
                return None
            p1 = self._state.p1_score
            p2 = self._state.p2_score
            if event.player == "p1":
                p1 += event.delta
            else:
                p2 += event.delta
            return self._state.with_changes(
                p1_score=p1,
                p2_score=p2,
                timeline=self._push_timeline(
                    self._state.timeline,
                    TimelineEntry(
                        t_ms=event.t_ms,
                        kind="manual_adjust",
                        description=f"{event.player} {event.delta:+d}",
                    ),
                ),
            )
        if event.op == "set_score":
            if event.p1_score is None or event.p2_score is None:
                log.warning("invalid set_score event: %r", event)
                return None
            return self._state.with_changes(
                p1_score=event.p1_score,
                p2_score=event.p2_score,
                timeline=self._push_timeline(
                    self._state.timeline,
                    TimelineEntry(
                        t_ms=event.t_ms,
                        kind="manual_set_score",
                        description=f"placar = {event.p1_score} x {event.p2_score}",
                    ),
                ),
            )
        if event.op == "swap_turn":
            new_player: PlayerId = "p2" if self._state.current_player == "p1" else "p1"
            return self._state.with_changes(
                current_player=new_player,
                pocketed_this_turn=0,
                timeline=self._push_timeline(
                    self._state.timeline,
                    TimelineEntry(
                        t_ms=event.t_ms,
                        kind="manual_swap_turn",
                        description=f"vez forçada para {new_player}",
                    ),
                ),
            )
        if event.op == "rename":
            return self._state.with_changes(
                p1_name=event.p1_name or self._state.p1_name,
                p2_name=event.p2_name or self._state.p2_name,
            )
        if event.op == "correct_last":
            if event.color is None:
                log.warning("correct_last requires a color")
                return None
            return self._correct_last_pocket(event.color, event.t_ms)
        if event.op == "pause":
            return self._state.with_changes(paused=True)
        if event.op == "resume":
            return self._state.with_changes(paused=False)
        if event.op == "reset":
            return ScoreState(
                p1_name=self._state.p1_name,
                p2_name=self._state.p2_name,
                current_player="p1",
                balls_remaining=dict(_initial_balls_str()),
                rules_name="brasileira",
            )
        if event.op == "start_match":
            return self._state.with_changes(
                match_started=True,
                timeline=self._push_timeline(
                    self._state.timeline,
                    TimelineEntry(
                        t_ms=event.t_ms,
                        kind="match_start",
                        description="partida iniciada",
                    ),
                ),
            )
        if event.op == "stop_match":
            return self._state.with_changes(
                match_started=False,
                timeline=self._push_timeline(
                    self._state.timeline,
                    TimelineEntry(
                        t_ms=event.t_ms,
                        kind="match_stop",
                        description="partida pausada",
                    ),
                ),
            )
        log.warning("unknown manual op %r", event.op)
        return None

    def _on_undo(self) -> ScoreState | None:
        if not self._history:
            log.info("undo requested but history is empty")
            return None
        _event, prev_state = self._history.pop()
        return prev_state

    # -- helpers -----------------------------------------------------------

    def _correct_last_pocket(self, new_color: BallColor, t_ms: int) -> ScoreState | None:
        # Find the most recent BallPocketed in history.
        for idx in range(len(self._history) - 1, -1, -1):
            event, prev_state = self._history[idx]
            if isinstance(event, BallPocketed):
                # Roll back to before the wrong pocket, then re-apply with the
                # corrected colour.
                self._state = prev_state
                self._history = self._history[:idx]
                corrected = BallPocketed(
                    color=new_color, pocket_id=event.pocket_id, t_ms=t_ms or event.t_ms
                )
                return self.apply(corrected)
        log.info("correct_last requested but no BallPocketed in history")
        return None

    @staticmethod
    def _push_timeline(
        existing: tuple[TimelineEntry, ...], entry: TimelineEntry
    ) -> tuple[TimelineEntry, ...]:
        new = (*existing, entry)
        if len(new) > MAX_TIMELINE_ENTRIES:
            new = new[-MAX_TIMELINE_ENTRIES:]
        return new


def _initial_balls_str() -> dict[str, int]:
    return {color.value: count for color, count in INITIAL_BALLS.items()}


__all__ = ["DEFAULT_POINTS", "INITIAL_BALLS", "BrazilianRules"]
