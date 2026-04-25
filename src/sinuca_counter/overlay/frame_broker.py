"""Latest-frame broker for MJPEG streaming.

The vision worker encodes a frame as JPEG every few iterations and publishes
it here. The MJPEG HTTP endpoint polls the broker and yields the newest
frame on the wire, so the browser's ``<img src="/stream.mjpg">`` shows the
same footage the scoring engine is watching.

Frames are stored as raw JPEG bytes to keep the broker independent of
OpenCV or numpy in the HTTP handler.
"""

from __future__ import annotations

import threading
from pathlib import Path

_PLACEHOLDER_JPEG_PATH = Path(__file__).resolve().parent / "static" / "placeholder.jpg"


def _placeholder_bytes() -> bytes:
    if _PLACEHOLDER_JPEG_PATH.exists():
        return _PLACEHOLDER_JPEG_PATH.read_bytes()
    # A 1x1 black JPEG as absolute fallback.
    return bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000ffdb004300"
        "080606070605080707070909080a0c140d0c0b0b0c1912130f"
        "141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c3033"
        "3434 1f27393d38323c2e333432 ffc0000b080001000101011100ffc400"
        "1f0000010501010101010100000000000000000102030405"
        "06070809 0a0bffc4 00b5 10 00 02 01 03 03 02 04 03 05 05 04 04 00 00 01 7d"
        "01 02 03 00 04 11 05 12 21 31 41 06 13 51 61 07 22 71 14 32 81 91 a1 08"
        "23 42 b1 c1 15 52 d1 f0 24 33 62 72 82 09 0a 16 17 18 19 1a 25 26 27 28"
        "29 2a 34 35 36 37 38 39 3a 43 44 45 46 47 48 49 4a 53 54 55 56 57 58 59"
        "5a 63 64 65 66 67 68 69 6a 73 74 75 76 77 78 79 7a 83 84 85 86 87 88 89"
        "8a 92 93 94 95 96 97 98 99 9a a2 a3 a4 a5 a6 a7 a8 a9 aa b2 b3 b4 b5 b6"
        "b7 b8 b9 ba c2 c3 c4 c5 c6 c7 c8 c9 ca d2 d3 d4 d5 d6 d7 d8 d9 da e1 e2"
        "e3 e4 e5 e6 e7 e8 e9 ea f1 f2 f3 f4 f5 f6 f7 f8 f9 fa ff da 00 08 01 01"
        "00 00 3f 00 fb d0 ff d9".replace(" ", "")
    )


class FrameBroker:
    """Thread-safe holder for the newest JPEG frame.

    The worker thread calls :meth:`publish` to set the current frame; HTTP
    handlers call :meth:`snapshot` to read it. :meth:`wait_for_update` blocks
    a consumer until a new frame is published (or a timeout elapses), which
    keeps the MJPEG loop from busy-polling the lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._latest: bytes | None = None
        self._version = 0

    def publish(self, jpeg_bytes: bytes) -> None:
        with self._condition:
            self._latest = jpeg_bytes
            self._version += 1
            self._condition.notify_all()

    def snapshot(self) -> tuple[bytes, int]:
        with self._lock:
            data = self._latest if self._latest is not None else _placeholder_bytes()
            return data, self._version

    def wait_for_update(self, last_version: int, timeout: float = 1.0) -> tuple[bytes, int]:
        """Block until the stored version is greater than ``last_version``."""

        with self._condition:
            if self._version <= last_version:
                self._condition.wait(timeout=timeout)
            data = self._latest if self._latest is not None else _placeholder_bytes()
            return data, self._version


__all__ = ["FrameBroker"]
