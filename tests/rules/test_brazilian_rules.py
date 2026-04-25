"""Camada 1 — rules engine. Aim for 100% coverage of BrazilianRules."""

from __future__ import annotations

import pytest

from sinuca_counter.rules import (
    BallColor,
    BallPocketed,
    BrazilianRules,
    ManualAdjustment,
    TurnEnded,
    Undo,
)
from sinuca_counter.rules.brazilian import DEFAULT_POINTS


def make_rules(**kwargs) -> BrazilianRules:
    return BrazilianRules(p1_name="Lucas", p2_name="Ricardo", **kwargs)


# -- pocketing scoring -------------------------------------------------------


@pytest.mark.parametrize("color", list(DEFAULT_POINTS.keys()))
def test_each_color_scored_correctly(color: BallColor) -> None:
    rules = make_rules()
    state = rules.apply(BallPocketed(color=color, pocket_id="top_left", t_ms=0))
    assert state.p1_score == DEFAULT_POINTS[color]
    assert state.p2_score == 0
    assert state.balls_remaining[color.value] == 0
    assert state.pocketed_this_turn == 1


def test_pocket_keeps_turn_until_turn_ended_with_zero() -> None:
    rules = make_rules()
    rules.apply(BallPocketed(color=BallColor.AMARELA, pocket_id="top_left", t_ms=0))
    state = rules.apply(TurnEnded(pocketed_this_turn=1, t_ms=10))
    assert state.current_player == "p1"
    assert state.pocketed_this_turn == 0


def test_turn_changes_when_turn_ended_with_zero_pocketed() -> None:
    rules = make_rules()
    state = rules.apply(TurnEnded(pocketed_this_turn=0, t_ms=10))
    assert state.current_player == "p2"


def test_turn_change_alternates() -> None:
    rules = make_rules()
    rules.apply(TurnEnded(pocketed_this_turn=0, t_ms=10))
    state = rules.apply(TurnEnded(pocketed_this_turn=0, t_ms=20))
    assert state.current_player == "p1"


def test_already_pocketed_color_logged_but_ignored(caplog: pytest.LogCaptureFixture) -> None:
    rules = make_rules()
    rules.apply(BallPocketed(color=BallColor.PRETA_BOLA_7, pocket_id="top_left", t_ms=0))
    state_before = rules.state
    with caplog.at_level("WARNING"):
        state = rules.apply(
            BallPocketed(color=BallColor.PRETA_BOLA_7, pocket_id="top_left", t_ms=10)
        )
    assert state == state_before


# -- bolão variants ----------------------------------------------------------


def test_bolao_premature_penalty_loses_rack_to_opponent() -> None:
    rules = make_rules(bolao_premature_penalty=True)
    state = rules.apply(BallPocketed(color=BallColor.PRETA_BOLA_7, pocket_id="top_left", t_ms=0))
    assert state.p1_score == 0
    assert state.p2_score == DEFAULT_POINTS[BallColor.PRETA_BOLA_7]


def test_bolao_at_end_scores_normally_under_penalty_variant() -> None:
    rules = make_rules(bolao_premature_penalty=True)
    for color in [
        BallColor.AMARELA,
        BallColor.VERMELHA,
        BallColor.VERDE,
        BallColor.MARROM,
        BallColor.AZUL,
        BallColor.ROSA,
    ]:
        rules.apply(BallPocketed(color=color, pocket_id="top_left", t_ms=0))
    p1_before = rules.state.p1_score
    state = rules.apply(BallPocketed(color=BallColor.PRETA_BOLA_7, pocket_id="top_left", t_ms=10))
    assert state.p1_score == p1_before + DEFAULT_POINTS[BallColor.PRETA_BOLA_7]


# -- manual adjustments ------------------------------------------------------


def test_manual_adjust_player_score() -> None:
    rules = make_rules()
    state = rules.apply(ManualAdjustment(op="adjust", player="p2", delta=5))
    assert state.p2_score == 5


def test_manual_adjust_invalid_player_ignored() -> None:
    rules = make_rules()
    state_before = rules.state
    state = rules.apply(ManualAdjustment(op="adjust", player=None, delta=3))
    assert state == state_before


def test_manual_adjust_missing_delta_ignored() -> None:
    rules = make_rules()
    state_before = rules.state
    state = rules.apply(ManualAdjustment(op="adjust", player="p1"))
    assert state == state_before


def test_set_score_overrides_state() -> None:
    rules = make_rules()
    rules.apply(BallPocketed(color=BallColor.AMARELA, pocket_id="top_left", t_ms=0))
    state = rules.apply(ManualAdjustment(op="set_score", p1_score=12, p2_score=7))
    assert state.p1_score == 12
    assert state.p2_score == 7


def test_set_score_missing_args_ignored() -> None:
    rules = make_rules()
    state_before = rules.state
    state = rules.apply(ManualAdjustment(op="set_score", p1_score=10))
    assert state == state_before


def test_swap_turn_forces_change() -> None:
    rules = make_rules()
    state = rules.apply(ManualAdjustment(op="swap_turn"))
    assert state.current_player == "p2"


def test_rename_updates_names() -> None:
    rules = make_rules()
    state = rules.apply(ManualAdjustment(op="rename", p1_name="João", p2_name="Maria"))
    assert state.p1_name == "João"
    assert state.p2_name == "Maria"


def test_pause_and_resume() -> None:
    rules = make_rules()
    state = rules.apply(ManualAdjustment(op="pause"))
    assert state.paused
    # Pocketing while paused is ignored.
    state2 = rules.apply(BallPocketed(color=BallColor.AMARELA, pocket_id="top_left", t_ms=0))
    assert state2 == state
    state3 = rules.apply(ManualAdjustment(op="resume"))
    assert not state3.paused


def test_turn_ended_while_paused_does_nothing() -> None:
    rules = make_rules()
    rules.apply(ManualAdjustment(op="pause"))
    state_before = rules.state
    state = rules.apply(TurnEnded(pocketed_this_turn=0, t_ms=10))
    assert state == state_before


def test_reset_clears_scores_keeps_names() -> None:
    rules = make_rules()
    rules.apply(BallPocketed(color=BallColor.AMARELA, pocket_id="top_left", t_ms=0))
    state = rules.apply(ManualAdjustment(op="reset"))
    assert state.p1_score == 0
    assert state.p2_score == 0
    assert state.p1_name == "Lucas"
    assert state.p2_name == "Ricardo"


def test_unknown_manual_op_ignored() -> None:
    rules = make_rules()
    state_before = rules.state
    state = rules.apply(ManualAdjustment(op="not_a_real_op"))  # type: ignore[arg-type]
    assert state == state_before


# -- correct_last ------------------------------------------------------------


def test_correct_last_replaces_color_of_most_recent_pocket() -> None:
    rules = make_rules()
    rules.apply(BallPocketed(color=BallColor.AMARELA, pocket_id="top_left", t_ms=0))
    state = rules.apply(ManualAdjustment(op="correct_last", color=BallColor.VERMELHA))
    assert state.p1_score == DEFAULT_POINTS[BallColor.VERMELHA]
    assert state.balls_remaining[BallColor.AMARELA.value] == 1
    assert state.balls_remaining[BallColor.VERMELHA.value] == 0


def test_correct_last_with_no_pocket_history_noop() -> None:
    rules = make_rules()
    state_before = rules.state
    state = rules.apply(ManualAdjustment(op="correct_last", color=BallColor.AMARELA))
    assert state == state_before


def test_correct_last_missing_color_ignored() -> None:
    rules = make_rules()
    state_before = rules.state
    state = rules.apply(ManualAdjustment(op="correct_last"))
    assert state == state_before


# -- undo --------------------------------------------------------------------


def test_undo_reverts_last_event() -> None:
    rules = make_rules()
    rules.apply(BallPocketed(color=BallColor.AMARELA, pocket_id="top_left", t_ms=0))
    state = rules.apply(Undo())
    assert state.p1_score == 0
    assert state.balls_remaining[BallColor.AMARELA.value] == 1


def test_undo_with_empty_history_noop() -> None:
    rules = make_rules()
    state_before = rules.state
    state = rules.apply(Undo())
    assert state == state_before


def test_unknown_event_type_ignored() -> None:
    rules = make_rules()
    state_before = rules.state

    class Foo:
        pass

    state = rules.apply(Foo())  # type: ignore[arg-type]
    assert state == state_before


# -- timeline ----------------------------------------------------------------


def test_timeline_contains_pocketed_entry() -> None:
    rules = make_rules()
    state = rules.apply(BallPocketed(color=BallColor.AMARELA, pocket_id="top_left", t_ms=12345))
    assert state.timeline
    assert state.timeline[-1].kind == "ball_pocketed"
    assert state.timeline[-1].t_ms == 12345


def test_timeline_truncates_to_last_n() -> None:
    rules = make_rules()
    for _ in range(60):
        rules.apply(ManualAdjustment(op="adjust", player="p1", delta=1))
    assert len(rules.state.timeline) <= 40
