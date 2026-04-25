"""Overlay HTTP/WebSocket server.

Exports a single FastAPI app constructed via :func:`create_app`. The app is
parameterised on a :class:`StateBus` so tests can drive it without a real
vision pipeline.
"""

from .server import OverlayServer, create_app
from .state_bus import StateBus

__all__ = ["OverlayServer", "StateBus", "create_app"]
