"""API contract tests."""

from __future__ import annotations

import numpy as np

from services.event_service import create_confirmed_event


def _event(class_name="fire", confidence=0.9, source="webcam"):
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    return create_confirmed_event(class_name, confidence, source, frame=frame)


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json["status"] == "healthy"
    assert response.json["version"]


def test_status_reports_real_state(client):
    data = client.get("/api/status").json

    assert data["status"] == "running"
    assert data["camera_status"] in {"unknown", "offline", "online"}
    assert data["model_status"] in {"loaded", "not loaded"}
    assert data["stream_active"] is False
    assert data["detection_count"] == 0


def test_status_counts_events_and_alerts(client):
    _event("fire")
    _event("smoke")
    data = client.get("/api/status").json

    assert data["detection_count"] == 2
    assert data["confirmed_incidents"] == 2
    assert data["pending_alerts"] == 2
    assert data["by_class"] == {"fire": 1, "smoke": 1}


def test_get_events_returns_persisted_data(client):
    _event("fire", 0.94)
    response = client.get("/api/events")

    assert response.status_code == 200
    assert isinstance(response.json, list)
    assert response.json[0]["class_name"] == "fire"
    assert response.json[0]["camera_source"] == "webcam"


def test_get_events_filters_by_class(client):
    _event("fire")
    _event("smoke")

    payload = client.get("/api/events?class=fire").json
    assert len(payload) == 1
    assert payload[0]["class_name"] == "fire"


def test_get_events_respects_limit(client):
    for _ in range(3):
        _event("fire")

    payload = client.get("/api/events?limit=2").json
    assert len(payload) == 2


def test_event_detail_returns_record_and_404(client):
    event_id = _event("fire")

    found = client.get(f"/api/events/{event_id}")
    assert found.status_code == 200
    assert found.json["id"] == event_id

    missing = client.get("/api/events/999999")
    assert missing.status_code == 404
    assert missing.json["error"] == "Event not found"


def test_alerts_endpoint_returns_listing(client):
    _event("fire")
    response = client.get("/api/alerts")

    assert response.status_code == 200
    assert "alerts" in response.json
    assert len(response.json["alerts"]) == 1
    assert response.json["alerts"][0]["status"] == "pending"


def test_acknowledge_alert_endpoint(client):
    _event("fire")
    alert_id = client.get("/api/alerts").json["alerts"][0]["id"]

    response = client.post(f"/api/alerts/{alert_id}/acknowledge")
    assert response.status_code == 200
    assert response.json["message"] == "Alert acknowledged"

    assert client.get("/api/alerts").json["alerts"][0]["acknowledged"] == 1


def test_acknowledge_unknown_alert_returns_404(client):
    response = client.post("/api/alerts/987654/acknowledge")
    assert response.status_code == 404


def test_settings_endpoint_returns_runtime_values(client):
    settings = client.get("/api/settings").json["settings"]

    assert 0.0 <= settings["confidence_threshold"] <= 1.0
    assert settings["alert_cooldown"] >= 0
    assert settings["confirmation_frames"] >= 1
    assert settings["model_path"].endswith(".pt")


def test_settings_update_applies_and_validates(client):
    response = client.put(
        "/api/settings",
        json={"confidence_threshold": 0.66, "alert_cooldown": 30},
    )
    assert response.status_code == 200
    assert response.json["settings"]["confidence_threshold"] == 0.66
    assert response.json["settings"]["alert_cooldown"] == 30

    assert client.put("/api/settings", json={"confidence_threshold": 1.5}).status_code == 400
    assert client.put("/api/settings", json={"alert_cooldown": "abc"}).status_code == 400
    assert client.put("/api/settings", json={"alert_cooldown": 0}).status_code == 400


def test_metrics_endpoint_reflects_database(client):
    _event("fire")
    _event("smoke")
    metrics = client.get("/api/metrics").json

    assert metrics["detection_count"] == 2
    assert metrics["confirmed_incidents"] == 2
    assert metrics["alerts_total"] == 2
    assert metrics["alerts_pending"] == 2
    assert metrics["by_class"] == {"fire": 1, "smoke": 1}


def test_stream_stop_is_idempotent(client):
    response = client.post("/api/stream/stop")
    assert response.status_code == 200
    assert response.json["stopped"] == 0
    assert response.json["stream_active"] is False


def test_camera_probe_reports_offline_without_a_device(client, monkeypatch):
    import routes.api as api_module
    import services.camera_service as camera_service

    monkeypatch.setattr(
        api_module,
        "open_camera",
        lambda source=None: (_ for _ in ()).throw(camera_service.CameraUnavailable("no device")),
    )
    payload = client.get("/api/camera/probe").json
    assert payload["camera_status"] == "offline"
    assert "no device" in payload["error"]


def test_events_stream_connects(client, monkeypatch):
    from config import Config

    monkeypatch.setattr(Config, "SSE_HEARTBEAT_SECONDS", 0.05)
    response = client.get("/api/events/stream", buffered=False)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["Content-Type"]


def test_events_stream_respects_disabled_flag(client, monkeypatch):
    from config import Config

    monkeypatch.setattr(Config, "SSE_ENABLED", False)
    response = client.get("/api/events/stream")
    assert response.status_code == 404
