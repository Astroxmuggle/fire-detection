"""Per-camera inference worker.

The worker owns the camera and the model and runs them in its own threads, so
monitoring is independent of any HTTP client. A reader thread pulls frames at a
bounded rate into a fixed-size queue; a processor thread runs the blank-frame
guard, the model and the confirmation engine, then publishes the latest
annotated frame to an in-memory buffer that any number of viewers can read.

Backpressure policy: when the queue is full the **oldest** frame is dropped and
counted. The queue therefore never exceeds ``queue_size`` and a slow model can
never grow memory without bound.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import cv2

from adapters.model.base import ModelAdapter
from adapters.video.base import VideoSource
from config import Config
from detection.frame_guard import annotate_skipped_frame, is_informative_frame
from detection.manager import DetectionManager
from services.event_service import create_confirmed_event
from services.status_service import OFFLINE, ONLINE, get_runtime_status

logger = logging.getLogger("firewatch.worker")


class WorkerState(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class WorkerConfig:
    fps_limit: float = 15.0
    queue_size: int = 8
    reconnect_initial: float = 1.0
    reconnect_max: float = 30.0
    jpeg_quality: int = 70
    join_timeout: float = 5.0

    @classmethod
    def from_settings(cls) -> "WorkerConfig":
        initial = max(0.05, float(Config.WORKER_RECONNECT_SECONDS))
        return cls(
            fps_limit=max(0.1, float(Config.WORKER_FPS_LIMIT)),
            queue_size=max(1, int(Config.WORKER_QUEUE_SIZE)),
            reconnect_initial=initial,
            reconnect_max=max(initial, float(Config.WORKER_RECONNECT_MAX_SECONDS)),
            jpeg_quality=max(1, min(100, int(Config.STREAM_JPEG_QUALITY))),
        )


@dataclass
class FramePayload:
    sequence: int
    jpeg: bytes
    annotated: Any = None
    detections: List[dict] = field(default_factory=list)


class FrameBuffer:
    """Single-slot latest-frame buffer; viewers block until a new frame exists."""

    def __init__(self):
        self._condition = threading.Condition()
        self._sequence = 0
        self._payload: Optional[FramePayload] = None
        self._closed = False

    def publish(self, payload: FramePayload) -> None:
        with self._condition:
            if self._closed:
                return
            self._sequence += 1
            payload.sequence = self._sequence
            self._payload = payload
            self._condition.notify_all()

    def wait_next(self, last_sequence: int, timeout: float = 2.0) -> Tuple[int, Optional[FramePayload]]:
        with self._condition:
            self._condition.wait_for(
                lambda: self._sequence != last_sequence or self._closed, timeout
            )
            if self._sequence == last_sequence:
                return last_sequence, None
            return self._sequence, self._payload

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    @property
    def closed(self) -> bool:
        with self._condition:
            return self._closed

    @property
    def latest(self) -> Optional[FramePayload]:
        with self._condition:
            return self._payload


class InferenceWorker:
    """Bounded, restartable inference loop for one camera."""

    def __init__(
        self,
        camera_id: int,
        name: str,
        source: VideoSource,
        adapter: ModelAdapter,
        config: Optional[WorkerConfig] = None,
        confirmation_manager: Optional[DetectionManager] = None,
    ):
        self.camera_id = int(camera_id)
        self.name = str(name)
        self.source = source
        self.adapter = adapter
        self.config = config or WorkerConfig.from_settings()
        self.manager = confirmation_manager or DetectionManager()
        self.buffer = FrameBuffer()
        self.status = get_runtime_status()

        self._queue: "queue.Queue" = queue.Queue(maxsize=self.config.queue_size)
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._threads: List[threading.Thread] = []
        self._state = WorkerState.STOPPED
        self._last_error: Optional[str] = None
        self._started_at: Optional[float] = None
        self._counters: Dict[str, int] = {
            "frames_read": 0,
            "frames_dropped": 0,
            "frames_processed": 0,
            "frames_skipped": 0,
            "detections": 0,
            "incidents": 0,
            "reconnects": 0,
            "replay_wraps": 0,
            "processing_errors": 0,
        }

    # ------------------------------------------------------------------ state
    @property
    def state(self) -> WorkerState:
        with self._lock:
            return self._state

    def is_alive(self) -> bool:
        with self._lock:
            return any(thread.is_alive() for thread in self._threads)

    def is_running(self) -> bool:
        return self.state in {WorkerState.STARTING, WorkerState.RUNNING, WorkerState.DEGRADED}

    def _set_state(self, state: WorkerState, error: Optional[str] = None) -> None:
        with self._lock:
            self._state = state
            if error is not None:
                self._last_error = error

        source_info = self.source.info()
        if state is WorkerState.RUNNING:
            self.status.set_camera(self.camera_id, ONLINE, source_info.raw, name=self.name)
        elif state in {WorkerState.DEGRADED, WorkerState.FAILED}:
            self.status.set_camera(self.camera_id, OFFLINE, source_info.raw, self._last_error, name=self.name)
        elif state is WorkerState.STOPPED:
            self.status.set_camera(self.camera_id, OFFLINE, source_info.raw, name=self.name)

        self.status.set_worker(self.camera_id, state.value, error=self._last_error, stats=self.stats())

    # -------------------------------------------------------------- lifecycle
    def start(self) -> None:
        """Open the source and start both threads.

        Opening happens synchronously so the caller can surface a 503 instead of
        returning a response that dies a moment later.
        """
        with self._lock:
            if self._state in {WorkerState.STARTING, WorkerState.RUNNING, WorkerState.DEGRADED}:
                return
            self._stop.clear()
            self._threads = []
            self._state = WorkerState.STARTING
            self._started_at = time.monotonic()

        try:
            self.source.open()
        except Exception as exc:  # noqa: BLE001 - reported as FAILED
            self._set_state(WorkerState.FAILED, str(exc))
            raise

        reader = threading.Thread(target=self._read_loop, name=f"fw-read-{self.camera_id}", daemon=True)
        processor = threading.Thread(target=self._process_loop, name=f"fw-proc-{self.camera_id}", daemon=True)

        with self._lock:
            self._threads = [reader, processor]

        self._set_state(WorkerState.RUNNING)
        reader.start()
        processor.start()
        logger.info("worker started for camera %s (%s)", self.camera_id, self.source.info().raw)

    def stop(self, timeout: Optional[float] = None) -> bool:
        """Stop the threads and release the camera. Idempotent."""
        join_timeout = self.config.join_timeout if timeout is None else timeout
        with self._lock:
            already_stopped = self._state is WorkerState.STOPPED and not self._threads
            self._stop.set()
            threads = list(self._threads)

        if already_stopped:
            self.buffer.close()
            return False

        # Give the loops a moment to notice the flag before touching the device.
        for thread in threads:
            thread.join(0.5)

        if any(thread.is_alive() for thread in threads):
            try:
                self.source.close()
            except Exception:  # noqa: BLE001 - best effort
                pass
            for thread in threads:
                thread.join(join_timeout)

        if any(thread.is_alive() for thread in threads):
            logger.warning("worker %s threads did not stop within %.1fs", self.camera_id, join_timeout)

        try:
            self.source.close()
        except Exception:  # noqa: BLE001 - best effort
            pass
        self.buffer.close()
        try:
            self.adapter.close()
        except Exception:  # noqa: BLE001 - best effort
            pass

        with self._lock:
            self._threads = []
        self._set_state(WorkerState.STOPPED)
        logger.info("worker stopped for camera %s", self.camera_id)
        return True

    # ------------------------------------------------------------------ loops
    def _read_loop(self) -> None:
        interval = 1.0 / self.config.fps_limit
        delay = self.config.reconnect_initial

        while not self._stop.is_set():
            if not self.source.is_open:
                try:
                    self.source.open()
                except Exception as exc:  # noqa: BLE001 - retry with backoff
                    self._set_state(WorkerState.DEGRADED, f"source unavailable: {exc}")
                    self._stop.wait(delay)
                    delay = min(delay * 2, self.config.reconnect_max)
                    continue
                with self._lock:
                    self._counters["reconnects"] += 1
                    # A file source that reaches EOF and reopens is replaying
                    # footage, not watching a live scene. Count the wraps so the
                    # API can show it explicitly instead of pretending the
                    # replay is live monitoring.
                    if self.source.info().kind == "file":
                        self._counters["replay_wraps"] += 1
                self._set_state(WorkerState.RUNNING)
                delay = self.config.reconnect_initial

            started = time.monotonic()
            try:
                ok, frame = self.source.read()
            except Exception as exc:  # noqa: BLE001 - treated as a lost camera
                ok, frame = False, None
                self._last_error = str(exc)

            if not ok or frame is None:
                self._set_state(WorkerState.DEGRADED, self._last_error or "frame read failed")
                try:
                    self.source.close()
                except Exception:  # noqa: BLE001 - best effort
                    pass
                self._stop.wait(self.config.reconnect_initial)
                continue

            with self._lock:
                self._counters["frames_read"] += 1
            self._enqueue(frame)
            self._stop.wait(max(0.0, interval - (time.monotonic() - started)))

    def _enqueue(self, frame) -> None:
        try:
            self._queue.put_nowait(frame)
            return
        except queue.Full:
            pass

        # Queue full: drop the oldest frame to make room for the newest.
        try:
            self._queue.get_nowait()
        except queue.Empty:  # pragma: no cover - race with the processor
            pass
        with self._lock:
            self._counters["frames_dropped"] += 1
        try:
            self._queue.put_nowait(frame)
        except queue.Full:  # pragma: no cover - race with the processor
            with self._lock:
                self._counters["frames_dropped"] += 1

    def _process_loop(self) -> None:
        while not self._stop.is_set():
            try:
                frame = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                self._process_frame(frame)
            except Exception as exc:  # noqa: BLE001 - one bad frame must not kill the worker
                logger.exception("processing error on camera %s", self.camera_id)
                with self._lock:
                    self._counters["processing_errors"] += 1
                self._last_error = str(exc)

    def _process_frame(self, frame) -> None:
        if not is_informative_frame(frame, Config.MIN_FRAME_STD):
            with self._lock:
                self._counters["frames_skipped"] += 1
            annotated = annotate_skipped_frame(frame)
            payload = self._encode(annotated)
            if payload is not None:
                self.buffer.publish(FramePayload(sequence=0, jpeg=payload, annotated=annotated))
            self.status.mark_frame(self.camera_id, skipped=True)
            return

        prediction = self.adapter.predict(frame)
        confirmed = self.manager.process_detections(
            prediction.detections, frame_shape=frame.shape
        )

        stored = 0
        for item in confirmed:
            create_confirmed_event(
                class_name=item.get("class_name", "unknown"),
                confidence=item.get("confidence", 0.0),
                camera_source=self.camera_label(),
                frame=prediction.annotated if prediction.annotated is not None else frame,
                alert_status="confirmed",
                event_type="detection",
                camera_id=self.camera_id,
                source_kind=self.source.info().kind,
            )
            stored += 1

        with self._lock:
            self._counters["frames_processed"] += 1
            self._counters["detections"] += len(prediction.detections)
            self._counters["incidents"] += stored

        annotated = prediction.annotated if prediction.annotated is not None else frame
        payload = self._encode(annotated)
        if payload is not None:
            self.buffer.publish(
                FramePayload(
                    sequence=0,
                    jpeg=payload,
                    annotated=annotated,
                    detections=prediction.detections,
                )
            )
        self.status.mark_frame(self.camera_id)

    # ---------------------------------------------------------------- helpers
    def camera_label(self) -> str:
        raw = self.source.info().raw
        base = f"camera:{raw}" if raw.isdigit() else raw
        return base if self.camera_id <= 1 else f"{base}#{self.camera_id}"

    def _encode(self, frame) -> Optional[bytes]:
        if frame is None:
            return None
        ok, buffer = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.config.jpeg_quality]
        )
        return buffer.tobytes() if ok else None

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            counters = dict(self._counters)
            state = self._state.value
            started_at = self._started_at
        source_info = self.source.info()
        counters.update({
            "state": state,
            "source_kind": source_info.kind,
            "is_live": source_info.is_live,
            "queue_size": self._queue.qsize(),
            "queue_max": self.config.queue_size,
            "last_error": self._last_error,
            "uptime_seconds": None if started_at is None else round(time.monotonic() - started_at, 1),
        })
        return counters
