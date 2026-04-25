"""Ghost tests — prove RuleSet consumers don't depend on BrazilianRules itself.

A trivial stub satisfying the Protocol must be acceptable wherever a
:class:`RuleSet` is expected. Same for :class:`VideoSource`.
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from sinuca_counter.rules import (
    BallPocketed,
    BrazilianRules,
    GameEvent,
    RuleSet,
    ScoreState,
)
from sinuca_counter.rules.state import BallColor
from sinuca_counter.video import VideoSource


class _StubRuleSet:
    def __init__(self) -> None:
        self._state = ScoreState(rules_name="stub")
        self.applied: list[GameEvent] = []

    @property
    def state(self) -> ScoreState:
        return self._state

    def apply(self, event: GameEvent) -> ScoreState:
        self.applied.append(event)
        return self._state


def test_stub_satisfies_ruleset_protocol() -> None:
    stub: RuleSet = _StubRuleSet()  # this assignment is the test
    assert isinstance(stub, RuleSet)


def test_brazilian_rules_satisfies_protocol() -> None:
    rules = BrazilianRules()
    assert isinstance(rules, RuleSet)


def test_consumer_only_depends_on_protocol() -> None:
    """A function typed against RuleSet must accept any conforming stub."""

    def consumer(engine: RuleSet) -> ScoreState:
        return engine.apply(BallPocketed(color=BallColor.AMARELA, pocket_id="top_left", t_ms=0))

    state = consumer(_StubRuleSet())
    assert isinstance(state, ScoreState)


class _StubVideoSource:
    def frames(self) -> Iterator[tuple[np.ndarray, int]]:
        yield np.zeros((8, 8, 3), dtype=np.uint8), 0

    def close(self) -> None:
        return None


def test_stub_video_source_satisfies_protocol() -> None:
    src: VideoSource = _StubVideoSource()
    assert isinstance(src, VideoSource)
    frames = list(src.frames())
    assert len(frames) == 1
