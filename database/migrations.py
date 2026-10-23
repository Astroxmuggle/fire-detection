"""Numbered, ordered SQL migrations with a schema-version table.

Deliberately small: SQLite is the deployment target and Alembic would add a
dependency without adding anything this project needs. Each ``NNNN_name.sql``
file is applied once, inside a transaction, and recorded in
``schema_migrations``. Running the migration set again is a no-op; a database
created by a *newer* release is refused instead of being silently used.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_FILE_PATTERN = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")

VERSION_TABLE = "schema_migrations"


class MigrationError(RuntimeError):
    """A migration failed; the transaction has been rolled back."""


class UnsupportedSchemaVersion(MigrationError):
    """The database was created by a newer release than this code knows about."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def discover_migrations(directory: Optional[Path] = None) -> List[Migration]:
    """Return every migration file, ordered by version."""
    folder = Path(directory or MIGRATIONS_DIR)
    if not folder.is_dir():
        raise MigrationError(f"migrations directory not found: {folder}")

    migrations: List[Migration] = []
    for path in sorted(folder.glob("*.sql")):
        match = _FILE_PATTERN.match(path.name)
        if match is None:
            raise MigrationError(
                f"invalid migration filename {path.name!r}; expected NNNN_name.sql"
            )
        migrations.append(Migration(int(match.group(1)), match.group(2), path))

    versions = [migration.version for migration in migrations]
    if len(set(versions)) != len(versions):
        raise MigrationError(f"duplicate migration versions in {folder}")

    return sorted(migrations, key=lambda migration: migration.version)


def split_statements(sql: str) -> List[str]:
    """Split a migration file into individual statements.

    Comments are stripped first. The migrations in this project contain no
    semicolons inside string literals or trigger bodies, so a plain split is
    sufficient and keeps the runner dependency-free.
    """
    without_comments = re.sub(r"--[^\n]*", "", sql)
    return [statement.strip() for statement in without_comments.split(";") if statement.strip()]


def ensure_version_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    connection.commit()


def current_version(connection: sqlite3.Connection) -> int:
    try:
        row = connection.execute(f"SELECT COALESCE(MAX(version), 0) FROM {VERSION_TABLE}").fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row[0]) if row else 0


def applied_versions(connection: sqlite3.Connection) -> List[int]:
    try:
        rows = connection.execute(f"SELECT version FROM {VERSION_TABLE} ORDER BY version").fetchall()
    except sqlite3.OperationalError:
        return []
    return [int(row[0]) for row in rows]


def apply_migrations(
    connection: sqlite3.Connection,
    directory: Optional[Path] = None,
    target: Optional[int] = None,
) -> List[int]:
    """Apply all pending migrations; returns the versions applied in this call."""
    ensure_version_table(connection)

    migrations = discover_migrations(directory)
    if target is not None:
        migrations = [migration for migration in migrations if migration.version <= target]

    latest_known = migrations[-1].version if migrations else 0
    if current_version(connection) > latest_known:
        raise UnsupportedSchemaVersion(
            f"database schema version {current_version(connection)} is newer than this "
            f"release supports ({latest_known}); upgrade the application or restore a backup"
        )

    applied: List[int] = []
    for migration in migrations:
        if migration.version <= current_version(connection):
            continue
        _apply_one(connection, migration)
        applied.append(migration.version)
    return applied


def _apply_one(connection: sqlite3.Connection, migration: Migration) -> None:
    statements = split_statements(migration.path.read_text(encoding="utf-8"))
    previous_isolation = connection.isolation_level

    try:
        connection.isolation_level = None  # explicit transaction control
        connection.execute("BEGIN IMMEDIATE")
        for statement in statements:
            connection.execute(statement)
        connection.execute(
            f"INSERT INTO {VERSION_TABLE} (version, name, applied_at) VALUES (?, ?, ?)",
            (migration.version, migration.name, _utc_now()),
        )
        connection.execute("COMMIT")
    except Exception as exc:  # noqa: BLE001 - re-raised as a typed migration error
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise MigrationError(
            f"migration {migration.version:04d}_{migration.name} failed and was rolled back: {exc}"
        ) from exc
    finally:
        connection.isolation_level = previous_isolation


def migration_summary(connection: sqlite3.Connection) -> dict:
    """Small status payload used by tests and diagnostics."""
    return {
        "current_version": current_version(connection),
        "applied": applied_versions(connection),
        "available": [migration.version for migration in discover_migrations()],
    }
