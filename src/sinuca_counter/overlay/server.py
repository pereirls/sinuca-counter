"""FastAPI server: overlay, control panel and WebSocket bridge.

The server is intentionally agnostic of the rules implementation: it talks to
the engine through a callback (``apply_event``) and broadcasts the resulting
:class:`ScoreState` to any subscriber.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from sinuca_counter.rules.events import GameEvent, ManualAdjustment, Undo
from sinuca_counter.rules.state import BallColor, ScoreState

from .frame_broker import FrameBroker
from .playback import PlaybackBus, PlaybackController
from .state_bus import StateBus, state_to_payload

STATIC_DIR = Path(__file__).resolve().parent / "static"

MJPEG_BOUNDARY = "sinuca-frame"


def mjpeg_generator(
    broker: FrameBroker,
    *,
    max_chunks: int | None = None,
    wait_timeout: float = 1.0,
):
    """Yield raw MJPEG boundary+frame chunks from a :class:`FrameBroker`.

    ``max_chunks`` is a test knob that makes the generator terminate after
    ``max_chunks`` frames; production callers leave it at ``None`` for an
    infinite stream. This generator is sync so Starlette runs it in a thread
    pool, which keeps the event loop free.
    """

    last_version = -1
    produced = 0
    while True:
        if max_chunks is not None and produced >= max_chunks:
            return
        jpeg, version = broker.wait_for_update(last_version, timeout=wait_timeout)
        last_version = version
        yield (
            (
                f"--{MJPEG_BOUNDARY}\r\n"
                "Content-Type: image/jpeg\r\n"
                f"Content-Length: {len(jpeg)}\r\n\r\n"
            ).encode("ascii")
            + jpeg
            + b"\r\n"
        )
        produced += 1


# --- request bodies ----------------------------------------------------------


class AdjustBody(BaseModel):
    player: Literal["p1", "p2"]
    delta: int


class SetScoreBody(BaseModel):
    p1: int = Field(..., ge=0)
    p2: int = Field(..., ge=0)


class RenameBody(BaseModel):
    p1: str | None = None
    p2: str | None = None


class CorrectLastBody(BaseModel):
    color: str  # value of BallColor


class SeekBody(BaseModel):
    ms: int = Field(..., ge=0)


class SpeedBody(BaseModel):
    rate: float = Field(..., gt=0)


# --- async wiring ------------------------------------------------------------


ApplyEventFn = Callable[[GameEvent], ScoreState | Awaitable[ScoreState]]


class OverlayServer:
    """Glue that owns a :class:`StateBus` and an apply-event hook."""

    def __init__(
        self,
        bus: StateBus,
        apply_event: ApplyEventFn,
    ) -> None:
        self._bus = bus
        self._apply_event = apply_event
        self._lock = asyncio.Lock()

    async def submit(self, event: GameEvent) -> ScoreState:
        """Apply an event and broadcast the resulting state."""

        async with self._lock:
            result = self._apply_event(event)
            if asyncio.iscoroutine(result):
                state = await result
            else:
                state = result  # type: ignore[assignment]
        await self._bus.publish(state)
        return state

    @property
    def bus(self) -> StateBus:
        return self._bus


# --- factory -----------------------------------------------------------------


def create_app(
    bus: StateBus,
    apply_event: ApplyEventFn,
    *,
    static_dir: Path | None = None,
    frame_broker: FrameBroker | None = None,
    playback_controller: PlaybackController | None = None,
    playback_bus: PlaybackBus | None = None,
) -> FastAPI:
    server = OverlayServer(bus, apply_event)
    app = FastAPI(title="Sinuca Counter Overlay", version="0.1.0")
    app.state.overlay_server = server
    app.state.bus = bus
    broker = frame_broker if frame_broker is not None else FrameBroker()
    app.state.frame_broker = broker
    app.state.playback_controller = playback_controller
    app.state.playback_bus = playback_bus

    static = static_dir or STATIC_DIR
    if static.exists():
        app.mount(
            "/static",
            StaticFiles(directory=str(static)),
            name="static",
        )

    @app.get("/")
    async def overlay_page(request: Request) -> Any:  # noqa: ANN401
        theme = request.query_params.get("theme", "transparent")
        if theme not in {"transparent", "window"}:
            theme = "transparent"
        path = static / "overlay.html"
        if not path.exists():
            return JSONResponse({"error": "overlay assets missing"}, status_code=500)
        return FileResponse(path)

    @app.get("/watch")
    async def watch_page() -> Any:  # noqa: ANN401
        path = static / "watch.html"
        if not path.exists():
            return JSONResponse({"error": "watch assets missing"}, status_code=500)
        return FileResponse(path)

    @app.get("/control")
    async def control_page() -> Any:  # noqa: ANN401
        path = static / "control.html"
        if not path.exists():
            return JSONResponse({"error": "control assets missing"}, status_code=500)
        return FileResponse(path)

    @app.get("/stream.mjpg")
    async def stream_mjpg(request: Request) -> Any:  # noqa: ANN401
        return StreamingResponse(
            mjpeg_generator(broker),
            media_type=f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}",
        )

    @app.get("/state")
    async def get_state() -> dict[str, Any]:
        return state_to_payload(bus.state)

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        async with bus.subscribe() as queue:
            try:
                while True:
                    state = await queue.get()
                    await socket.send_json(state_to_payload(state))
            except WebSocketDisconnect:
                return
            except Exception:  # pragma: no cover - defensive
                return

    @app.post("/control/adjust")
    async def control_adjust(body: AdjustBody) -> dict[str, Any]:
        state = await server.submit(
            ManualAdjustment(op="adjust", player=body.player, delta=body.delta)
        )
        return state_to_payload(state)

    @app.post("/control/set_score")
    async def control_set_score(body: SetScoreBody) -> dict[str, Any]:
        state = await server.submit(
            ManualAdjustment(op="set_score", p1_score=body.p1, p2_score=body.p2)
        )
        return state_to_payload(state)

    @app.post("/control/swap_turn")
    async def control_swap_turn() -> dict[str, Any]:
        state = await server.submit(ManualAdjustment(op="swap_turn"))
        return state_to_payload(state)

    @app.post("/control/rename")
    async def control_rename(body: RenameBody) -> dict[str, Any]:
        state = await server.submit(ManualAdjustment(op="rename", p1_name=body.p1, p2_name=body.p2))
        return state_to_payload(state)

    @app.post("/control/correct_last")
    async def control_correct_last(body: CorrectLastBody) -> dict[str, Any]:
        try:
            color = BallColor(body.color)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        state = await server.submit(ManualAdjustment(op="correct_last", color=color))
        return state_to_payload(state)

    @app.post("/control/undo")
    async def control_undo() -> dict[str, Any]:
        state = await server.submit(Undo())
        return state_to_payload(state)

    @app.post("/control/pause")
    async def control_pause() -> dict[str, Any]:
        state = await server.submit(ManualAdjustment(op="pause"))
        return state_to_payload(state)

    @app.post("/control/resume")
    async def control_resume() -> dict[str, Any]:
        state = await server.submit(ManualAdjustment(op="resume"))
        return state_to_payload(state)

    @app.post("/control/reset")
    async def control_reset() -> dict[str, Any]:
        state = await server.submit(ManualAdjustment(op="reset"))
        return state_to_payload(state)

    @app.post("/control/start_match")
    async def control_start_match() -> dict[str, Any]:
        state = await server.submit(ManualAdjustment(op="start_match"))
        return state_to_payload(state)

    @app.post("/control/stop_match")
    async def control_stop_match() -> dict[str, Any]:
        state = await server.submit(ManualAdjustment(op="stop_match"))
        return state_to_payload(state)

    # --- playback control ---------------------------------------------------

    def _require_playback() -> PlaybackController:
        if playback_controller is None:
            raise HTTPException(
                status_code=409,
                detail="playback control unavailable (no video source)",
            )
        return playback_controller

    async def _publish_playback_now() -> None:
        if playback_controller is not None and playback_bus is not None:
            await playback_bus.publish(playback_controller.snapshot())

    @app.get("/playback")
    async def get_playback() -> dict[str, Any]:
        if playback_controller is None:
            return {
                "paused": False,
                "speed": 1.0,
                "current_time_ms": 0,
                "duration_ms": 0,
                "has_video": False,
            }
        return playback_controller.snapshot().to_dict()

    @app.post("/control/playback/pause")
    async def control_playback_pause() -> dict[str, Any]:
        ctrl = _require_playback()
        ctrl.set_paused(True)
        await _publish_playback_now()
        return ctrl.snapshot().to_dict()

    @app.post("/control/playback/play")
    async def control_playback_play() -> dict[str, Any]:
        ctrl = _require_playback()
        ctrl.set_paused(False)
        await _publish_playback_now()
        return ctrl.snapshot().to_dict()

    @app.post("/control/playback/seek")
    async def control_playback_seek(body: SeekBody) -> dict[str, Any]:
        ctrl = _require_playback()
        ctrl.request_seek(body.ms)
        await _publish_playback_now()
        return ctrl.snapshot().to_dict()

    @app.post("/control/playback/speed")
    async def control_playback_speed(body: SpeedBody) -> dict[str, Any]:
        ctrl = _require_playback()
        ctrl.set_speed(body.rate)
        await _publish_playback_now()
        return ctrl.snapshot().to_dict()

    @app.websocket("/ws/playback")
    async def ws_playback(socket: WebSocket) -> None:
        await socket.accept()
        if playback_bus is None:
            # Send a single "no video" snapshot and close so the JS client
            # gets predictable behaviour without having to special-case the
            # endpoint not being there.
            await socket.send_json(
                {
                    "paused": False,
                    "speed": 1.0,
                    "current_time_ms": 0,
                    "duration_ms": 0,
                    "has_video": False,
                }
            )
            await socket.close()
            return
        async with playback_bus.subscribe() as queue:
            try:
                while True:
                    snapshot = await queue.get()
                    await socket.send_json(snapshot.to_dict())
            except WebSocketDisconnect:
                return
            except Exception:  # pragma: no cover - defensive
                return

    return app


__all__ = ["OverlayServer", "create_app"]
