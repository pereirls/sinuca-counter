"""Vision pipeline orchestrator.

Connects :class:`TableCalibrator`, :class:`BallDetector`, :class:`ColorClassifier`,
:class:`BallTracker`, :class:`PocketEventDetector` and :class:`TurnEndDetector`
into a single component that turns frames into :class:`VisionEvent` streams.

Phase 1b will inject a different :class:`BallDetector` (YOLO) without
touching this orchestrator.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from .calibrator import TableCalibrator
from .classifier import ColorClassifier
from .detector import BallDetector
from .events import FrameProcessed, VisionEvent
from .pocket import PocketEventDetector
from .tracker import BallTracker
from .turn import TurnEndDetector


class VisionPipeline:
    """Frame in, events out."""

    def __init__(
        self,
        calibrator: TableCalibrator,
        detector: BallDetector,
        classifier: ColorClassifier,
        tracker: BallTracker,
        pocket_detector: PocketEventDetector,
        turn_detector: TurnEndDetector,
    ) -> None:
        self._calibrator = calibrator
        self._detector = detector
        self._classifier = classifier
        self._tracker = tracker
        self._pocket_detector = pocket_detector
        self._turn_detector = turn_detector

    def process(self, frame: np.ndarray, t_ms: int) -> Iterable[VisionEvent]:
        rectified = self._calibrator.warp(frame)
        detections = self._detector.detect(rectified)
        self._tracker.update(detections, t_ms, self._classifier.classify)
        events: list[VisionEvent] = []
        for pocket_event in self._pocket_detector.evaluate(t_ms):
            self._turn_detector.note_pocket()
            events.append(pocket_event)
        events.extend(self._turn_detector.evaluate(t_ms))
        events.append(FrameProcessed(t_ms=t_ms, n_tracks=len(self._tracker.visible_tracks())))
        return events


__all__ = ["VisionPipeline"]
