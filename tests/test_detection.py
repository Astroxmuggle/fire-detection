"""Unit tests for the detection, confirmation, evidence and alert layers."""

from __future__ import annotations

import numpy as np
import pytest

from alerts.manager import (
    AlertManager,
    acknowledge_alert,
    acknowledge_alerts_for_event,
    get_alerts_for_event,
)
from config import Config
from detection.confirmation import ConfirmationTracker
from detection.frame_guard import frame_detail_score, is_informative_frame
from detection.manager import DetectionManager
from detection.postprocess import filter_detections, non_max_suppression
from services.camera_service import CameraUnavailable, start_stream, stop_stream
from services.event_service import create_confirmed_event, get_event_by_id
from services.evidence_service import resolve_evidence_path, save_evidence_frame


def fire(confidence=0.9, box=(0, 0, 40, 40)):
    return {"class_name": "fire", "confidence": confidence, "bbox": list(box)}


def smoke(confidence=0.8, box=(100, 100, 160, 160)):
    return {"class_name": "smoke", "confidence": confidence, "bbox": list(box)}


# --------------------------------------------------------------- confirmation
def test_confirmation_requires_consecutive_frames():
    tracker = ConfirmationTracker(required_frames=2)
    assert tracker.update_frame([fire()]) == []
    assert len(tracker.update_frame([fire()])) == 1


def test_confirmation_latches_and_does_not_repeat():
    manager = DetectionManager(required_frames=2, release_frames=3, cooldown_seconds=0)
    results = [len(manager.process_detections([fire()])) for _ in range(5)]
    assert results == [0, 1, 0, 0, 0]


def test_fire_and_smoke_in_the_same_frame_both_confirm():
    """Regression: a shared counter used to make this case confirm *nothing*."""
    manager = DetectionManager(
        required_frames=2,
        release_frames=3,
        cooldown_seconds=0,
        class_thresholds={"fire": 0.5, "smoke": 0.5},
    )
    results = [len(manager.process_detections([fire(), smoke()])) for _ in range(3)]
    assert results == [0, 2, 0]
    assert manager.confirmation.confirmed_classes == {"fire", "smoke"}


def test_confirmation_rearms_after_release_frames():
    manager = DetectionManager(required_frames=2, release_frames=3, cooldown_seconds=0)
    results = []
    results += [len(manager.process_detections([fire()])) for _ in range(2)]
    results += [len(manager.process_detections([])) for _ in range(3)]
    results += [len(manager.process_detections([fire()])) for _ in range(2)]
    assert results == [0, 1, 0, 0, 0, 0, 1]


def test_confirmation_cooldown_blocks_rapid_reconfirm():
    manager = DetectionManager(required_frames=1, release_frames=1, cooldown_seconds=60)
    assert len(manager.process_detections([fire()], now=0)) == 1
    assert len(manager.process_detections([], now=1)) == 0
    assert len(manager.process_detections([fire()], now=2)) == 0
    assert len(manager.process_detections([fire()], now=61)) == 1


def test_confirmation_clears_after_empty_frame():
    manager = DetectionManager(required_frames=2)
    detection = fire()

    assert manager.process_detections([detection]) == []
    assert manager.process_detections([]) == []
    assert manager.process_detections([detection]) == []
    assert len(manager.process_detections([detection])) == 1


def test_confirmation_accepts_model_bbox_shape_and_class_id():
    manager = DetectionManager(required_frames=1, class_thresholds={"fire": 0.5})
    confirmed = manager.process_detections([
        {"class_id": 0, "confidence": 0.92, "bbox": [[1, 1, 11, 11]]}
    ])
    assert len(confirmed) == 1
    assert confirmed[0]["class_name"] == "fire"
    assert confirmed[0]["bbox"] == [1.0, 1.0, 11.0, 11.0]


# ------------------------------------------------------------------ filtering
def test_filter_detections_keeps_high_confidence_items_only():
    detections = [
        {"class_id": 0, "confidence": 0.95, "bbox": [0, 0, 10, 10]},
        {"class_id": 1, "confidence": 0.60, "bbox": [20, 20, 40, 40]},
        {"class_id": 0, "confidence": 0.35, "bbox": [50, 50, 60, 60]},
    ]
    filtered = filter_detections(detections, 0.5)
    assert len(filtered) == 2
    assert all(item["confidence"] >= 0.5 for item in filtered)


def test_filter_detections_honours_per_class_thresholds():
    detections = [
        {"class_name": "fire", "confidence": 0.52, "bbox": [0, 0, 10, 10]},
        {"class_name": "smoke", "confidence": 0.52, "bbox": [20, 20, 40, 40]},
    ]
    filtered = filter_detections(detections, 0.5, {"fire": 0.50, "smoke": 0.60})
    assert [item["class_name"] for item in filtered] == ["fire"]


def test_non_max_suppression_returns_reduced_detections():
    detections = [
        {"class_id": 0, "confidence": 0.95, "bbox": [[0, 0, 10, 10]]},
        {"class_id": 0, "confidence": 0.92, "bbox": [[1, 1, 11, 11]]},
        {"class_id": 1, "confidence": 0.40, "bbox": [[50, 50, 80, 80]]},
    ]
    reduced = non_max_suppression(detections, iou_threshold=0.5)
    assert isinstance(reduced, list)
    assert len(reduced) == 2
    assert reduced[0]["confidence"] == 0.95


def test_non_max_suppression_skips_detections_without_a_box():
    detections = [
        {"class_name": "fire", "confidence": 0.9, "bbox": None},
        {"class_name": "fire", "confidence": 0.8, "bbox": [0, 0, 20, 20]},
    ]
    assert len(non_max_suppression(detections, 0.4)) == 1


def test_manager_rejects_boxes_below_the_minimum_area():
    manager = DetectionManager(
        required_frames=1,
        min_box_area_ratio=0.001,
        max_box_area_ratio=0.92,
    )
    frame_shape = (480, 640, 3)
    assert manager.process_detections([fire(box=(0, 0, 1, 1))], frame_shape=frame_shape) == []
    assert len(manager.process_detections([fire(box=(0, 0, 100, 100))], frame_shape=frame_shape)) == 1


def test_manager_rejects_full_frame_boxes():
    manager = DetectionManager(required_frames=1, max_box_area_ratio=0.92)
    frame_shape = (480, 640, 3)
    assert manager.process_detections([fire(box=(0, 0, 640, 480))], frame_shape=frame_shape) == []


# ---------------------------------------------------------------- frame guard
def test_frame_guard_rejects_blank_frames():
    for value in (5, 128, 200, 245):
        blank = np.full((480, 640, 3), value, dtype=np.uint8)
        assert is_informative_frame(blank, Config.MIN_FRAME_STD) is False
        assert frame_detail_score(blank) == pytest.approx(0.0)


def test_frame_guard_accepts_detailed_frames():
    rng = np.random.default_rng(1234)
    noisy = rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)
    assert is_informative_frame(noisy, Config.MIN_FRAME_STD) is True


# -------------------------------------------------------------------- evidence
def test_save_evidence_frame_writes_jpeg(temp_dir):
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    output = save_evidence_frame(frame, "fire", "camera:0", output_dir=temp_dir)

    assert output.exists()
    assert output.suffix.lower() == ".jpg"
    assert ":" not in output.name
    assert output.read_bytes()[:2] == b"\xff\xd8"


def test_save_evidence_frame_uses_configured_directory():
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    output = save_evidence_frame(frame, "smoke", "camera:1")
    assert output.parent == Config.EVIDENCE_DIR
    assert output.exists()


def test_resolve_evidence_path_rejects_traversal(temp_dir):
    inside = temp_dir / "ok.jpg"
    inside.write_bytes(b"\xff\xd8data")
    outside = temp_dir.parent / "outside.jpg"
    outside.write_bytes(b"\xff\xd8data")

    assert resolve_evidence_path(inside, base_dir=temp_dir) == inside.resolve()
    assert resolve_evidence_path(outside, base_dir=temp_dir) is None
    assert resolve_evidence_path(None, base_dir=temp_dir) is None
    assert resolve_evidence_path("C:\\Windows\\win.ini", base_dir=temp_dir) is None


# ---------------------------------------------------------------------- events
def test_create_confirmed_event_persists_record_snapshot_and_alert():
    frame = np.zeros((80, 80, 3), dtype=np.uint8)
    event_id = create_confirmed_event(
        class_name="fire",
        confidence=0.94,
        camera_source="webcam",
        frame=frame,
        alert_status="confirmed",
    )

    event = get_event_by_id(event_id)
    assert event["alert_status"] == "confirmed"
    assert event["class_name"] == "fire"
    assert event["snapshot_path"] is not None
    assert str(Config.EVIDENCE_DIR) in event["snapshot_path"]

    alerts = get_alerts_for_event(event_id)
    assert len(alerts) == 1
    assert alerts[0]["alert_level"] == "fire"
    assert alerts[0]["acknowledged"] == 0


def test_acknowledge_alerts_for_event_marks_them_acknowledged():
    frame = np.zeros((40, 40, 3), dtype=np.uint8)
    event_id = create_confirmed_event("smoke", 0.88, "camera:2", frame=frame)

    assert acknowledge_alerts_for_event(event_id) == 1
    alerts = get_alerts_for_event(event_id)
    assert alerts[0]["acknowledged"] == 1


def test_acknowledge_alert_returns_false_for_unknown_id():
    assert acknowledge_alert(987654) is False


# ---------------------------------------------------------------------- alerts
def test_alert_manager_enforces_cooldown():
    manager = AlertManager(alert_cooldown=60, sound_enabled=False)
    assert manager.trigger_alert("fire") is True
    assert manager.trigger_alert("fire") is False
    assert manager.notify("fire") is False


def test_alert_manager_records_every_event_even_within_cooldown():
    manager = AlertManager(alert_cooldown=60, sound_enabled=False)
    first = manager.create_alert(event_id=1, alert_level="fire")
    second = manager.create_alert(event_id=2, alert_level="fire")
    assert first["event_id"] == 1
    assert second["event_id"] == 2
    assert second["status"] == "pending"


def test_alert_sound_is_skipped_when_disabled():
    manager = AlertManager(alert_cooldown=0, sound_enabled=False)
    assert manager.play_sound("fire") is False


# ---------------------------------------------------------------------- camera
def test_parse_camera_source_accepts_index_url_and_path():
    from services.camera_service import parse_camera_source

    assert parse_camera_source(1) == 1
    assert parse_camera_source("0") == 0
    assert parse_camera_source("rtsp://user:pass@host:554/stream") == "rtsp://user:pass@host:554/stream"
    assert parse_camera_source("C:/clips/fire.mp4") == "C:/clips/fire.mp4"


def test_start_stream_fails_fast_when_model_is_missing(temp_dir):
    with pytest.raises(FileNotFoundError):
        start_stream(model_path=str(temp_dir / "missing.pt"))
    stop_stream()


def test_start_stream_fails_fast_when_camera_is_unavailable(monkeypatch):
    import services.camera_service as camera_service

    monkeypatch.setattr(
        camera_service,
        "open_camera",
        lambda source=None: (_ for _ in ()).throw(CameraUnavailable("no device")),
    )
    with pytest.raises(CameraUnavailable):
        start_stream()
    stop_stream()


# ---------------------------------------------------------------- evaluation
def test_evaluation_service_computes_precision_recall_and_f1():
    from services.evaluation_service import compute_precision_recall_f1, summarize_predictions

    result = compute_precision_recall_f1(true_positives=8, false_positives=2, false_negatives=4)

    assert result["precision"] == pytest.approx(0.8)
    assert result["recall"] == pytest.approx(8 / 12)
    assert 0.0 < result["f1_score"] <= 1.0

    empty = compute_precision_recall_f1(0, 0, 0)
    assert empty["precision"] == 0.0 and empty["recall"] == 0.0 and empty["f1_score"] == 0.0

    summary = summarize_predictions([
        {"class_name": "Fire", "confidence": 0.91},
        {"class_name": "smoke", "confidence": 0.40},
    ])
    assert summary["total_predictions"] == 2
    assert summary["high_confidence_predictions"] == 1
    assert summary["by_class"] == {"fire": 1, "smoke": 1}
