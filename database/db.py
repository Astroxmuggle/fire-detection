"""SQLite access layer.

The database file location is resolved from the environment so tests can point
the whole application at a throw-away file without touching production data.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _resolve_database_path() -> Path:
    override = os.getenv("DATABASE_PATH")
    if override and override.strip():
        return Path(override).expanduser()
    return BASE_DIR / "fire_detection.db"


DATABASE_PATH = _resolve_database_path()


def get_db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    connection = get_db_connection()
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS detection_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                class_name TEXT NOT NULL,
                confidence REAL NOT NULL,
                camera_source TEXT NOT NULL,
                alert_status TEXT NOT NULL,
                snapshot_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                alert_level TEXT NOT NULL,
                acknowledged INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_created_at ON detection_events (created_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_alert_status ON detection_events (alert_status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_event_id ON alerts (event_id)"
        )
        connection.commit()
    finally:
        connection.close()


def query_db(query, params=(), one=False):
    connection = get_db_connection()
    try:
        rows = connection.execute(query, params).fetchall()
    finally:
        connection.close()
    if one:
        return dict(rows[0]) if rows else None
    return [dict(row) for row in rows]


def execute_db(query, params=()):
    connection = get_db_connection()
    try:
        connection.execute(query, params)
        connection.commit()
    finally:
        connection.close()
    return True


def get_event_history(limit=100):
    connection = get_db_connection()
    try:
        rows = connection.execute(
            "SELECT * FROM detection_events ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        connection.close()
    return [dict(row) for row in rows]


def get_db():
    return get_db_connection()


def close_db(connection=None):
    if connection is not None:
        connection.close()
