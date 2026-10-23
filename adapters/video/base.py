"""Video-source contract.

A source is anything the worker can open, read frames from and close: a webcam,
an RTSP/HTTP stream or a video file. The worker never touches OpenCV directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Protocol, Tuple, runtime_checkable

_NETWORK_PREFIXES = ("rtsp://", "rtmp://", "http://", "https://", "udp://", "tcp://")
_INTEGER = re.compile(r"^-?\d+$")


class VideoSourceError(RuntimeError):
    """Base class for video-source problems."""


class VideoSourceUnavailable(VideoSourceError):
    """The source could not be opened (missing device, unreachable stream, bad path)."""


@dataclass(frozen=True)
class SourceInfo:
    raw: str
    kind: str  # "webcam" | "network" | "file"
    is_live: bool


def parse_source(value, default=None):
    """Return an int for device indices, a str for URLs and paths."""
    raw = default if value is None else value
    if isinstance(raw, int):
        return raw

    text = str(raw).strip()
    if not text:
        return 0 if default is None else default
    if _INTEGER.match(text):
        return int(text)
    return text


def classify_source(value) -> SourceInfo:
    parsed = parse_source(value)
    if isinstance(parsed, int):
        return SourceInfo(raw=str(parsed), kind="webcam", is_live=True)

    lowered = parsed.lower()
    if lowered.startswith(_NETWORK_PREFIXES):
        return SourceInfo(raw=parsed, kind="network", is_live=True)
    return SourceInfo(raw=parsed, kind="file", is_live=False)


@runtime_checkable
class VideoSource(Protocol):
    """Minimal capture surface used by the inference worker."""

    @property
    def is_open(self) -> bool:
        ...

    def info(self) -> SourceInfo:
        ...

    def open(self) -> None:
        ...

    def read(self) -> Tuple[bool, Optional[object]]:
        ...

    def close(self) -> None:
        ...
