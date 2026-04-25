"""Command-line entrypoint.

Wires :class:`FileVideoSource` → :class:`VisionPipeline` → :class:`BrazilianRules`
→ :class:`OverlayServer` and runs them all together. The vision loop runs in a
background thread so the FastAPI server can serve HTTP/WebSocket on the main
asyncio loop.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import socket
import threading
from collections.abc import Iterable
from pathlib import Path

import uvicorn

from .overlay.server import create_app
from .overlay.state_bus import StateBus
from .rules.base import RuleSet
from .rules.brazilian import BrazilianRules
from .rules.events import GameEvent
from .rules.state import ScoreState
from .video.file import FileVideoSource
from .vision.calibrator import CalibrationData, TableCalibrator
from .vision.classifier import ColorClassifier
from .vision.detector import HsvBallDetector
from .vision.events import (
    BallPocketed,
    CalibrationLost,
    FrameProcessed,
    TurnEnded,
    VisionEvent,
)
from .vision.palette import PaletteCalibrator
from .vision.pipeline import VisionPipeline
from .vision.pocket import PocketEventDetector
from .vision.tracker import BallTracker
from .vision.turn import TurnEndDetector

log = logging.getLogger(__name__)


# --- helpers ----------------------------------------------------------------


def _calibration_path(video_path: Path) -> Path:
    return video_path.with_suffix(video_path.suffix + ".calib.json")


def _palette_path(video_path: Path) -> Path:
    return video_path.with_suffix(video_path.suffix + ".palette.json")


def _replay_path(video_path: Path) -> Path:
    return video_path.with_suffix(video_path.suffix + ".replay.jsonl")


def _load_or_calibrate(
    video_path: Path,
    *,
    sample_frame=None,
    interactive: bool = True,
) -> TableCalibrator:
    path = _calibration_path(video_path)
    if path.exists():
        log.info("loading calibration from %s", path)
        return TableCalibrator.load(path)
    if not interactive or sample_frame is None:
        raise FileNotFoundError(f"calibration {path!s} missing; rerun without --no-interactive")
    calibrator = TableCalibrator.from_clicks(sample_frame)  # pragma: no cover
    calibrator.save(path)
    return calibrator


def _load_palette(video_path: Path) -> PaletteCalibrator:
    path = _palette_path(video_path)
    if path.exists():
        log.info("loading palette from %s", path)
        return PaletteCalibrator.load(path)
    log.info("using default palette (no %s found)", path)
    return PaletteCalibrator.default()


def _find_free_port(host: str, start: int) -> int:
    port = start
    for _ in range(50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return port
            except OSError:
                port += 1
    raise RuntimeError(f"no free port found starting at {start}")


# --- runner -----------------------------------------------------------------


def _serialize_event(event: GameEvent | VisionEvent) -> str:
    payload: dict[str, object] = {"type": type(event).__name__}
    for k, v in event.__dict__.items():
        payload[k] = getattr(v, "value", v)
    return json.dumps(payload, default=str)


class VisionWorker:
    """Pumps frames through the pipeline and pushes events into the rules engine."""

    def __init__(
        self,
        source: FileVideoSource,
        pipeline: VisionPipeline,
        rules: RuleSet,
        bus: StateBus,
        loop: asyncio.AbstractEventLoop,
        replay_log: Path | None = None,
    ) -> None:
        self._source = source
        self._pipeline = pipeline
        self._rules = rules
        self._bus = bus
        self._loop = loop
        self._replay_log = replay_log
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        with self._open_replay_log() as log_handle:
            for frame, t_ms in self._source.frames():
                if self._stop.is_set():
                    return
                events = self._pipeline.process(frame, t_ms)
                self._dispatch(events, log_handle)

    @contextlib.contextmanager
    def _open_replay_log(self):
        if self._replay_log is None:
            yield None
            return
        with open(self._replay_log, "a", encoding="utf-8") as fh:
            yield fh

    def _dispatch(
        self,
        events: Iterable[VisionEvent],
        log_handle,  # type: ignore[no-untyped-def]
    ) -> None:
        for event in events:
            if isinstance(event, FrameProcessed):
                continue
            if log_handle is not None:
                log_handle.write(_serialize_event(event) + "\n")
                log_handle.flush()
            if isinstance(event, BallPocketed | TurnEnded):
                state = self._rules.apply(event)
                asyncio.run_coroutine_threadsafe(self._bus.publish(state), self._loop)
            elif isinstance(event, CalibrationLost):
                state = self._rules.state.with_changes(
                    detection_status=f"calibration lost: {event.reason}"
                )
                asyncio.run_coroutine_threadsafe(self._bus.publish(state), self._loop)


def _apply_event_factory(rules: RuleSet, replay_log: Path | None):
    def apply(event: GameEvent) -> ScoreState:
        if replay_log is not None:
            with open(replay_log, "a", encoding="utf-8") as fh:
                fh.write(_serialize_event(event) + "\n")
        return rules.apply(event)

    return apply


# --- main -------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sinuca-counter")
    parser.add_argument("--video", required=True, help="path to .mp4 file")
    parser.add_argument(
        "--rules",
        choices=["brasileira"],
        default="brasileira",
        help="modality (only 'brasileira' on MVP)",
    )
    parser.add_argument("--p1", default="P1", help="player 1 name")
    parser.add_argument("--p2", default="P2", help="player 2 name")
    parser.add_argument(
        "--saque",
        choices=["p1", "p2"],
        default="p1",
        help="who breaks (starting player)",
    )
    parser.add_argument(
        "--bolao-penalty",
        action="store_true",
        help="apply premature-bolão penalty (loses rack)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="fail if calibration is missing instead of asking for clicks",
    )
    parser.add_argument(
        "--no-vision",
        action="store_true",
        help="serve overlay/control panel only (skip vision processing)",
    )
    parser.add_argument(
        "--no-replay-log",
        action="store_true",
        help="skip writing the .replay.jsonl event log",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser


def _build_rules(args: argparse.Namespace) -> RuleSet:
    if args.rules == "brasileira":
        return BrazilianRules(
            p1_name=args.p1,
            p2_name=args.p2,
            starting_player=args.saque,
            bolao_premature_penalty=args.bolao_penalty,
        )
    raise ValueError(f"unsupported rules: {args.rules}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    video_path = Path(args.video).resolve()
    rules = _build_rules(args)
    bus = StateBus(initial=rules.state)
    replay_log = None if args.no_replay_log else _replay_path(video_path)
    apply_event = _apply_event_factory(rules, replay_log)

    app = create_app(bus, apply_event)

    port = _find_free_port(args.host, args.port)
    config = uvicorn.Config(app, host=args.host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    async def runner() -> None:
        server_task = asyncio.create_task(server.serve())
        worker_thread: threading.Thread | None = None
        worker: VisionWorker | None = None

        if not args.no_vision:
            source = FileVideoSource(video_path)
            sample_frame = None
            try:
                sample_frame, _ = next(iter(source.frames()))
            except StopIteration:
                source.close()
                raise RuntimeError("video has no frames") from None
            calibrator = _load_or_calibrate(
                video_path,
                sample_frame=sample_frame,
                interactive=not args.no_interactive,
            )
            palette = _load_palette(video_path)
            classifier = ColorClassifier(palette)
            detector = HsvBallDetector()
            tracker = BallTracker()
            pocket_detector = PocketEventDetector(calibrator.calibration, tracker)
            turn_detector = TurnEndDetector(tracker)
            pipeline = VisionPipeline(
                calibrator=calibrator,
                detector=detector,
                classifier=classifier,
                tracker=tracker,
                pocket_detector=pocket_detector,
                turn_detector=turn_detector,
            )
            # Re-open the video so frame iteration starts at frame 0.
            source.close()
            source = FileVideoSource(video_path)
            worker = VisionWorker(
                source=source,
                pipeline=pipeline,
                rules=rules,
                bus=bus,
                loop=asyncio.get_running_loop(),
                replay_log=replay_log,
            )
            worker_thread = threading.Thread(target=worker.run, name="vision", daemon=True)
            worker_thread.start()

        log.info(
            "overlay http://%s:%d  control http://%s:%d/control", args.host, port, args.host, port
        )
        try:
            await server_task
        finally:
            if worker is not None:
                worker.stop()
            if worker_thread is not None:
                worker_thread.join(timeout=2.0)

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:  # pragma: no cover
        return 0
    return 0


# Provide CalibrationData re-export for users wanting to build calibrations
# programmatically without going through the interactive UI.
__all__ = ["CalibrationData", "build_parser", "main"]


if __name__ == "__main__":  # pragma: no cover
    with contextlib.suppress(KeyboardInterrupt):
        raise SystemExit(main())
