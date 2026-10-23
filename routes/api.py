"""JSON API."""

from __future__ import annotations

import cv2

from flask import Blueprint, jsonify, request

from alerts.manager import acknowledge_alert, get_alerts
from config import Config
from services.camera_service import (
    CameraError,
    open_camera,
    parse_camera_source,
    stop_stream,
)
from services.event_service import get_event_by_id, get_event_stats, get_events, reset_alert_manager
from services.metrics_service import get_metrics
from services.status_service import get_runtime_status

api_bp = Blueprint("api", __name__)


@api_bp.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "service": Config.APP_NAME, "version": Config.VERSION}), 200


@api_bp.route("/status", methods=["GET"])
def status():
    runtime = get_runtime_status().snapshot()
    stats = get_event_stats()
    alerts = get_alerts(limit=200)

    return jsonify({
        "status": "running",
        "app": Config.APP_NAME,
        "version": Config.VERSION,
        "camera_status": runtime["camera_status"],
        "camera_source": runtime["camera_source"] or str(parse_camera_source()),
        "camera_error": runtime["camera_error"],
        "model_status": "loaded" if runtime["model_loaded"] else "not loaded",
        "model_path": runtime["model_path"],
        "model_classes": runtime["model_classes"],
        "stream_active": runtime["stream_active"],
        "frames_processed": runtime["frames_processed"],
        "frames_skipped": runtime["frames_skipped"],
        "uptime_seconds": runtime["uptime_seconds"],
        "detection_count": stats["detection_count"],
        "confirmed_incidents": stats["confirmed_incidents"],
        "pending_incidents": stats["pending_incidents"],
        "by_class": stats["by_class"],
        "alert_count": len(alerts),
        "pending_alerts": sum(1 for item in alerts if not item.get("acknowledged")),
    }), 200


@api_bp.route("/events", methods=["GET"])
def events():
    filters = request.args.to_dict()
    return jsonify(get_events(filters)), 200


@api_bp.route("/events/<int:event_id>", methods=["GET"])
def event_detail(event_id):
    event_data = get_event_by_id(event_id)
    if event_data:
        return jsonify(event_data), 200
    return jsonify({"error": "Event not found"}), 404


@api_bp.route("/alerts", methods=["GET"])
def alerts():
    return jsonify({"alerts": get_alerts()}), 200


@api_bp.route("/alerts/<int:alert_id>/acknowledge", methods=["POST"])
def acknowledge_alert_route(alert_id):
    if acknowledge_alert(alert_id):
        return jsonify({"message": "Alert acknowledged", "alert_id": alert_id}), 200
    return jsonify({"error": "Alert not found"}), 404


@api_bp.route("/settings", methods=["GET"])
def settings():
    return jsonify({
        "settings": {
            "confidence_threshold": Config.CONFIDENCE_THRESHOLD,
            "fire_confidence_threshold": Config.FIRE_CONFIDENCE_THRESHOLD,
            "smoke_confidence_threshold": Config.SMOKE_CONFIDENCE_THRESHOLD,
            "alert_cooldown": Config.ALERT_COOLDOWN,
            "confirmation_frames": Config.CONFIRMATION_FRAMES,
            "confirmation_release_frames": Config.CONFIRMATION_RELEASE_FRAMES,
            "camera_source": str(parse_camera_source()),
            "frame_width": Config.FRAME_WIDTH,
            "frame_height": Config.FRAME_HEIGHT,
            "model_path": Config.MODEL_PATH,
        }
    }), 200


@api_bp.route("/settings", methods=["PUT"])
def update_settings():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON payload required"}), 400

    casts = {
        "confidence_threshold": float,
        "fire_confidence_threshold": float,
        "smoke_confidence_threshold": float,
        "alert_cooldown": int,
        "confirmation_frames": int,
        "confirmation_release_frames": int,
        "frame_width": int,
        "frame_height": int,
    }
    attributes = {
        "confidence_threshold": "CONFIDENCE_THRESHOLD",
        "fire_confidence_threshold": "FIRE_CONFIDENCE_THRESHOLD",
        "smoke_confidence_threshold": "SMOKE_CONFIDENCE_THRESHOLD",
        "alert_cooldown": "ALERT_COOLDOWN",
        "confirmation_frames": "CONFIRMATION_FRAMES",
        "confirmation_release_frames": "CONFIRMATION_RELEASE_FRAMES",
        "frame_width": "FRAME_WIDTH",
        "frame_height": "FRAME_HEIGHT",
    }

    applied = {}
    for key, cast in casts.items():
        if key not in payload:
            continue
        try:
            value = cast(payload[key])
        except (TypeError, ValueError):
            return jsonify({"error": f"Invalid value for {key}"}), 400
        if cast is float and not 0.0 <= value <= 1.0:
            return jsonify({"error": f"{key} must be between 0.0 and 1.0"}), 400
        if cast is int and value <= 0:
            return jsonify({"error": f"{key} must be a positive integer"}), 400

        setattr(Config, attributes[key], value)
        applied[key] = value

    if "alert_cooldown" in applied:
        reset_alert_manager()

    return jsonify({
        "settings": {
            "confidence_threshold": Config.CONFIDENCE_THRESHOLD,
            "alert_cooldown": Config.ALERT_COOLDOWN,
            "confirmation_frames": Config.CONFIRMATION_FRAMES,
            "camera_source": str(parse_camera_source()),
        },
        "applied": applied,
        "message": "Settings updated for new capture sessions",
    }), 200


@api_bp.route("/metrics", methods=["GET"])
def metrics():
    return jsonify(get_metrics()), 200


@api_bp.route("/stream/stop", methods=["POST"])
def stream_stop():
    stopped = stop_stream()
    return jsonify({"stopped": stopped, "stream_active": False}), 200


@api_bp.route("/camera/probe", methods=["GET"])
def camera_probe():
    """Try to open the configured source once and report the result."""
    source = request.args.get("source", None)
    camera = None
    try:
        camera = open_camera(source)
        ok, frame = camera.read()
        if not ok or frame is None:
            return jsonify({
                "camera_status": "offline",
                "source": str(parse_camera_source(source)),
                "error": "Source opened but no frame was returned",
            }), 200

        height, width = frame.shape[:2]
        return jsonify({
            "camera_status": "online",
            "source": str(parse_camera_source(source)),
            "resolution": f"{width}x{height}",
        }), 200
    except CameraError as exc:
        return jsonify({
            "camera_status": "offline",
            "source": str(parse_camera_source(source)),
            "error": str(exc),
        }), 200
    finally:
        if camera is not None:
            camera.release()
