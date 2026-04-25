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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from sinuca_counter.rules.events import GameEvent, ManualAdjustment, Undo
from sinuca_counter.rules.state import BallColor, ScoreState

from .state_bus import StateBus, state_to_payload

STATIC_DIR = Path(__file__).resolve().parent / "static"


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
) -> FastAPI:
    server = OverlayServer(bus, apply_event)
    app = FastAPI(title="Sinuca Counter Overlay", version="0.1.0")
    app.state.overlay_server = server
    app.state.bus = bus

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

    @app.get("/control")
    async def control_page() -> Any:  # noqa: ANN401
        path = static / "control.html"
        if not path.exists():
            return JSONResponse({"error": "control assets missing"}, status_code=500)
        return FileResponse(path)

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

    return app


__all__ = ["OverlayServer", "create_app"]
