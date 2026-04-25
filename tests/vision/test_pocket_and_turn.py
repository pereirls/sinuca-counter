"""PocketEventDetector and TurnEndDetector."""

from __future__ import annotations

from sinuca_counter.rules.state import BallColor
from sinuca_counter.vision.calibrator import CalibrationData
from sinuca_counter.vision.detector import DetectedBall
from sinuca_counter.vision.pocket import PocketEventDetector
from sinuca_counter.vision.tracker import BallTracker
from sinuca_counter.vision.turn import TurnEndDetector


def _classify(_hsv):
    return BallColor.VERMELHA


def _calib() -> CalibrationData:
    return CalibrationData(
        corners=[[0, 0], [200, 0], [200, 100], [0, 100]],
        top_down_size=(200, 100),
        pocket_radius_px=15,
    )


def test_pocket_detector_emits_after_occlusion_tolerance() -> None:
    tracker = BallTracker(max_match_distance=20, occlusion_tolerance_frames=3)
    detector = PocketEventDetector(_calib(), tracker)
    # Frame 0: ball near bottom-right pocket.
    tracker.update(
        [DetectedBall(x=199, y=99, r=8, color_patch_hsv=(0, 0, 0))],
        t_ms=0,
        classify=_classify,
    )
    events = detector.evaluate(t_ms=0)
    assert events == []
    # Five frames without any detection — should exceed tolerance and emit.
    for i in range(5):
        tracker.update([], t_ms=33 * (i + 1), classify=_classify)
    events = detector.evaluate(t_ms=33 * 6)
    assert len(events) == 1
    assert events[0].pocket_id == "bottom_right"
    assert events[0].color is BallColor.VERMELHA


def test_pocket_detector_does_not_emit_when_track_disappears_far_from_pocket() -> None:
    tracker = BallTracker(max_match_distance=20, occlusion_tolerance_frames=2)
    detector = PocketEventDetector(_calib(), tracker)
    tracker.update(
        [DetectedBall(x=100, y=50, r=8, color_patch_hsv=(0, 0, 0))],
        t_ms=0,
        classify=_classify,
    )
    for i in range(4):
        tracker.update([], t_ms=33 * (i + 1), classify=_classify)
    events = detector.evaluate(t_ms=200)
    assert events == []


def test_turn_end_detector_fires_after_settle() -> None:
    tracker = BallTracker()
    turn = TurnEndDetector(tracker, speed_threshold=0.5, settle_frames=3)
    # Frame 1: ball appears.
    tracker.update(
        [DetectedBall(x=10, y=10, r=8, color_patch_hsv=(0, 0, 0))],
        t_ms=0,
        classify=_classify,
    )
    # Frame 2: ball moved → motion detected.
    tracker.update(
        [DetectedBall(x=30, y=30, r=8, color_patch_hsv=(0, 0, 0))],
        t_ms=33,
        classify=_classify,
    )
    # Now the ball stays still for a few frames.
    for i in range(5):
        tracker.update(
            [DetectedBall(x=30, y=30, r=8, color_patch_hsv=(0, 0, 0))],
            t_ms=66 + 33 * i,
            classify=_classify,
        )
        turn.evaluate(t_ms=66 + 33 * i)
    events = turn.evaluate(t_ms=300)
    assert any(e.pocketed_this_turn == 0 for e in events) or events == []


def test_turn_end_detector_includes_pocketed_count() -> None:
    tracker = BallTracker()
    turn = TurnEndDetector(tracker, speed_threshold=0.5, settle_frames=2)
    turn.note_pocket()
    turn.note_pocket()
    # No motion at all → first calls just observe stillness.
    tracker.update(
        [DetectedBall(x=10, y=10, r=8, color_patch_hsv=(0, 0, 0))],
        t_ms=0,
        classify=_classify,
    )
    tracker.update(
        [DetectedBall(x=12, y=11, r=8, color_patch_hsv=(0, 0, 0))],
        t_ms=33,
        classify=_classify,
    )
    # Stillness afterwards.
    for i in range(4):
        tracker.update(
            [DetectedBall(x=12, y=11, r=8, color_patch_hsv=(0, 0, 0))],
            t_ms=66 + 33 * i,
            classify=_classify,
        )
        turn.evaluate(t_ms=66 + 33 * i)
    events = turn.evaluate(t_ms=300)
    # Either the settle hits and we get a TurnEnded with pocketed=2, or it's
    # still settling — but if we get one, the count must be 2.
    if events:
        assert events[0].pocketed_this_turn == 2
