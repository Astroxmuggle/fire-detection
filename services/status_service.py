"""Runtime status of the model, the cameras and the detection loops."""

from __future__ import annotations

import threading
import time
from typing import Dict, Optional

UNKNOWN = "unknown"
ONLINE = "online"
OFFLINE = "offline"
BUSY = "busy"
LOW_DETAIL = "low_detail"


class RuntimeStatus:
    """Thread-safe snapshot of what the service is actually doing.

    Per-camera state lives in its own bucket; the aggregate fields
    (``camera_status``, ``stream_active``, ``frames_processed``) are derived so
    the original single-camera API keeps working unchanged.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._global = {
            "model_loaded": False,
            "model_path": None,
            "model_classes": [],
            "frames_processed": 0,
            "frames_skipped": 0,
            "last_frame_at": None,
            "last_error": None,
            "started_at": time.time(),
        }
        self._cameras: Dict[int, dict] = {}

    # ------------------------------------------------------------- primitives
    def _bucket(self, camera_id) -> dict:
        key = int(camera_id) if camera_id is not None else 0
        return self._cameras.setdefault(
            key,
            {
                "camera_id": key,
                "name": None,
                "source": None,
                "status": UNKNOWN,
                "error": None,
                "stream_active": False,
                "frames_processed": 0,
                "frames_skipped": 0,
                "last_frame_at": None,
            },
        )

    def set_model(self, loaded: bool, path: Optional[str] = None, classes=None):
        with self._lock:
            self._global["model_loaded"] = bool(loaded)
            self._global["model_path"] = str(path) if path else None
            self._global["model_classes"] = list(classes or [])

    def set_camera(
        self,
        camera_id,
        status: str,
        source=None,
        error: Optional[str] = None,
        name: Optional[str] = None,
    ):
        with self._lock:
            bucket = self._bucket(camera_id)
            bucket["status"] = str(status)
            if source is not None:
                bucket["source"] = str(source)
            if name is not None:
                bucket["name"] = str(name)
            bucket["error"] = error

    def mark_stream(self, camera_id, active: bool):
        with self._lock:
            self._bucket(camera_id)["stream_active"] = bool(active)

    def mark_frame(self, camera_id=None, skipped: bool = False):
        with self._lock:
            self._global["last_frame_at"] = time.time()
            if skipped:
                self._global["frames_skipped"] += 1
            else:
                self._global["frames_processed"] += 1

            if camera_id is None:
                return
            bucket = self._bucket(camera_id)
            if skipped:
                bucket["frames_skipped"] += 1
            else:
                bucket["frames_processed"] += 1
            bucket["last_frame_at"] = self._global["last_frame_at"]

    def record_error(self, error: str):
        with self._lock:
            self._global["last_error"] = str(error)

    # ------------------------------------------------------------------ output
    def _camera_payload(self, bucket: dict) -> dict:
        payload = dict(bucket)
        payload["last_frame_age_seconds"] = (
            None
            if bucket["last_frame_at"] is None
            else round(time.time() - bucket["last_frame_at"], 1)
        )
        return payload

    def snapshot(self) -> dict:
        with self._lock:
            state = dict(self._global)
            cameras = [self._camera_payload(bucket) for bucket in self._cameras.values()]

        cameras.sort(key=lambda item: item["camera_id"])
        active = [camera for camera in cameras if camera["stream_active"]]

        if active:
            camera_status = ONLINE
        elif cameras and all(camera["status"] == OFFLINE for camera in cameras):
            camera_status = OFFLINE
        elif cameras and any(camera["status"] == ONLINE for camera in cameras):
            camera_status = ONLINE
        else:
            camera_status = UNKNOWN

        primary = active[0] if active else (cameras[0] if cameras else None)

        state.update({
            "camera_status": camera_status,
            "camera_source": primary["source"] if primary else None,
            "camera_error": primary["error"] if primary else None,
            "stream_active": bool(active),
            "active_streams": len(active),
            "cameras": cameras,
            "uptime_seconds": round(time.time() - state["started_at"], 1),
            "last_frame_age_seconds": (
                None
                if state["last_frame_at"] is None
                else round(time.time() - state["last_frame_at"], 1)
            ),
        })
        return state


_STATUS = RuntimeStatus()


def get_runtime_status() -> RuntimeStatus:
    return _STATUS


def reset_runtime_status() -> None:
    global _STATUS
    _STATUS = RuntimeStatus()
