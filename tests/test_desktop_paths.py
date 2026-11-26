"""Desktop path resolution: data root, config seeding, and log paths."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

import engine


def _write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _minimal_config(**overrides) -> dict:
    cfg = {
        "allowed_categories": ["test_category"],
        "video_extensions": [".mp4"],
        "image_extensions": [".jpg"],
        "audio_extensions": [".mp3"],
        "document_extensions": [".pdf"],
        "model": {"name": "test-model", "temperature": 0.1, "num_ctx": 1024},
        "preview": {"image_max_edge": 512, "video_grid_scale": 300, "extraction_workers": 0},
        "naming": {"case_style": "snake_case", "max_filename_chars": 0, "sort_folders": True},
        "naming_templates": {"default": "{topic}_{description}"},
        "logging": {"directory": "logs", "max_upload_size": 1024},
        "prompt_profiles": {"active": "general_balanced", "profiles": {}},
    }
    cfg.update(overrides)
    return cfg


def _isolate_legacy_exe(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(engine.sys, "executable", str(tmp_path / "bin" / "backend.exe"))


def test_amr_data_dir_overrides_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("AMR_DATA_DIR", str(tmp_path / "portable"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    assert engine.resolve_data_dir() == tmp_path / "portable"


def test_app_data_dir_default(monkeypatch, tmp_path):
    monkeypatch.delenv("AMR_DATA_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    assert engine.resolve_data_dir() == tmp_path / "roaming" / "ai-media-renamer"

    monkeypatch.delenv("APPDATA", raising=False)
    assert engine.resolve_data_dir() == Path.home() / "AppData" / "Roaming" / "ai-media-renamer"


def test_source_config_path_uses_repo(monkeypatch, tmp_path):
    monkeypatch.delenv("AMR_DATA_DIR", raising=False)
    monkeypatch.setattr(engine, "is_frozen", lambda: False)
    monkeypatch.setattr(engine, "BASE_DIR", tmp_path)
    monkeypatch.setattr(engine, "APP_DATA_DIR", tmp_path / "appdata")
    assert engine.resolve_config_path() == tmp_path / "config.json"


def test_override_config_path_uses_data_root(monkeypatch, tmp_path):
    monkeypatch.setenv("AMR_DATA_DIR", str(tmp_path / "portable"))
    monkeypatch.setattr(engine, "is_frozen", lambda: False)
    monkeypatch.setattr(engine, "APP_DATA_DIR", tmp_path / "appdata")
    assert engine.resolve_config_path() == tmp_path / "appdata" / "config.json"


def test_frozen_config_path_uses_data_root(monkeypatch, tmp_path):
    monkeypatch.delenv("AMR_DATA_DIR", raising=False)
    monkeypatch.setattr(engine, "is_frozen", lambda: True)
    monkeypatch.setattr(engine, "APP_DATA_DIR", tmp_path / "appdata")
    assert engine.resolve_config_path() == tmp_path / "appdata" / "config.json"


def test_seed_config_from_bundled_default(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    default_data = _minimal_config(allowed_categories=["from_default"])
    _write_json(bundle / "config.default.json", default_data)
    config_path = tmp_path / "data" / "config.json"

    monkeypatch.setattr(engine, "is_frozen", lambda: True)
    monkeypatch.setattr(engine, "BUNDLE_DIR", bundle)
    monkeypatch.setattr(engine, "BASE_DIR", tmp_path / "install")
    monkeypatch.setattr(engine, "CONFIG_PATH", config_path)
    _isolate_legacy_exe(monkeypatch, tmp_path)

    engine._seed_config_if_missing()

    assert config_path.exists()
    assert json.loads(config_path.read_text(encoding="utf-8"))["allowed_categories"] == ["from_default"]


def test_legacy_portable_config_imported_once(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    _write_json(bundle / "config.default.json", _minimal_config(allowed_categories=["default"]))
    install = tmp_path / "install"
    legacy = _write_json(install / "config.json", _minimal_config(allowed_categories=["legacy"]))
    config_path = tmp_path / "data" / "config.json"

    monkeypatch.setattr(engine, "is_frozen", lambda: True)
    monkeypatch.setattr(engine, "BUNDLE_DIR", bundle)
    monkeypatch.setattr(engine, "BASE_DIR", install)
    monkeypatch.setattr(engine, "CONFIG_PATH", config_path)
    _isolate_legacy_exe(monkeypatch, tmp_path)

    engine._seed_config_if_missing()
    assert json.loads(config_path.read_text(encoding="utf-8"))["allowed_categories"] == ["legacy"]

    _write_json(legacy, _minimal_config(allowed_categories=["changed"]))
    engine._seed_config_if_missing()
    assert json.loads(config_path.read_text(encoding="utf-8"))["allowed_categories"] == ["legacy"]


def test_seed_does_not_overwrite_existing_config(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    _write_json(bundle / "config.default.json", _minimal_config(allowed_categories=["default"]))
    install = tmp_path / "install"
    _write_json(install / "config.json", _minimal_config(allowed_categories=["legacy"]))
    config_path = _write_json(
        tmp_path / "data" / "config.json",
        _minimal_config(allowed_categories=["existing"]),
    )

    monkeypatch.setattr(engine, "is_frozen", lambda: True)
    monkeypatch.setattr(engine, "BUNDLE_DIR", bundle)
    monkeypatch.setattr(engine, "BASE_DIR", install)
    monkeypatch.setattr(engine, "CONFIG_PATH", config_path)
    _isolate_legacy_exe(monkeypatch, tmp_path)

    engine._seed_config_if_missing()

    assert json.loads(config_path.read_text(encoding="utf-8"))["allowed_categories"] == ["existing"]


def test_source_log_dir_is_repo(monkeypatch, tmp_path):
    monkeypatch.delenv("AMR_DATA_DIR", raising=False)
    monkeypatch.setattr(engine, "is_frozen", lambda: False)
    monkeypatch.setattr(engine, "BASE_DIR", tmp_path)
    monkeypatch.setattr(engine, "APP_DATA_DIR", tmp_path / "appdata")

    assert engine._resolve_log_dir({"logging": {"directory": "logs"}}) == tmp_path / "logs"

    absolute = tmp_path / "elsewhere" / "logs"
    assert engine._resolve_log_dir({"logging": {"directory": str(absolute)}}) == absolute


def test_frozen_log_dir_is_data_root(monkeypatch, tmp_path):
    monkeypatch.delenv("AMR_DATA_DIR", raising=False)
    monkeypatch.setattr(engine, "is_frozen", lambda: True)
    monkeypatch.setattr(engine, "APP_DATA_DIR", tmp_path / "data")

    assert engine._resolve_log_dir({"logging": {"directory": "logs"}}) == tmp_path / "data" / "logs"


def test_reload_config_refreshes_log_dir(monkeypatch, tmp_path):
    log_dir = tmp_path / "fresh_logs"
    cfg = _minimal_config(logging={"directory": str(log_dir), "max_upload_size": 1024})

    for name in (
        "config",
        "ALLOWED_CATEGORIES",
        "VIDEO_EXTENSIONS",
        "IMAGE_EXTENSIONS",
        "AUDIO_EXTENSIONS",
        "DOCUMENT_EXTENSIONS",
        "MODEL_NAME",
        "TEXT_MODEL_NAME",
        "MODEL_TEMPERATURE",
        "MODEL_NUM_CTX",
        "IMAGE_PREVIEW_MAX_EDGE",
        "VIDEO_GRID_SCALE",
        "EXTRACTION_WORKERS",
        "DEFAULT_CASE_STYLE",
        "DEFAULT_MAX_FILENAME_CHARS",
        "DEFAULT_SORT_FOLDERS",
        "NAMED_TEMPLATES",
        "DEFAULT_TEMPLATE_STRING",
        "PROMPT_PROFILES",
        "LOG_DIR",
        "CONFIG_LOAD_ERROR",
    ):
        monkeypatch.setattr(engine, name, getattr(engine, name))
    monkeypatch.setattr(engine, "LOG_DIR", tmp_path / "stale_logs")
    monkeypatch.setattr(engine, "load_config", lambda **kwargs: deepcopy(cfg))

    engine.reload_config()

    assert engine.LOG_DIR == log_dir


def test_load_config_absolute_path(tmp_path):
    config_path = _write_json(
        tmp_path / "custom.json",
        _minimal_config(allowed_categories=["absolute"]),
    )

    result = engine.load_config(str(config_path))

    assert result["allowed_categories"] == ("absolute",)
    assert config_path.exists()


def test_save_config_creates_parents(monkeypatch, tmp_path):
    config_path = tmp_path / "nested" / "deeper" / "config.json"
    monkeypatch.setattr(engine, "CONFIG_PATH", config_path)
    monkeypatch.setattr(engine, "config", _minimal_config())

    engine.save_config()

    assert config_path.exists()
    loaded = json.loads(config_path.read_text(encoding="utf-8"))
    assert loaded["model"]["name"] == "test-model"


def test_save_config_raises_on_failure(monkeypatch, tmp_path):
    config_path = tmp_path / "nested" / "config.json"
    monkeypatch.setattr(engine, "CONFIG_PATH", config_path)
    monkeypatch.setattr(engine, "config", _minimal_config())

    def _fail_replace(src, dst):
        raise OSError("disk is full")

    monkeypatch.setattr(engine.os, "replace", _fail_replace)

    with pytest.raises(OSError):
        engine.save_config()
