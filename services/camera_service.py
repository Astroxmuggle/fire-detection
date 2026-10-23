"""Camera capture and live detection streams.

Each camera in the registry can own one capture session. Sessions are objects so
every failure that can happen *before* the first frame (missing model, unplugged
camera, busy device) is raised synchronously — that is what lets the HTTP layer
answer 503 instead of returning a 200 and then dying halfway through the
multipart body.
"""

from __future__ import annotations

import os
import threading
from typing import Dict, Iterator, List, Optional

import cv2
from ultralytics import YOLO

from config import Config
from detection.frame_guard import annotate_skipped_frame, is_informative_frame
from detection.manager import DetectionManager
from services.camera_registry import Camera, resolve_camera, sync_from_config
from services.event_service import create_confirmed_event
from services.status_service import OFFLINE, ONLINE, get_runtime_status


class CameraError(RuntimeError):
    """Base class for camera problems."""


class CameraUnavailable(CameraError):
    """The camera or stream source could not be opened."""


class StreamBusy(CameraError):
    """That camera already has an active capture session."""


def parse_camera_source(value=None):
    """Accept ``0``, ``"0"``, ``"rtsp://..."`` or a video file path."""
    raw = Config.CAMERA_SOURCE if value is None else value
    if isinstance(raw, int):
        return raw

    text = str(raw).strip()
    if not text:
        return Config.CAMERA_INDEX
    try:
        return int(text)
    except ValueError:
        return text


def open_camera(camera_source=None) -> cv2.VideoCapture:
    source = parse_camera_source(camera_source)

    camera = cv2.VideoCapture(source)
    if not camera.isOpened() and isinstance(source, int) and os.name == "nt":
        # Some Windows webcams only open through the DirectShow backend.
        camera.release()
        dshow = getattr(cv2, "CAP_DSHOW", None)
        if dshow is not None:
            camera = cv2.VideoCapture(source, dshow)

    if not camera.isOpened():
        raise CameraUnavailable(f"Could not open camera source {source!r}")

    if isinstance(source, int):
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, Config.FRAME_WIDTH)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.FRAME_HEIGHT)

    return camera


def _results_to_detections(results):
    if not results or len(results) == 0 or results[0].boxes is None:
        return []

    names = getattr(results[0], "names", {}) or {}
    detections = []
    for box in results[0].boxes:
        confidence = float(box.conf[0]) if hasattr(box.conf, "__len__") else float(box.conf)
        class_id = int(box.cls[0]) if hasattr(box.cls, "__len__") else int(box.cls)
        detections.append({
            "class_name": str(names.get(class_id, class_id)).lower(),
            "class_id": class_id,
            "confidence": confidence,
            "bbox": box.xyxy[0].tolist(),
        })
    return detections


class CameraStream:
    """One live capture session: model + camera + detection state."""

    def __init__(self, camera: Camera, model_path=None, confidence_threshold=None):
        self.camera_id = camera.id
        self.camera_name = camera.name
        self.model_path = str(model_path or Config.MODEL_PATH)
        if not os.path.isfile(self.model_path):
            raise FileNotFoundError(f"Model not found at {self.model_path}")

        self.source = parse_camera_source(camera.source)
        self.status = get_runtime_status()
        self.closed = False
        self.frames_yielded = 0

        self.model = YOLO(self.model_path)
        self.class_names = list(getattr(self.model, "names", {}).values())
        self.status.set_model(True, self.model_path, self.class_names)

        self.capture = open_camera(camera.source)
        self.status.set_camera(self.camera_id, ONLINE, self.source, name=self.camera_name)

        self.confidence_threshold = float(
            Config.CONFIDENCE_THRESHOLD if confidence_threshold is None else confidence_threshold
        )
        self.manager = DetectionManager(confidence_threshold=self.confidence_threshold)
        self.jpeg_quality = int(Config.STREAM_JPEG_QUALITY)
        self.camera_label = self._camera_label()

    def _camera_label(self) -> str:
        base = f"camera:{self.source}" if isinstance(self.source, int) else str(self.source)
        return base if self.camera_id <= 1 else f"{base}#{self.camera_id}"

    # ------------------------------------------------------------------ helpers
    def _confirm_and_store(self, detections, annotated_frame) -> int:
        stored = 0
        confirmed = self.manager.process_detections(detections, frame_shape=annotated_frame.shape)
        for item in confirmed:
            create_confirmed_event(
                class_name=item.get("class_name", "unknown"),
                confidence=item.get("confidence", 0.0),
                camera_source=self.camera_label,
                frame=annotated_frame,
                alert_status="confirmed",
                event_type="detection",
            )
            stored += 1
        return stored

    def _annotate(self, frame, results):
        try:
            return results[0].plot()
        except Exception:  # noqa: BLE001 - plotting must never break the stream
            return frame

    def _encode(self, frame) -> Optional[bytes]:
        ok, buffer = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
        )
        if not ok:
            return None
        return buffer.tobytes()

    # ------------------------------------------------------------------- frames
    def frames(self) -> Iterator[bytes]:
        self.status.mark_stream(self.camera_id, True)
        try:
            while not self.closed:
                ok, frame = self.capture.read()
                if not ok or frame is None:
                    self.status.set_camera(
                        self.camera_id, OFFLINE, self.source, "Frame capture failed", name=self.camera_name
                    )
                    break

                if not is_informative_frame(frame, Config.MIN_FRAME_STD):
                    self.status.mark_frame(self.camera_id, skipped=True)
                    annotated_frame = annotate_skipped_frame(frame)
                else:
                    results = self.model(
                        frame,
                        conf=self.confidence_threshold,
                        imgsz=640,
                        verbose=False,
                    )
                    annotated_frame = self._annotate(frame, results)
                    self._confirm_and_store(_results_to_detections(results), annotated_frame)
                    self.status.mark_frame(self.camera_id)

                payload = self._encode(annotated_frame)
                if payload is None:
                    continue

                self.frames_yielded += 1
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(payload)).encode() + b"\r\n\r\n"
                    + payload + b"\r\n"
                )
        finally:
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.capture.release()
        except Exception:  # noqa: BLE001 - release must never raise
            pass
        self.status.set_camera(self.camera_id, OFFLINE, self.source, name=self.camera_name)
        self.status.mark_stream(self.camera_id, False)
        release_stream(self)


# -------------------------------------------------------------------- registry
_stream_lock = threading.Lock()
_active_streams: Dict[int, CameraStream] = {}


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
    """Open a capture session for one camera, or raise a descriptive error."""
    camera = _resolve_camera_or_raise(camera_id)

    with _stream_lock:
        existing = _active_streams.get(camera.id)
        if existing is not None and not existing.closed:
            raise StreamBusy(f"Camera {camera.id} ({camera.name}) is already streaming")

        try:
            stream = CameraStream(
                camera,
                model_path=model_path,
                confidence_threshold=confidence_threshold,
            )
        except CameraUnavailable as exc:
            get_runtime_status().set_camera(camera.id, OFFLINE, camera.source, str(exc), name=camera.name)
            raise
        except Exception as exc:
            get_runtime_status().record_error(str(exc))
            raise

        _active_streams[camera.id] = stream
        return stream


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


def active_camera_ids() -> List[int]:
    with _stream_lock:
        return sorted(cid for cid, stream in _active_streams.items() if not stream.closed)


def stop_stream(camera_id=None) -> int:
    """Stop one camera's session, or all of them. Returns how many were stopped."""
    with _stream_lock:
        if camera_id is None:
            streams = list(_active_streams.values())
        else:
            stream = _active_streams.get(int(camera_id))
            streams = [stream] if stream is not None else []

    stopped = 0
    for stream in streams:
        if stream is not None and not stream.closed:
            stream.close()
            stopped += 1
    return stopped


# ------------------------------------------------------------------ legacy API
def generate_stream(model_path=None, camera_index=None, confidence_threshold=None):
    """Backwards-compatible generator wrapper around :class:`CameraStream`."""
    stream = start_stream(
        camera_id=camera_index,
        model_path=model_path,
        confidence_threshold=confidence_threshold,
    )
    yield from stream.frames()
