"""Tests for the rack-delta ShotPhaseDetector."""

from __future__ import annotations

from sinuca_counter.rules.state import BallColor
from sinuca_counter.vision.detector import DetectedBall
from sinuca_counter.vision.events import BallPocketed, TurnEnded, VisionEvent
from sinuca_counter.vision.shot_phase import ShotPhaseDetector
from sinuca_counter.vision.tracker import BallTracker


def _balls_at(positions: list[tuple[int, int]]) -> list[DetectedBall]:
    # Encode the position into the HSV patch so the classifier can distinguish
    # balls by (x, y) for test purposes.
    return [
        DetectedBall(x=float(x), y=float(y), r=8.0, color_patch_hsv=(x, y, 0)) for x, y in positions
    ]


def _classify_fixed(hsv: tuple[int, int, int]) -> BallColor:  # noqa: ARG001
    return BallColor.VERMELHA


def _run_sequence(
    frames: list[list[tuple[int, int]]],
    *,
    speed_threshold: float = 0.5,
    settle_frames: int = 3,
    min_shot_frames: int = 1,
    max_pocketed_per_shot: int = 6,
    dt: int = 33,
) -> tuple[list[VisionEvent], ShotPhaseDetector]:
    """Feed a list of per-frame ball positions and return collected events.

    Every frame goes through ``tracker.update`` and ``det.evaluate`` so the
    state machine sees motion rise and fall like it would in production.
    """

    tracker = BallTracker(max_match_distance=30.0, occlusion_tolerance_frames=30)
    det = ShotPhaseDetector(
        tracker,
        speed_threshold=speed_threshold,
        settle_frames=settle_frames,
        min_shot_frames=min_shot_frames,
        max_pocketed_per_shot=max_pocketed_per_shot,
        armed=True,
    )
    events: list[VisionEvent] = []
    t = 0
    for positions in frames:
        tracker.update(_balls_at(positions), t_ms=t, classify=_classify_fixed)
        events.extend(det.evaluate(t_ms=t))
        t += dt
    return events, det


def test_idle_state_emits_nothing_while_balls_rest() -> None:
    events, det = _run_sequence([[(10, 10), (50, 50)]] * 10)
    assert events == []
    assert det.state_name == "IDLE"


def test_shot_with_no_pocket_emits_only_turn_ended_zero() -> None:
    # 3 still frames to warm up the tracker, then 4 moving frames, then 6
    # still frames (settle_frames=3 + a margin).
    still = [(10, 10), (50, 50)]
    frames: list[list[tuple[int, int]]] = [still] * 3
    # Motion: move ball at (50,50) step by step.
    for offset in range(1, 5):
        frames.append([(10, 10), (50 + offset * 8, 50)])
    final = [(10, 10), (50 + 4 * 8, 50)]
    frames.extend([final] * 8)

    events, det = _run_sequence(frames)
    pockets = [e for e in events if isinstance(e, BallPocketed)]
    turns = [e for e in events if isinstance(e, TurnEnded)]
    assert pockets == []
    assert len(turns) == 1
    assert turns[0].pocketed_this_turn == 0
    assert det.state_name == "IDLE"


def test_shot_with_one_disappeared_ball_emits_pocketed_and_turn_ended() -> None:
    still = [(10, 10), (50, 50)]
    frames: list[list[tuple[int, int]]] = [still] * 3
    # Both balls settled; cue shot sends (50,50) across the table.
    for offset in range(1, 5):
        frames.append([(10, 10), (50 + offset * 8, 50)])
    # Ball pocketed: from here on only ball (10,10) is seen.
    frames.extend([[(10, 10)]] * 8)

    events, _ = _run_sequence(frames)
    pockets = [e for e in events if isinstance(e, BallPocketed)]
    turns = [e for e in events if isinstance(e, TurnEnded)]
    assert len(pockets) == 1
    assert pockets[0].pocket_id == "unknown"
    assert pockets[0].color == BallColor.VERMELHA
    assert len(turns) == 1
    assert turns[0].pocketed_this_turn == 1


def test_transient_occlusion_during_shot_does_not_emit_pocketed() -> None:
    still = [(10, 10), (50, 50)]
    frames: list[list[tuple[int, int]]] = [still] * 3
    # Shot begins.
    frames.append([(15, 10), (60, 50)])
    # During shot, ball (10,10) briefly disappears (cue covers it).
    frames.append([(62, 50)])
    frames.append([(64, 50)])
    # Ball reappears and settles.
    final = [(10, 10), (64, 50)]
    frames.extend([final] * 8)

    events, _ = _run_sequence(frames)
    pockets = [e for e in events if isinstance(e, BallPocketed)]
    assert pockets == [], "brief occlusion must not fire BallPocketed"


def test_massive_drop_is_treated_as_glitch() -> None:
    still = [(x * 10, 10) for x in range(10)]
    frames: list[list[tuple[int, int]]] = [still] * 3
    # Motion.
    frames.append([(x * 10 + 2, 10) for x in range(10)])
    frames.append([(x * 10 + 4, 10) for x in range(10)])
    # All balls vanish — a global detection glitch.
    frames.extend([[]] * 8)

    events, _ = _run_sequence(frames, max_pocketed_per_shot=3)
    pockets = [e for e in events if isinstance(e, BallPocketed)]
    turns = [e for e in events if isinstance(e, TurnEnded)]
    assert pockets == []
    # The detector still reports a turn boundary with zero pocketed because
    # the whole event was discarded as a glitch.
    assert any(t.pocketed_this_turn == 0 for t in turns)


def test_state_machine_returns_to_idle_after_emission() -> None:
    still = [(10, 10), (50, 50)]
    frames: list[list[tuple[int, int]]] = [still] * 3
    for offset in range(1, 5):
        frames.append([(10, 10), (50 + offset * 8, 50)])
    frames.extend([[(10, 10), (82, 50)]] * 8)
    _, det = _run_sequence(frames)
    assert det.state_name == "IDLE"


def test_motion_spike_below_min_shot_frames_is_ignored() -> None:
    still = [(10, 10), (50, 50)]
    frames: list[list[tuple[int, int]]] = [still] * 3
    # Single-frame spike, then back to still.
    frames.append([(20, 10), (50, 50)])
    frames.extend([still] * 8)

    events, det = _run_sequence(frames, min_shot_frames=4)
    assert events == []
    assert det.state_name == "IDLE"


def test_disarmed_detector_emits_nothing_even_with_pocket() -> None:
    tracker = BallTracker(max_match_distance=30.0, occlusion_tolerance_frames=30)
    det = ShotPhaseDetector(
        tracker,
        speed_threshold=0.5,
        settle_frames=3,
        min_shot_frames=1,
        armed=False,  # disarmed by default
    )
    events: list[VisionEvent] = []
    t = 0
    still = [(10, 10), (50, 50)]
    frames: list[list[tuple[int, int]]] = [still] * 3
    for offset in range(1, 5):
        frames.append([(10, 10), (50 + offset * 8, 50)])
    frames.extend([[(10, 10)]] * 8)
    for positions in frames:
        tracker.update(_balls_at(positions), t_ms=t, classify=_classify_fixed)
        events.extend(det.evaluate(t_ms=t))
        t += 33
    assert events == []
    assert det.armed is False


def test_arm_takes_a_fresh_baseline_and_starts_emitting() -> None:
    tracker = BallTracker(max_match_distance=30.0, occlusion_tolerance_frames=30)
    det = ShotPhaseDetector(
        tracker,
        speed_threshold=0.5,
        settle_frames=3,
        min_shot_frames=1,
        armed=False,
    )
    # Warm-up phase: balls bouncing around while disarmed.
    t = 0
    for _ in range(5):
        tracker.update(
            _balls_at([(10, 10), (50, 50)]),
            t_ms=t,
            classify=_classify_fixed,
        )
        det.evaluate(t_ms=t)
        t += 33

    # Operator clicks "Iniciar partida".
    det.arm(t_ms=t)
    assert det.armed is True

    # Now drive a real shot and pocket one ball.
    events: list[VisionEvent] = []
    frames: list[list[tuple[int, int]]] = [[(10, 10), (50, 50)]] * 3
    for offset in range(1, 5):
        frames.append([(10, 10), (50 + offset * 8, 50)])
    frames.extend([[(10, 10)]] * 8)
    for positions in frames:
        tracker.update(_balls_at(positions), t_ms=t, classify=_classify_fixed)
        events.extend(det.evaluate(t_ms=t))
        t += 33

    pockets = [e for e in events if isinstance(e, BallPocketed)]
    assert len(pockets) == 1


def test_disarm_clears_state() -> None:
    tracker = BallTracker(max_match_distance=30.0, occlusion_tolerance_frames=30)
    det = ShotPhaseDetector(tracker, armed=True)
    det.disarm()
    assert det.armed is False
    assert det.state_name == "IDLE"
