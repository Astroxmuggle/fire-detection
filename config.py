"""Application configuration.

Resolution order for every value:

1. real environment variables,
2. a local ``.env`` file next to this module (it never overrides a real
   environment variable),
3. the defaults declared below.

A deliberately dependency-free ``.env`` parser is used so the project can be
cloned and started without installing anything beyond ``requirements.txt``.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


def load_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """Load ``KEY=VALUE`` pairs from *path* into ``os.environ``.

    Blank lines and ``#`` comments are ignored, surrounding quotes are
    stripped, and values already present in the environment win.
    """
    loaded: dict[str, str] = {}
    if not path.is_file():
        return loaded

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not key or key in os.environ:
            continue

        os.environ[key] = value
        loaded[key] = value

    return loaded


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or not value.strip() else value.strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        return default


# Load .env before the class body evaluates the environment.
load_env_file()


class Config:
    APP_NAME = "FireWatch AI"
    VERSION = "1.1.0"

    DEBUG = _env_bool("DEBUG", False)
    SECRET_KEY = _env_str("SECRET_KEY", "dev-secret-key")
    HOST = _env_str("HOST", "127.0.0.1")
    PORT = _env_int("PORT", 5000)
    LOGGING_LEVEL = _env_str("LOGGING_LEVEL", "INFO").upper()

    # ---------------------------------------------------------------- storage
    DATABASE_PATH = Path(
        _env_str("DATABASE_PATH", str((BASE_DIR / "fire_detection.db").resolve()))
    )
    DATABASE_URI = "sqlite:///" + str(DATABASE_PATH)
    DATABASE_TRACK_MODIFICATIONS = False

    EVIDENCE_DIR = Path(_env_str("EVIDENCE_DIR", str(BASE_DIR / "snapshots")))
    LOG_DIR = Path(_env_str("LOG_DIR", str(BASE_DIR / "logs")))

    # ------------------------------------------------------------------ model
    MODELS_DIR = BASE_DIR / "models"
    MODEL_PATH = _env_str("MODEL_PATH", str(MODELS_DIR / "best.pt"))

    # ----------------------------------------------------------------- camera
    # A webcam index ("0") or any OpenCV stream URL ("rtsp://user:pass@host/...").
    CAMERA_SOURCE = _env_str("CAMERA_SOURCE", _env_str("CAMERA_INDEX", "0"))
    # Optional multi-camera list, comma/semicolon separated. When set it seeds
    # the camera registry on first start; otherwise CAMERA_SOURCE is used.
    CAMERA_SOURCES = _env_str("CAMERA_SOURCES", "")
    CAMERA_INDEX = _env_int("CAMERA_INDEX", 0)  # kept for backwards compatibility
    FRAME_WIDTH = _env_int("FRAME_WIDTH", 640)
    FRAME_HEIGHT = _env_int("FRAME_HEIGHT", 480)

    # -------------------------------------------------------------- detection
    CONFIDENCE_THRESHOLD = _env_float("CONFIDENCE_THRESHOLD", 0.50)
    FIRE_CONFIDENCE_THRESHOLD = _env_float("FIRE_CONFIDENCE_THRESHOLD", 0.50)
    SMOKE_CONFIDENCE_THRESHOLD = _env_float("SMOKE_CONFIDENCE_THRESHOLD", 0.55)
    IOU_THRESHOLD = _env_float("IOU_THRESHOLD", 0.40)

    # A detection whose box is smaller than this fraction of the frame is
    # treated as noise; larger than MAX_BOX_AREA_RATIO means a full-frame blob.
    MIN_BOX_AREA_RATIO = _env_float("MIN_BOX_AREA_RATIO", 0.0004)
    MAX_BOX_AREA_RATIO = _env_float("MAX_BOX_AREA_RATIO", 0.92)

    # Frames below this standard deviation are blank (covered lens, dark room,
    # uniform wall) and are not sent to the model at all.
    MIN_FRAME_STD = _env_float("MIN_FRAME_STD", 6.0)

    # Temporal confirmation: a class must appear in CONFIRMATION_FRAMES
    # consecutive frames, stays latched while visible, and re-arms only after
    # CONFIRMATION_RELEASE_FRAMES frames without it.
    CONFIRMATION_FRAMES = _env_int("CONFIRMATION_FRAMES", 2)
    CONFIRMATION_RELEASE_FRAMES = _env_int("CONFIRMATION_RELEASE_FRAMES", 3)
    CONFIRMATION_COOLDOWN = _env_float("CONFIRMATION_COOLDOWN", 5.0)

    # ---------------------------------------------------------------- alerting
    ALERT_COOLDOWN = _env_int("ALERT_COOLDOWN", 60)
    ALERT_SOUND_ENABLED = _env_bool("ALERT_SOUND_ENABLED", True)

    # ------------------------------------------------------------------- misc
    STREAM_JPEG_QUALITY = _env_int("STREAM_JPEG_QUALITY", 70)
    EVENT_RETENTION_DAYS = _env_int("EVENT_RETENTION_DAYS", 30)  # 0 = keep forever, default 30 days

    # ----------------------------------------------------------------- workers
    # Background inference worker. Monitoring runs without any browser attached;
    # frames are queued in a bounded buffer and the oldest is dropped under load.
    WORKER_FPS_LIMIT = _env_float("WORKER_FPS_LIMIT", 15.0)
    WORKER_QUEUE_SIZE = _env_int("WORKER_QUEUE_SIZE", 8)
    WORKER_RECONNECT_SECONDS = _env_float("WORKER_RECONNECT_SECONDS", 2.0)
    WORKER_RECONNECT_MAX_SECONDS = _env_float("WORKER_RECONNECT_MAX_SECONDS", 30.0)
    # Start monitoring every enabled camera at application boot.
    MONITORING_AUTOSTART = _env_bool("MONITORING_AUTOSTART", False)

    # -------------------------------------------------------------------- SSE
    # Server-Sent Events use an in-process bus: supported with a single server
    # process. Use threads (gunicorn --threads) rather than processes.
    SSE_ENABLED = _env_bool("SSE_ENABLED", True)
    SSE_HEARTBEAT_SECONDS = _env_float("SSE_HEARTBEAT_SECONDS", 15.0)
    SSE_QUEUE_SIZE = _env_int("SSE_QUEUE_SIZE", 100)
    SSE_MAX_SUBSCRIBERS = _env_int("SSE_MAX_SUBSCRIBERS", 16)
    SSE_REPLAY_BUFFER = _env_int("SSE_REPLAY_BUFFER", 256)
