"""Video source abstractions.

The MVP only ships :class:`FileVideoSource`. Future phases (webcam, screen
capture) plug in by implementing :class:`VideoSource` without changes to any
consumer.
"""

from .base import VideoSource
from .file import FileVideoSource

__all__ = ["FileVideoSource", "VideoSource"]
