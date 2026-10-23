"""Runtime status of the camera, the model and the detection loop."""

from __future__ import annotations

import threading
import time
from typing import Optional


class RuntimeStatus:
    """Thread-safe snapshot of what the service is actually doing."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = {
            "model_loaded": False,
            "model_path": None,
            "model_classes": [],
            "camera_status": "unknown",  # unknown | online | offline | busy | low_detail
            "camera_source": None,
            "camera_error": None,
            "frames_processed": 0,
            "frames_skipped": 0,
            "last_frame_at": None,
            "last_error": None,
            "stream_active": False,
            "started_at": time.time(),
        }

    def _set(self, **changes):
        with self._lock:
            self._state.update(changes)

    # ------------------------------------------------------------------ events
    def set_model(self, loaded: bool, path: Optional[str] = None, classes=None):
        self._set(
            model_loaded=bool(loaded),
            model_path=str(path) if path else None,
            model_classes=list(classes or []),
        )

    def set_camera(self, status: str, source=None, error: Optional[str] = None):
        self._set(
            camera_status=str(status),
            camera_source=None if source is None else str(source),
            camera_error=error,
        )

    def mark_stream(self, active: bool):
        self._set(stream_active=bool(active))

    def mark_frame(self, skipped: bool = False):
        with self._lock:
            if skipped:
                self._state["frames_skipped"] += 1
            else:
                self._state["frames_processed"] += 1
            self._state["last_frame_at"] = time.time()

    def record_error(self, error: str):
        self._set(last_error=str(error))

    # ------------------------------------------------------------------ output
    def snapshot(self) -> dict:
        with self._lock:
            state = dict(self._state)
        state["uptime_seconds"] = round(time.time() - state["started_at"], 1)
        state["last_frame_age_seconds"] = (
            None
            if state["last_frame_at"] is None
            else round(time.time() - state["last_frame_at"], 1)
        )
        return state


_STATUS = RuntimeStatus()


def get_runtime_status() -> RuntimeStatus:
    return _STATUS


def reset_runtime_status() -> None:
    global _STATUS
    _STATUS = RuntimeStatus()
