"""HTTP + WebSocket contract tests for the overlay server."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

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
