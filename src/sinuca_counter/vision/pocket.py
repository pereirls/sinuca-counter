"""Detects when a tracked ball disappeared into a pocket."""

from __future__ import annotations

from .calibrator import CalibrationData
from .events import BallPocketed
from .tracker import BallTracker


class PocketEventDetector:
    """Emits :class:`BallPocketed` when a track disappears near a pocket."""

    def __init__(
        self,
        calibration: CalibrationData,
        tracker: BallTracker,
        *,
        confirmation_extra_frames: int = 0,
    ) -> None:
        self._pockets = calibration.pocket_centers()
        self._radius = calibration.pocket_radius_px
        self._tracker = tracker
        self._confirmation = confirmation_extra_frames
        self._already_emitted: set[int] = set()

    def evaluate(self, t_ms: int) -> list[BallPocketed]:
        events: list[BallPocketed] = []
        # Snapshot to allow safe removal in the loop.
        for track in list(self._tracker.tracks):
            if track.track_id in self._already_emitted:
                continue
            min_required = self._tracker.occlusion_tolerance_frames + self._confirmation
            if track.missed_frames <= min_required:
                continue
            pocket_id = self._nearest_pocket(track.x, track.y)
            if pocket_id is None:
                # Disappeared somewhere away from a pocket; let the tracker
                # garbage-collect it without scoring.
                self._tracker.remove(track.track_id)
                continue
            events.append(
                BallPocketed(
                    color=track.color,
                    pocket_id=pocket_id,
                    t_ms=track.last_seen_t_ms or t_ms,
                )
            )
            self._already_emitted.add(track.track_id)
            self._tracker.remove(track.track_id)
        return events

    def _nearest_pocket(self, x: float, y: float) -> str | None:
        best_id = None
        best_dist = self._radius
        for pocket_id, (px, py) in self._pockets.items():
            dist = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
            if dist <= best_dist:
                best_dist = dist
                best_id = pocket_id
        return best_id


__all__ = ["PocketEventDetector"]
