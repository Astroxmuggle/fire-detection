-- 0001_incidents.sql
--
-- Baseline schema (idempotent) plus the incident lifecycle.
--
-- Applied inside a single transaction by database/migrations.py. The baseline
-- statements are repeated here so a brand-new database and a database created
-- by the pre-migration code converge to the same schema; on an existing
-- database they are no-ops.
--
-- Nothing is dropped or rewritten: existing detection_events and alert rows and
-- their identifiers are preserved, and detection_events only gains a nullable
-- incident_id column.

CREATE TABLE IF NOT EXISTS detection_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    class_name TEXT NOT NULL,
    confidence REAL NOT NULL,
    camera_source TEXT NOT NULL,
    alert_status TEXT NOT NULL,
    snapshot_path TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    alert_level TEXT NOT NULL,
    acknowledged INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cameras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_created_at ON detection_events (created_at);
CREATE INDEX IF NOT EXISTS idx_events_alert_status ON detection_events (alert_status);
CREATE INDEX IF NOT EXISTS idx_alerts_event_id ON alerts (event_id);

-- An incident groups one or more confirmed detections of the same class on the
-- same camera. camera_id 0 means "camera not identified" (legacy callers).
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL DEFAULT 0,
    camera_source TEXT NOT NULL,
    class_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'acknowledged', 'closed')),
    source_kind TEXT NOT NULL DEFAULT 'unknown',
    opened_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    acknowledged_at TEXT,
    acknowledged_by TEXT,
    closed_at TEXT,
    closed_by TEXT,
    close_reason TEXT,
    first_event_id INTEGER,
    last_event_id INTEGER,
    event_count INTEGER NOT NULL DEFAULT 0,
    peak_confidence REAL,
    last_confidence REAL,
    evidence_event_id INTEGER,
    notes TEXT
);

-- At most one active incident per camera/class. This is the concurrency-safe
-- guarantee against duplicate active incidents; the application also coalesces
-- explicitly, but the database refuses a duplicate even if two writers race.
CREATE UNIQUE INDEX IF NOT EXISTS ux_incidents_active
    ON incidents (camera_id, class_name)
    WHERE status IN ('open', 'acknowledged');

CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents (status, opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_camera ON incidents (camera_id, class_name);

CREATE TABLE IF NOT EXISTS incident_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_incident_transitions_incident
    ON incident_transitions (incident_id, id);

-- Link every confirmed detection to the incident it fed. Nullable: historical
-- rows migrated from the previous schema keep NULL and stay untouched.
ALTER TABLE detection_events ADD COLUMN incident_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_events_incident ON detection_events (incident_id);
