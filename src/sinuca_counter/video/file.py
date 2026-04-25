"""File-backed video source. Wraps :class:`cv2.VideoCapture`."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np


class FileVideoSource:
    """Reads frames from a video file on disk.

    Parameters
    ----------
    path:
        Path to a video file readable by OpenCV (mp4, mkv, mov, ...).

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    RuntimeError
        If OpenCV cannot open the file (typically because ffmpeg is missing).
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        if not self._path.exists():
            raise FileNotFoundError(f"video file not found: {self._path}")
        self._capture = cv2.VideoCapture(str(self._path))
        if not self._capture.isOpened():
            raise RuntimeError(
                f"OpenCV could not open {self._path!s}. Make sure ffmpeg is installed."
            )

    @property
    def path(self) -> Path:
        return self._path

    @property
    def fps(self) -> float:
        return float(self._capture.get(cv2.CAP_PROP_FPS) or 0.0)

    def frames(self) -> Iterator[tuple[np.ndarray, int]]:
        try:
            while True:
                ok, frame = self._capture.read()
                if not ok or frame is None:
                    return
                t_ms = int(self._capture.get(cv2.CAP_PROP_POS_MSEC))
                yield frame, t_ms
        finally:
            self.close()

    def close(self) -> None:
        if self._capture is not None and self._capture.isOpened():
            self._capture.release()
