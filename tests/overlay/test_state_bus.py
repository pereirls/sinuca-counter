"""StateBus pub/sub semantics."""

from __future__ import annotations

import asyncio

import pytest

from sinuca_counter.overlay.state_bus import StateBus
from sinuca_counter.rules.state import ScoreState


@pytest.mark.asyncio
async def test_subscriber_gets_initial_state_immediately() -> None:
    initial = ScoreState(p1_name="A", p2_name="B")
    bus = StateBus(initial)
    async with bus.subscribe() as queue:
        first = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert first == initial


@pytest.mark.asyncio
async def test_publish_broadcasts_to_all_subscribers() -> None:
    bus = StateBus()
    async with bus.subscribe() as q1, bus.subscribe() as q2:
        # Drain the initial state pushed on subscribe.
        await q1.get()
        await q2.get()
        new_state = ScoreState(p1_name="X")
        await bus.publish(new_state)
        v1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        v2 = await asyncio.wait_for(q2.get(), timeout=1.0)
        assert v1 == new_state == v2


def test_subscriber_count_starts_at_zero() -> None:
    bus = StateBus()
    assert bus.subscriber_count() == 0
