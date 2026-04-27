"""HTTP + WebSocket contract tests for the overlay server."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from sinuca_counter.overlay.frame_broker import FrameBroker
from sinuca_counter.overlay.server import create_app
from sinuca_counter.overlay.state_bus import StateBus
from sinuca_counter.rules.brazilian import BrazilianRules
from sinuca_counter.rules.events import GameEvent
from sinuca_counter.rules.state import ScoreState


def _make_client() -> tuple[TestClient, BrazilianRules, StateBus]:
    rules = BrazilianRules(p1_name="Lucas", p2_name="Ricardo")
    bus = StateBus(initial=rules.state)

    def apply(event: GameEvent) -> ScoreState:
        return rules.apply(event)

    app = create_app(bus, apply)
    return TestClient(app), rules, bus


def test_state_endpoint_returns_initial_state() -> None:
    client, rules, _ = _make_client()
    response = client.get("/state")
    assert response.status_code == 200
    payload = response.json()
    assert payload["p1_name"] == "Lucas"
    assert payload["rules_name"] == "brasileira"


def test_adjust_endpoint_updates_score() -> None:
    client, _, _ = _make_client()
    response = client.post("/control/adjust", json={"player": "p1", "delta": 3})
    assert response.status_code == 200
    assert response.json()["p1_score"] == 3


def test_set_score_endpoint() -> None:
    client, _, _ = _make_client()
    response = client.post("/control/set_score", json={"p1": 7, "p2": 4})
    assert response.status_code == 200
    payload = response.json()
    assert payload["p1_score"] == 7
    assert payload["p2_score"] == 4


def test_swap_turn_endpoint() -> None:
    client, _, _ = _make_client()
    response = client.post("/control/swap_turn")
    assert response.status_code == 200
    assert response.json()["current_player"] == "p2"


def test_rename_endpoint() -> None:
    client, _, _ = _make_client()
    response = client.post("/control/rename", json={"p1": "X", "p2": "Y"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["p1_name"] == "X"
    assert payload["p2_name"] == "Y"


def test_correct_last_endpoint_validates_color() -> None:
    client, _, _ = _make_client()
    response = client.post("/control/correct_last", json={"color": "not_a_color"})
    assert response.status_code == 400


def test_undo_endpoint_reverts_last_event() -> None:
    client, _, _ = _make_client()
    client.post("/control/adjust", json={"player": "p1", "delta": 5})
    response = client.post("/control/undo")
    assert response.status_code == 200
    assert response.json()["p1_score"] == 0


def test_pause_resume_endpoints() -> None:
    client, _, _ = _make_client()
    assert client.post("/control/pause").json()["paused"] is True
    assert client.post("/control/resume").json()["paused"] is False


def test_reset_endpoint() -> None:
    client, _, _ = _make_client()
    client.post("/control/adjust", json={"player": "p1", "delta": 5})
    response = client.post("/control/reset")
    assert response.status_code == 200
    assert response.json()["p1_score"] == 0
    assert response.json()["p1_name"] == "Lucas"


def test_websocket_pushes_initial_state_and_updates() -> None:
    client, _, _ = _make_client()
    with client.websocket_connect("/ws") as ws:
        first = json.loads(ws.receive_text())
        assert first["p1_name"] == "Lucas"
        client.post("/control/adjust", json={"player": "p1", "delta": 1})
        second = json.loads(ws.receive_text())
        assert second["p1_score"] == 1


def test_overlay_html_returned() -> None:
    client, _, _ = _make_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"<html" in response.content


def test_control_html_returned() -> None:
    client, _, _ = _make_client()
    response = client.get("/control")
    assert response.status_code == 200
    assert b"Painel de controle" in response.content


def test_watch_html_returned() -> None:
    client, _, _ = _make_client()
    response = client.get("/watch")
    assert response.status_code == 200
    assert b"stream.mjpg" in response.content


def test_mjpeg_route_is_registered() -> None:
    client, _, _ = _make_client()
    routes = {getattr(r, "path", None) for r in client.app.router.routes}
    assert "/stream.mjpg" in routes


def test_mjpeg_generator_emits_boundary_and_jpeg_bytes() -> None:
    from sinuca_counter.overlay.server import MJPEG_BOUNDARY, mjpeg_generator

    broker = FrameBroker()
    broker.publish(b"\xff\xd8\xff\xd9HELLO")
    chunks = list(mjpeg_generator(broker, max_chunks=1, wait_timeout=0.01))
    assert len(chunks) == 1
    chunk = chunks[0]
    assert f"--{MJPEG_BOUNDARY}".encode() in chunk
    assert b"Content-Type: image/jpeg" in chunk
    assert b"HELLO" in chunk
    assert chunk.endswith(b"\r\n")


def test_mjpeg_generator_uses_placeholder_when_no_frame_published() -> None:
    from sinuca_counter.overlay.server import mjpeg_generator

    broker = FrameBroker()  # no publish()
    chunks = list(mjpeg_generator(broker, max_chunks=1, wait_timeout=0.01))
    assert len(chunks) == 1
    assert b"Content-Type: image/jpeg" in chunks[0]


def test_start_match_and_stop_match_endpoints() -> None:
    client, _, _ = _make_client()
    state = client.post("/control/start_match").json()
    assert state["match_started"] is True
    state = client.post("/control/stop_match").json()
    assert state["match_started"] is False


def _make_client_with_playback(duration_ms: int = 12_000):
    from sinuca_counter.overlay.playback import PlaybackBus, PlaybackController

    rules = BrazilianRules(p1_name="Lucas", p2_name="Ricardo")
    bus = StateBus(initial=rules.state)
    ctrl = PlaybackController(has_video=True, duration_ms=duration_ms)
    pb_bus = PlaybackBus(initial=ctrl.snapshot())

    def apply(event: GameEvent) -> ScoreState:
        return rules.apply(event)

    app = create_app(
        bus,
        apply,
        playback_controller=ctrl,
        playback_bus=pb_bus,
    )
    return TestClient(app), ctrl, pb_bus


def test_playback_endpoint_returns_no_video_when_unavailable() -> None:
    client, _, _ = _make_client()
    response = client.get("/playback")
    assert response.status_code == 200
    assert response.json()["has_video"] is False


def test_playback_pause_play_endpoints_drive_controller() -> None:
    client, ctrl, _ = _make_client_with_playback()
    assert client.post("/control/playback/pause").json()["paused"] is True
    assert ctrl.is_paused() is True
    assert client.post("/control/playback/play").json()["paused"] is False
    assert ctrl.is_paused() is False


def test_playback_seek_endpoint_records_request() -> None:
    client, ctrl, _ = _make_client_with_playback(duration_ms=10_000)
    response = client.post("/control/playback/seek", json={"ms": 4500})
    assert response.status_code == 200
    assert response.json()["current_time_ms"] == 4500
    assert ctrl.consume_seek() == 4500


def test_playback_speed_endpoint_clamps_to_safe_range() -> None:
    client, ctrl, _ = _make_client_with_playback()
    response = client.post("/control/playback/speed", json={"rate": 999.0})
    assert response.status_code == 200
    assert response.json()["speed"] <= 8.0
    assert ctrl.speed() <= 8.0


def test_playback_endpoints_409_when_no_video() -> None:
    client, _, _ = _make_client()
    assert client.post("/control/playback/pause").status_code == 409
    assert client.post("/control/playback/seek", json={"ms": 100}).status_code == 409


def test_playback_websocket_pushes_initial_snapshot() -> None:
    client, _, _ = _make_client_with_playback(duration_ms=8000)
    with client.websocket_connect("/ws/playback") as ws:
        snap = json.loads(ws.receive_text())
        assert snap["has_video"] is True
        assert snap["duration_ms"] == 8000
