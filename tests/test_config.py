"""Configuration tests."""

from __future__ import annotations

from pathlib import Path

from config import Config, load_env_file

VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def test_config_has_required_runtime_values():
    assert isinstance(Config.DATABASE_PATH, Path)
    assert isinstance(Config.EVIDENCE_DIR, Path)
    assert Config.MODEL_PATH.endswith(".pt")
    assert 0.0 <= Config.CONFIDENCE_THRESHOLD <= 1.0
    assert 0.0 <= Config.FIRE_CONFIDENCE_THRESHOLD <= 1.0
    assert 0.0 <= Config.SMOKE_CONFIDENCE_THRESHOLD <= 1.0
    assert Config.ALERT_COOLDOWN > 0
    assert Config.CONFIRMATION_FRAMES >= 1
    assert Config.CONFIRMATION_RELEASE_FRAMES >= 1
    assert Config.MIN_FRAME_STD >= 0
    assert Config.MIN_BOX_AREA_RATIO < Config.MAX_BOX_AREA_RATIO
    assert Config.LOGGING_LEVEL in VALID_LEVELS


def test_model_is_bundled_inside_the_project():
    model = Path(Config.MODEL_PATH)
    assert model.name == "best.pt"
    assert model.parent.name == "models"


def test_default_host_stays_local():
    assert Config.HOST in {"127.0.0.1", "localhost"}


def test_env_file_parser_handles_comments_quotes_and_export(temp_dir, monkeypatch):
    env_file = temp_dir / "sample.env"
    env_file.write_text(
        "\n".join([
            "# a comment",
            "",
            "FIREWATCH_TEST_PLAIN=hello",
            'FIREWATCH_TEST_QUOTED="hello world"',
            "export FIREWATCH_TEST_EXPORT=yes",
            "FIREWATCH_TEST_EQUALS=a=b",
        ]),
        encoding="utf-8",
    )
    for key in (
        "FIREWATCH_TEST_PLAIN",
        "FIREWATCH_TEST_QUOTED",
        "FIREWATCH_TEST_EXPORT",
        "FIREWATCH_TEST_EQUALS",
    ):
        monkeypatch.delenv(key, raising=False)

    loaded = load_env_file(env_file)

    assert loaded["FIREWATCH_TEST_PLAIN"] == "hello"
    assert loaded["FIREWATCH_TEST_QUOTED"] == "hello world"
    assert loaded["FIREWATCH_TEST_EXPORT"] == "yes"
    assert loaded["FIREWATCH_TEST_EQUALS"] == "a=b"


def test_env_file_does_not_override_real_environment(temp_dir, monkeypatch):
    env_file = temp_dir / "sample.env"
    env_file.write_text("FIREWATCH_TEST_KEEP=from-file\n", encoding="utf-8")
    monkeypatch.setenv("FIREWATCH_TEST_KEEP", "from-process")

    loaded = load_env_file(env_file)

    assert "FIREWATCH_TEST_KEEP" not in loaded
    assert __import__("os").environ["FIREWATCH_TEST_KEEP"] == "from-process"


def test_missing_env_file_is_not_an_error(temp_dir):
    assert load_env_file(temp_dir / "missing.env") == {}
