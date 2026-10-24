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
from services.camera_registry import get_camera, list_cameras
from services.camera_service import CameraError, StreamBusy, start_stream
from services.event_service import get_event_by_id, get_events, get_event_history
from services.evidence_service import resolve_evidence_path
from services.incident_service import (
    IncidentError,
    IncidentNotFound,
    InvalidTransition,
    acknowledge as acknowledge_incident,
    close as close_incident,
    get_incident,
    get_incident_for_event,
    get_incident_stats,
    get_transitions,
    list_incidents,
)
from services.serializers import serialize_event

web_bp = Blueprint("web", __name__)


@web_bp.route("/")
@web_bp.route("/dashboard")
def dashboard():
    return render_template(
        "dashboard.html",
        page="dashboard",
        cameras=list_cameras(include_disabled=True),
        incident_stats=get_incident_stats(),
        recent_events=get_event_history(limit=15),
    )


@web_bp.route("/history")
@web_bp.route("/incidents")
def history():
    view_mode = request.args.get("view", "incidents")  # "incidents" or "events"
    class_filter = request.args.get("class") or None
    camera_filter = request.args.get("camera") or None
    status_filter = request.args.get("status") or None
    search_query = (request.args.get("q") or "").strip() or None

    incident_stats = get_incident_stats()

    if view_mode == "events":
        filters = {}
        if class_filter:
            filters["class"] = class_filter
        if camera_filter:
            filters["camera_source"] = camera_filter
        if status_filter:
            filters["alert_status"] = status_filter
        raw_items = get_events(filters)
        if search_query:
            q = search_query.lower()
            raw_items = [
                e
                for e in raw_items
                if q in str(e.get("id"))
                or q in str(e.get("camera_source", "")).lower()
                or q in str(e.get("class_name", "")).lower()
            ]
        items = raw_items
        total = len(items)
    else:
        # Incident triage view (default)
        inc_filters = {}
        if status_filter and status_filter in ("open", "acknowledged", "closed"):
            inc_filters["status"] = status_filter
        if class_filter:
            inc_filters["class"] = class_filter
        raw_items = list_incidents(inc_filters)
        if camera_filter:
            raw_items = [
                i
                for i in raw_items
                if str(i.get("camera_source")) == camera_filter
                or str(i.get("camera_id")) == camera_filter
            ]
        if search_query:
            q = search_query.lower()
            raw_items = [
                i
                for i in raw_items
                if q in str(i.get("id"))
                or q in str(i.get("camera_source", "")).lower()
                or q in str(i.get("class_name", "")).lower()
                or q in str(i.get("close_reason", "")).lower()
                or q in str(i.get("notes", "")).lower()
            ]
        items = raw_items
        total = len(items)

    return render_template(
        "history.html",
        page="history",
        view_mode=view_mode,
        items=items[:100],
        total=total,
        incident_stats=incident_stats,
        class_filter=class_filter,
        camera_filter=camera_filter,
        status_filter=status_filter,
        search_query=search_query,
        cameras=list_cameras(include_disabled=True),
    )


@web_bp.route("/video_feed")
def video_feed():
    """Start a capture session for one camera and stream it as multipart JPEG."""
    camera_id = request.args.get("camera", type=int)
    takeover = request.args.get("takeover", "0").lower() in ("1", "true")
    if camera_id is not None and get_camera(camera_id) is None:
        return jsonify({"error": f"Camera {camera_id} not found"}), 404

    try:
        stream = start_stream(camera_id=camera_id, takeover=takeover)
    except StreamBusy as exc:
        return jsonify({"error": str(exc), "hint": "Stop the other viewer first."}), 409
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc), "hint": "Train or copy a model into models/best.pt."}), 503
    except CameraError as exc:
        return jsonify({"error": str(exc), "hint": "Check the camera source in .env or the camera registry."}), 503
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
    return jsonify([serialize_event(row) for row in get_events({})])


@web_bp.route("/incidents/<int:incident_id>")
def incident_workspace(incident_id):
    incident = get_incident(incident_id)
    if incident is None:
        abort(404)

    events = get_events({"incident_id": incident_id})
    transitions = get_transitions(incident_id)

    evidence_event_id = incident.get("evidence_event_id") or (events[0]["id"] if events else None)
    evidence_path = None
    if evidence_event_id:
        ev_row = get_event_by_id(evidence_event_id)
        if ev_row:
            evidence_path = resolve_evidence_path(ev_row.get("snapshot_path"))

    alerts = []
    for ev in events:
        alerts.extend(get_alerts_for_event(ev["id"]))

    return render_template(
        "incident_detail.html",
        page="history",
        incident=incident,
        events=events,
        transitions=transitions,
        evidence_event_id=evidence_event_id,
        has_evidence=evidence_path is not None,
        alerts=alerts,
        is_incident_model=True,
    )


@web_bp.route("/incident/<int:event_id>")
def incident_detail(event_id):
    event = get_event_by_id(event_id)
    if event is None:
        abort(404)

    lifecycle = get_incident_for_event(event_id)
    evidence_path = resolve_evidence_path(event.get("snapshot_path"))

    if lifecycle:
        events = get_events({"incident_id": lifecycle["id"]})
        transitions = get_transitions(lifecycle["id"])
        evidence_event_id = lifecycle.get("evidence_event_id") or event_id
        if evidence_event_id and evidence_event_id != event_id:
            ev_row = get_event_by_id(evidence_event_id)
            if ev_row:
                evidence_path = resolve_evidence_path(ev_row.get("snapshot_path"))

        alerts = []
        for ev in events:
            alerts.extend(get_alerts_for_event(ev["id"]))

        return render_template(
            "incident_detail.html",
            page="history",
            incident=lifecycle,
            events=events,
            transitions=transitions,
            evidence_event_id=evidence_event_id,
            has_evidence=evidence_path is not None,
            alerts=alerts,
            is_incident_model=True,
        )

    return render_template(
        "incident_detail.html",
        page="history",
        incident=event,
        events=[event],
        transitions=[],
        evidence_event_id=event_id,
        has_evidence=evidence_path is not None,
        alerts=get_alerts_for_event(event_id),
        is_incident_model=False,
    )


@web_bp.route("/incidents/<int:incident_id>/acknowledge", methods=["POST"])
def incident_acknowledge_lifecycle(incident_id):
    try:
        result = acknowledge_incident(incident_id, actor="operator")
    except IncidentNotFound:
        abort(404)
    except InvalidTransition as exc:
        flash(str(exc), "info")
    else:
        flash(
            "Incident acknowledged." if result.get("changed") else "Incident was already acknowledged.",
            "success",
        )

    try:
        from services.event_bus import publish
        from services.serializers import serialize_incident
        if result:
            publish("incident", serialize_incident(result))
    except Exception:
        pass

    return redirect(url_for("web.incident_workspace", incident_id=incident_id))


@web_bp.route("/incidents/<int:incident_id>/close", methods=["POST"])
def incident_close_lifecycle(incident_id):
    reason = request.form.get("reason") or "resolved"
    note = request.form.get("note") or None

    try:
        result = close_incident(incident_id, reason=reason, actor="operator", note=note)
    except IncidentNotFound:
        abort(404)
    except InvalidTransition as exc:
        flash(str(exc), "info")
    except IncidentError as exc:
        flash(str(exc), "info")
    else:
        flash(
            f"Incident #{incident_id} closed as {reason}." if result.get("changed") else "Incident was already closed.",
            "success",
        )

    try:
        from services.event_bus import publish
        from services.serializers import serialize_incident
        if result:
            publish("incident", serialize_incident(result))
    except Exception:
        pass

    return redirect(url_for("web.incident_workspace", incident_id=incident_id))


@web_bp.route("/incident/<int:event_id>/acknowledge", methods=["POST"])
def incident_acknowledge(event_id):
    if get_event_by_id(event_id) is None:
        abort(404)
    updated = acknowledge_alerts_for_event(event_id)
    lifecycle = get_incident_for_event(event_id)
    if lifecycle and lifecycle["status"] == "open":
        try:
            acknowledge_incident(lifecycle["id"], actor="operator")
        except Exception:
            pass

    flash(
        f"Acknowledged {updated} alert(s)." if updated else "No pending alerts for this incident.",
        "success" if updated else "info",
    )
    return redirect(url_for("web.incident_detail", event_id=event_id))


@web_bp.route("/evidence/<int:event_id>")
def evidence(event_id):
    event = get_event_by_id(event_id)
    if event is None:
        abort(404)

    path = resolve_evidence_path(event.get("snapshot_path"))
    if path is None:
        abort(404)

    return send_file(path, mimetype="image/jpeg", max_age=0)
