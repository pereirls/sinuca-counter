"""Tracker association and occlusion handling."""

from __future__ import annotations

from sinuca_counter.rules.state import BallColor
from sinuca_counter.vision.detector import DetectedBall
from sinuca_counter.vision.tracker import BallTracker


def _classify(_hsv: tuple[int, int, int]) -> BallColor:
    return BallColor.AMARELA


def test_tracker_keeps_identity_for_close_detections() -> None:
    tracker = BallTracker(max_match_distance=20.0, occlusion_tolerance_frames=5)
    det1 = [DetectedBall(x=100, y=100, r=10, color_patch_hsv=(0, 0, 0))]
    det2 = [DetectedBall(x=105, y=98, r=10, color_patch_hsv=(0, 0, 0))]
    tracker.update(det1, t_ms=0, classify=_classify)
    tracks = tracker.update(det2, t_ms=33, classify=_classify)
    assert len(tracks) == 1
    assert tracks[0].track_id == 1


def test_tracker_creates_new_id_when_far() -> None:
    tracker = BallTracker(max_match_distance=10.0, occlusion_tolerance_frames=5)
    tracker.update([DetectedBall(x=0, y=0, r=10, color_patch_hsv=(0, 0, 0))], 0, _classify)
    tracks = tracker.update(
        [DetectedBall(x=200, y=200, r=10, color_patch_hsv=(0, 0, 0))],
        33,
        _classify,
    )
    ids = sorted(t.track_id for t in tracks)
    assert ids == [1, 2]


def test_tracker_marks_invisible_after_missed_detection() -> None:
    tracker = BallTracker(max_match_distance=20.0, occlusion_tolerance_frames=3)
    tracker.update([DetectedBall(x=0, y=0, r=10, color_patch_hsv=(0, 0, 0))], 0, _classify)
    tracks = tracker.update([], 33, _classify)
    assert tracks[0].visible is False
    assert tracks[0].missed_frames == 1


def test_tracker_speed_uses_history() -> None:
    tracker = BallTracker(max_match_distance=20.0)
    tracker.update([DetectedBall(x=0, y=0, r=10, color_patch_hsv=(0, 0, 0))], 0, _classify)
    tracker.update([DetectedBall(x=3, y=4, r=10, color_patch_hsv=(0, 0, 0))], 33, _classify)
    track = tracker.tracks[0]
    assert abs(track.speed - 5.0) < 1e-6
