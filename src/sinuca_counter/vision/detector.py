"""Ball detector — Phase 1a uses HSV + HoughCircles.

Phase 1b will provide a ``YoloBallDetector`` implementing the same protocol
without changes to the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import cv2
import numpy as np


@dataclass(frozen=True)
class DetectedBall:
    """A detection in top-down coordinates."""

    x: float
    y: float
    r: float
    color_patch_hsv: tuple[int, int, int]


@runtime_checkable
class BallDetector(Protocol):
    """Single method: detect balls on a top-down rectified image."""

    def detect(self, top_down_bgr: np.ndarray) -> list[DetectedBall]: ...


class HsvBallDetector:
    """Classical pipeline: mask out the felt then run HoughCircles.

    Parameters are tunable via constructor arguments so an operator can iterate
    quickly when working on a new table; defaults are the values that worked on
    the project's reference fixtures.
    """

    def __init__(
        self,
        *,
        felt_hue_range: tuple[int, int] = (35, 95),
        felt_saturation_min: int = 60,
        felt_value_min: int = 40,
        min_radius: int = 8,
        max_radius: int = 22,
        hough_dp: float = 1.2,
        hough_min_dist: float = 18.0,
        hough_param1: float = 80.0,
        hough_param2: float = 18.0,
    ) -> None:
        self._felt_hue_range = felt_hue_range
        self._felt_saturation_min = felt_saturation_min
        self._felt_value_min = felt_value_min
        self._min_radius = min_radius
        self._max_radius = max_radius
        self._hough_dp = hough_dp
        self._hough_min_dist = hough_min_dist
        self._hough_param1 = hough_param1
        self._hough_param2 = hough_param2

    # -- public API --------------------------------------------------------

    def detect(self, top_down_bgr: np.ndarray) -> list[DetectedBall]:
        if top_down_bgr is None or top_down_bgr.size == 0:
            return []
        hsv = cv2.cvtColor(top_down_bgr, cv2.COLOR_BGR2HSV)
        not_felt = self._not_felt_mask(hsv)
        gray = cv2.cvtColor(top_down_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.bitwise_and(gray, gray, mask=not_felt)
        gray = cv2.medianBlur(gray, 5)
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=self._hough_dp,
            minDist=self._hough_min_dist,
            param1=self._hough_param1,
            param2=self._hough_param2,
            minRadius=self._min_radius,
            maxRadius=self._max_radius,
        )
        results: list[DetectedBall] = []
        if circles is None:
            return results
        for cx, cy, r in circles[0]:
            patch_hsv = self._sample_patch(hsv, int(cx), int(cy), int(r))
            results.append(
                DetectedBall(
                    x=float(cx),
                    y=float(cy),
                    r=float(r),
                    color_patch_hsv=patch_hsv,
                )
            )
        return results

    # -- helpers -----------------------------------------------------------

    def _not_felt_mask(self, hsv: np.ndarray) -> np.ndarray:
        h_lo, h_hi = self._felt_hue_range
        felt = cv2.inRange(
            hsv,
            np.array([h_lo, self._felt_saturation_min, self._felt_value_min], dtype=np.uint8),
            np.array([h_hi, 255, 255], dtype=np.uint8),
        )
        # Smooth and invert.
        felt = cv2.morphologyEx(felt, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        return cv2.bitwise_not(felt)

    @staticmethod
    def _sample_patch(hsv: np.ndarray, cx: int, cy: int, r: int) -> tuple[int, int, int]:
        h_img, w_img = hsv.shape[:2]
        radius = max(1, r - 2)
        x0 = max(0, cx - radius)
        y0 = max(0, cy - radius)
        x1 = min(w_img, cx + radius + 1)
        y1 = min(h_img, cy + radius + 1)
        patch = hsv[y0:y1, x0:x1]
        if patch.size == 0:
            return (0, 0, 0)
        # Median is robust to highlights/shadows.
        med = np.median(patch.reshape(-1, 3), axis=0)
        return (int(med[0]), int(med[1]), int(med[2]))


# Public alias preferred in user-facing code.
OpenCVBallDetector = HsvBallDetector


__all__ = ["BallDetector", "DetectedBall", "HsvBallDetector", "OpenCVBallDetector"]
