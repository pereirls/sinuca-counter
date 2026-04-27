"""Integration-ish tests for the VisionWorker playback plumbing.

These tests don't do any real CV — they replace the source, pipeline and
shot detector with lightweight fakes so we can assert specifically the
orchestration rules:

* a seek while the match is active re-arms the detector (keeps ``armed=True``)
  and does not silently turn detection off.
* the underlying video source is ``close()``d on every exit path.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import numpy as np

from sinuca_counter.cli import VisionWorker
from sinuca_counter.overlay.frame_broker import FrameBroker
from sinuca_counter.overlay.playback import PlaybackBus, PlaybackController
from sinuca_counter.overlay.state_bus import StateBus
from sinuca_counter.rules.brazilian import BrazilianRules
from sinuca_counter.vision.shot_phase import ShotPhaseDetector
from sinuca_counter.vision.tracker import BallTracker


class _FakeSource:
    """Minimal stand-in for FileVideoSource."""

    def __init__(self, n_frames: int = 100) -> None:
        self.fps = 30.0
        self.duration_ms = int(n_frames / self.fps * 1000)
        self._n = n_frames
        self._i = 0
        self.seeks: list[int] = []
        self.closed = False

    def read_frame(self) -> tuple[np.ndarray, int] | None:
        if self.closed or self._i >= self._n:
            return None
        t_ms = int(self._i / self.fps * 1000)
        self._i += 1
        # Tiny black frame — pipeline won't touch it because we replace it.
        return np.zeros((4, 4, 3), dtype=np.uint8), t_ms

    def seek_ms(self, ms: int) -> None:
        self.seeks.append(int(ms))
        self._i = int(round(ms / 1000.0 * self.fps))

    def close(self) -> None:
        self.closed = True


class _FakePipeline:
    def process(self, frame: Any, t_ms: int) -> list:  # noqa: ANN401
        return []


def _run_briefly(worker: VisionWorker, n_ticks: int = 2) -> threading.Thread:
    thread = threading.Thread(target=worker.run, daemon=True)
    thread.start()
    # Give the worker a moment to advance a few frames.
    import time as _time

    for _ in range(n_ticks):
        _time.sleep(0.05)
    return thread


def _spin_loop(loop: asyncio.AbstractEventLoop) -> threading.Thread:
    """Run ``loop`` forever on a background thread so the worker's
    ``run_coroutine_threadsafe`` calls actually execute and the test suite
    doesn't see RuntimeWarnings about never-awaited coroutines.
    """

    def runner() -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    return t


def _stop_loop(loop: asyncio.AbstractEventLoop, thread: threading.Thread) -> None:
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2.0)


def _build_worker(
    *,
    armed: bool,
    loop: asyncio.AbstractEventLoop,
) -> tuple[VisionWorker, _FakeSource, ShotPhaseDetector]:
    source = _FakeSource(n_frames=1000)
    rules = BrazilianRules(p1_name="A", p2_name="B")
    bus = StateBus(initial=rules.state)
    playback = PlaybackController(has_video=True, duration_ms=source.duration_ms)
    playback_bus = PlaybackBus(initial=playback.snapshot())
    tracker = BallTracker()
    shot_phase = ShotPhaseDetector(tracker, armed=armed)
    worker = VisionWorker(
        source=source,  # type: ignore[arg-type]
        pipeline=_FakePipeline(),  # type: ignore[arg-type]
        rules=rules,
        bus=bus,
        loop=loop,
        frame_broker=FrameBroker(),
        playback=playback,
        playback_bus=playback_bus,
        shot_phase=shot_phase,
    )
    # Attach the controller so tests can drive it.
    worker._playback_ctrl_for_test = playback  # type: ignore[attr-defined]
    return worker, source, shot_phase


def test_seek_while_armed_rearms_detector_instead_of_disarming() -> None:
    loop = asyncio.new_event_loop()
    loop_thread = _spin_loop(loop)
    try:
        worker, source, shot_phase = _build_worker(armed=True, loop=loop)
        thread = _run_briefly(worker)

        worker._playback_ctrl_for_test.request_seek(5000)  # type: ignore[attr-defined]
        import time as _time

        _time.sleep(0.2)
        worker.stop()
        thread.join(timeout=2.0)

        # The detector must still be armed after the seek (not disarmed) so
        # shot detection continues at the new position.
        assert shot_phase.armed is True, "seek during active match must keep detector armed"
        assert 5000 in source.seeks
    finally:
        _stop_loop(loop, loop_thread)
        loop.close()


def test_source_is_closed_when_worker_exits_on_stop() -> None:
    loop = asyncio.new_event_loop()
    loop_thread = _spin_loop(loop)
    try:
        worker, source, _ = _build_worker(armed=False, loop=loop)
        thread = _run_briefly(worker)
        worker.stop()
        thread.join(timeout=2.0)
        assert source.closed is True
    finally:
        _stop_loop(loop, loop_thread)
        loop.close()


def test_source_is_closed_when_worker_reaches_end_of_file() -> None:
    loop = asyncio.new_event_loop()
    loop_thread = _spin_loop(loop)
    try:
        source = _FakeSource(n_frames=3)
        rules = BrazilianRules(p1_name="A", p2_name="B")
        bus = StateBus(initial=rules.state)
        playback = PlaybackController(has_video=True, duration_ms=source.duration_ms)
        playback_bus = PlaybackBus(initial=playback.snapshot())
        worker = VisionWorker(
            source=source,  # type: ignore[arg-type]
            pipeline=_FakePipeline(),  # type: ignore[arg-type]
            rules=rules,
            bus=bus,
            loop=loop,
            frame_broker=FrameBroker(),
            playback=playback,
            playback_bus=playback_bus,
            shot_phase=None,
        )
        thread = threading.Thread(target=worker.run, daemon=True)
        thread.start()
        thread.join(timeout=3.0)
        assert not thread.is_alive(), "worker should exit cleanly at EOF"
        assert source.closed is True
    finally:
        _stop_loop(loop, loop_thread)
        loop.close()
