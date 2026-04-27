"""Tests for the playback control subsystem."""

from __future__ import annotations

import asyncio

import pytest

from sinuca_counter.overlay.playback import (
    MAX_SPEED,
    MIN_SPEED,
    PlaybackBus,
    PlaybackController,
)


def test_controller_starts_in_default_state() -> None:
    ctrl = PlaybackController(has_video=True, duration_ms=5000)
    snap = ctrl.snapshot()
    assert snap.paused is False
    assert snap.speed == 1.0
    assert snap.current_time_ms == 0
    assert snap.duration_ms == 5000
    assert snap.has_video is True


def test_set_paused_and_speed() -> None:
    ctrl = PlaybackController(has_video=True)
    ctrl.set_paused(True)
    assert ctrl.is_paused() is True
    ctrl.set_paused(False)
    assert ctrl.is_paused() is False
    ctrl.set_speed(2.0)
    assert ctrl.speed() == 2.0


def test_speed_is_clamped_to_safe_range() -> None:
    ctrl = PlaybackController(has_video=True)
    ctrl.set_speed(0.0)
    assert ctrl.speed() == MIN_SPEED
    ctrl.set_speed(999.0)
    assert ctrl.speed() == MAX_SPEED


def test_seek_request_is_consumed_only_once() -> None:
    ctrl = PlaybackController(has_video=True, duration_ms=10_000)
    ctrl.request_seek(3500)
    assert ctrl.consume_seek() == 3500
    assert ctrl.consume_seek() is None


def test_seek_request_clamps_to_duration() -> None:
    ctrl = PlaybackController(has_video=True, duration_ms=5000)
    ctrl.request_seek(99_999)
    assert ctrl.consume_seek() == 5000
    ctrl.request_seek(-100)
    assert ctrl.consume_seek() == 0


def test_report_position_is_reflected_in_snapshot() -> None:
    ctrl = PlaybackController(has_video=True)
    ctrl.report_position(1234)
    assert ctrl.snapshot().current_time_ms == 1234


def test_seek_immediately_updates_reported_position() -> None:
    """The UI thumb should reflect the requested position right away,
    without waiting for the worker to actually seek."""
    ctrl = PlaybackController(has_video=True, duration_ms=10_000)
    ctrl.request_seek(4000)
    assert ctrl.snapshot().current_time_ms == 4000


@pytest.mark.asyncio
async def test_playback_bus_delivers_initial_snapshot_to_subscribers() -> None:
    ctrl = PlaybackController(has_video=True, duration_ms=8_000)
    bus = PlaybackBus(initial=ctrl.snapshot())
    async with bus.subscribe() as queue:
        first = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert first.duration_ms == 8_000


@pytest.mark.asyncio
async def test_playback_bus_publishes_updates() -> None:
    bus = PlaybackBus()
    ctrl = PlaybackController(has_video=True)
    async with bus.subscribe() as queue:
        await queue.get()  # drop initial
        ctrl.set_paused(True)
        await bus.publish(ctrl.snapshot())
        update = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert update.paused is True
