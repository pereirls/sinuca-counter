"""Computer vision pipeline.

Default detector in this release is YOLO via Ultralytics (``YoloBallDetector``,
requires ``uv sync --extra yolo``); the classical OpenCV detector
(``HsvBallDetector``) remains available for environments without GPU/torch.

Detection runs on the native frame — there is no manual table calibration
("4 corner clicks"). Score events are inferred by diffing per-colour ball
counts between the pre-shot and post-shot stable snapshots
(:class:`ShotPhaseDetector`).
"""

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
from .shot_phase import ShotPhaseDetector
from .tracker import BallTracker, TrackedBall

__all__ = [
    "BallDetector",
    "BallTracker",
    "CalibrationLost",
    "ColorClassifier",
    "DetectedBall",
    "FrameProcessed",
    "HsvBallDetector",
    "OpenCVBallDetector",
    "PaletteCalibrator",
    "ShotPhaseDetector",
    "TrackedBall",
    "VisionEvent",
    "VisionPipeline",
]
