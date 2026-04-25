"""YOLO-based ball detector.

Implements :class:`BallDetector` using an `Ultralytics <https://docs.ultralytics.com/>`_
YOLO model. Out of the box it uses ``yolov8n.pt`` pretrained on COCO and
filters for the generic ``sports ball`` class (index 32), which is a
surprisingly effective starting point for billiards balls. Fine-tuning on
domain footage is recommended but not required to get useful detections.

The detector is a drop-in replacement for :class:`HsvBallDetector`: it
consumes a BGR frame and returns :class:`DetectedBall` instances with an
HSV colour patch sampled from the centre of each bounding box. The existing
:class:`ColorClassifier` can consume those patches unchanged.

Requires the optional ``[yolo]`` extra (``uv sync --extra yolo``). When the
extra is not installed, constructing this class raises a helpful
:class:`ImportError`.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from .detector import DetectedBall

log = logging.getLogger(__name__)

COCO_SPORTS_BALL_CLASS = 32


class YoloBallDetector:
    """Ball detector backed by an Ultralytics YOLO model."""

    def __init__(
        self,
        weights: str = "yolov8n.pt",
        *,
        classes: list[int] | None = None,
        conf: float = 0.25,
        iou: float = 0.45,
        imgsz: int = 640,
        device: str | None = None,
    ) -> None:
        try:
            from ultralytics import YOLO  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "YoloBallDetector requires the optional `ultralytics` package. "
                "Install the YOLO extras with `uv sync --extra yolo`."
            ) from exc
        log.info("loading YOLO weights: %s", weights)
        self._model = YOLO(weights)
        self._classes = classes if classes is not None else [COCO_SPORTS_BALL_CLASS]
        self._conf = conf
        self._iou = iou
        self._imgsz = imgsz
        self._device = device

    def detect(self, frame_bgr: np.ndarray) -> list[DetectedBall]:
        if frame_bgr is None or frame_bgr.size == 0:
            return []
        results = self._model.predict(
            frame_bgr,
            conf=self._conf,
            iou=self._iou,
            imgsz=self._imgsz,
            classes=self._classes,
            verbose=False,
            device=self._device,
        )
        if not results:
            return []
        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        detections: list[DetectedBall] = []
        for box in boxes:
            xyxy = box.xyxy[0].tolist() if hasattr(box.xyxy, "tolist") else list(box.xyxy[0])
            x1, y1, x2, y2 = (float(v) for v in xyxy)
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            r = max(1.0, (x2 - x1 + y2 - y1) / 4.0)
            patch_hsv = _sample_patch_hsv(hsv, cx, cy, r)
            detections.append(DetectedBall(x=cx, y=cy, r=r, color_patch_hsv=patch_hsv))
        return detections


def _sample_patch_hsv(hsv: np.ndarray, cx: float, cy: float, r: float) -> tuple[int, int, int]:
    h, w = hsv.shape[:2]
    radius = max(1, int(r * 0.6))
    x0 = max(0, int(cx) - radius)
    y0 = max(0, int(cy) - radius)
    x1 = min(w, int(cx) + radius + 1)
    y1 = min(h, int(cy) + radius + 1)
    patch = hsv[y0:y1, x0:x1]
    if patch.size == 0:
        return (0, 0, 0)
    med = np.median(patch.reshape(-1, 3), axis=0)
    return (int(med[0]), int(med[1]), int(med[2]))


__all__ = ["COCO_SPORTS_BALL_CLASS", "YoloBallDetector"]
