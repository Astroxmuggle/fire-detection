"""Incident lifecycle: coalescing, transitions, concurrency, API and evidence."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import numpy as np
import pytest

import database.db as db
from services.event_service import create_confirmed_event, get_event_by_id, get_events
from services.incident_service import (
    IncidentError,
    IncidentNotFound,
    InvalidTransition,
    acknowledge,
    close,
    get_incident,
    get_incident_stats,
    get_transitions,
    list_incidents,
)


def make_event(
    class_name="fire",
    confidence=0.9,
    camera_id=1,
    source="camera:0",
    source_kind="file",
    frame=None,
):
    return create_confirmed_event(
        class_name,
        confidence,
        source,
        frame=frame,
        camera_id=camera_id,
        source_kind=source_kind,
        play_sound=False,
    )


# ------------------------------------------------------------------ coalescing
def test_repeated_detections_update_a_single_active_incident():
    first = make_event(confidence=0.80)
    second = make_event(confidence=0.95)

    incidents = list_incidents()
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident["status"] == "open"
    assert incident["event_count"] == 2
    assert incident["first_event_id"] == first
    assert incident["last_event_id"] == second
    assert incident["peak_confidence"] == pytest.approx(0.95)

    assert get_event_by_id(first)["incident_id"] == incident["id"]
    assert get_event_by_id(second)["incident_id"] == incident["id"]


def test_different_classes_and_cameras_get_separate_incidents():
    make_event("fire", camera_id=1)
    make_event("smoke", camera_id=1)
    make_event("fire", camera_id=2)

    incidents = list_incidents()
    assert len(incidents) == 3
    assert {(item["camera_id"], item["class_name"]) for item in incidents} == {
        (1, "fire"),
        (1, "smoke"),
        (2, "fire"),
    }


# ------------------------------------------------------------------ lifecycle
def test_acknowledge_is_persisted_and_idempotent():
    make_event()
    incident = list_incidents()[0]

    result = acknowledge(incident["id"], actor="tester", note="seen on site")
    assert result["status"] == "acknowledged"
    assert result["acknowledged_at"]
    assert result["acknowledged_by"] == "tester"
    assert result["changed"] is True

    repeated = acknowledge(incident["id"])
    assert repeated["status"] == "acknowledged"
    assert repeated["changed"] is False

    # Survives a brand-new connection, i.e. an application restart.
    raw = sqlite3.connect(db.DATABASE_PATH)
    try:
        status = raw.execute("SELECT status FROM incidents WHERE id = ?", (incident["id"],)).fetchone()[0]
    finally:
        raw.close()
    assert status == "acknowledged"


def test_acknowledgement_does_not_hide_new_detections():
    make_event()
    incident = list_incidents()[0]
    acknowledge(incident["id"])

    make_event(confidence=0.97)

    updated = get_incident(incident["id"])
    assert updated["status"] == "acknowledged"  # not silently reopened or closed
    assert updated["event_count"] == 2
    assert updated["peak_confidence"] == pytest.approx(0.97)


def test_close_records_reason_and_blocks_further_transitions():
    make_event()
    incident = list_incidents()[0]
    acknowledge(incident["id"])

    result = close(incident["id"], reason="false_positive", actor="tester")
    assert result["status"] == "closed"
    assert result["close_reason"] == "false_positive"
    assert result["closed_at"]

    assert close(incident["id"])["changed"] is False  # idempotent

    with pytest.raises(InvalidTransition):
        acknowledge(incident["id"])

    transitions = get_transitions(incident["id"])
    assert [item["to_status"] for item in transitions] == ["open", "acknowledged", "closed"]


def test_closed_incident_is_not_reopened_by_a_new_detection():
    make_event()
    original = list_incidents()[0]
    close(original["id"], reason="resolved")

    make_event(confidence=0.88)

    incidents = list_incidents()
    assert len(incidents) == 2
    active = [item for item in incidents if item["status"] != "closed"]
    assert len(active) == 1
    assert active[0]["id"] != original["id"]


def test_invalid_requests_are_rejected_clearly():
    with pytest.raises(IncidentNotFound):
        acknowledge(999999)

    make_event()
    incident = list_incidents()[0]

    with pytest.raises(IncidentError):
        close(incident["id"], reason="because-i-said-so")


def test_incident_stats_count_each_state():
    make_event("fire", camera_id=1)
    make_event("smoke", camera_id=1)
    close(list_incidents({"class": "smoke"})[0]["id"], reason="resolved")

    stats = get_incident_stats()
    assert stats["open"] == 1
    assert stats["closed"] == 1
    assert stats["acknowledged"] == 0
    assert stats["total"] == 2


# ----------------------------------------------------------------- concurrency
def test_concurrent_writers_neither_lose_nor_duplicate_records():
    thread_count, per_thread = 8, 4
    barrier = threading.Barrier(thread_count)
    errors = []

    def worker():
        try:
            barrier.wait(timeout=15)
            for _ in range(per_thread):
                make_event(confidence=0.9)
        except Exception as exc:  # noqa: BLE001 - surfaced by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=worker, name=f"writer-{i}") for i in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    assert all(not thread.is_alive() for thread in threads)

    total = thread_count * per_thread
    incidents = list_incidents()
    assert len(incidents) == 1
    assert incidents[0]["event_count"] == total

    events = get_events({"incident_id": incidents[0]["id"]})
    assert len(events) == total
    assert len({event["id"] for event in events}) == total  # no duplicates

    from alerts.manager import get_alerts

    assert len(get_alerts()) == total  # one alert per confirmed event, none lost


# --------------------------------------------------------------------- replay
def test_file_source_replay_is_tagged_and_does_not_inflate_incidents():
    for _ in range(6):
        make_event(source_kind="file")

    incidents = list_incidents()
    assert len(incidents) == 1
    assert incidents[0]["source_kind"] == "file"
    assert incidents[0]["event_count"] == 6


# ------------------------------------------------------------------------ API
def test_api_incident_lifecycle(client):
    make_event(confidence=0.9)
    make_event(confidence=0.92)

    listing = client.get("/api/incidents").json
    assert len(listing) == 1
    incident_id = listing[0]["id"]

    detail = client.get(f"/api/incidents/{incident_id}").json
    assert detail["event_count"] == 2
    assert len(detail["events"]) == 2
    assert len(detail["transitions"]) == 1

    acknowledged = client.post(f"/api/incidents/{incident_id}/acknowledge", json={"actor": "api-test"})
    assert acknowledged.status_code == 200
    assert acknowledged.json["incident"]["status"] == "acknowledged"
    assert acknowledged.json["changed"] is True

    assert client.post(f"/api/incidents/{incident_id}/acknowledge").json["changed"] is False

    closed = client.post(f"/api/incidents/{incident_id}/close", json={"reason": "resolved"})
    assert closed.status_code == 200
    assert closed.json["incident"]["status"] == "closed"

    conflict = client.post(f"/api/incidents/{incident_id}/acknowledge")
    assert conflict.status_code == 409

    assert client.post("/api/incidents/999999/close").status_code == 404
    assert client.get("/api/incidents/999999").status_code == 404


def test_api_rejects_an_unknown_close_reason(client):
    make_event()
    incident_id = client.get("/api/incidents").json[0]["id"]

    response = client.post(f"/api/incidents/{incident_id}/close", json={"reason": "nonsense"})
    assert response.status_code == 400


def test_api_never_exposes_filesystem_paths(client):
    event_id = make_event(frame=np.zeros((32, 32, 3), dtype=np.uint8))

    event = client.get("/api/events").json[0]
    assert "snapshot_path" not in event
    assert event["has_evidence"] is True
    assert event["evidence_url"] == f"/evidence/{event_id}"

    incident = client.get("/api/incidents").json[0]
    assert "snapshot_path" not in incident
    assert incident["evidence_url"] == event["evidence_url"]

    legacy = client.get("/events").json[0]
    assert "snapshot_path" not in legacy


def test_missing_evidence_file_does_not_break_pages(client):
    event_id = make_event(frame=np.zeros((32, 32, 3), dtype=np.uint8))
    stored = get_event_by_id(event_id)["snapshot_path"]
    assert stored and Path(stored).is_file()

    Path(stored).unlink()

    page = client.get(f"/incident/{event_id}")
    assert page.status_code == 200
    assert b"missing on disk" in page.data

    assert client.get(f"/evidence/{event_id}").status_code == 404
