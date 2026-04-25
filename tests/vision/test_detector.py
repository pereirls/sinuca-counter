"""Synthetic-image smoke test for the OpenCV detector."""

from __future__ import annotations

import cv2
import numpy as np

from sinuca_counter.vision.detector import HsvBallDetector


def _green_felt_with_balls() -> np.ndarray:
    img = np.zeros((200, 400, 3), dtype=np.uint8)
    img[:, :] = (40, 130, 40)  # BGR-ish green felt
    cv2.circle(img, (80, 100), 14, (10, 30, 200), -1)  # red ball
    cv2.circle(img, (320, 100), 14, (240, 240, 240), -1)  # white-ish ball
    return img


def test_detector_finds_at_least_one_ball() -> None:
    detector = HsvBallDetector()
    img = _green_felt_with_balls()
    detections = detector.detect(img)
    assert len(detections) >= 1


def test_detector_returns_empty_on_empty_input() -> None:
    detector = HsvBallDetector()
    detections = detector.detect(np.zeros((0, 0, 3), dtype=np.uint8))
    assert detections == []
