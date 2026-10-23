"""Event persistence and queries."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from alerts.manager import AlertManager
from config import Config
from database.db import get_db_connection, transaction
from services import incident_service
from services.evidence_service import save_evidence_frame

_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Process-wide alert manager so the cool-down actually spans events."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager(alert_cooldown=Config.ALERT_COOLDOWN)
    return _alert_manager


def reset_alert_manager() -> None:
    """Drop the cached manager (tests and settings reloads)."""
    global _alert_manager
    _alert_manager = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_event(event_type, class_label, confidence, camera_source, alert_status, snapshot_path=None):
    connection = get_db_connection()
    try:
        cursor = connection.execute(
            """
            INSERT INTO detection_events (
                event_type, class_name, confidence, camera_source,
                alert_status, snapshot_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_type,
                str(class_label),
                float(confidence),
                str(camera_source),
                str(alert_status),
                str(snapshot_path) if snapshot_path is not None else None,
                _utc_now(),
            ),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def create_confirmed_event(
    class_name,
    confidence,
    camera_source,
    frame=None,
    alert_status="confirmed",
    event_type="detection",
    play_sound=True,
    camera_id=None,
    source_kind=None,
):
    """Persist a confirmed detection, its evidence frame, its incident and its alert.

    The event insert, the incident create/update and the alert insert commit in
    one transaction, so a crash can never leave an incident without its event or
    an event without its alert. Evidence is written to disk first (outside the
    database lock) and referenced by path.
    """
    snapshot_path = None
    if frame is not None:
        snapshot_path = save_evidence_frame(frame, class_name, camera_source)

    resolved_camera_id = int(camera_id) if camera_id is not None else 0
    resolved_kind = str(source_kind or "unknown")
    manager = get_alert_manager()

    with transaction() as connection:
        cursor = connection.execute(
            """
            INSERT INTO detection_events (
                event_type, class_name, confidence, camera_source,
                alert_status, snapshot_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_type,
                str(class_name),
                float(confidence),
                str(camera_source),
                str(alert_status),
                str(snapshot_path) if snapshot_path is not None else None,
                _utc_now(),
            ),
        )
        event_id = cursor.lastrowid

        incident_id = incident_service.record_detection(
            connection,
            event_id=event_id,
            camera_id=resolved_camera_id,
            camera_source=str(camera_source),
            class_name=str(class_name),
            confidence=confidence,
            source_kind=resolved_kind,
            has_evidence=snapshot_path is not None,
        )

        alert_level = str(class_name or "info").lower()
        manager.create_alert(
            event_id=event_id,
            alert_level=alert_level,
            alert_type=alert_level,
            connection=connection,
        )

    if play_sound:
        manager.notify(str(class_name or "info").lower())

    try:
        from services.event_bus import publish
        publish("event", {
            "id": event_id,
            "incident_id": incident_id,
            "class_name": str(class_name),
            "confidence": float(confidence),
            "camera_source": str(camera_source),
            "alert_status": str(alert_status),
            "has_evidence": snapshot_path is not None,
        })
        incident_row = incident_service.get_incident(incident_id)
        if incident_row:
            from services.serializers import serialize_incident
            publish("incident", serialize_incident(incident_row))
    except Exception:
        pass

    return event_id


def get_events(filters=None):
    filters = filters or {}
    connection = get_db_connection()
    try:
        query = "SELECT * FROM detection_events"
        params = []
        conditions = []

        if filters.get("class"):
            conditions.append("class_name = ?")
            params.append(str(filters["class"]).lower())
        if filters.get("camera_source"):
            conditions.append("camera_source = ?")
            params.append(filters["camera_source"])
        if filters.get("alert_status"):
            conditions.append("alert_status = ?")
            params.append(filters["alert_status"])
        if filters.get("incident_id") is not None:
            conditions.append("incident_id = ?")
            params.append(int(filters["incident_id"]))
        if filters.get("since"):
            conditions.append("created_at >= ?")
            params.append(filters["since"])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC, id DESC"
        limit = filters.get("limit")
        if limit:
            try:
                query += " LIMIT ?"
                params.append(int(limit))
            except (TypeError, ValueError):
                pass

        rows = connection.execute(query, params).fetchall()
    finally:
        connection.close()
    return [dict(row) for row in rows]


def get_event_by_id(event_id):
    connection = get_db_connection()
    try:
        row = connection.execute(
            "SELECT * FROM detection_events WHERE id = ?",
            (int(event_id),),
        ).fetchone()
    finally:
        connection.close()
    return dict(row) if row else None


def get_event_history(limit=100):
    connection = get_db_connection()
    try:
        rows = connection.execute(
            "SELECT * FROM detection_events ORDER BY created_at DESC, id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    finally:
        connection.close()
    return [dict(row) for row in rows]


def get_event_stats() -> dict:
    connection = get_db_connection()
    try:
        total = connection.execute("SELECT COUNT(*) FROM detection_events").fetchone()[0]
        confirmed = connection.execute(
            "SELECT COUNT(*) FROM detection_events WHERE alert_status != 'pending'"
        ).fetchone()[0]
        pending = connection.execute(
            "SELECT COUNT(*) FROM detection_events WHERE alert_status = 'pending'"
        ).fetchone()[0]
        by_class = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT class_name, COUNT(*) FROM detection_events GROUP BY class_name"
            ).fetchall()
        }
        last_event = connection.execute(
            "SELECT created_at FROM detection_events ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()
    finally:
        connection.close()

    return {
        "detection_count": total,
        "confirmed_incidents": confirmed,
        "pending_incidents": pending,
        "by_class": by_class,
        "last_event_at": last_event[0] if last_event else None,
    }


def clear_event_history(include_alerts=True):
    """Delete stored events (and optionally their alerts).

    This is a maintenance helper; automated tests use a throw-away database and
    must never call it against production data.
    """
    connection = get_db_connection()
    try:
        connection.execute("DELETE FROM detection_events")
        if include_alerts:
            connection.execute("DELETE FROM alerts")
        connection.commit()
    finally:
        connection.close()
