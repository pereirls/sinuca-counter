"""VideoSource protocol — the only contract a frame producer must satisfy."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class VideoSource(Protocol):
    """Iterates over frames from some underlying source.

    Implementations must yield ``(frame, timestamp_ms)`` tuples where ``frame``
    is a BGR ``numpy.ndarray`` with shape ``(H, W, 3)`` and ``timestamp_ms`` is
    a monotonically non-decreasing integer.

    The stream ends when the iterator is exhausted (file ends, user stops the
    webcam, etc.). Implementations are responsible for releasing any resources
    when iteration ends.
    """

    def frames(self) -> Iterator[tuple[np.ndarray, int]]: ...

    def close(self) -> None: ...
