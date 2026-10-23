"""Tests for the model adapter, video sources and the bounded inference worker.

These tests exercise the *new* layer in isolation (stub model, stub source) plus
one parity test that runs the real checkpoint.
"""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
import pytest

import services.camera_service as camera_service
from adapters.model.base import ModelInfo, Prediction
from adapters.model.yolo import YoloModelAdapter
from adapters.video.base import SourceInfo, VideoSourceUnavailable
from detection.manager import DetectionManager
from services.event_service import get_events
from workers.inference_worker import (
    FrameBuffer,
    FramePayload,
    InferenceWorker,
    WorkerConfig,
    WorkerState,
)
from workers.manager import CameraWorkerManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------- stubs
class FakeSource:
    """Scriptable video source."""

    def __init__(self, frame_factory=None, fail_after=None, open_error=None, reopen_fails=False):
        self._frame_factory = frame_factory or detailed_frame
        self.fail_after = fail_after
        self.open_error = open_error
        self.reopen_fails = reopen_fails
        self.reads = 0
        self.opens = 0
        self.closes = 0
        self._open = False

    @property
    def is_open(self):
        return self._open

    def info(self):
        return SourceInfo(raw="fake-source", kind="file", is_live=False)

    def open(self):
        self.opens += 1
        if self.open_error is not None:
            raise self.open_error
        if self.reopen_fails and self.opens > 1:
            raise VideoSourceUnavailable("device disappeared")
        self._open = True

    def read(self):
        self.reads += 1
        if not self._open:
            return False, None
        if self.fail_after is not None and self.reads > self.fail_after:
            return False, None
        return True, self._frame_factory()

    def close(self):
        self.closes += 1
        self._open = False


class StubAdapter:
    """Model adapter returning fixed detections without loading torch."""

    def __init__(self, detections=None, delay=0.0):
        self.detections = list(detections or [])
        self.delay = delay
        self.calls = 0
        self.closed = False

    def info(self):
        return ModelInfo(name="stub", path="stub", task="detect", classes={0: "fire", 1: "smoke"})

    def predict(self, frame):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return Prediction(detections=[dict(item) for item in self.detections], annotated=frame.copy())

    def close(self):
        self.closed = True


def detailed_frame():
    rng = np.random.default_rng(7)
    return rng.integers(0, 255, (96, 96, 3), dtype=np.uint8)


def blank_frame():
    return np.full((96, 96, 3), 200, dtype=np.uint8)


def fire_detection(box=(8, 8, 60, 60), confidence=0.9):
    return {"class_name": "fire", "confidence": confidence, "bbox": list(box)}


def fast_config(**overrides):
    values = dict(
        fps_limit=100.0,
        queue_size=4,
        reconnect_initial=0.01,
        reconnect_max=0.05,
        jpeg_quality=70,
        join_timeout=2.0,
    )
    values.update(overrides)
    return WorkerConfig(**values)


def wait_for(predicate, timeout=5.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


# ------------------------------------------------------------------ adapter
def test_model_adapter_matches_the_pre_adapter_conversion():
    """Parity: the adapter must produce exactly what the old inline code did."""
    frames = sorted((PROJECT_ROOT / "snapshots").glob("*.jpg"))
    if not frames:
        pytest.skip("no stored frames available")

    frame = cv2.imread(str(frames[0]))
    assert frame is not None

    adapter = YoloModelAdapter()
    try:
        info = adapter.info()
        assert info.classes == {0: "fire", 1: "smoke"}
        assert info.path.endswith("best.pt")

        # Reference conversion: verbatim copy of the pre-adapter implementation.
        raw = adapter._model(frame, conf=adapter.confidence_threshold, imgsz=640, verbose=False)
        reference = []
        for box in raw[0].boxes:
            confidence = float(box.conf[0]) if hasattr(box.conf, "__len__") else float(box.conf)
            class_id = int(box.cls[0]) if hasattr(box.cls, "__len__") else int(box.cls)
            reference.append({
                "class_name": str(raw[0].names.get(class_id, class_id)).lower(),
                "class_id": class_id,
                "confidence": confidence,
                "bbox": box.xyxy[0].tolist(),
            })

        prediction = adapter.predict(frame)
        assert prediction.detections == reference
        assert prediction.annotated is not None
        assert prediction.annotated.shape == frame.shape
    finally:
        adapter.close()


def test_yolo_adapter_fails_fast_without_a_checkpoint(temp_dir):
    with pytest.raises(FileNotFoundError):
        YoloModelAdapter(model_path=str(temp_dir / "missing.pt"))


# -------------------------------------------------------------------- worker
def test_worker_ignores_blank_frames_and_never_calls_the_model():
    adapter = StubAdapter(detections=[fire_detection()])
    source = FakeSource(frame_factory=blank_frame)
    worker = InferenceWorker(1, "blank-cam", source, adapter, config=fast_config())

    worker.start()
    try:
        assert wait_for(lambda: worker.stats()["frames_skipped"] >= 3)
        assert adapter.calls == 0
        assert worker.stats()["frames_processed"] == 0
        assert worker.buffer.latest is not None  # viewers still get an annotated frame
    finally:
        worker.stop()


def test_worker_confirms_once_then_latches():
    adapter = StubAdapter(detections=[fire_detection()])
    source = FakeSource(frame_factory=detailed_frame)
    manager = DetectionManager(required_frames=2, release_frames=3, cooldown_seconds=5)
    worker = InferenceWorker(1, "fire-cam", source, adapter, config=fast_config(), confirmation_manager=manager)

    worker.start()
    try:
        assert wait_for(lambda: worker.stats()["incidents"] >= 1)
        time.sleep(0.3)
        assert worker.stats()["incidents"] == 1
        assert len(get_events({})) == 1
    finally:
        worker.stop()


def test_worker_stop_is_clean_and_idempotent():
    source = FakeSource(frame_factory=detailed_frame)
    worker = InferenceWorker(1, "cam", source, StubAdapter(), config=fast_config())

    worker.start()
    assert worker.is_alive() is True

    assert worker.stop() is True
    assert worker.state is WorkerState.STOPPED
    assert worker.is_alive() is False
    assert source.closes >= 1
    assert worker.stop() is False


def test_worker_queue_is_bounded_and_drops_frames():
    source = FakeSource(frame_factory=detailed_frame)
    adapter = StubAdapter(delay=0.15)  # much slower than the reader
    worker = InferenceWorker(1, "slow-cam", source, adapter, config=fast_config(fps_limit=200, queue_size=2))

    worker.start()
    try:
        assert wait_for(lambda: worker.stats()["frames_dropped"] > 0)
        stats = worker.stats()
        assert stats["queue_size"] <= 2
        assert stats["frames_read"] > stats["frames_dropped"]
    finally:
        worker.stop()


def test_worker_reports_degraded_when_the_camera_disappears():
    source = FakeSource(frame_factory=detailed_frame, fail_after=1, reopen_fails=True)
    worker = InferenceWorker(1, "lossy-cam", source, StubAdapter(), config=fast_config())

    worker.start()
    try:
        assert wait_for(lambda: worker.state is WorkerState.DEGRADED)
        stats = worker.stats()
        assert stats["state"] == "degraded"
        assert stats["last_error"]
        worker.stop()
        assert worker.state is WorkerState.STOPPED
    finally:
        worker.stop()


def test_worker_fails_fast_when_the_source_cannot_open():
    source = FakeSource(open_error=VideoSourceUnavailable("no device"))
    worker = InferenceWorker(1, "missing-cam", source, StubAdapter(), config=fast_config())

    with pytest.raises(VideoSourceUnavailable):
        worker.start()
    assert worker.state is WorkerState.FAILED
    assert worker.stop() is True
    assert worker.state is WorkerState.STOPPED


# ------------------------------------------------------------ frame buffer
def test_frame_buffer_blocks_then_serves_the_same_frame_to_every_viewer():
    buffer = FrameBuffer()
    sequence, payload = buffer.wait_next(0, timeout=0.05)
    assert (sequence, payload) == (0, None)

    buffer.publish(FramePayload(sequence=0, jpeg=b"jpeg-bytes"))
    first = buffer.wait_next(0, timeout=0.5)
    second = buffer.wait_next(0, timeout=0.5)
    assert first[0] == second[0] == 1
    assert first[1] is second[1]
    assert first[1].jpeg == b"jpeg-bytes"

    buffer.close()
    assert buffer.wait_next(1, timeout=0.05)[1] is None


# ------------------------------------------------- monitoring without a viewer
def _install_stub_manager(monkeypatch, adapter_factory=None, config=None):
    manager = CameraWorkerManager(
        adapter_factory=adapter_factory or (lambda model_path=None, confidence_threshold=None: StubAdapter([fire_detection()])),
        source_factory=lambda camera: FakeSource(frame_factory=detailed_frame),
        config_factory=lambda: config or fast_config(),
    )
    monkeypatch.setattr(camera_service, "worker_manager", manager)
    return manager


def test_monitoring_continues_without_any_viewer(monkeypatch):
    _install_stub_manager(monkeypatch)

    worker = camera_service.start_monitoring(1)
    try:
        assert worker.is_alive() is True
        assert camera_service.is_monitoring(1) is True
        assert camera_service.is_stream_active(1) is False  # nobody is watching
        assert wait_for(lambda: len(get_events({})) >= 1)
    finally:
        camera_service.stop_all_monitoring()

    assert camera_service.is_monitoring(1) is False


def test_detaching_a_viewer_does_not_stop_monitoring(monkeypatch):
    _install_stub_manager(monkeypatch)

    stream = camera_service.start_stream(1)
    try:
        assert camera_service.is_stream_active(1) is True
        stream.close()
        assert camera_service.is_stream_active(1) is False
        assert camera_service.is_monitoring(1) is True
    finally:
        camera_service.stop_stream(1)

    assert camera_service.is_monitoring(1) is False


def test_worker_endpoint_reports_health(client, monkeypatch):
    _install_stub_manager(monkeypatch)

    started = client.post("/api/cameras/1/monitoring/start")
    assert started.status_code == 200
    assert started.json["worker"]["state"] == "running"

    payload = client.get("/api/workers").json
    assert payload["monitoring_active"] == 1
    assert payload["workers"][0]["camera_id"] == 1
    assert payload["workers"][0]["state"] == "running"

    assert client.post("/api/stream/stop").status_code == 200
    assert client.get("/api/workers").json["monitoring_active"] == 0


def test_camera_with_running_worker_cannot_be_deleted(client, monkeypatch):
    _install_stub_manager(monkeypatch)
    client.post("/api/cameras/1/monitoring/start")
    try:
        response = client.delete("/api/cameras/1")
        assert response.status_code == 409
        assert "Stop the stream" in response.json["error"]
    finally:
        client.post("/api/stream/stop")
