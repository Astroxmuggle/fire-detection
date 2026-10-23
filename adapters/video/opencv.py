"""OpenCV implementation of the video-source contract.

Contains the capture-opening logic that used to live in
``services.camera_service.open_camera`` (including the Windows DirectShow
fallback). The public function is kept single-argument so a test or caller can
replace it without knowing the adapter internals.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

import cv2

from adapters.video.base import SourceInfo, VideoSource, VideoSourceUnavailable, classify_source, parse_source
from config import Config


def open_capture(source=None):
    """Open an OpenCV capture for an index, URL or file path.

    Raises ``VideoSourceUnavailable`` when the device/stream cannot be opened.
    """
    parsed = Config.CAMERA_SOURCE if source is None else source
    parsed = parse_source(parsed, default=Config.CAMERA_INDEX)

    capture = cv2.VideoCapture(parsed)
    if not capture.isOpened() and isinstance(parsed, int) and os.name == "nt":
        # Some Windows webcams only open through the DirectShow backend.
        capture.release()
        dshow = getattr(cv2, "CAP_DSHOW", None)
        if dshow is not None:
            capture = cv2.VideoCapture(parsed, dshow)

    if not capture.isOpened():
        raise VideoSourceUnavailable(f"Could not open camera source {parsed!r}")

    if isinstance(parsed, int):
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, Config.FRAME_WIDTH)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.FRAME_HEIGHT)

    return capture


class OpenCVVideoSource(VideoSource):
    """Webcam / RTSP / file source backed by ``cv2.VideoCapture``."""

    def __init__(self, raw_source, opener=None):
        self.raw_source = raw_source
        self._opener = opener or open_capture
        self._capture = None
        self._info = classify_source(raw_source)

    @property
    def is_open(self) -> bool:
        return self._capture is not None

    def info(self) -> SourceInfo:
        return self._info

    def open(self) -> None:
        if self._capture is not None:
            return
        # The opener is resolved at call time so tests can replace it.
        capture = self._opener(self.raw_source)
        is_open = getattr(capture, "isOpened", None)
        if callable(is_open) and not is_open():
            try:
                capture.release()
            except Exception:  # noqa: BLE001 - best effort
                pass
            raise VideoSourceUnavailable(f"Could not open camera source {self.raw_source!r}")
        self._capture = capture

    def read(self) -> Tuple[bool, Optional[object]]:
        if self._capture is None:
            return False, None
        ok, frame = self._capture.read()
        if not ok or frame is None:
            return False, None
        return True, frame

    def close(self) -> None:
        capture, self._capture = self._capture, None
        if capture is None:
            return
        try:
            capture.release()
        except Exception:  # noqa: BLE001 - release must never raise
            pass
