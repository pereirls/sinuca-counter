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

    @property
    def duration_ms(self) -> int:
        """Total video duration in milliseconds, or 0 when unknown."""

        frame_count = self._capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        fps = self.fps
        if frame_count <= 0 or fps <= 0:
            return 0
        return int(round(frame_count / fps * 1000.0))

    def position_ms(self) -> int:
        return int(self._capture.get(cv2.CAP_PROP_POS_MSEC))

    def seek_ms(self, ms: int) -> None:
        """Seek the underlying ``VideoCapture`` to ``ms`` milliseconds."""

        target = max(0, int(ms))
        self._capture.set(cv2.CAP_PROP_POS_MSEC, float(target))

    def read_frame(self) -> tuple[np.ndarray, int] | None:
        """Read one frame; returns ``None`` when the stream is exhausted.

        This is the pull-based companion to :meth:`frames` and is what the
        :class:`VisionWorker` uses when playback control (pause/seek) is
        active — driving an iterator from the outside is awkward.
        """

        ok, frame = self._capture.read()
        if not ok or frame is None:
            return None
        return frame, self.position_ms()

    def frames(self) -> Iterator[tuple[np.ndarray, int]]:
        try:
            while True:
                item = self.read_frame()
                if item is None:
                    return
                yield item
        finally:
            self.close()

    def close(self) -> None:
        if self._capture is not None and self._capture.isOpened():
            self._capture.release()
