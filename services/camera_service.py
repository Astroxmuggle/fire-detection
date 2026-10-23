"""Camera compatibility layer: resolve cameras and attach viewers to workers.

This module used to own capture *and* inference. Since Milestone 1 it owns
neither: the camera, the model and the detection loop live in an
``InferenceWorker`` and keep running whether or not a browser is connected.
What remains here is the viewer side (one MJPEG stream per camera) plus the
public functions the routes and tests already use.
"""

from __future__ import annotations

import threading
from typing import Iterator, List, Optional

from adapters.video.base import VideoSourceError, VideoSourceUnavailable, parse_source
from config import Config
from services.camera_registry import Camera, resolve_camera, sync_from_config
from workers.inference_worker import InferenceWorker
from workers.manager import CameraWorkerManager

# Backwards-compatible exception names.
CameraError = VideoSourceError
CameraUnavailable = VideoSourceUnavailable


class StreamBusy(CameraError):
    """A viewer is already attached to that camera."""


# --------------------------------------------------------------------- helpers
def parse_camera_source(value=None):
    """Accept ``0``, ``"0"``, ``"rtsp://..."`` or a video file path."""
    raw = Config.CAMERA_SOURCE if value is None else value
    return parse_source(raw, default=Config.CAMERA_INDEX)


def open_camera(camera_source=None):
    """Open an OpenCV capture; kept as a module-level, replaceable function."""
    from adapters.video.opencv import open_capture

    return open_capture(camera_source)


def _build_adapter(model_path=None, confidence_threshold=None):
    from adapters.model.yolo import YoloModelAdapter

    return YoloModelAdapter(model_path, confidence_threshold)


def _build_source(camera: Camera):
    from adapters.video.opencv import OpenCVVideoSource

    # ``open_camera`` is looked up at call time so tests and deployments can
    # replace the opener without touching the adapter.
    return OpenCVVideoSource(camera.source, opener=open_camera)


worker_manager = CameraWorkerManager(adapter_factory=_build_adapter, source_factory=_build_source)


# -------------------------------------------------------------------- viewing
class CameraStream:
    """A viewer attached to a camera worker's latest-frame buffer."""

    def __init__(self, worker: InferenceWorker):
        self.worker = worker
        self.camera_id = worker.camera_id
        self.camera_name = worker.name
        self.closed = False
        self.frames_yielded = 0

    def frames(self) -> Iterator[bytes]:
        from services.status_service import get_runtime_status

        status = get_runtime_status()
        status.mark_stream(self.camera_id, True)
        sequence = 0
        try:
            while not self.closed:
                sequence, payload = self.worker.buffer.wait_next(sequence, timeout=2.0)
                if payload is None:
                    if not self.worker.is_alive():
                        break
                    continue

                self.frames_yielded += 1
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(payload.jpeg)).encode() + b"\r\n\r\n"
                    + payload.jpeg + b"\r\n"
                )
        finally:
            self.close()

    def close(self):
        """Detach this viewer. The worker (and monitoring) keeps running."""
        if self.closed:
            return
        self.closed = True
        from services.status_service import get_runtime_status

        get_runtime_status().mark_stream(self.camera_id, False)
        release_stream(self)


# ------------------------------------------------------------------- registry
_stream_lock = threading.Lock()
_active_streams: dict = {}


def _resolve_camera_or_raise(camera_id=None) -> Camera:
    camera = resolve_camera(camera_id)
    if camera is None:
        sync_from_config()
        camera = resolve_camera(camera_id)
    if camera is None:
        raise CameraUnavailable(
            f"No camera configured (requested id={camera_id!r}). Set CAMERA_SOURCE or add one via the registry."
        )
    if not camera.enabled:
        raise CameraUnavailable(f"Camera {camera.id} ({camera.name}) is disabled")
    return camera


def start_stream(camera_id=None, model_path=None, confidence_threshold=None) -> CameraStream:
    """Attach a viewer, starting the camera's worker if it is not running."""
    camera = _resolve_camera_or_raise(camera_id)

    with _stream_lock:
        existing = _active_streams.get(camera.id)
        if existing is not None and not existing.closed:
            raise StreamBusy(f"Camera {camera.id} ({camera.name}) is already streaming")

    worker = worker_manager.ensure(
        camera,
        model_path=model_path,
        confidence_threshold=confidence_threshold,
    )
    stream = CameraStream(worker)

    with _stream_lock:
        _active_streams[camera.id] = stream

    return stream


def start_monitoring(camera_id=None, model_path=None, confidence_threshold=None) -> InferenceWorker:
    """Start a camera worker without attaching any viewer (headless monitoring)."""
    camera = _resolve_camera_or_raise(camera_id)
    return worker_manager.ensure(
        camera,
        model_path=model_path,
        confidence_threshold=confidence_threshold,
    )


def release_stream(stream: Optional[CameraStream] = None) -> None:
    with _stream_lock:
        if stream is None:
            _active_streams.clear()
            return
        if _active_streams.get(stream.camera_id) is stream:
            _active_streams.pop(stream.camera_id, None)


def is_stream_active(camera_id=None) -> bool:
    with _stream_lock:
        if camera_id is None:
            return any(not stream.closed for stream in _active_streams.values())
        stream = _active_streams.get(int(camera_id))
        return stream is not None and not stream.closed


def is_monitoring(camera_id=None) -> bool:
    return worker_manager.is_monitoring(camera_id)


def active_camera_ids() -> List[int]:
    with _stream_lock:
        return sorted(cid for cid, stream in _active_streams.items() if not stream.closed)


def stop_stream(camera_id=None) -> int:
    """Stop monitoring (and detach viewers) for one camera, or all of them."""
    with _stream_lock:
        if camera_id is None:
            streams = list(_active_streams.values())
            _active_streams.clear()
        else:
            stream = _active_streams.pop(int(camera_id), None)
            streams = [stream] if stream is not None else []

    for stream in streams:
        if stream is not None:
            stream.close()

    if camera_id is None:
        return worker_manager.stop_all()
    return 1 if worker_manager.stop(camera_id) else 0


def stop_all_monitoring() -> int:
    """Stop every worker and detach every viewer."""
    with _stream_lock:
        streams = list(_active_streams.values())
        _active_streams.clear()
    for stream in streams:
        if stream is not None:
            stream.close()
    return worker_manager.stop_all()


def worker_status() -> List[dict]:
    return worker_manager.status()


# ------------------------------------------------------------------ legacy API
def generate_stream(model_path=None, camera_index=None, confidence_threshold=None):
    """Backwards-compatible generator wrapper around :class:`CameraStream`."""
    stream = start_stream(
        camera_id=camera_index,
        model_path=model_path,
        confidence_threshold=confidence_threshold,
    )
    yield from stream.frames()
