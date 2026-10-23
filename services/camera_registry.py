"""Named camera sources persisted in SQLite.

The registry is the single place that knows which cameras exist. A camera is a
row: an id, a display name, an OpenCV source (webcam index, RTSP URL or video
file) and an enabled flag. On first start the table is seeded from
``CAMERA_SOURCES`` / ``CAMERA_SOURCE`` so a single-camera deployment needs no
configuration at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from config import Config
from database.db import get_db_connection

_SOURCE_SPLIT = re.compile(r"[;,\n]")


@dataclass(frozen=True)
class Camera:
    id: int
    name: str
    source: str
    enabled: bool = True

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "enabled": self.enabled,
        }


def _row_to_camera(row) -> Camera:
    return Camera(
        id=int(row["id"]),
        name=row["name"],
        source=row["source"],
        enabled=bool(row["enabled"]),
    )


def parse_sources(value) -> List[str]:
    """Split ``CAMERA_SOURCES`` into individual sources."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = [str(item) for item in value]
    else:
        items = _SOURCE_SPLIT.split(str(value))

    return [item.strip() for item in items if item and item.strip()]


def configured_sources() -> List[str]:
    return parse_sources(getattr(Config, "CAMERA_SOURCES", "")) or parse_sources(Config.CAMERA_SOURCE)


def list_cameras(include_disabled: bool = False) -> List[Camera]:
    connection = get_db_connection()
    try:
        query = "SELECT id, name, source, enabled FROM cameras"
        if not include_disabled:
            query += " WHERE enabled = 1"
        query += " ORDER BY id"
        rows = connection.execute(query).fetchall()
    finally:
        connection.close()
    return [_row_to_camera(row) for row in rows]


def get_camera(camera_id) -> Optional[Camera]:
    if camera_id is None:
        return None
    try:
        identifier = int(camera_id)
    except (TypeError, ValueError):
        return None

    connection = get_db_connection()
    try:
        row = connection.execute(
            "SELECT id, name, source, enabled FROM cameras WHERE id = ?",
            (identifier,),
        ).fetchone()
    finally:
        connection.close()
    return _row_to_camera(row) if row else None


def get_default_camera() -> Optional[Camera]:
    cameras = list_cameras()
    return cameras[0] if cameras else None


def resolve_camera(camera_id=None) -> Optional[Camera]:
    """Return the requested camera, or the first enabled one."""
    if camera_id is not None:
        return get_camera(camera_id)
    return get_default_camera()


def add_camera(name: str, source: str, enabled: bool = True) -> Camera:
    source = str(source).strip()
    if not source:
        raise ValueError("A camera source is required")

    existing = _find_by_source(source)
    if existing is not None:
        return existing

    connection = get_db_connection()
    try:
        cursor = connection.execute(
            "INSERT INTO cameras (name, source, enabled, created_at) VALUES (?, ?, ?, ?)",
            (
                str(name).strip() or f"Camera {len(list_cameras(include_disabled=True)) + 1}",
                source,
                1 if enabled else 0,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        connection.commit()
        new_id = cursor.lastrowid
    finally:
        connection.close()
    return get_camera(new_id)


def set_camera_enabled(camera_id, enabled: bool) -> bool:
    connection = get_db_connection()
    try:
        cursor = connection.execute(
            "UPDATE cameras SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, int(camera_id)),
        )
        connection.commit()
        return (cursor.rowcount or 0) > 0
    finally:
        connection.close()


def delete_camera(camera_id) -> bool:
    connection = get_db_connection()
    try:
        cursor = connection.execute("DELETE FROM cameras WHERE id = ?", (int(camera_id),))
        connection.commit()
        return (cursor.rowcount or 0) > 0
    finally:
        connection.close()


def _find_by_source(source: str) -> Optional[Camera]:
    connection = get_db_connection()
    try:
        row = connection.execute(
            "SELECT id, name, source, enabled FROM cameras WHERE source = ?",
            (source,),
        ).fetchone()
    finally:
        connection.close()
    return _row_to_camera(row) if row else None


def sync_from_config(sources: Optional[Iterable[str]] = None, force: bool = False) -> List[Camera]:
    """Seed the registry from configuration when it is empty.

    ``force`` re-adds configured sources that are missing without deleting any
    user-defined camera.
    """
    existing = list_cameras(include_disabled=True)
    if existing and not force:
        return existing

    candidates = parse_sources(sources) if sources is not None else configured_sources()
    for index, source in enumerate(candidates, start=1):
        if _find_by_source(source) is None:
            name = "Main camera" if len(candidates) == 1 else f"Camera {index}"
            add_camera(name, source)

    return list_cameras(include_disabled=True)


def camera_state_map() -> dict:
    """Camera rows keyed by id, for merging with runtime state."""
    return {camera.id: camera for camera in list_cameras(include_disabled=True)}
