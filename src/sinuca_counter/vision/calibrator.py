"""Table calibration: pick four corners → homography to top-down view.

The MVP relies on a fixed camera. Calibration is done once per video and
persisted to ``<video>.calib.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# Top-down virtual table dimensions in pixels. Aspect ratio 2:1 (typical pool
# table); resolution chosen for fast Hough transforms.
TOP_DOWN_W = 800
TOP_DOWN_H = 400


@dataclass(frozen=True)
class CalibrationData:
    """Persisted calibration for a single video."""

    corners: list[list[float]]  # 4 (x,y) clicks in source-frame coordinates
    top_down_size: tuple[int, int] = (TOP_DOWN_W, TOP_DOWN_H)
    pocket_radius_px: int = 28

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["top_down_size"] = list(self.top_down_size)
        return d

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CalibrationData:
        size = tuple(payload.get("top_down_size", [TOP_DOWN_W, TOP_DOWN_H]))
        return cls(
            corners=[list(c) for c in payload["corners"]],
            top_down_size=(int(size[0]), int(size[1])),
            pocket_radius_px=int(payload.get("pocket_radius_px", 28)),
        )

    def pocket_centers(self) -> dict[str, tuple[int, int]]:
        """Six pocket positions in top-down coordinates."""

        w, h = self.top_down_size
        return {
            "top_left": (0, 0),
            "top_mid": (w // 2, 0),
            "top_right": (w, 0),
            "bottom_left": (0, h),
            "bottom_mid": (w // 2, h),
            "bottom_right": (w, h),
        }


class TableCalibrator:
    """Build / load / apply the perspective transform for a table."""

    def __init__(self, calibration: CalibrationData) -> None:
        self._calibration = calibration
        src = np.array(calibration.corners, dtype=np.float32)
        if src.shape != (4, 2):
            raise ValueError(f"calibration must contain exactly 4 corners, got {src.shape}")
        w, h = calibration.top_down_size
        dst = np.array(
            [[0, 0], [w, 0], [w, h], [0, h]],
            dtype=np.float32,
        )
        self._homography = cv2.getPerspectiveTransform(src, dst)

    @property
    def calibration(self) -> CalibrationData:
        return self._calibration

    @property
    def top_down_size(self) -> tuple[int, int]:
        return self._calibration.top_down_size

    def warp(self, frame: np.ndarray) -> np.ndarray:
        return cv2.warpPerspective(frame, self._homography, self._calibration.top_down_size)

    # -- persistence -------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> TableCalibrator:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(CalibrationData.from_dict(data))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self._calibration.to_dict(), indent=2),
            encoding="utf-8",
        )

    # -- interactive picking ----------------------------------------------

    @classmethod
    def from_clicks(
        cls, frame: np.ndarray, *, window_name: str = "Calibrate table"
    ) -> TableCalibrator:  # pragma: no cover - requires a display
        """Open a CV2 window and ask the user to click the 4 corners."""

        clicks: list[tuple[float, float]] = []

        def on_click(event: int, x: int, y: int, flags: int, _param: Any) -> None:
            if event == cv2.EVENT_LBUTTONDOWN and len(clicks) < 4:
                clicks.append((float(x), float(y)))

        cv2.namedWindow(window_name)
        cv2.setMouseCallback(window_name, on_click)

        while len(clicks) < 4:
            view = frame.copy()
            for i, (cx, cy) in enumerate(clicks):
                cv2.circle(view, (int(cx), int(cy)), 6, (0, 255, 0), 2)
                cv2.putText(
                    view,
                    str(i + 1),
                    (int(cx) + 8, int(cy) - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2,
                )
            cv2.putText(
                view,
                "Click 4 corners (TL, TR, BR, BL) and press any key when done",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
            )
            cv2.imshow(window_name, view)
            if cv2.waitKey(20) & 0xFF != 255:  # any key
                break
        cv2.destroyWindow(window_name)
        if len(clicks) != 4:
            raise RuntimeError("calibration aborted: 4 corners are required")
        return cls(CalibrationData(corners=[list(c) for c in clicks]))


__all__ = ["TOP_DOWN_H", "TOP_DOWN_W", "CalibrationData", "TableCalibrator"]
