"""Camera registry, multi-camera streaming and the camera API."""

from __future__ import annotations

import numpy as np
import pytest

import services.camera_service as camera_service
from services.camera_registry import (
    add_camera,
    delete_camera,
    get_camera,
    get_default_camera,
    list_cameras,
    parse_sources,
    set_camera_enabled,
    sync_from_config,
)


class FakeCapture:
    """Minimal stand-in for cv2.VideoCapture."""

    def __init__(self, frame=None, opened=True):
        self.frame = frame if frame is not None else np.zeros((64, 64, 3), dtype=np.uint8)
        self.opened = opened
        self.released = False

    def isOpened(self):
        return self.opened

    def read(self):
        return True, self.frame.copy()

    def set(self, *args, **kwargs):
        return True

    def release(self):
        self.released = True


# -------------------------------------------------------------------- registry
def test_sync_from_config_seeds_a_default_camera():
    cameras = sync_from_config(sources=["0"])

    assert len(cameras) == 1
    assert cameras[0].enabled is True
    assert cameras[0].source == "0"
    assert cameras[0].name == "Main camera"
    assert get_default_camera().id == cameras[0].id


def test_sync_from_config_is_idempotent():
    first = sync_from_config(sources=["0"])
    second = sync_from_config(sources=["0"])

    assert [camera.id for camera in first] == [camera.id for camera in second]


def test_add_camera_deduplicates_by_source():
    first = add_camera("Front", "rtsp://example/1")
    second = add_camera("Front again", "rtsp://example/1")

    assert first.id == second.id
    assert len([c for c in list_cameras() if c.source == "rtsp://example/1"]) == 1


def test_add_camera_requires_a_source():
    with pytest.raises(ValueError):
        add_camera("Broken", "   ")


def test_disable_and_delete_camera():
    camera = add_camera("Back", "rtsp://example/2")
    assert set_camera_enabled(camera.id, False) is True

    assert get_camera(camera.id).enabled is False
    assert all(item.id != camera.id for item in list_cameras())  # enabled-only listing

    assert delete_camera(camera.id) is True
    assert get_camera(camera.id) is None
    assert delete_camera(camera.id) is False


def test_parse_sources_accepts_lists_and_separators():
    assert parse_sources("0, 1") == ["0", "1"]
    assert parse_sources("rtsp://a;rtsp://b") == ["rtsp://a", "rtsp://b"]
    assert parse_sources("0\n1\n") == ["0", "1"]
    assert parse_sources("") == []
    assert parse_sources(None) == []


# ------------------------------------------------------------- streaming logic
def test_two_cameras_can_stream_at_the_same_time(monkeypatch):
    second = add_camera("Second", "1")
    monkeypatch.setattr(camera_service, "open_camera", lambda source=None: FakeCapture())

    first_stream = camera_service.start_stream(camera_id=1)
    second_stream = camera_service.start_stream(camera_id=second.id)
    try:
        assert camera_service.is_stream_active(1) is True
        assert camera_service.is_stream_active(second.id) is True
        assert camera_service.active_camera_ids() == [1, second.id]

        with pytest.raises(camera_service.StreamBusy):
            camera_service.start_stream(camera_id=1)
    finally:
        first_stream.close()
        second_stream.close()

    assert camera_service.is_stream_active() is False


def test_stop_stream_targets_one_camera(monkeypatch):
    second = add_camera("Second", "1")
    monkeypatch.setattr(camera_service, "open_camera", lambda source=None: FakeCapture())

    first_stream = camera_service.start_stream(camera_id=1)
    second_stream = camera_service.start_stream(camera_id=second.id)

    assert camera_service.stop_stream(second.id) == 1
    assert camera_service.is_stream_active(second.id) is False
    assert camera_service.is_stream_active(1) is True

    assert camera_service.stop_stream() == 1
    assert camera_service.is_stream_active() is False
    assert first_stream.closed is True


def test_start_stream_rejects_disabled_camera(monkeypatch):
    camera = add_camera("Disabled", "9")
    set_camera_enabled(camera.id, False)
    monkeypatch.setattr(camera_service, "open_camera", lambda source=None: FakeCapture())

    with pytest.raises(camera_service.CameraUnavailable):
        camera_service.start_stream(camera_id=camera.id)


def test_start_stream_without_any_camera_reports_clearly(monkeypatch):
    import database.db as db
    from services import camera_registry

    connection = db.get_db_connection()
    connection.execute("DELETE FROM cameras")
    connection.commit()
    connection.close()

    monkeypatch.setattr(camera_registry, "configured_sources", lambda: [])
    monkeypatch.setattr(camera_service, "sync_from_config", lambda *a, **k: [])

    with pytest.raises(camera_service.CameraUnavailable):
        camera_service.start_stream()


# ------------------------------------------------------------------ HTTP layer
def test_camera_listing_endpoint(client):
    payload = client.get("/api/cameras").json

    assert len(payload["cameras"]) == 1
    camera = payload["cameras"][0]
    assert camera["source"] == "0"
    assert camera["enabled"] is True
    assert camera["status"] in {"unknown", "offline", "online"}
    assert camera["stream_active"] is False


def test_camera_create_update_and_delete(client):
    created = client.post("/api/cameras", json={"name": "Roof", "source": "rtsp://cam/roof"})
    assert created.status_code == 201
    camera_id = created.json["camera"]["id"]

    assert client.post("/api/cameras", json={"name": "x"}).status_code == 400

    updated = client.patch(f"/api/cameras/{camera_id}", json={"enabled": False})
    assert updated.status_code == 200
    assert updated.json["camera"]["enabled"] is False

    deleted = client.delete(f"/api/cameras/{camera_id}")
    assert deleted.status_code == 200
    assert client.delete(f"/api/cameras/{camera_id}").status_code == 404


def test_camera_cannot_be_deleted_while_streaming(client):
    class BusyStream:
        camera_id = 1
        closed = False

    camera_service._active_streams[1] = BusyStream()
    try:
        response = client.delete("/api/cameras/1")
        assert response.status_code == 409
        assert "Stop the stream" in response.json["error"]
    finally:
        camera_service._active_streams.clear()


def test_status_exposes_camera_list(client):
    payload = client.get("/api/status").json

    assert isinstance(payload["cameras"], list)
    assert payload["cameras"][0]["id"] == 1
    assert payload["active_streams"] == 0


def test_probe_unknown_camera_returns_404(client):
    assert client.get("/api/camera/probe?camera_id=424242").status_code == 404
