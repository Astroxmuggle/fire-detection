"""SQLite access layer.

Connections are opened with a busy timeout and, when the filesystem supports it,
WAL journaling, so several camera workers can write without blocking each other
for long. Write paths that need a read-then-write cycle use
:func:`transaction`, which takes an immediate write lock up front instead of
risking a lost update between the read and the write.

Schema changes are owned by :mod:`database.migrations`; this module never
creates tables ad hoc.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List

from database.migrations import apply_migrations, current_version

BASE_DIR = Path(__file__).resolve().parent.parent
BUSY_TIMEOUT_MS = 10_000


def _resolve_database_path() -> Path:
    override = os.getenv("DATABASE_PATH")
    if override and override.strip():
        return Path(override).expanduser()
    return BASE_DIR / "fire_detection.db"


DATABASE_PATH = _resolve_database_path()


def _configure(connection: sqlite3.Connection) -> sqlite3.Connection:
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA foreign_keys = ON")
    # WAL lets readers proceed while a worker writes. It is a persistent
    # database setting; on filesystems that reject it we keep the default mode.
    try:
        connection.execute("PRAGMA journal_mode = WAL")
    except sqlite3.DatabaseError:
        pass
    return connection


def get_db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=BUSY_TIMEOUT_MS / 1000.0)
    return _configure(connection)


@contextmanager
def transaction(immediate: bool = True) -> Iterator[sqlite3.Connection]:
    """Explicit transaction boundary.

    ``immediate=True`` acquires the write lock as the transaction starts, which
    serialises the read-check-write sequence used when creating or updating an
    incident. The connection is always closed and the transaction always ends
    in COMMIT or ROLLBACK.
    """
    connection = get_db_connection()
    previous_isolation = connection.isolation_level
    try:
        connection.isolation_level = None
        connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        yield connection
        connection.execute("COMMIT")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.isolation_level = previous_isolation
        connection.close()


def init_db() -> List[int]:
    """Apply pending migrations. Safe to call on every start."""
    connection = get_db_connection()
    try:
        return apply_migrations(connection)
    finally:
        connection.close()


def schema_version() -> int:
    connection = get_db_connection()
    try:
        return current_version(connection)
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
