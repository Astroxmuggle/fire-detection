/* FireWatch AI dashboard behaviour. No framework, no build step. */

const REFRESH_MS = 5000;
const MAX_EVENTS = 8;

function el(tag, options = {}, children = []) {
    const node = document.createElement(tag);
    if (options.className) node.className = options.className;
    if (options.text !== undefined) node.textContent = options.text;
    Object.entries(options.attrs || {}).forEach(([key, value]) => {
        node.setAttribute(key, value);
    });
    children.forEach((child) => child && node.appendChild(child));
    return node;
}

function setBadge(id, text, variant) {
    const badge = document.getElementById(id);
    if (!badge) return;
    badge.textContent = text;
    badge.className = `badge ${variant}`;
}

function formatTime(value) {
    if (!value) return "—";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString();
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, { cache: "no-store", ...options });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(payload.error || `Request failed (${response.status})`);
    }
    return payload;
}

function confidenceCell(confidence) {
    const value = Number(confidence) || 0;
    const fill = el("span", { className: "fill" });
    fill.style.width = `${Math.max(0, Math.min(1, value)) * 100}%`;
    return el("div", { className: "confidence-bar" }, [
        el("span", { className: "track" }, [fill]),
        el("span", { text: value.toFixed(3) }),
    ]);
}

async function refreshStatus() {
    const status = await fetchJson("/api/status");

    const cameraVariant = status.camera_status === "online" ? "online"
        : status.camera_status === "offline" ? "offline" : "unknown";
    setBadge("camera-badge", `Camera: ${status.camera_status}`, cameraVariant);
    setBadge(
        "model-badge",
        `Model: ${status.model_status}`,
        status.model_status === "loaded" ? "online" : "unknown",
    );
    setBadge(
        "stream-badge",
        `Stream: ${status.stream_active ? "live" : "idle"}`,
        status.stream_active ? "online" : "muted",
    );

    document.getElementById("stat-detections").textContent = status.detection_count ?? 0;
    document.getElementById("stat-confirmed").textContent = status.confirmed_incidents ?? 0;
    document.getElementById("stat-alerts").textContent = status.pending_alerts ?? 0;
    document.getElementById("stat-frames").textContent = status.frames_processed ?? 0;
    document.getElementById("stat-skipped").textContent = status.frames_skipped ?? 0;
    document.getElementById("last-updated").textContent = new Date().toLocaleTimeString();

    if (status.camera_status === "offline" && status.camera_error) {
        showOverlay("Camera unavailable", status.camera_error);
    }
}

async function refreshAlerts() {
    const payload = await fetchJson("/api/alerts");
    const list = document.getElementById("alert-list");
    list.replaceChildren();

    if (!payload.alerts || payload.alerts.length === 0) {
        list.appendChild(el("li", { className: "empty", text: "No alerts recorded yet" }));
        return;
    }

    payload.alerts.slice(0, 6).forEach((alert) => {
        const badge = el("span", {
            className: `badge ${alert.acknowledged ? "acknowledged" : "pending"}`,
            text: alert.acknowledged ? "acknowledged" : "pending",
        });
        list.appendChild(el("li", {}, [
            el("div", {}, [
                el("div", { text: `${alert.alert_level} · alert #${alert.id}` }),
                el("div", { className: "meta", text: formatTime(alert.created_at) }),
            ]),
            badge,
        ]));
    });
}

async function refreshEvents() {
    const events = await fetchJson("/api/events?limit=20");
    const body = document.getElementById("event-table-body");
    body.replaceChildren();

    if (!Array.isArray(events) || events.length === 0) {
        const cell = el("td", { className: "empty", text: "No incidents recorded yet" });
        cell.colSpan = 6;
        body.appendChild(el("tr", {}, [cell]));
        return;
    }

    events.slice(0, MAX_EVENTS).forEach((event) => {
        const link = el("a", {
            className: "btn small",
            text: "Open",
            attrs: { href: `/incident/${event.id}` },
        });
        body.appendChild(el("tr", {}, [
            el("td", { text: formatTime(event.created_at) }),
            el("td", {}, [el("span", { className: `badge ${event.class_name}`, text: event.class_name })]),
            el("td", {}, [confidenceCell(event.confidence)]),
            el("td", { text: event.camera_source }),
            el("td", {}, [el("span", {
                className: `badge ${event.alert_status === "pending" ? "pending" : "confirmed"}`,
                text: event.alert_status,
            })]),
            el("td", {}, [link]),
        ]));
    });
}

function showOverlay(title, message) {
    const overlay = document.getElementById("video-overlay");
    if (!overlay) return;
    overlay.querySelector("strong").textContent = title;
    document.getElementById("video-message").textContent = message;
    overlay.classList.add("visible");
}

function hideOverlay() {
    const overlay = document.getElementById("video-overlay");
    if (overlay) overlay.classList.remove("visible");
}

function wireStream() {
    const feed = document.getElementById("video-feed");
    const startButton = document.getElementById("btn-start");
    const stopButton = document.getElementById("btn-stop");
    if (!feed || !startButton || !stopButton) return;

    feed.addEventListener("error", async () => {
        let message = "Check /api/status for details.";
        try {
            const status = await fetchJson("/api/status");
            message = status.camera_error || `Camera is ${status.camera_status}.`;
        } catch (error) {
            /* keep the generic message */
        }
        showOverlay("Stream unavailable", message);
        setBadge("stream-badge", "Stream: idle", "muted");
    });

    startButton.addEventListener("click", () => {
        hideOverlay();
        feed.src = `/video_feed?_=${Date.now()}`;
        setBadge("stream-badge", "Stream: starting", "unknown");
    });

    stopButton.addEventListener("click", async () => {
        feed.removeAttribute("src");
        try {
            await fetch("/api/stream/stop", { method: "POST" });
        } catch (error) {
            /* the capture may already be closed */
        }
        setBadge("stream-badge", "Stream: idle", "muted");
        showOverlay("Stream stopped", "Press start to reopen the capture device.");
    });
}

async function refreshAll() {
    const tasks = [refreshStatus(), refreshAlerts(), refreshEvents()];
    const results = await Promise.allSettled(tasks);
    const failure = results.find((result) => result.status === "rejected");
    if (failure) {
        console.error(failure.reason);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    wireStream();
    refreshAll();
    window.setInterval(refreshAll, REFRESH_MS);
});
