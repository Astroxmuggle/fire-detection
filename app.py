"""FireWatch AI application entry point."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, render_template

from config import Config
from database.db import init_db
from routes.api import api_bp
from routes.web import web_bp
from services.camera_registry import sync_from_config


def configure_logging(level: str | None = None) -> logging.Logger:
    """Send logs to a rotating file and the console, and return the app logger."""
    log_level = getattr(logging, (level or Config.LOGGING_LEVEL or "INFO").upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(log_level)

    if not any(isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler)
               for handler in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)

    try:
        Config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = Config.LOG_DIR / "firewatch.log"
        if not any(
            isinstance(handler, RotatingFileHandler)
            and getattr(handler, "baseFilename", "") == str(log_file)
            for handler in root.handlers
        ):
            file_handler = RotatingFileHandler(
                log_file, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
    except OSError as exc:  # read-only deployments still work with console logging
        root.warning("File logging disabled: %s", exc)

    return logging.getLogger("firewatch")


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.config.setdefault("SECRET_KEY", config_object.SECRET_KEY)

    init_db()
    configure_logging()

    # Seed the camera registry from configuration on first start.
    sync_from_config()

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(web_bp)

    register_error_handlers(app)

    @app.context_processor
    def inject_globals():
        return {
            "app_name": Config.APP_NAME,
            "app_version": Config.VERSION,
        }

    logging.getLogger("firewatch").info(
        "%s %s starting (database=%s, model=%s)",
        Config.APP_NAME,
        Config.VERSION,
        Config.DATABASE_PATH,
        Config.MODEL_PATH,
    )
    return app


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(error):
        if _wants_html():
            return render_template("error.html", code=404, message="Page not found"), 404
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def server_error(error):  # pragma: no cover - exercised manually
        app.logger.exception("Unhandled error: %s", error)
        if _wants_html():
            return render_template("error.html", code=500, message="Internal server error"), 500
        return jsonify({"error": "Internal server error"}), 500


def _wants_html() -> bool:
    from flask import request

    best = request.accept_mimetypes.best
    return best == "text/html" or (
        request.accept_mimetypes["text/html"] >= request.accept_mimetypes["application/json"]
    )


app = create_app()


if __name__ == "__main__":
    app.run(
        host=app.config["HOST"],
        port=app.config["PORT"],
        debug=app.config["DEBUG"],
        threaded=True,
        use_reloader=False,
    )
