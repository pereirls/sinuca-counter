"""Computer vision pipeline.

Phase 1a ships a classical OpenCV detector. Phase 1b will swap the
:class:`BallDetector` implementation for a YOLO-based one without changing any
other module.
"""

from .calibrator import CalibrationData, TableCalibrator
from .classifier import ColorClassifier
from .detector import (
    BallDetector,
    DetectedBall,
    HsvBallDetector,
    OpenCVBallDetector,
)
from .events import CalibrationLost, FrameProcessed, VisionEvent
from .palette import PaletteCalibrator
from .pipeline import VisionPipeline
from .pocket import PocketEventDetector
from .tracker import BallTracker, TrackedBall
from .turn import TurnEndDetector

__all__ = [
    "BallDetector",
    "BallTracker",
    "CalibrationData",
    "CalibrationLost",
    "ColorClassifier",
    "DetectedBall",
    "FrameProcessed",
    "HsvBallDetector",
    "OpenCVBallDetector",
    "PaletteCalibrator",
    "PocketEventDetector",
    "TableCalibrator",
    "TrackedBall",
    "TurnEndDetector",
    "VisionEvent",
    "VisionPipeline",
]
