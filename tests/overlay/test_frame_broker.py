"""Tests for the FrameBroker (shared latest-frame store for MJPEG)."""

from __future__ import annotations

import threading
import time

from sinuca_counter.overlay.frame_broker import FrameBroker


def test_snapshot_returns_placeholder_when_empty() -> None:
    broker = FrameBroker()
    data, version = broker.snapshot()
    assert isinstance(data, bytes)
    assert len(data) > 0
    assert version == 0


def test_publish_then_snapshot_returns_published_bytes() -> None:
    broker = FrameBroker()
    payload = b"\xff\xd8\xff\xd9"  # minimal JPEG markers
    broker.publish(payload)
    data, version = broker.snapshot()
    assert data == payload
    assert version == 1


def test_wait_for_update_returns_on_publish() -> None:
    broker = FrameBroker()
    broker.publish(b"first")

    result: dict[str, bytes | int] = {}

    def waiter() -> None:
        data, version = broker.wait_for_update(last_version=1, timeout=2.0)
        result["data"] = data
        result["version"] = version

    t = threading.Thread(target=waiter)
    t.start()
    time.sleep(0.05)
    broker.publish(b"second")
    t.join(timeout=2.0)

    assert result.get("data") == b"second"
    assert result.get("version") == 2


def test_wait_for_update_times_out_without_new_publish() -> None:
    broker = FrameBroker()
    broker.publish(b"only")
    start = time.monotonic()
    data, version = broker.wait_for_update(last_version=1, timeout=0.15)
    elapsed = time.monotonic() - start
    assert data == b"only"
    assert version == 1
    assert elapsed < 0.5  # returned after the configured timeout
