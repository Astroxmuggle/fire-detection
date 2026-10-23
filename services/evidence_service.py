"""Evidence snapshot storage."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

from config import Config

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def default_evidence_dir() -> Path:
    return Path(Config.EVIDENCE_DIR)


def ensure_evidence_dir(output_dir=None) -> Path:
    target_dir = Path(output_dir) if output_dir is not None else default_evidence_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def _sanitize(value, fallback="unknown") -> str:
    cleaned = _UNSAFE_CHARS.sub("_", str(value or fallback).strip().lower())
    return cleaned.strip(" .") or fallback


def save_evidence_frame(frame, class_name, camera_source, output_dir=None) -> Path:
    if frame is None:
        raise ValueError("Frame is required to save evidence.")

    array = np.asarray(frame)
    if array.size == 0:
        raise ValueError("Frame is empty.")

    safe_class = _sanitize(class_name, "unknown")
    safe_camera = _sanitize(camera_source, "unknown")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{safe_class}_{safe_camera}_{timestamp}_{uuid4().hex[:8]}.jpg"

    filepath = ensure_evidence_dir(output_dir) / filename
    if not cv2.imwrite(str(filepath), array):
        raise IOError(f"Failed to save evidence frame to {filepath}")

    return filepath


def resolve_evidence_path(snapshot_path, base_dir=None):
    """Return *snapshot_path* only when it resolves inside the evidence folder.

    Used by the download route so a crafted database value cannot expose
    arbitrary files on disk.
    """
    if not snapshot_path:
        return None

    base = Path(base_dir) if base_dir is not None else default_evidence_dir()
    try:
        base_resolved = base.resolve()
        candidate = Path(snapshot_path)
        if not candidate.is_absolute():
            candidate = base_resolved / candidate
        candidate = candidate.resolve()
    except (OSError, RuntimeError, ValueError):
        return None

    if base_resolved not in candidate.parents and candidate.parent != base_resolved:
        return None
    if not candidate.is_file():
        return None
    return candidate
