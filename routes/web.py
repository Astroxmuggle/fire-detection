"""HTML pages and the MJPEG stream."""

from __future__ import annotations

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from alerts.manager import acknowledge_alerts_for_event, get_alerts_for_event
from services.camera_service import CameraError, StreamBusy, start_stream
from services.event_service import get_event_by_id, get_events
from services.evidence_service import resolve_evidence_path

web_bp = Blueprint("web", __name__)


@web_bp.route("/")
@web_bp.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", page="dashboard")


@web_bp.route("/history")
def history():
    class_filter = request.args.get("class") or None
    events = get_events({"class": class_filter} if class_filter else {})
    return render_template(
        "history.html",
        page="history",
        events=events[:100],
        total=len(events),
        class_filter=class_filter,
    )


@web_bp.route("/video_feed")
def video_feed():
    """Start the capture session and stream it as multipart JPEG."""
    try:
        stream = start_stream()
    except StreamBusy as exc:
        return jsonify({"error": str(exc), "hint": "Stop the other viewer first."}), 409
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc), "hint": "Train or copy a model into models/best.pt."}), 503
    except CameraError as exc:
        return jsonify({"error": str(exc), "hint": "Check the camera source in .env."}), 503
    except Exception as exc:  # noqa: BLE001 - never leak a stack trace to the page
        return jsonify({"error": str(exc)}), 503

    return Response(
        stream.frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@web_bp.route("/events")
def events():
    """Kept for backwards compatibility with the original JSON endpoint."""
    return jsonify(get_events({}))


@web_bp.route("/incident/<int:event_id>")
def incident_detail(event_id):
    incident = get_event_by_id(event_id)
    if incident is None:
        abort(404)
    return render_template(
        "incident_detail.html",
        page="history",
        incident=incident,
        alerts=get_alerts_for_event(event_id),
    )


@web_bp.route("/incident/<int:event_id>/acknowledge", methods=["POST"])
def incident_acknowledge(event_id):
    if get_event_by_id(event_id) is None:
        abort(404)
    updated = acknowledge_alerts_for_event(event_id)
    flash(
        f"Acknowledged {updated} alert(s)." if updated else "No pending alerts for this incident.",
        "success" if updated else "info",
    )
    return redirect(url_for("web.incident_detail", event_id=event_id))


@web_bp.route("/evidence/<int:event_id>")
def evidence(event_id):
    incident = get_event_by_id(event_id)
    if incident is None:
        abort(404)

    path = resolve_evidence_path(incident.get("snapshot_path"))
    if path is None:
        abort(404)

    return send_file(path, mimetype="image/jpeg", max_age=0)
