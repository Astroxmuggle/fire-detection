"""JSON projections shared by the REST API, the HTML pages and SSE.

Two rules:

* filesystem paths never leave the process — events expose ``evidence_url`` and
  ``has_evidence`` instead of ``snapshot_path``;
* camera sources are passed through :func:`redact_source`, so RTSP credentials
  never appear in a response or an event payload.
"""

from __future__ import annotations

from typing import Any, Dict

from services.redaction import redact_source


def serialize_event(row) -> Dict[str, Any]:
    data = dict(row)
    snapshot_path = data.pop("snapshot_path", None)
    data["camera_source"] = redact_source(data.get("camera_source"))
    data["has_evidence"] = bool(snapshot_path)
    data["evidence_url"] = f"/evidence/{data['id']}" if snapshot_path else None
    return data


def serialize_incident(row) -> Dict[str, Any]:
    data = dict(row)
    data["camera_source"] = redact_source(data.get("camera_source"))
    evidence_event_id = data.get("evidence_event_id")
    data["has_evidence"] = bool(evidence_event_id)
    data["evidence_url"] = f"/evidence/{evidence_event_id}" if evidence_event_id else None
    return data


def serialize_alert(row) -> Dict[str, Any]:
    data = dict(row)
    return {
        "id": data.get("id"),
        "event_id": data.get("event_id"),
        "alert_level": data.get("alert_level"),
        "acknowledged": bool(data.get("acknowledged")),
        "status": "acknowledged" if data.get("acknowledged") else "pending",
        "created_at": data.get("created_at"),
    }


def serialize_worker(worker: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(worker)
    if "source" in data:
        data["source"] = redact_source(data.get("source"))
    return data
