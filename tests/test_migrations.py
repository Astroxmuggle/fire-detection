"""Migration runner: ordering, idempotency, legacy upgrade and rollback."""

from __future__ import annotations

import sqlite3

import pytest

from database.migrations import (
    MigrationError,
    UnsupportedSchemaVersion,
    apply_migrations,
    current_version,
    discover_migrations,
    ensure_version_table,
    migration_summary,
    split_statements,
)

LEGACY_SCHEMA = """
CREATE TABLE detection_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    class_name TEXT NOT NULL,
    confidence REAL NOT NULL,
    camera_source TEXT NOT NULL,
    alert_status TEXT NOT NULL,
    snapshot_path TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    alert_level TEXT NOT NULL,
    acknowledged INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE cameras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_events_created_at ON detection_events (created_at);
"""


def _connect(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def test_fresh_database_reaches_the_latest_version(temp_dir):
    connection = _connect(temp_dir / "fresh.db")
    try:
        applied = apply_migrations(connection)
        assert applied == [1]
        assert current_version(connection) == 1

        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"detection_events", "alerts", "cameras", "incidents",
                "incident_transitions", "schema_migrations"} <= tables

        columns = [row[1] for row in connection.execute("PRAGMA table_info(detection_events)")]
        assert "incident_id" in columns
    finally:
        connection.close()


def test_running_migrations_again_is_a_noop(temp_dir):
    connection = _connect(temp_dir / "idempotent.db")
    try:
        assert apply_migrations(connection) == [1]
        assert apply_migrations(connection) == []
        assert current_version(connection) == 1
    finally:
        connection.close()


def test_legacy_database_is_migrated_without_losing_data(temp_dir):
    path = temp_dir / "legacy.db"
    connection = _connect(path)
    try:
        connection.executescript(LEGACY_SCHEMA)
        connection.execute(
            "INSERT INTO cameras (id, name, source, enabled) VALUES (7, 'Legacy cam', '0', 1)"
        )
        connection.execute(
            """
            INSERT INTO detection_events
                (id, event_type, class_name, confidence, camera_source, alert_status, snapshot_path, created_at)
            VALUES (42, 'detection', 'fire', 0.91, 'camera:0', 'confirmed', NULL, '2026-10-01T10:00:00+00:00')
            """
        )
        connection.execute(
            "INSERT INTO alerts (id, event_id, alert_level, acknowledged) VALUES (3, 42, 'fire', 1)"
        )
        connection.commit()

        applied = apply_migrations(connection)
        assert applied == [1]

        event = connection.execute("SELECT * FROM detection_events WHERE id = 42").fetchone()
        assert event["id"] == 42
        assert event["class_name"] == "fire"
        assert event["incident_id"] is None  # history is preserved, not rewritten

        alert = connection.execute("SELECT * FROM alerts WHERE id = 3").fetchone()
        assert alert["event_id"] == 42 and alert["acknowledged"] == 1

        camera = connection.execute("SELECT * FROM cameras WHERE id = 7").fetchone()
        assert camera["name"] == "Legacy cam"

        assert connection.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == 0
    finally:
        connection.close()


def test_newer_schema_version_is_refused(temp_dir):
    connection = _connect(temp_dir / "future.db")
    try:
        ensure_version_table(connection)
        connection.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (99, 'from-the-future', '2030-01-01')"
        )
        connection.commit()

        with pytest.raises(UnsupportedSchemaVersion) as excinfo:
            apply_migrations(connection)
        assert "newer" in str(excinfo.value)
    finally:
        connection.close()


def test_failed_migration_rolls_back(temp_dir):
    migrations_dir = temp_dir / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0001_ok.sql").write_text("CREATE TABLE t_ok (id INTEGER);", encoding="utf-8")
    (migrations_dir / "0002_bad.sql").write_text(
        "CREATE TABLE t_bad (id INTEGER);\nTHIS IS NOT VALID SQL;", encoding="utf-8"
    )

    connection = _connect(temp_dir / "rollback.db")
    try:
        assert apply_migrations(connection, directory=migrations_dir, target=1) == [1]

        with pytest.raises(MigrationError):
            apply_migrations(connection, directory=migrations_dir)

        assert current_version(connection) == 1
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "t_ok" in tables
        assert "t_bad" not in tables  # rolled back with its transaction
    finally:
        connection.close()


def test_discovery_is_ordered_and_rejects_bad_names(temp_dir):
    migrations_dir = temp_dir / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0002_second.sql").write_text("SELECT 1;", encoding="utf-8")
    (migrations_dir / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")

    found = discover_migrations(migrations_dir)
    assert [migration.version for migration in found] == [1, 2]

    (migrations_dir / "oops.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(MigrationError):
        discover_migrations(migrations_dir)


def test_statement_splitter_ignores_comments_and_blank_lines():
    sql = """
    -- a comment
    CREATE TABLE a (id INTEGER);

    -- another comment
    CREATE INDEX idx_a ON a (id);
    """
    assert split_statements(sql) == [
        "CREATE TABLE a (id INTEGER)",
        "CREATE INDEX idx_a ON a (id)",
    ]


def test_migration_summary_reports_state(temp_dir):
    connection = _connect(temp_dir / "summary.db")
    try:
        apply_migrations(connection)
        summary = migration_summary(connection)
        assert summary["current_version"] == 1
        assert summary["applied"] == [1]
        assert 1 in summary["available"]
    finally:
        connection.close()
