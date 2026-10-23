/* ==========================================================================
   VERDANT FIRE — Command Center Application Logic
   Vanilla JavaScript • Zero External Dependencies • Real-Time SSE
   ========================================================================== */

const REFRESH_MS = 5000;
const MAX_EVENTS = 10;
let lastSyncTimestamp = Date.now();
let audioAlertsEnabled = localStorage.getItem("verdant_audio_enabled") !== "false";

/* --------------------------------------------------------------------------
   Utility DOM Helpers
   -------------------------------------------------------------------------- */
function el(tag, options = {}, children = []) {
    const node = document.createElement(tag);
    if (options.className) node.className = options.className;
    if (options.text !== undefined) node.textContent = options.text;
    if (options.html !== undefined) node.innerHTML = options.html;
    Object.entries(options.attrs || {}).forEach(([key, value]) => {
        node.setAttribute(key, value);
    });
    children.forEach((child) => child && node.appendChild(child));
    return node;
}

function formatRelativeTime(dateString) {
    if (!dateString) return "just now";
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) return dateString;
    const diffSec = Math.floor((Date.now() - date.getTime()) / 1000);
    if (diffSec < 5) return "just now";
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatTimestamp(value) {
    if (!value) return "--:--:--";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, { cache: "no-store", ...options });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(payload.error || `Request failed (${response.status})`);
    }
    return payload;
}

/* --------------------------------------------------------------------------
   Real-Time Operational Chronometer
   -------------------------------------------------------------------------- */
function updateClocks() {
    const now = new Date();
    const utcClock = document.getElementById("clock-utc");
    const localClock = document.getElementById("clock-local");
    const freshness = document.getElementById("sync-freshness");

    if (utcClock) {
        utcClock.textContent = now.toUTCString().split(" ")[4] || now.toISOString().substring(11, 19);
    }
    if (localClock) {
        localClock.textContent = now.toTimeString().split(" ")[0];
    }
    if (freshness) {
        const secAgo = Math.max(0, Math.floor((Date.now() - lastSyncTimestamp) / 1000));
        freshness.textContent = secAgo === 0 ? "Synced just now" : `Synced ${secAgo}s ago`;
    }
}

/* --------------------------------------------------------------------------
   Confidence Cell Renderer
   -------------------------------------------------------------------------- */
function renderConfidenceCell(confidence, className = "") {
    const val = Number(confidence) || 0;
    const pct = Math.max(0, Math.min(1, val)) * 100;
    const fill = el("span", { className: `fill ${className}` });
    fill.style.width = `${pct}%`;
    return el("div", { className: "confidence-bar" }, [
        el("span", { className: "track" }, [fill]),
        el("span", { className: "conf-text", text: val.toFixed(3) }),
    ]);
}

/* --------------------------------------------------------------------------
   Master Status Posture Indicator
   -------------------------------------------------------------------------- */
function updateSystemPosture(status, alerts) {
    const pill = document.getElementById("system-status-pill");
    if (!pill) return;

    const unackedAlerts = (alerts || []).filter((a) => !a.acknowledged);
    const hasHazard = unackedAlerts.length > 0 || (status.confirmed_incidents > 0 && status.pending_alerts > 0);

    if (hasHazard) {
        pill.className = "system-posture-badge danger";
        pill.querySelector(".posture-text").textContent = `▲ ACTIVE HAZARD (${unackedAlerts.length})`;
    } else if (status.stream_active || status.monitoring_active > 0) {
        pill.className = "system-posture-badge nominal";
        pill.querySelector(".posture-text").textContent = "● SYSTEM NOMINAL";
    } else {
        pill.className = "system-posture-badge idle";
        pill.querySelector(".posture-text").textContent = "◼ MONITORING IDLE";
    }
}

/* --------------------------------------------------------------------------
   Refresh Runtime Telemetry
   -------------------------------------------------------------------------- */
async function refreshStatus() {
    let status;
    try {
        status = await fetchJson("/api/status");
    } catch (err) {
        console.warn("Status fetch failed:", err);
        return;
    }

    lastSyncTimestamp = Date.now();

    // 1. Telemetry KPI Cards
    const cameras = status.cameras || [];
    const activeCameras = cameras.filter((c) => c.status === "online" || c.monitoring || c.stream_active).length;
    const totalCameras = cameras.length || 1;

    const statCamActive = document.getElementById("stat-cameras-active");
    const statCamTotal = document.getElementById("stat-cameras-total");
    if (statCamActive) statCamActive.textContent = activeCameras;
    if (statCamTotal) statCamTotal.textContent = `/ ${totalCameras} online`;

    const camBadge = document.getElementById("camera-badge");
    if (camBadge) {
        camBadge.textContent = `Camera: ${status.camera_status}`;
        camBadge.className = `telemetry-status-pill ${status.camera_status === "online" ? "online" : ""}`;
    }

    const streamBadge = document.getElementById("stream-badge");
    if (streamBadge) {
        streamBadge.textContent = `Stream: ${status.stream_active ? "active" : "idle"}`;
    }

    const workerStat = document.getElementById("stat-worker-status");
    if (workerStat) {
        const anyWorker = status.monitoring_active > 0;
        workerStat.textContent = anyWorker ? "active (monitoring)" : "idle";
    }

    // Inference KPI
    const statFrames = document.getElementById("stat-frames");
    const statSkipped = document.getElementById("stat-skipped");
    const modelBadge = document.getElementById("model-badge");
    if (statFrames) statFrames.textContent = status.frames_processed ?? 0;
    if (statSkipped) statSkipped.textContent = status.frames_skipped ?? 0;
    if (modelBadge) {
        modelBadge.textContent = `Model: ${status.model_status}`;
        modelBadge.className = `telemetry-status-pill ${status.model_status === "loaded" ? "online" : ""}`;
    }

    // Confirmed Incidents KPI
    const statConfirmed = document.getElementById("stat-confirmed");
    const statDetections = document.getElementById("stat-detections");
    const statFireCount = document.getElementById("stat-fire-count");
    const statSmokeCount = document.getElementById("stat-smoke-count");
    if (status.incidents) {
        if (statConfirmed) {
            const activeInc = (status.incidents.open || 0) + (status.incidents.acknowledged || 0);
            statConfirmed.textContent = activeInc;
        }
        if (statFireCount && statSmokeCount) {
            statFireCount.textContent = status.incidents.open || 0;
            statSmokeCount.textContent = status.incidents.acknowledged || 0;
        }
        const incMeta = document.getElementById("incident-meta-breakdown");
        if (incMeta) {
            incMeta.textContent = `${status.incidents.open || 0} Open • ${status.incidents.acknowledged || 0} Acked • ${status.incidents.closed || 0} Closed`;
        }
    } else {
        if (statConfirmed) statConfirmed.textContent = status.confirmed_incidents ?? 0;
        if (statFireCount) statFireCount.textContent = status.by_class?.fire ?? 0;
        if (statSmokeCount) statSmokeCount.textContent = status.by_class?.smoke ?? 0;
    }
    if (statDetections) statDetections.textContent = status.detection_count ?? 0;

    // Alerts KPI
    const statAlerts = document.getElementById("stat-alerts");
    const navAlertCount = document.getElementById("nav-alert-count");
    const queueCountBadge = document.getElementById("alert-queue-count");
    const pendingCount = status.pending_alerts ?? 0;
    if (statAlerts) statAlerts.textContent = pendingCount;
    if (navAlertCount) navAlertCount.textContent = pendingCount;
    if (queueCountBadge) queueCountBadge.textContent = pendingCount;

    // Last update
    const lastUpdated = document.getElementById("last-updated");
    if (lastUpdated) lastUpdated.textContent = new Date().toLocaleTimeString();

    // Footer Uptime
    const footerUptime = document.getElementById("footer-uptime");
    if (footerUptime && status.uptime_seconds !== undefined) {
        const hrs = Math.floor(status.uptime_seconds / 3600);
        const mins = Math.floor((status.uptime_seconds % 3600) / 60);
        footerUptime.textContent = `Uptime: ${hrs}h ${mins}m`;
    }

    // Topbar camera chip
    const camSummaryText = document.getElementById("camera-summary-text");
    const camSummaryDot = document.getElementById("camera-status-dot");
    if (camSummaryText) {
        camSummaryText.textContent = `Camera: ${status.camera_status} (${status.stream_active ? "Live" : "Idle"})`;
    }
    if (camSummaryDot) {
        camSummaryDot.className = `chip-dot ${status.camera_status === "online" ? "online" : "offline"}`;
    }

    // Active Camera In-Viewport HUD (Reference A)
    const hudCamName = document.getElementById("hud-cam-name");
    const hudCamSource = document.getElementById("hud-cam-source");
    const hudStreamState = document.getElementById("hud-stream-state");
    const hudStreamStateText = document.getElementById("hud-stream-state-text");
    const hudFreshness = document.getElementById("hud-frame-freshness");

    if (hudCamSource && status.camera_source) {
        hudCamSource.textContent = `SRC: ${status.camera_source}`;
    }

    if (hudStreamState && hudStreamStateText) {
        if (status.stream_active) {
            hudStreamState.className = "hud-status-badge live";
            hudStreamStateText.textContent = "● LIVE REC";
        } else if (status.monitoring_active > 0) {
            hudStreamState.className = "hud-status-badge live";
            hudStreamStateText.textContent = "● WORKER ACTIVE";
        } else if (status.camera_status === "offline") {
            hudStreamState.className = "hud-status-badge offline";
            hudStreamStateText.textContent = "OFFLINE";
        } else {
            hudStreamState.className = "hud-status-badge idle";
            hudStreamStateText.textContent = "STREAM IDLE";
        }
    }

    if (hudFreshness) {
        hudFreshness.textContent = status.stream_active ? "FRESHNESS: < 1s" : "FRESHNESS: --";
    }

    // Nav Stream Indicator
    const navStreamDot = document.getElementById("nav-stream-indicator");
    if (navStreamDot) {
        navStreamDot.className = `live-dot ${status.stream_active ? "active" : ""}`;
    }

    // Check camera errors
    if (status.camera_status === "offline" && status.camera_error) {
        showOverlay("Camera Disconnected / Offline", status.camera_error);
    }
}

/* --------------------------------------------------------------------------
   Refresh Recent Alerts Queue (Reference B)
   -------------------------------------------------------------------------- */
async function refreshAlerts() {
    const list = document.getElementById("alert-list");
    if (!list) return;

    let payload;
    try {
        payload = await fetchJson("/api/alerts");
    } catch (err) {
        return;
    }

    const alerts = payload.alerts || [];

    // Filter to latest 6 alerts
    list.replaceChildren();

    if (alerts.length === 0) {
        const emptyLi = el("li", { className: "alert-queue-empty" }, [
            el("div", { className: "empty-shield", text: "✓" }),
            el("strong", { text: "All Systems Nominal" }),
            el("span", { text: "No unacknowledged fire or smoke alerts" }),
        ]);
        list.appendChild(emptyLi);
        return;
    }

    alerts.slice(0, 8).forEach((alert) => {
        const isFire = alert.alert_level === "critical" || alert.alert_level === "fire";
        const isSmoke = alert.alert_level === "warning" || alert.alert_level === "smoke";
        const itemClass = isFire ? "fire" : isSmoke ? "smoke" : "";

        const headline = `${(alert.alert_level || "ALERT").toUpperCase()} — #${alert.id}`;
        const timeMeta = `${formatRelativeTime(alert.created_at)} • Event #${alert.event_id || "--"}`;

        const item = el("li", { className: `alert-queue-item ${itemClass}` }, [
            el("div", { className: "alert-info-left" }, [
                el("span", { className: "alert-headline", text: headline }),
                el("span", { className: "alert-meta-time", text: timeMeta }),
            ]),
            el("div", { className: "alert-action-right" }, [
                alert.acknowledged
                    ? el("span", { className: "badge acknowledged", text: "ACKNOWLEDGED" })
                    : el("button", {
                        className: "btn-micro",
                        text: "Ack",
                        attrs: { "data-alert-id": alert.id, title: "Acknowledge alert" },
                    }),
            ]),
        ]);

        const ackBtn = item.querySelector("button[data-alert-id]");
        if (ackBtn) {
            ackBtn.addEventListener("click", async (e) => {
                e.preventDefault();
                ackBtn.disabled = true;
                ackBtn.textContent = "...";
                try {
                    await fetchJson(`/api/alerts/${alert.id}/acknowledge`, { method: "POST" });
                    refreshAll();
                } catch (err) {
                    ackBtn.disabled = false;
                    ackBtn.textContent = "Retry";
                }
            });
        }

        list.appendChild(item);
    });

    // Update system posture with alerts info
    try {
        const status = await fetchJson("/api/status");
        updateSystemPosture(status, alerts);
    } catch (e) {
        /* ignore */
    }
}

/* --------------------------------------------------------------------------
   Refresh Latest Events Table (Reference B & D)
   -------------------------------------------------------------------------- */
async function refreshEvents() {
    const body = document.getElementById("event-table-body");
    if (!body) return;

    let events;
    try {
        events = await fetchJson("/api/events?limit=15");
    } catch (err) {
        return;
    }

    body.replaceChildren();

    if (!Array.isArray(events) || events.length === 0) {
        const cell = el("td", { className: "table-cell-empty", attrs: { colspan: "6" } }, [
            el("div", { className: "table-empty-box" }, [
                el("span", { className: "empty-icon", text: "🛡️" }),
                el("strong", { text: "No incidents recorded yet" }),
                el("p", { text: "Events will populate here automatically upon verified detection of fire or smoke." }),
            ]),
        ]);
        body.appendChild(el("tr", {}, [cell]));
        return;
    }

    // Update bottom detection HUD bar with sensor posture
    const latest = events[0];
    const hudBar = document.getElementById("hud-detection-bar");
    const hudTitle = document.getElementById("hud-detection-title");
    const hudSub = document.getElementById("hud-detection-sub");
    const hudIcon = document.getElementById("hud-detection-icon");
    const isStreamActive = document.getElementById("hud-stream-state")?.classList.contains("live");

    if (hudBar) {
        if (!isStreamActive) {
            hudBar.className = "hud-detection-readout idle";
            if (hudIcon) hudIcon.textContent = "⏸️";
            if (hudTitle) hudTitle.textContent = "SENSOR STANDBY";
            if (hudSub) hudSub.textContent = "Monitoring paused • Start feed to activate real-time detection";
        } else if (latest && (Date.now() - new Date(latest.created_at).getTime()) < 45000 && latest.alert_status === "confirmed") {
            hudBar.className = "hud-detection-readout hazard";
            if (hudIcon) hudIcon.textContent = "🔥";
            if (hudTitle) hudTitle.textContent = `▲ HAZARD DETECTED: ${latest.class_name.toUpperCase()}`;
            if (hudSub) hudSub.textContent = `Confidence: ${(Number(latest.confidence) * 100).toFixed(1)}% • Camera: ${latest.camera_source}`;
        } else {
            hudBar.className = "hud-detection-readout nominal";
            if (hudIcon) hudIcon.textContent = "🛡️";
            if (hudTitle) hudTitle.textContent = "STATUS: NOMINAL";
            if (hudSub) hudSub.textContent = "No active fire or smoke detected in monitored zone";
        }
    }

    events.slice(0, MAX_EVENTS).forEach((event) => {
        const link = el("a", {
            className: "btn small secondary",
            text: "Investigate →",
            attrs: { href: `/incident/${event.id}` },
        });

        const row = el("tr", { className: "incident-row" }, [
            el("td", { className: "col-time", text: formatRelativeTime(event.created_at) }),
            el("td", { className: "col-class" }, [
                el("span", { className: `badge ${event.class_name}`, text: event.class_name }),
            ]),
            el("td", { className: "col-conf" }, [
                renderConfidenceCell(event.confidence, event.class_name),
            ]),
            el("td", { className: "col-source" }, [
                el("span", { className: "camera-source-pill", text: event.camera_source }),
            ]),
            el("td", { className: "col-status" }, [
                el("span", {
                    className: `badge ${event.alert_status === "pending" ? "pending" : "confirmed"}`,
                    text: event.alert_status,
                }),
            ]),
            el("td", { className: "col-action" }, [link]),
        ]);

        body.appendChild(row);
    });
}

/* --------------------------------------------------------------------------
   Camera Viewport Overlays & Streaming Controls (Reference A)
   -------------------------------------------------------------------------- */
function showOverlay(title, message) {
    const overlay = document.getElementById("video-overlay");
    if (!overlay) return;
    const titleEl = overlay.querySelector(".overlay-title");
    const msgEl = document.getElementById("video-message");
    if (titleEl) titleEl.textContent = title;
    if (msgEl) msgEl.textContent = message;
    overlay.classList.add("visible");
}

function hideOverlay() {
    const overlay = document.getElementById("video-overlay");
    if (overlay) overlay.classList.remove("visible");
}

function getSelectedCameraId() {
    const select = document.getElementById("camera-select");
    return select && select.value ? select.value : "";
}

function wireStream() {
    const feed = document.getElementById("video-feed");
    const startBtn = document.getElementById("btn-start");
    const stopBtn = document.getElementById("btn-stop");
    const startOverlayBtn = document.getElementById("btn-start-overlay");
    const monitorBgBtn = document.getElementById("btn-monitor-bg-overlay");
    const workerToggleBtn = document.getElementById("btn-worker-toggle");
    const fullscreenBtn = document.getElementById("btn-fullscreen");
    const cameraSelect = document.getElementById("camera-select");

    const doStartStream = () => {
        hideOverlay();
        const cameraId = getSelectedCameraId();
        const suffix = cameraId ? `camera=${encodeURIComponent(cameraId)}&` : "";
        feed.src = `/video_feed?${suffix}_=${Date.now()}`;

        const hudState = document.getElementById("hud-stream-state");
        const hudText = document.getElementById("hud-stream-state-text");
        if (hudState && hudText) {
            hudState.className = "hud-status-badge connecting";
            hudText.textContent = "CONNECTING...";
        }

        const hudBar = document.getElementById("hud-detection-bar");
        const hudTitle = document.getElementById("hud-detection-title");
        const hudSub = document.getElementById("hud-detection-sub");
        const hudIcon = document.getElementById("hud-detection-icon");
        if (hudBar) {
            hudBar.className = "hud-detection-readout nominal";
            if (hudIcon) hudIcon.textContent = "🛡️";
            if (hudTitle) hudTitle.textContent = "OPTICAL SCANNING...";
            if (hudSub) hudSub.textContent = "Connecting to capture pipeline and initializing inference";
        }
    };

    const doStopStream = async () => {
        feed.removeAttribute("src");
        const cameraId = getSelectedCameraId();
        try {
            await fetchJson("/api/stream/stop", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(cameraId ? { camera_id: Number(cameraId) } : {}),
            });
        } catch (e) {
            /* capture may already be closed */
        }
        showOverlay("Stream stopped", "Press start to reopen capture pipeline and display live video.");
        const hudBar = document.getElementById("hud-detection-bar");
        const hudTitle = document.getElementById("hud-detection-title");
        const hudSub = document.getElementById("hud-detection-sub");
        const hudIcon = document.getElementById("hud-detection-icon");
        if (hudBar) {
            hudBar.className = "hud-detection-readout idle";
            if (hudIcon) hudIcon.textContent = "⏸️";
            if (hudTitle) hudTitle.textContent = "SENSOR STANDBY";
            if (hudSub) hudSub.textContent = "Monitoring paused • Start feed to activate real-time detection";
        }
        refreshStatus();
    };

    const doStartBgMonitoring = async () => {
        const cameraId = getSelectedCameraId() || 1;
        try {
            await fetchJson(`/api/cameras/${cameraId}/monitoring/start`, { method: "POST" });
            const workerBadge = document.getElementById("monitoring-worker-badge");
            if (workerBadge) workerBadge.textContent = "Worker: ACTIVE";
            refreshStatus();
        } catch (err) {
            alert(`Unable to start background worker: ${err.message}`);
        }
    };

    if (startBtn) startBtn.addEventListener("click", doStartStream);
    if (startOverlayBtn) startOverlayBtn.addEventListener("click", doStartStream);
    if (stopBtn) stopBtn.addEventListener("click", doStopStream);
    if (monitorBgBtn) monitorBgBtn.addEventListener("click", doStartBgMonitoring);
    if (workerToggleBtn) workerToggleBtn.addEventListener("click", doStartBgMonitoring);

    if (feed) {
        feed.addEventListener("load", () => {
            hideOverlay();
            const hudState = document.getElementById("hud-stream-state");
            const hudText = document.getElementById("hud-stream-state-text");
            if (hudState && hudText) {
                hudState.className = "hud-status-badge live";
                hudText.textContent = "● LIVE REC";
            }
        });

        feed.addEventListener("error", async () => {
            let message = "Check /api/status for operational details.";
            try {
                const status = await fetchJson("/api/status");
                message = status.camera_error || `Camera reported state '${status.camera_status}'.`;
            } catch (e) {
                /* fallback */
            }
            showOverlay("Capture Pipeline Unavailable", message);
            const hudState = document.getElementById("hud-stream-state");
            const hudText = document.getElementById("hud-stream-state-text");
            if (hudState && hudText) {
                hudState.className = "hud-status-badge offline";
                hudText.textContent = "OFFLINE";
            }
        });
    }

    if (cameraSelect) {
        cameraSelect.addEventListener("change", () => {
            const selectedText = cameraSelect.options[cameraSelect.selectedIndex]?.text || "CAM";
            const hudCamName = document.getElementById("hud-cam-name");
            if (hudCamName) hudCamName.textContent = selectedText.split(" ")[0];
            if (feed && feed.getAttribute("src")) {
                doStartStream();
            }
        });
    }

    if (fullscreenBtn) {
        fullscreenBtn.addEventListener("click", () => {
            const wrap = document.getElementById("video-viewport-wrap");
            if (!wrap) return;
            if (!document.fullscreenElement) {
                wrap.requestFullscreen().catch(() => {});
            } else {
                document.exitFullscreen().catch(() => {});
            }
        });
    }
}

/* --------------------------------------------------------------------------
   Master Acknowledge All Action
   -------------------------------------------------------------------------- */
function wireAcknowledgeAll() {
    const handleAckAll = async () => {
        try {
            await fetchJson("/api/alerts/acknowledge-all", { method: "POST" });
            refreshAll();
        } catch (err) {
            console.error("Ack all failed:", err);
        }
    };

    const headerBtn = document.getElementById("btn-ack-all-header");
    const queueBtn = document.getElementById("btn-ack-all-queue");
    if (headerBtn) headerBtn.addEventListener("click", handleAckAll);
    if (queueBtn) queueBtn.addEventListener("click", handleAckAll);
}

/* --------------------------------------------------------------------------
   Audio Alert Controls
   -------------------------------------------------------------------------- */
function wireAudioToggle() {
    const audioBtn = document.getElementById("btn-audio-toggle");
    if (!audioBtn) return;

    const iconOn = document.getElementById("audio-icon-on");
    const iconOff = document.getElementById("audio-icon-off");

    const updateAudioIcons = () => {
        if (iconOn && iconOff) {
            iconOn.style.display = audioAlertsEnabled ? "" : "none";
            iconOff.style.display = audioAlertsEnabled ? "none" : "";
        }
        audioBtn.setAttribute("title", audioAlertsEnabled ? "Audio Alerts: Enabled" : "Audio Alerts: Muted");
    };

    updateAudioIcons();

    audioBtn.addEventListener("click", () => {
        audioAlertsEnabled = !audioAlertsEnabled;
        localStorage.setItem("verdant_audio_enabled", audioAlertsEnabled ? "true" : "false");
        updateAudioIcons();
    });
}

/* --------------------------------------------------------------------------
   Mobile Sidebar Toggle
   -------------------------------------------------------------------------- */
function wireSidebarToggle() {
    const btn = document.getElementById("btn-sidebar-toggle");
    const sidebar = document.getElementById("app-sidebar");
    if (!btn || !sidebar) return;

    btn.addEventListener("click", () => {
        sidebar.classList.toggle("open");
    });

    document.addEventListener("click", (e) => {
        if (sidebar.classList.contains("open") && !sidebar.contains(e.target) && !btn.contains(e.target)) {
            sidebar.classList.remove("open");
        }
    });
}

/* --------------------------------------------------------------------------
   Real-Time Server-Sent Events (SSE) Receiver
   -------------------------------------------------------------------------- */
function wireSSE() {
    if (!window.EventSource) return;

    const pulseDot = document.getElementById("sidebar-pulse-dot");
    const pulseLabel = document.getElementById("sidebar-pulse-label");

    try {
        const source = new EventSource("/api/events/stream");

        source.onopen = () => {
            if (pulseDot) pulseDot.className = "status-indicator-dot online";
            if (pulseLabel) pulseLabel.textContent = "SSE LINK ACTIVE";
        };

        source.addEventListener("event", () => {
            refreshAll();
        });

        source.addEventListener("incident", () => {
            refreshAll();
        });

        source.addEventListener("alert", () => {
            refreshAlerts();
            refreshStatus();
        });

        source.addEventListener("resync", () => {
            refreshAll();
        });

        source.onerror = () => {
            // Automatic fallback to background interval polling
            if (pulseDot) pulseDot.className = "status-indicator-dot";
            if (pulseLabel) pulseLabel.textContent = "POLL (5s)";
        };
    } catch (e) {
        if (pulseLabel) pulseLabel.textContent = "POLL (5s)";
    }
}

/* --------------------------------------------------------------------------
   Refresh Orchestration
   -------------------------------------------------------------------------- */
async function refreshAll() {
    const tasks = [refreshStatus(), refreshAlerts(), refreshEvents()];
    await Promise.allSettled(tasks);
}

/* --------------------------------------------------------------------------
   Lifecycle Initialization
   -------------------------------------------------------------------------- */
document.addEventListener("DOMContentLoaded", () => {
    updateClocks();
    setInterval(updateClocks, 1000);

    wireSidebarToggle();
    wireStream();
    wireAcknowledgeAll();
    wireAudioToggle();
    wireSSE();

    refreshAll();
    setInterval(refreshAll, REFRESH_MS);
});
