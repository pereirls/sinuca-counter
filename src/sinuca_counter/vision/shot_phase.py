"""Rack-delta shot-phase detector.

This replaces the pocket-geometry based detector of Phase 1a with a more
robust approach: watch aggregate ball motion to identify when a shot starts
and when it has settled, then diff the per-colour ball counts between the
two snapshots. Any ball that was on the table before the shot and is not
on the table afterwards is considered pocketed.

Why this is better than "ball disappeared = pocketed":

* It is blind to temporary occlusions by the cue or the player: during the
  shot phase we do NOT emit anything; we only compare counts once the table
  has been still long enough for occluders to have cleared.
* It does not require knowing where the pockets are — no calibration, no
  homography, no 4-corner clicking. "Pocketed" is defined as "was there,
  isn't there anymore after settling", which is its actual physical meaning.
* It naturally pairs each :class:`BallPocketed` with a :class:`TurnEnded`
  emission so the rules engine sees a consistent shot boundary.

The detector runs a tiny state machine::

    IDLE ──(motion rises)──> IN_SHOT ──(motion subsides)──> SETTLING
      ▲                                                       │
      └──────── (settled long enough, emit diff) ─────────────┘

The pre-shot snapshot is taken the instant motion crosses the threshold. The
post-shot snapshot is taken once motion has stayed below the threshold for
``settle_frames`` frames. Any counts that dropped become BallPocketed events.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sinuca_counter.rules.state import BallColor

from .events import BallPocketed, TurnEnded, VisionEvent
from .tracker import BallTracker

log = logging.getLogger(__name__)


@dataclass
class _Snapshot:
    counts: dict[BallColor, int]
    t_ms: int


class ShotPhaseDetector:
    """Emits :class:`BallPocketed` + :class:`TurnEnded` per settled shot.

    Parameters
    ----------
    tracker
        The :class:`BallTracker` feeding this detector.
    speed_threshold
        Aggregate pixel-per-frame motion above which the table is considered
        "in motion". A whole rack of balls at rest sums close to 0; a single
        ball at cue-shot speed is easily several dozen.
    settle_frames
        How many consecutive frames must stay below ``speed_threshold`` after
        a shot before the post-shot snapshot is taken. ~1.5s at 30fps by
        default — long enough for occluders (cue, player arm) to clear.
    min_shot_frames
        Minimum duration of the IN_SHOT phase before it can transition to
        SETTLING. Prevents single-frame motion spikes from triggering false
        shots.
    max_pocketed_per_shot
        Safety cap: if the computed diff claims more than this many balls
        were pocketed in a single shot, the detector treats it as a
        detection glitch (e.g. whole frame lost) and discards the event.
    """

    def __init__(
        self,
        tracker: BallTracker,
        *,
        speed_threshold: float = 1.5,
        settle_frames: int = 45,
        min_shot_frames: int = 3,
        max_pocketed_per_shot: int = 3,
    ) -> None:
        self._tracker = tracker
        self._speed_threshold = speed_threshold
        self._settle_frames = settle_frames
        self._min_shot_frames = min_shot_frames
        self._max_pocketed_per_shot = max_pocketed_per_shot

        self._state: str = "IDLE"
        self._pre_shot: _Snapshot | None = None
        self._still_frames = 0
        self._shot_frames = 0

    # -- public API --------------------------------------------------------

    @property
    def state_name(self) -> str:
        return self._state

    def evaluate(self, t_ms: int) -> list[VisionEvent]:
        visible = self._tracker.visible_tracks()
        agg_speed = sum(t.speed for t in visible)
        moving = agg_speed > self._speed_threshold

        if self._state == "IDLE":
            return self._on_idle(moving, visible, t_ms)
        if self._state == "IN_SHOT":
            return self._on_in_shot(moving)
        if self._state == "SETTLING":
            return self._on_settling(moving, t_ms)
        return []

    # -- state handlers ----------------------------------------------------

    def _on_idle(self, moving: bool, visible, t_ms: int) -> list[VisionEvent]:
        if not moving:
            return []
        self._pre_shot = _Snapshot(counts=_count_by_color(visible), t_ms=t_ms)
        self._state = "IN_SHOT"
        self._shot_frames = 0
        log.debug("shot start at %sms, snapshot=%s", t_ms, self._pre_shot.counts)
        return []

    def _on_in_shot(self, moving: bool) -> list[VisionEvent]:
        self._shot_frames += 1
        if moving:
            return []
        if self._shot_frames < self._min_shot_frames:
            # Motion spike too short; go back to idle and drop the snapshot.
            self._state = "IDLE"
            self._pre_shot = None
            return []
        self._state = "SETTLING"
        self._still_frames = 0
        return []

    def _on_settling(self, moving: bool, t_ms: int) -> list[VisionEvent]:
        if moving:
            self._state = "IN_SHOT"
            self._still_frames = 0
            return []
        self._still_frames += 1
        if self._still_frames < self._settle_frames:
            return []
        return self._finalise_shot(t_ms)

    def _finalise_shot(self, t_ms: int) -> list[VisionEvent]:
        post_counts = _count_by_color(self._tracker.visible_tracks())
        pre = self._pre_shot.counts if self._pre_shot else {}
        events: list[VisionEvent] = []
        pocketed = 0
        for color, pre_count in pre.items():
            delta = pre_count - post_counts.get(color, 0)
            for _ in range(max(0, delta)):
                events.append(BallPocketed(color=color, pocket_id="unknown", t_ms=t_ms))
                pocketed += 1
        if pocketed > self._max_pocketed_per_shot:
            log.warning(
                "shot delta implies %d pocketed balls (cap=%d); discarding as a detection glitch",
                pocketed,
                self._max_pocketed_per_shot,
            )
            events = []
            pocketed = 0
        events.append(TurnEnded(pocketed_this_turn=pocketed, t_ms=t_ms))
        self._state = "IDLE"
        self._pre_shot = None
        self._still_frames = 0
        self._shot_frames = 0
        log.debug("shot ended at %sms, pocketed=%d", t_ms, pocketed)
        return events


def _count_by_color(visible_tracks) -> dict[BallColor, int]:
    counts: dict[BallColor, int] = {}
    for t in visible_tracks:
        counts[t.color] = counts.get(t.color, 0) + 1
    return counts


__all__ = ["ShotPhaseDetector"]
