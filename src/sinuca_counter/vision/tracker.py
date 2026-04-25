"""Frame-to-frame association by proximity, with occlusion tolerance."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import count

from sinuca_counter.rules.state import BallColor

from .detector import DetectedBall

ColorClassifyFn = Callable[[tuple[int, int, int]], BallColor]


@dataclass
class TrackedBall:
    """A ball tracked across multiple frames."""

    track_id: int
    x: float
    y: float
    r: float
    last_seen_t_ms: int
    color: BallColor
    color_patch_hsv: tuple[int, int, int]
    missed_frames: int = 0
    visible: bool = True
    history: list[tuple[float, float]] = field(default_factory=list)

    @property
    def speed(self) -> float:
        """Approximate magnitude of last movement (pixels per frame)."""

        if len(self.history) < 2:
            return 0.0
        (x0, y0), (x1, y1) = self.history[-2], self.history[-1]
        return ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5


class BallTracker:
    """Greedy nearest-neighbour matcher with occlusion tolerance."""

    def __init__(
        self,
        *,
        max_match_distance: float = 35.0,
        occlusion_tolerance_frames: int = 30,
        history_length: int = 8,
    ) -> None:
        self._max_match_distance = max_match_distance
        self._occlusion_tolerance_frames = occlusion_tolerance_frames
        self._history_length = history_length
        self._tracks: dict[int, TrackedBall] = {}
        self._ids = count(1)

    @property
    def occlusion_tolerance_frames(self) -> int:
        return self._occlusion_tolerance_frames

    @property
    def tracks(self) -> list[TrackedBall]:
        return list(self._tracks.values())

    def visible_tracks(self) -> list[TrackedBall]:
        return [t for t in self._tracks.values() if t.visible]

    def update(
        self,
        detections: list[DetectedBall],
        t_ms: int,
        classify: ColorClassifyFn,
    ) -> list[TrackedBall]:
        """Match detections to existing tracks; update visibility flags."""

        unmatched_dets = list(range(len(detections)))
        unmatched_tracks = set(self._tracks.keys())

        # Greedy: for each track, find the closest detection within range.
        for tid, track in list(self._tracks.items()):
            best_idx = -1
            best_dist = self._max_match_distance + 1
            for di in unmatched_dets:
                d = detections[di]
                dist = ((d.x - track.x) ** 2 + (d.y - track.y) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_idx = di
            if best_idx >= 0 and best_dist <= self._max_match_distance:
                d = detections[best_idx]
                track.x = d.x
                track.y = d.y
                track.r = d.r
                track.last_seen_t_ms = t_ms
                track.color_patch_hsv = d.color_patch_hsv
                track.color = classify(d.color_patch_hsv)
                track.missed_frames = 0
                track.visible = True
                track.history.append((d.x, d.y))
                if len(track.history) > self._history_length:
                    track.history = track.history[-self._history_length :]
                unmatched_dets.remove(best_idx)
                unmatched_tracks.discard(tid)

        # Existing tracks that didn't match get a "missed frame" mark.
        for tid in unmatched_tracks:
            track = self._tracks[tid]
            track.missed_frames += 1
            track.visible = False
            if track.missed_frames > self._occlusion_tolerance_frames:
                # Permanent removal happens in PocketEventDetector; here we
                # simply leave the track around in invisible state so the
                # pocket detector can still inspect it.
                pass

        # Anything left over is a brand new track.
        for di in unmatched_dets:
            d = detections[di]
            tid = next(self._ids)
            color = classify(d.color_patch_hsv)
            self._tracks[tid] = TrackedBall(
                track_id=tid,
                x=d.x,
                y=d.y,
                r=d.r,
                last_seen_t_ms=t_ms,
                color=color,
                color_patch_hsv=d.color_patch_hsv,
                missed_frames=0,
                visible=True,
                history=[(d.x, d.y)],
            )
        return self.tracks

    def remove(self, track_id: int) -> None:
        self._tracks.pop(track_id, None)


__all__ = ["BallTracker", "TrackedBall"]
