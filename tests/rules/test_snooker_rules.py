"""Tests for SnookerRules (6-red European and 15-red English variants)."""

from __future__ import annotations

import pytest

from sinuca_counter.rules import (
    BallColor,
    BallPocketed,
    ManualAdjustment,
    SnookerRules,
    TurnEnded,
    Undo,
)
from sinuca_counter.rules.snooker import (
    FINISHING_ORDER,
    SNOOKER_POINTS,
    TARGET_COLOUR_ANY,
    TARGET_FRAME_OVER,
    TARGET_RED,
)


def make_rules(reds: int = 6) -> SnookerRules:
    return SnookerRules(
        reds=reds,
        rules_name=f"snooker-{reds}",
        p1_name="Lucas",
        p2_name="Ricardo",
    )


# -- initial state -----------------------------------------------------------


def test_initial_state_6_red() -> None:
    rules = make_rules(reds=6)
    state = rules.state
    assert state.rules_name == "snooker-6"
    assert state.target_ball == TARGET_RED
    assert state.balls_remaining[BallColor.VERMELHA.value] == 6
    for colour in FINISHING_ORDER:
        assert state.balls_remaining[colour.value] == 1
    assert state.p1_score == 0
    assert state.p2_score == 0


def test_initial_state_15_red() -> None:
    rules = make_rules(reds=15)
    assert rules.state.balls_remaining[BallColor.VERMELHA.value] == 15


def test_invalid_reds_raises() -> None:
    with pytest.raises(ValueError):
        SnookerRules(reds=0, rules_name="bad")


# -- reds phase --------------------------------------------------------------


def test_red_then_colour_alternation() -> None:
    rules = make_rules(reds=6)
    s1 = rules.apply(BallPocketed(color=BallColor.VERMELHA, pocket_id="x", t_ms=0))
    assert s1.p1_score == 1
    assert s1.balls_remaining[BallColor.VERMELHA.value] == 5
    assert s1.target_ball == TARGET_COLOUR_ANY

    # Any colour is legal while in reds phase.
    s2 = rules.apply(BallPocketed(color=BallColor.PRETA_BOLA_7, pocket_id="x", t_ms=1))
    assert s2.p1_score == 1 + 7
    # Respotted — stays at 1.
    assert s2.balls_remaining[BallColor.PRETA_BOLA_7.value] == 1
    # Back to expecting a red.
    assert s2.target_ball == TARGET_RED

    # End turn with 2 pockets — player keeps the cue.
    s3 = rules.apply(TurnEnded(pocketed_this_turn=2, t_ms=2))
    assert s3.current_player == "p1"


def test_colour_before_red_is_a_foul_no_score_and_turn_ends() -> None:
    rules = make_rules(reds=6)
    # Expected: red. But player pockets a blue.
    s1 = rules.apply(BallPocketed(color=BallColor.AZUL, pocket_id="x", t_ms=0))
    assert s1.p1_score == 0
    # Ball count untouched for the foul.
    assert s1.balls_remaining[BallColor.AZUL.value] == 1

    s2 = rules.apply(TurnEnded(pocketed_this_turn=1, t_ms=1))
    # Foul in shot → turn goes to the opponent even though pocketed_this_turn > 0.
    assert s2.current_player == "p2"


def test_red_then_red_second_red_is_a_foul() -> None:
    rules = make_rules(reds=6)
    rules.apply(BallPocketed(color=BallColor.VERMELHA, pocket_id="x", t_ms=0))
    s = rules.apply(BallPocketed(color=BallColor.VERMELHA, pocket_id="x", t_ms=1))
    # Second red is illegal (expected a colour next).
    assert s.p1_score == 1  # only the first red counted
    s_end = rules.apply(TurnEnded(pocketed_this_turn=2, t_ms=2))
    # Foul → turn to p2.
    assert s_end.current_player == "p2"


# -- finishing phase ---------------------------------------------------------


def _clear_reds(rules: SnookerRules, reds: int) -> None:
    """Pocket all reds alternating with yellow (cheapest colour, respotted)."""

    t = 0
    for _ in range(reds):
        rules.apply(BallPocketed(color=BallColor.VERMELHA, pocket_id="x", t_ms=t))
        t += 1
        rules.apply(BallPocketed(color=BallColor.AMARELA, pocket_id="x", t_ms=t))
        t += 1


def test_transition_to_finishing_phase_happens_after_last_red() -> None:
    rules = make_rules(reds=6)
    _clear_reds(rules, 6)
    # After 6 reds + 6 yellows, the last yellow is pocketed *after* the
    # last red has been consumed — so it counts as the first finishing
    # colour and stays down. The next target is the colour above yellow
    # (green).
    state = rules.state
    assert state.balls_remaining[BallColor.VERMELHA.value] == 0
    # Points: 6 reds × 1 + 6 yellows × 2 = 18.
    assert state.p1_score == 18
    assert state.target_ball == BallColor.VERDE.value
    assert state.balls_remaining[BallColor.AMARELA.value] == 0


def test_finishing_phase_scores_in_ascending_order() -> None:
    rules = make_rules(reds=6)
    _clear_reds(rules, 6)
    # Continue with the rest of the colours in order.
    for colour in FINISHING_ORDER[1:]:  # green onwards (yellow already done)
        state = rules.apply(BallPocketed(color=colour, pocket_id="x", t_ms=0))
        assert state.balls_remaining[colour.value] == 0
    # After black, frame is over.
    assert rules.state.target_ball == TARGET_FRAME_OVER
    # Points: 18 (reds phase) + 3+4+5+6+7 = 43
    assert rules.state.p1_score == 18 + 3 + 4 + 5 + 6 + 7


def test_finishing_phase_wrong_colour_is_a_foul() -> None:
    rules = make_rules(reds=6)
    _clear_reds(rules, 6)
    # Expected green next (yellow was consumed during the transition);
    # player pockets blue.
    s = rules.apply(BallPocketed(color=BallColor.AZUL, pocket_id="x", t_ms=0))
    assert s.p1_score == 18
    assert s.balls_remaining[BallColor.AZUL.value] == 1
    s = rules.apply(TurnEnded(pocketed_this_turn=1, t_ms=1))
    assert s.current_player == "p2"


def test_frame_over_ignores_further_pockets() -> None:
    rules = make_rules(reds=6)
    _clear_reds(rules, 6)
    for colour in FINISHING_ORDER[1:]:
        rules.apply(BallPocketed(color=colour, pocket_id="x", t_ms=0))
    pre_state = rules.state
    # Further pockets are ignored.
    s = rules.apply(BallPocketed(color=BallColor.PRETA_BOLA_7, pocket_id="x", t_ms=99))
    assert s == pre_state


# -- turn management ---------------------------------------------------------


def test_miss_ends_turn_and_target_stays_red_for_opponent() -> None:
    rules = make_rules(reds=6)
    s = rules.apply(TurnEnded(pocketed_this_turn=0, t_ms=0))
    assert s.current_player == "p2"
    assert s.target_ball == TARGET_RED


def test_miss_in_finishing_phase_keeps_next_colour_target() -> None:
    rules = make_rules(reds=6)
    _clear_reds(rules, 6)
    # Expected green; miss.
    s = rules.apply(TurnEnded(pocketed_this_turn=0, t_ms=0))
    assert s.current_player == "p2"
    # Same target — lowest remaining colour.
    assert s.target_ball == BallColor.VERDE.value


# -- manual adjustments ------------------------------------------------------


def test_manual_adjust_changes_score() -> None:
    rules = make_rules(reds=6)
    s = rules.apply(ManualAdjustment(op="adjust", player="p2", delta=7))
    assert s.p2_score == 7


def test_manual_swap_turn_resets_target_to_current_phase() -> None:
    rules = make_rules(reds=6)
    # Pocket a red so target is "colour".
    rules.apply(BallPocketed(color=BallColor.VERMELHA, pocket_id="x", t_ms=0))
    assert rules.state.target_ball == TARGET_COLOUR_ANY
    s = rules.apply(ManualAdjustment(op="swap_turn"))
    assert s.current_player == "p2"
    # After swap in reds phase, the new shooter starts on a red again.
    assert s.target_ball == TARGET_RED


def test_manual_reset_restores_initial_state() -> None:
    rules = make_rules(reds=6)
    rules.apply(BallPocketed(color=BallColor.VERMELHA, pocket_id="x", t_ms=0))
    rules.apply(BallPocketed(color=BallColor.PRETA_BOLA_7, pocket_id="x", t_ms=1))
    s = rules.apply(ManualAdjustment(op="reset"))
    assert s.p1_score == 0
    assert s.balls_remaining[BallColor.VERMELHA.value] == 6
    assert s.target_ball == TARGET_RED
    # Names preserved.
    assert s.p1_name == "Lucas"


def test_undo_rolls_back_last_event() -> None:
    rules = make_rules(reds=6)
    rules.apply(BallPocketed(color=BallColor.VERMELHA, pocket_id="x", t_ms=0))
    before = rules.state
    rules.apply(BallPocketed(color=BallColor.PRETA_BOLA_7, pocket_id="x", t_ms=1))
    s = rules.apply(Undo())
    assert s == before


def test_pause_blocks_ball_pocketed() -> None:
    rules = make_rules(reds=6)
    rules.apply(ManualAdjustment(op="pause"))
    s = rules.apply(BallPocketed(color=BallColor.VERMELHA, pocket_id="x", t_ms=0))
    # State unchanged while paused.
    assert s.p1_score == 0
    rules.apply(ManualAdjustment(op="resume"))
    s2 = rules.apply(BallPocketed(color=BallColor.VERMELHA, pocket_id="x", t_ms=1))
    assert s2.p1_score == 1


def test_points_map_matches_standard_snooker_values() -> None:
    assert SNOOKER_POINTS[BallColor.VERMELHA] == 1
    assert SNOOKER_POINTS[BallColor.AMARELA] == 2
    assert SNOOKER_POINTS[BallColor.VERDE] == 3
    assert SNOOKER_POINTS[BallColor.MARROM] == 4
    assert SNOOKER_POINTS[BallColor.AZUL] == 5
    assert SNOOKER_POINTS[BallColor.ROSA] == 6
    assert SNOOKER_POINTS[BallColor.PRETA_BOLA_7] == 7


def test_snooker_implements_ruleset_protocol() -> None:
    from sinuca_counter.rules import RuleSet

    rules: RuleSet = make_rules(6)
    assert isinstance(rules, RuleSet)


def test_snooker_start_match_sets_match_started_flag() -> None:
    rules = make_rules(reds=6)
    assert rules.state.match_started is False
    state = rules.apply(ManualAdjustment(op="start_match"))
    assert state.match_started is True
    state = rules.apply(ManualAdjustment(op="stop_match"))
    assert state.match_started is False
