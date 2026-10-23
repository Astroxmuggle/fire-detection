"""HTML page and stream routing tests."""

from __future__ import annotations

import numpy as np

from alerts.manager import get_alerts_for_event
from services.event_service import create_confirmed_event


def _event(class_name="fire", confidence=0.91):
    frame = np.zeros((48, 48, 3), dtype=np.uint8)
    return create_confirmed_event(class_name, confidence, "camera:0", frame=frame)


def test_dashboard_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"FireWatch AI" in response.data
    assert b"Camera feed" in response.data
    assert b"Incident history" in response.data


def test_dashboard_alias_renders(client):
    assert client.get("/dashboard").status_code == 200


def test_history_page_lists_events(client):
    _event("fire")
    _event("smoke")

    response = client.get("/history")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "fire" in body and "smoke" in body
    assert "Incident history" in body


def test_history_page_filters_by_class(client):
    _event("fire")
    _event("smoke")

    body = client.get("/history?class=fire").get_data(as_text=True)
    assert "fire" in body
    assert ">smoke<" not in body


def test_incident_detail_renders_with_evidence(client):
    event_id = _event("fire")

    response = client.get(f"/incident/{event_id}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert f"Incident #{event_id}" in body
    assert f"/evidence/{event_id}" in body


def test_incident_detail_missing_returns_404_page(client):
    response = client.get("/incident/999999")
    assert response.status_code == 404
    assert b"Back to dashboard" in response.data


def test_evidence_route_serves_the_snapshot(client):
    event_id = _event("smoke")

    response = client.get(f"/evidence/{event_id}")
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert response.data[:2] == b"\xff\xd8"


def test_evidence_route_404_for_unknown_event(client):
    assert client.get("/evidence/999999").status_code == 404


def test_acknowledging_an_incident_marks_its_alerts(client):
    event_id = _event("fire")
    assert get_alerts_for_event(event_id)[0]["acknowledged"] == 0

    response = client.post(f"/incident/{event_id}/acknowledge")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/incident/{event_id}")

    assert get_alerts_for_event(event_id)[0]["acknowledged"] == 1


def test_video_feed_returns_503_when_no_camera(client, monkeypatch):
    import services.camera_service as camera_service

    monkeypatch.setattr(
        camera_service,
        "open_camera",
        lambda source=None: (_ for _ in ()).throw(camera_service.CameraUnavailable("no device")),
    )

    response = client.get("/video_feed")
    assert response.status_code == 503
    assert response.is_json
    assert "no device" in response.json["error"]


def test_video_feed_returns_409_when_stream_is_busy(client, monkeypatch):
    import services.camera_service as camera_service

    class BusyStream:
        closed = False

        def release(self):
            self.closed = True

    camera_service._active_stream = BusyStream()
    try:
        response = client.get("/video_feed")
        assert response.status_code == 409
    finally:
        camera_service._active_stream = None


def test_unknown_page_returns_html_404(client):
    response = client.get("/definitely-not-a-page")
    assert response.status_code == 404
    assert b"Back to dashboard" in response.data


def test_legacy_events_endpoint_still_returns_json(client):
    _event("fire")
    response = client.get("/events")
    assert response.status_code == 200
    assert isinstance(response.json, list)
