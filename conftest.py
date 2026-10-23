"""Shared pytest fixtures.

Every test gets its own SQLite database and evidence folder, so the suite can
never read, wipe or pollute operational data. Directories are created with the
default mode (not ``tempfile.mkdtemp``'s 0o700) so they stay accessible on
Windows sandboxes that drop the owner ACE for mode-0700 directories.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MUTABLE_CONFIG = (
    "CONFIDENCE_THRESHOLD",
    "FIRE_CONFIDENCE_THRESHOLD",
    "SMOKE_CONFIDENCE_THRESHOLD",
    "ALERT_COOLDOWN",
    "CONFIRMATION_FRAMES",
    "CONFIRMATION_RELEASE_FRAMES",
    "FRAME_WIDTH",
    "FRAME_HEIGHT",
)


def make_temp_dir(prefix: str) -> Path:
    """Create a directory the current (possibly sandboxed) user can use."""
    base = Path(tempfile.gettempdir()) / "firewatch-tests" / f"{prefix}-{uuid4().hex[:8]}"
    base.mkdir(parents=True, exist_ok=True)
    return base


# The application imports and calls init_db() at import time; point that first
# database at a scratch file so no test ever touches fire_detection.db.
_BOOTSTRAP = make_temp_dir("bootstrap")
os.environ.setdefault("DATABASE_PATH", str(_BOOTSTRAP / "bootstrap.db"))
os.environ.setdefault("EVIDENCE_DIR", str(_BOOTSTRAP / "snapshots"))


@pytest.fixture
def temp_dir():
    path = make_temp_dir("tmp")
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_app_storage(monkeypatch):
    """Redirect storage and reset every piece of process-wide state."""
    import database.db as db
    from config import Config
    from services import event_service, status_service
    from services.metrics_service import get_metrics_service

    saved_config = {name: getattr(Config, name) for name in MUTABLE_CONFIG}
    workdir = make_temp_dir("case")

    monkeypatch.setattr(db, "DATABASE_PATH", workdir / "test.db")
    monkeypatch.setattr(Config, "EVIDENCE_DIR", workdir / "snapshots")
    monkeypatch.setattr(Config, "ALERT_SOUND_ENABLED", False)
    monkeypatch.setattr(Config, "LOG_DIR", workdir / "logs")

    db.init_db()
    event_service.reset_alert_manager()
    # Keep the configured cool-down visible to config tests, but never let it
    # suppress alerts inside a test.
    event_service.get_alert_manager().alert_cooldown = 0
    status_service.reset_runtime_status()
    get_metrics_service().reset_counters()

    try:
        yield workdir
    finally:
        event_service.reset_alert_manager()
        status_service.reset_runtime_status()
        for name, value in saved_config.items():
            setattr(Config, name, value)
        shutil.rmtree(workdir, ignore_errors=True)


@pytest.fixture
def client():
    from app import app

    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client
