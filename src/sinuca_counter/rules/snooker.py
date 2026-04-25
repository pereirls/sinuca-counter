"""Snooker rules — 6-red (European) and 15-red (English) variants.

Scoring values are the standard snooker table: red=1, yellow=2, green=3,
brown=4, blue=5, pink=6, black=7. The only difference between the two
variants is how many reds start on the table (6 for the European short
snooker; 15 for the classical English snooker).

This implementation is a practical MVP — it enforces the core flow rather
than the full foul rulebook:

* **Reds phase.** While any reds remain on the table, the player must pocket
  a red, then a colour, then a red, and so on. Reds stay down; pocketed
  colours are respotted (balls_remaining goes back to 1) until the reds are
  gone. Pocketing the wrong type of ball earns no points and ends the turn.
* **Colours phase.** Once all reds are gone, colours must be pocketed in
  ascending value order (yellow → green → brown → blue → pink → black).
  Each stays down once pocketed. Pocketing the wrong colour ends the turn.
  After the black falls, the frame is over — subsequent pocket events are
  ignored with a warning.
* **Same-player continuation.** A player keeps the cue whenever their shot
  was legal and pocketed at least one ball. A legal shot that pocketed zero
  balls, or any illegal shot (wrong ball, multiple balls pocketed in one
  shot including an illegal one) ends the turn.

Not modelled in the MVP (can be layered on via :class:`ManualAdjustment` by
the operator): free balls, fouls with specific penalty points paid to the
opponent, cue-ball fouls, and miss/re-rack variants.
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


# Points by colour in snooker.
SNOOKER_POINTS: dict[BallColor, int] = {
    BallColor.VERMELHA: 1,  # red
    BallColor.AMARELA: 2,  # yellow
    BallColor.VERDE: 3,  # green
    BallColor.MARROM: 4,  # brown
    BallColor.AZUL: 5,  # blue
    BallColor.ROSA: 6,  # pink
    BallColor.PRETA_BOLA_7: 7,  # black
}

# Finishing phase: colours in ascending value (exclude red).
FINISHING_ORDER: list[BallColor] = [
    BallColor.AMARELA,
    BallColor.VERDE,
    BallColor.MARROM,
    BallColor.AZUL,
    BallColor.ROSA,
    BallColor.PRETA_BOLA_7,
]

# Sentinel target values stored in ScoreState.target_ball.
TARGET_RED = BallColor.VERMELHA.value
TARGET_COLOUR_ANY = "colour"
TARGET_FRAME_OVER = ""

MAX_TIMELINE_ENTRIES = 40


class SnookerRules:
    """Rules engine for snooker (6-red European or 15-red English)."""

    def __init__(
        self,
        *,
        reds: int,
        rules_name: str,
        p1_name: str = "P1",
        p2_name: str = "P2",
        starting_player: PlayerId = "p1",
    ) -> None:
        if reds <= 0:
            raise ValueError(f"reds must be > 0, got {reds}")
        self._initial_reds = reds
        balls = _initial_balls(reds)
        self._state = ScoreState(
            p1_name=p1_name,
            p2_name=p2_name,
            current_player=starting_player,
            balls_remaining=balls,
            rules_name=rules_name,
            target_ball=TARGET_RED,
        )
        # History for undo: (event, state_before_event).
        self._history: list[tuple[GameEvent, ScoreState]] = []
        # True if any BallPocketed in the *current* shot was illegal.
        self._shot_had_foul = False

    # -- RuleSet protocol --------------------------------------------------

    @property
    def state(self) -> ScoreState:
        return self._state

    def apply(self, event: GameEvent) -> ScoreState:
        try:
            new_state = self._dispatch(event)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("snooker engine ignored event %r due to %r", event, exc)
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
        log.warning("snooker: unknown event type %r", type(event).__name__)
        return None

    # -- handlers ----------------------------------------------------------

    def _on_ball_pocketed(self, event: BallPocketed) -> ScoreState | None:
        if self._state.paused:
            log.info("snooker: ball %s ignored (paused)", event.color)
            return None
        if self._state.target_ball == TARGET_FRAME_OVER:
            log.info("snooker: frame is over, ignoring pocket of %s", event.color)
            return None
        target = self._state.target_ball

        # Decide legality.
        if target == TARGET_RED:
            is_legal = event.color is BallColor.VERMELHA
        elif target == TARGET_COLOUR_ANY:
            is_legal = event.color is not BallColor.VERMELHA
        else:
            # Finishing phase — expecting a specific colour.
            is_legal = event.color.value == target

        if not is_legal:
            self._shot_had_foul = True
            timeline = self._push_timeline(
                TimelineEntry(
                    t_ms=event.t_ms,
                    kind="snooker_foul",
                    description=(
                        f"bola errada: {event.color.value} (esperava {_target_label(target)})"
                    ),
                ),
            )
            return self._state.with_changes(timeline=timeline)

        # Legal pocket — score and update balls_remaining / target.
        points = SNOOKER_POINTS[event.color]
        p1 = self._state.p1_score + (points if self._state.current_player == "p1" else 0)
        p2 = self._state.p2_score + (points if self._state.current_player == "p2" else 0)

        balls = dict(self._state.balls_remaining)
        reds_remaining = balls.get(BallColor.VERMELHA.value, 0)

        new_target: str
        if event.color is BallColor.VERMELHA:
            # Pocketed a red → consume it; next target is a colour.
            balls[BallColor.VERMELHA.value] = reds_remaining - 1
            new_target = TARGET_COLOUR_ANY
        elif self._in_reds_phase():
            # During reds phase, pocketed colours are respotted.
            balls[event.color.value] = 1
            # If any reds still remain on the table (including the one we
            # did NOT just pocket), next target is red again; otherwise we
            # begin the finishing phase.
            if balls.get(BallColor.VERMELHA.value, 0) > 0:
                new_target = TARGET_RED
            else:
                new_target = FINISHING_ORDER[0].value
                # In finishing phase all colours stay down — so the colour
                # we just pocketed is NOT respotted. Undo that respot.
                balls[event.color.value] = 0
        else:
            # Finishing phase — stays down, move to next colour.
            balls[event.color.value] = 0
            new_target = _next_finishing_target(event.color)

        timeline = self._push_timeline(
            TimelineEntry(
                t_ms=event.t_ms,
                kind="ball_pocketed",
                description=(
                    f"{event.color.value} (+{points}) → "
                    f"{self._state.p1_name if self._state.current_player == 'p1' else self._state.p2_name}"
                ),
            ),
        )
        return self._state.with_changes(
            p1_score=p1,
            p2_score=p2,
            balls_remaining=balls,
            target_ball=new_target,
            pocketed_this_turn=self._state.pocketed_this_turn + 1,
            timeline=timeline,
        )

    def _on_turn_ended(self, event: TurnEnded) -> ScoreState | None:
        if self._state.paused:
            return None
        fouled = self._shot_had_foul
        self._shot_had_foul = False
        pocketed = (
            event.pocketed_this_turn
            if event.pocketed_this_turn is not None
            else self._state.pocketed_this_turn
        )
        # Same player continues only if the shot was clean and pocketed ≥1 ball.
        if pocketed > 0 and not fouled:
            # Keep player; reset per-turn counter. target_ball is already up
            # to date from the BallPocketed handler.
            return self._state.with_changes(pocketed_this_turn=0)

        # Turn changes hands.
        new_player: PlayerId = "p2" if self._state.current_player == "p1" else "p1"
        target = self._resume_target_for_new_turn()
        reason = "falta" if fouled else "vez sem bola"
        timeline = self._push_timeline(
            TimelineEntry(
                t_ms=event.t_ms,
                kind="turn_change",
                description=f"{reason}: vez de "
                + (self._state.p2_name if new_player == "p2" else self._state.p1_name),
            ),
        )
        return self._state.with_changes(
            current_player=new_player,
            pocketed_this_turn=0,
            target_ball=target,
            timeline=timeline,
        )

    def _on_manual(self, event: ManualAdjustment) -> ScoreState | None:
        if event.op == "adjust":
            if event.player not in ("p1", "p2") or event.delta is None:
                log.warning("snooker: invalid adjust event: %r", event)
                return None
            p1 = self._state.p1_score + (event.delta if event.player == "p1" else 0)
            p2 = self._state.p2_score + (event.delta if event.player == "p2" else 0)
            return self._state.with_changes(
                p1_score=p1,
                p2_score=p2,
                timeline=self._push_timeline(
                    TimelineEntry(
                        t_ms=event.t_ms,
                        kind="manual_adjust",
                        description=f"{event.player} {event.delta:+d}",
                    ),
                ),
            )
        if event.op == "set_score":
            if event.p1_score is None or event.p2_score is None:
                return None
            return self._state.with_changes(
                p1_score=event.p1_score,
                p2_score=event.p2_score,
                timeline=self._push_timeline(
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
                target_ball=self._resume_target_for_new_turn(),
                timeline=self._push_timeline(
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
            # Finding "last legal pocket" with respotting + phase transitions
            # is non-trivial; simplest correct behaviour is to undo-then-redo
            # externally. We document this as unsupported in snooker for now.
            log.info("snooker: correct_last not supported; use undo + re-submit")
            return None
        if event.op == "pause":
            return self._state.with_changes(paused=True)
        if event.op == "resume":
            return self._state.with_changes(paused=False)
        if event.op == "reset":
            balls = _initial_balls(self._initial_reds)
            return ScoreState(
                p1_name=self._state.p1_name,
                p2_name=self._state.p2_name,
                current_player="p1",
                balls_remaining=balls,
                rules_name=self._state.rules_name,
                target_ball=TARGET_RED,
            )
        log.warning("snooker: unknown manual op %r", event.op)
        return None

    def _on_undo(self) -> ScoreState | None:
        if not self._history:
            return None
        _event, prev_state = self._history.pop()
        # Undoing resets the per-shot foul flag conservatively.
        self._shot_had_foul = False
        return prev_state

    # -- helpers -----------------------------------------------------------

    def _in_reds_phase(self) -> bool:
        return self._state.balls_remaining.get(BallColor.VERMELHA.value, 0) > 0

    def _resume_target_for_new_turn(self) -> str:
        """Choose the expected ball for a player who just took over the cue."""
        if self._state.balls_remaining.get(BallColor.VERMELHA.value, 0) > 0:
            return TARGET_RED
        # Finishing phase — lowest remaining colour.
        for colour in FINISHING_ORDER:
            if self._state.balls_remaining.get(colour.value, 0) > 0:
                return colour.value
        return TARGET_FRAME_OVER

    def _push_timeline(self, entry: TimelineEntry) -> tuple[TimelineEntry, ...]:
        new = (*self._state.timeline, entry)
        if len(new) > MAX_TIMELINE_ENTRIES:
            new = new[-MAX_TIMELINE_ENTRIES:]
        return new


def _initial_balls(reds: int) -> dict[str, int]:
    return {
        BallColor.VERMELHA.value: reds,
        BallColor.AMARELA.value: 1,
        BallColor.VERDE.value: 1,
        BallColor.MARROM.value: 1,
        BallColor.AZUL.value: 1,
        BallColor.ROSA.value: 1,
        BallColor.PRETA_BOLA_7.value: 1,
    }


def _next_finishing_target(current: BallColor) -> str:
    try:
        idx = FINISHING_ORDER.index(current)
    except ValueError:
        return TARGET_FRAME_OVER
    if idx + 1 < len(FINISHING_ORDER):
        return FINISHING_ORDER[idx + 1].value
    return TARGET_FRAME_OVER


def _target_label(target: str) -> str:
    if target == TARGET_RED:
        return "vermelha"
    if target == TARGET_COLOUR_ANY:
        return "qualquer colorida"
    if target == TARGET_FRAME_OVER:
        return "partida encerrada"
    return target


__all__ = [
    "FINISHING_ORDER",
    "SNOOKER_POINTS",
    "SnookerRules",
    "TARGET_COLOUR_ANY",
    "TARGET_FRAME_OVER",
    "TARGET_RED",
]
