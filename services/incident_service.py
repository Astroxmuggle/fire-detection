"""Incident lifecycle: grouping confirmed detections into operator work items.

Vocabulary
----------
* **Raw detection** — one model output above threshold on one frame. Not stored
  individually and not shown to operators.
* **Confirmed detection event** — a raw detection that survived temporal
  confirmation. Stored in ``detection_events`` with an evidence frame.
* **Incident** — the operator-facing work item grouping confirmed detections of
  the same class on the same camera while it stays active. Stored in
  ``incidents``; every confirmed event points at the incident it fed.
* **Alert** — the notification record for one confirmed event (audible cue,
  acknowledgement flag). Alerts remain per event.

Lifecycle (only these transitions exist)::

    open ──acknowledge──► acknowledged ──close──► closed
      └──────────────────────close──────────────────┘

Rules
-----
* A confirmed detection either **updates** the single active incident for its
  (camera, class) pair or **opens** a new one. Closed incidents are never
  reopened; a later detection starts a new incident.
* Acknowledging means "an operator has seen this". It explicitly does **not**
  mean the hazard is gone: new detections keep attaching to the acknowledged
  incident, and only an explicit close ends it.
* No automatic closure. Nothing here touches life-safety equipment.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database.db import get_db_connection, transaction

ACTIVE_STATUSES = ("open", "acknowledged")
VALID_STATUSES = ("open", "acknowledged", "closed")
CLOSE_REASONS = ("resolved", "false_positive", "duplicate", "other")


class IncidentError(RuntimeError):
    """Base class for incident lifecycle errors."""


class IncidentNotFound(IncidentError):
    pass


class InvalidTransition(IncidentError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_dict(row) -> Optional[Dict[str, Any]]:
    return dict(row) if row is not None else None


# ------------------------------------------------------------------ write path
def record_detection(
    connection: sqlite3.Connection,
    event_id: int,
    camera_id: int,
    camera_source: str,
    class_name: str,
    confidence: float,
    source_kind: str = "unknown",
    has_evidence: bool = False,
) -> int:
    """Attach a confirmed detection to its active incident, or open one.

    Must run inside a caller-provided transaction (see ``database.db.transaction``)
    so the event insert, the incident update and the alert insert commit
    together. Returns the incident id.
    """
    camera_id = int(camera_id or 0)
    class_name = str(class_name).lower()
    now = _utc_now()

    row = connection.execute(
        """
        SELECT * FROM incidents
        WHERE camera_id = ? AND class_name = ? AND status IN ('open', 'acknowledged')
        ORDER BY id DESC LIMIT 1
        """,
        (camera_id, class_name),
    ).fetchone()

    if row is None:
        try:
            cursor = connection.execute(
                """
                INSERT INTO incidents (
                    camera_id, camera_source, class_name, status, source_kind,
                    opened_at, updated_at, first_event_id, last_event_id,
                    event_count, peak_confidence, last_confidence, evidence_event_id
                ) VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    camera_id,
                    str(camera_source),
                    class_name,
                    str(source_kind),
                    now,
                    now,
                    int(event_id),
                    int(event_id),
                    float(confidence),
                    float(confidence),
                    int(event_id) if has_evidence else None,
                ),
            )
            incident_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO incident_transitions
                    (incident_id, from_status, to_status, actor, reason, created_at)
                VALUES (?, NULL, 'open', 'system', 'first confirmed detection', ?)
                """,
                (incident_id, now),
            )
        except sqlite3.IntegrityError:
            # Another writer created the active incident between our SELECT and
            # INSERT (the partial unique index caught it). Join theirs.
            row = connection.execute(
                """
                SELECT * FROM incidents
                WHERE camera_id = ? AND class_name = ? AND status IN ('open', 'acknowledged')
                ORDER BY id DESC LIMIT 1
                """,
                (camera_id, class_name),
            ).fetchone()
            if row is None:  # pragma: no cover - only if the winner closed it
                raise
            incident_id = _update_active(connection, row, event_id, confidence, has_evidence)
    else:
        incident_id = _update_active(connection, row, event_id, confidence, has_evidence)

    connection.execute(
        "UPDATE detection_events SET incident_id = ? WHERE id = ?",
        (incident_id, int(event_id)),
    )
    return incident_id


def _update_active(connection, row, event_id: int, confidence: float, has_evidence: bool) -> int:
    incident_id = int(row["id"])
    peak = max(float(row["peak_confidence"] or 0.0), float(confidence))
    evidence_event_id = int(event_id) if has_evidence else row["evidence_event_id"]

    connection.execute(
        """
        UPDATE incidents
        SET last_event_id = ?, event_count = event_count + 1,
            last_confidence = ?, peak_confidence = ?, updated_at = ?,
            evidence_event_id = ?
        WHERE id = ?
        """,
        (
            int(event_id),
            float(confidence),
            peak,
            _utc_now(),
            evidence_event_id,
            incident_id,
        ),
    )
    return incident_id


def acknowledge(incident_id: int, actor: str = "operator", note: Optional[str] = None) -> Dict[str, Any]:
    """Move an open incident to acknowledged. Idempotent for repeated requests."""
    with transaction() as connection:
        row = connection.execute("SELECT * FROM incidents WHERE id = ?", (int(incident_id),)).fetchone()
        if row is None:
            raise IncidentNotFound(f"incident {incident_id} not found")

        if row["status"] == "closed":
            raise InvalidTransition("a closed incident cannot be acknowledged")
        if row["status"] == "acknowledged":
            return {**_row_to_dict(row), "changed": False}

        now = _utc_now()
        connection.execute(
            """
            UPDATE incidents
            SET status = 'acknowledged', acknowledged_at = ?, acknowledged_by = ?,
                updated_at = ?, notes = COALESCE(?, notes)
            WHERE id = ?
            """,
            (now, str(actor), now, note, int(incident_id)),
        )
        connection.execute(
            """
            INSERT INTO incident_transitions
                (incident_id, from_status, to_status, actor, reason, created_at)
            VALUES (?, 'open', 'acknowledged', ?, ?, ?)
            """,
            (int(incident_id), str(actor), note or "operator acknowledgement", now),
        )
        # The operator saw this occurrence: its alerts are acknowledged with it.
        connection.execute(
            """
            UPDATE alerts SET acknowledged = 1
            WHERE acknowledged = 0 AND event_id IN (
                SELECT id FROM detection_events WHERE incident_id = ?
            )
            """,
            (int(incident_id),),
        )

        updated = connection.execute("SELECT * FROM incidents WHERE id = ?", (int(incident_id),)).fetchone()
        return {**_row_to_dict(updated), "changed": True}


def close(
    incident_id: int,
    reason: str = "resolved",
    actor: str = "operator",
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Close an open or acknowledged incident. Idempotent for repeated requests."""
    if reason not in CLOSE_REASONS:
        raise IncidentError(f"unknown close reason {reason!r}; expected one of {CLOSE_REASONS}")

    with transaction() as connection:
        row = connection.execute("SELECT * FROM incidents WHERE id = ?", (int(incident_id),)).fetchone()
        if row is None:
            raise IncidentNotFound(f"incident {incident_id} not found")
        if row["status"] == "closed":
            return {**_row_to_dict(row), "changed": False}

        now = _utc_now()
        connection.execute(
            """
            UPDATE incidents
            SET status = 'closed', closed_at = ?, closed_by = ?, close_reason = ?,
                updated_at = ?, notes = COALESCE(?, notes)
            WHERE id = ?
            """,
            (now, str(actor), reason, now, note, int(incident_id)),
        )
        connection.execute(
            """
            INSERT INTO incident_transitions
                (incident_id, from_status, to_status, actor, reason, created_at)
            VALUES (?, ?, 'closed', ?, ?, ?)
            """,
            (int(incident_id), row["status"], str(actor), reason, now),
        )

        updated = connection.execute("SELECT * FROM incidents WHERE id = ?", (int(incident_id),)).fetchone()
        return {**_row_to_dict(updated), "changed": True}


# ------------------------------------------------------------------- read path
def get_incident(incident_id: int) -> Optional[Dict[str, Any]]:
    connection = get_db_connection()
    try:
        row = connection.execute("SELECT * FROM incidents WHERE id = ?", (int(incident_id),)).fetchone()
    finally:
        connection.close()
    return _row_to_dict(row)


def get_incident_for_event(event_id: int) -> Optional[Dict[str, Any]]:
    connection = get_db_connection()
    try:
        row = connection.execute(
            """
            SELECT i.* FROM incidents i
            JOIN detection_events e ON e.incident_id = i.id
            WHERE e.id = ?
            """,
            (int(event_id),),
        ).fetchone()
    finally:
        connection.close()
    return _row_to_dict(row)


def get_active_incident(camera_id, class_name) -> Optional[Dict[str, Any]]:
    connection = get_db_connection()
    try:
        row = connection.execute(
            """
            SELECT * FROM incidents
            WHERE camera_id = ? AND class_name = ? AND status IN ('open', 'acknowledged')
            ORDER BY id DESC LIMIT 1
            """,
            (int(camera_id or 0), str(class_name).lower()),
        ).fetchone()
    finally:
        connection.close()
    return _row_to_dict(row)


def list_incidents(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    filters = filters or {}
    connection = get_db_connection()
    try:
        query = "SELECT * FROM incidents"
        params: List[Any] = []
        conditions: List[str] = []

        status = filters.get("status")
        if status:
            if str(status) not in VALID_STATUSES:
                raise IncidentError(f"unknown status {status!r}")
            conditions.append("status = ?")
            params.append(str(status))
        if filters.get("camera_id") is not None:
            conditions.append("camera_id = ?")
            params.append(int(filters["camera_id"]))
        if filters.get("class"):
            conditions.append("class_name = ?")
            params.append(str(filters["class"]).lower())
        if filters.get("active"):
            conditions.append("status IN ('open', 'acknowledged')")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY opened_at DESC, id DESC"

        limit = filters.get("limit")
        if limit:
            query += " LIMIT ?"
            params.append(int(limit))

        rows = connection.execute(query, params).fetchall()
    finally:
        connection.close()
    return [dict(row) for row in rows]


def get_transitions(incident_id: int) -> List[Dict[str, Any]]:
    connection = get_db_connection()
    try:
        rows = connection.execute(
            "SELECT * FROM incident_transitions WHERE incident_id = ? ORDER BY id",
            (int(incident_id),),
        ).fetchall()
    finally:
        connection.close()
    return [dict(row) for row in rows]


def get_incident_stats() -> Dict[str, int]:
    connection = get_db_connection()
    try:
        rows = connection.execute(
            "SELECT status, COUNT(*) FROM incidents GROUP BY status"
        ).fetchall()
    finally:
        connection.close()

    stats = {status: 0 for status in VALID_STATUSES}
    for status, count in rows:
        stats[str(status)] = int(count)
    stats["total"] = sum(stats[status] for status in VALID_STATUSES)
    return stats
