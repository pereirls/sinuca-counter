"""Vision pipeline orchestrator.

Connects :class:`BallDetector`, :class:`ColorClassifier`, :class:`BallTracker`
and :class:`ShotPhaseDetector` into a single component that turns raw BGR
frames into :class:`VisionEvent` streams. The pipeline operates on native
frame coordinates — no homography, no manual table calibration — and
relies on the detector (OpenCV classical or YOLO) to localise the balls.

Swap the :class:`BallDetector` implementation to trade off CPU cost vs.
robustness without touching this orchestrator or anything downstream.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from .classifier import ColorClassifier
from .detector import BallDetector
from .events import FrameProcessed, VisionEvent
from .shot_phase import ShotPhaseDetector
from .tracker import BallTracker


class VisionPipeline:
    """Frame in, events out."""

    def __init__(
        self,
        detector: BallDetector,
        classifier: ColorClassifier,
        tracker: BallTracker,
        shot_phase_detector: ShotPhaseDetector,
    ) -> None:
        self._detector = detector
        self._classifier = classifier
        self._tracker = tracker
        self._shot_phase_detector = shot_phase_detector

    def process(self, frame: np.ndarray, t_ms: int) -> Iterable[VisionEvent]:
        detections = self._detector.detect(frame)
        self._tracker.update(detections, t_ms, self._classifier.classify)
        events: list[VisionEvent] = list(self._shot_phase_detector.evaluate(t_ms))
        events.append(
            FrameProcessed(
                t_ms=t_ms,
                n_tracks=len(self._tracker.visible_tracks()),
            )
        )
        return events


__all__ = ["VisionPipeline"]
