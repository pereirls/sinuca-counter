"""Command-line entrypoint.

Wires :class:`FileVideoSource` → :class:`VisionPipeline` → rules engine →
:class:`OverlayServer` and runs them all together. The vision loop runs in
a background thread so the FastAPI server can serve HTTP/WebSocket on the
main asyncio loop.

Default detector is YOLO (Ultralytics) — install with ``uv sync --extra yolo``.
If the extra is not installed, the CLI transparently falls back to the
classical HSV/HoughCircles detector.
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

import cv2
import uvicorn

from .overlay.frame_broker import FrameBroker
from .overlay.server import create_app
from .overlay.state_bus import StateBus
from .rules.base import RuleSet
from .rules.brazilian import BrazilianRules
from .rules.events import GameEvent, ManualAdjustment
from .rules.snooker import SnookerRules
from .rules.state import ScoreState
from .video.file import FileVideoSource
from .vision.classifier import ColorClassifier
from .vision.detector import BallDetector, HsvBallDetector
from .vision.events import (
    BallPocketed,
    FrameProcessed,
    TurnEnded,
    VisionEvent,
)
from .vision.palette import PaletteCalibrator
from .vision.pipeline import VisionPipeline
from .vision.shot_phase import ShotPhaseDetector
from .vision.tracker import BallTracker

log = logging.getLogger(__name__)


# --- helpers ----------------------------------------------------------------


def _palette_path(video_path: Path) -> Path:
    return video_path.with_suffix(video_path.suffix + ".palette.json")


def _replay_path(video_path: Path) -> Path:
    return video_path.with_suffix(video_path.suffix + ".replay.jsonl")


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


def _build_detector(kind: str, weights: str) -> BallDetector:
    kind = kind.lower()
    if kind == "hsv":
        log.info("using classical HSV/HoughCircles detector")
        return HsvBallDetector()
    if kind == "yolo":
        try:
            from .vision.yolo_detector import YoloBallDetector
        except ImportError as exc:  # pragma: no cover - depends on extras
            raise ImportError(
                "Detector 'yolo' requires the [yolo] extra. "
                "Install with `uv sync --extra yolo` or pass `--detector hsv`."
            ) from exc
        try:
            return YoloBallDetector(weights=weights)
        except ImportError as exc:
            log.warning(
                "YOLO unavailable (%s) — falling back to classical HSV detector.",
                exc,
            )
            return HsvBallDetector()
    raise ValueError(f"unknown detector kind: {kind!r}")


# --- runner -----------------------------------------------------------------


def _serialize_event(event: GameEvent | VisionEvent) -> str:
    payload: dict[str, object] = {"type": type(event).__name__}
    for k, v in event.__dict__.items():
        payload[k] = getattr(v, "value", v)
    return json.dumps(payload, default=str)


class VisionWorker:
    """Pumps frames through the pipeline and pushes events into the rules engine.

    Also encodes every Nth frame as JPEG into the :class:`FrameBroker` so the
    ``/stream.mjpg`` endpoint can serve the processed footage back to the
    browser in sync with the score overlay.
    """

    def __init__(
        self,
        source: FileVideoSource,
        pipeline: VisionPipeline,
        rules: RuleSet,
        bus: StateBus,
        loop: asyncio.AbstractEventLoop,
        frame_broker: FrameBroker,
        *,
        stream_every_n_frames: int = 1,
        jpeg_quality: int = 75,
        replay_log: Path | None = None,
    ) -> None:
        self._source = source
        self._pipeline = pipeline
        self._rules = rules
        self._bus = bus
        self._loop = loop
        self._replay_log = replay_log
        self._frame_broker = frame_broker
        self._stream_every_n_frames = max(1, stream_every_n_frames)
        self._jpeg_quality = jpeg_quality
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        with self._open_replay_log() as log_handle:
            for frame_idx, (frame, t_ms) in enumerate(self._source.frames()):
                if self._stop.is_set():
                    return
                events = self._pipeline.process(frame, t_ms)
                self._dispatch(events, log_handle)
                if frame_idx % self._stream_every_n_frames == 0:
                    self._publish_frame(frame)

    def _publish_frame(self, frame) -> None:  # type: ignore[no-untyped-def]
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality],
        )
        if not ok:
            return
        self._frame_broker.publish(encoded.tobytes())

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


def _apply_event_factory(
    rules: RuleSet,
    replay_log: Path | None,
    *,
    shot_phase: ShotPhaseDetector | None = None,
):
    def apply(event: GameEvent) -> ScoreState:
        if replay_log is not None:
            with open(replay_log, "a", encoding="utf-8") as fh:
                fh.write(_serialize_event(event) + "\n")
        state = rules.apply(event)
        # Keep the vision-side shot detector armed/disarmed in lock-step
        # with the match_started flag owned by the rules engine. This way
        # start/stop_match come out of a single place (the control panel
        # endpoint) and nothing else has to know about wiring.
        if shot_phase is not None and isinstance(event, ManualAdjustment):
            if event.op == "start_match":
                shot_phase.arm(t_ms=event.t_ms)
            elif event.op in ("stop_match", "reset"):
                shot_phase.disarm()
        return state

    return apply


# --- main -------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sinuca-counter")
    parser.add_argument(
        "--video",
        help="path to .mp4 file (required unless --no-vision is used)",
    )
    parser.add_argument(
        "--rules",
        choices=["brasileira", "snooker-6", "snooker-15"],
        default="brasileira",
        help=(
            "modality: 'brasileira' (sinuca brasileira), 'snooker-6' "
            "(European 6-red snooker) or 'snooker-15' (English 15-red snooker)"
        ),
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
        help="[brasileira] apply premature-bolão penalty (loses rack)",
    )
    parser.add_argument(
        "--detector",
        choices=["yolo", "hsv"],
        default="yolo",
        help="detector backend: 'yolo' (default, needs [yolo] extra) or 'hsv' (classical)",
    )
    parser.add_argument(
        "--yolo-weights",
        default="yolov8n.pt",
        help="YOLO weights (path or Ultralytics name). Ignored when --detector=hsv.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
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
    parser.add_argument(
        "--stream-every-n-frames",
        type=int,
        default=2,
        help="publish every Nth processed frame to /stream.mjpg (default: 2)",
    )
    parser.add_argument(
        "--speed-threshold",
        type=float,
        default=1.5,
        help="aggregate motion threshold (pixels/frame) to consider the table in motion",
    )
    parser.add_argument(
        "--settle-frames",
        type=int,
        default=45,
        help="frames of stillness required before a shot is finalised (~1.5s at 30fps)",
    )
    parser.add_argument(
        "--min-shot-frames",
        type=int,
        default=3,
        help="minimum frames of motion before a shot is recognised",
    )
    parser.add_argument(
        "--auto-start",
        action="store_true",
        help="arm the shot detector immediately (skip waiting for 'Iniciar partida')",
    )
    parser.add_argument(
        "--debug-every-n-frames",
        type=int,
        default=30,
        help=("log motion/state/track counts every N frames at DEBUG level (set to 0 to disable)"),
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
    if args.rules == "snooker-6":
        return SnookerRules(
            reds=6,
            rules_name="snooker-6",
            p1_name=args.p1,
            p2_name=args.p2,
            starting_player=args.saque,
        )
    if args.rules == "snooker-15":
        return SnookerRules(
            reds=15,
            rules_name="snooker-15",
            p1_name=args.p1,
            p2_name=args.p2,
            starting_player=args.saque,
        )
    raise ValueError(f"unsupported rules: {args.rules}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.no_vision and not args.video:
        raise SystemExit("--video is required unless --no-vision is set")

    rules = _build_rules(args)
    frame_broker = FrameBroker()

    video_path: Path | None = Path(args.video).resolve() if args.video else None
    replay_log: Path | None = None
    if video_path is not None and not args.no_replay_log:
        replay_log = _replay_path(video_path)

    # Pre-build the vision pieces so the HTTP handlers can drive them via
    # start_match/stop_match/reset events.
    tracker: BallTracker | None = None
    shot_phase: ShotPhaseDetector | None = None
    pipeline: VisionPipeline | None = None
    detector: BallDetector | None = None
    source: FileVideoSource | None = None
    if not args.no_vision and video_path is not None:
        source = FileVideoSource(video_path)
        palette = _load_palette(video_path)
        classifier = ColorClassifier(palette)
        detector = _build_detector(args.detector, args.yolo_weights)
        # Larger occlusion tolerance now that the shot-phase detector is
        # responsible for deciding what "pocketed" means — we want tracks
        # to survive through the worst part of the shot.
        tracker = BallTracker(
            max_match_distance=45.0,
            occlusion_tolerance_frames=90,
        )
        shot_phase = ShotPhaseDetector(
            tracker,
            speed_threshold=args.speed_threshold,
            settle_frames=args.settle_frames,
            min_shot_frames=args.min_shot_frames,
            armed=args.auto_start,
            debug_every_n_frames=max(0, args.debug_every_n_frames),
        )
        if args.auto_start:
            # Reflect the armed state on the ScoreState so the UI is honest.
            rules.apply(ManualAdjustment(op="start_match"))
        pipeline = VisionPipeline(
            detector=detector,
            classifier=classifier,
            tracker=tracker,
            shot_phase_detector=shot_phase,
        )

    # Initialise the bus AFTER any auto-start side effects above, so the
    # initial state pushed to /state and the first WebSocket frame already
    # reflects match_started=True when --auto-start is in play.
    bus = StateBus(initial=rules.state)

    apply_event = _apply_event_factory(rules, replay_log, shot_phase=shot_phase)

    app = create_app(bus, apply_event, frame_broker=frame_broker)

    port = _find_free_port(args.host, args.port)
    config = uvicorn.Config(app, host=args.host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    async def runner() -> None:
        server_task = asyncio.create_task(server.serve())
        worker_thread: threading.Thread | None = None
        worker: VisionWorker | None = None

        if pipeline is not None and source is not None:
            worker = VisionWorker(
                source=source,
                pipeline=pipeline,
                rules=rules,
                bus=bus,
                loop=asyncio.get_running_loop(),
                frame_broker=frame_broker,
                stream_every_n_frames=max(1, args.stream_every_n_frames),
                replay_log=replay_log,
            )
            worker_thread = threading.Thread(target=worker.run, name="vision", daemon=True)
            worker_thread.start()

        log.info(
            "watch http://%s:%d/watch  control http://%s:%d/control",
            args.host,
            port,
            args.host,
            port,
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


__all__ = ["VisionWorker", "build_parser", "main"]


if __name__ == "__main__":  # pragma: no cover
    with contextlib.suppress(KeyboardInterrupt):
        raise SystemExit(main())
