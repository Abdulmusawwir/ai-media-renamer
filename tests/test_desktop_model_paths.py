"""Desktop model paths, session/undo roots, and legacy GGUF migration."""

import json
import time
from pathlib import Path

import pytest

import engine


def _write(path: Path, data: bytes = b"data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _enable_migration(monkeypatch) -> None:
    monkeypatch.setattr(engine, "is_frozen", lambda: True)


def _point_models(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    legacy = tmp_path / "legacy_models"
    dest = tmp_path / "models"
    monkeypatch.setattr(engine, "LEGACY_MODELS_DIR", legacy)
    monkeypatch.setattr(engine, "LLAMACPP_MODELS_DIR", dest)
    monkeypatch.setattr(engine, "_llamacpp_model_dir", lambda: dest)
    return legacy, dest


def test_session_undo_paths_use_user_data_dir():
    assert engine.SESSION_DIR == engine.USER_DATA_DIR / "sessions"
    assert engine.UNDO_DIR == engine.USER_DATA_DIR
    assert engine.UNDO_LOG_FILE == engine.UNDO_DIR / "undo_log.jsonl"


def test_model_dir_defaults_to_user_models(monkeypatch):
    monkeypatch.setattr(engine, "config", {"model": {"llamacpp": {}}})
    assert engine._llamacpp_model_dir() == engine.LLAMACPP_MODELS_DIR


def test_model_dir_honors_config_override(monkeypatch, tmp_path):
    custom = tmp_path / "custom_models"
    monkeypatch.setattr(
        engine,
        "config",
        {"model": {"llamacpp": {"model_dir": str(custom)}}},
    )
    assert engine._llamacpp_model_dir() == custom


def test_gguf_paths_and_download_agree(monkeypatch, tmp_path):
    model_dir = tmp_path / "models"
    monkeypatch.setattr(engine, "_llamacpp_model_dir", lambda: model_dir)

    gguf, mmproj = engine._llamacpp_gguf_paths("qwen2.5vl:7b")
    assert gguf == model_dir / "qwen2-vl-7b-q4_k_m.gguf"
    assert mmproj == model_dir / "mmproj-qwen2-vl-7b-q8_0.gguf"

    downloaded: list[Path] = []

    def fake_download(url, dest, **kwargs):
        downloaded.append(Path(dest))
        return True

    monkeypatch.setattr(engine, "download_file", fake_download)

    result = engine.download_llamacpp_model("qwen2.5vl:7b")

    assert Path(result) == gguf
    assert downloaded == [gguf]


def test_migration_source_mode_is_noop(monkeypatch, tmp_path):
    monkeypatch.delenv("AMR_DATA_DIR", raising=False)
    monkeypatch.setattr(engine, "is_frozen", lambda: False)
    legacy, dest = _point_models(monkeypatch, tmp_path)
    _write(legacy / "model.gguf")

    assert engine.migrate_llamacpp_models() == []
    assert (legacy / "model.gguf").exists()
    assert not (dest / "model.gguf").exists()


def test_migration_moves_gguf_and_mmproj(monkeypatch, tmp_path):
    _enable_migration(monkeypatch)
    legacy, dest = _point_models(monkeypatch, tmp_path)
    _write(legacy / "model.gguf", b"gguf")
    _write(legacy / "vision.mmproj", b"mmproj")
    _write(legacy / "mmproj-custom.bin", b"custom")
    _write(legacy / "notes.txt", b"keep me")

    moved = engine.migrate_llamacpp_models()

    assert {p.name for p in moved} == {"model.gguf", "vision.mmproj", "mmproj-custom.bin"}
    assert (dest / "model.gguf").read_bytes() == b"gguf"
    assert (dest / "vision.mmproj").read_bytes() == b"mmproj"
    assert (dest / "mmproj-custom.bin").read_bytes() == b"custom"
    assert not (legacy / "model.gguf").exists()
    assert not (legacy / "vision.mmproj").exists()
    assert not (legacy / "mmproj-custom.bin").exists()
    assert (legacy / "notes.txt").exists()


def test_migration_skips_existing_destination(monkeypatch, tmp_path):
    _enable_migration(monkeypatch)
    legacy, dest = _point_models(monkeypatch, tmp_path)
    _write(legacy / "model.gguf", b"new")
    _write(dest / "model.gguf", b"existing")

    assert engine.migrate_llamacpp_models() == []
    assert (dest / "model.gguf").read_bytes() == b"existing"
    assert (legacy / "model.gguf").read_bytes() == b"new"


def test_cross_volume_copy_uses_part_and_keeps_source_on_failure(monkeypatch, tmp_path):
    src = _write(tmp_path / "legacy" / "model.gguf", b"payload")
    dst = tmp_path / "models" / "model.gguf"
    calls: list[tuple[Path, Path]] = []

    def fail_replace(old, new):
        calls.append((Path(old), Path(new)))
        raise OSError("cross-volume move not permitted")

    def fail_copy(fsrc, fdst, length=0):
        raise OSError("disk full")

    monkeypatch.setattr(engine.os, "replace", fail_replace)
    monkeypatch.setattr(engine.shutil, "copyfileobj", fail_copy)

    with pytest.raises(OSError):
        engine._move_model_file(src, dst)

    assert calls
    assert src.exists()
    assert src.read_bytes() == b"payload"
    assert not dst.exists()
    assert not dst.with_name(dst.name + ".part").exists()


def test_cross_volume_copy_completes_and_removes_source(monkeypatch, tmp_path):
    src = _write(tmp_path / "legacy" / "model.gguf", b"payload")
    dst = tmp_path / "models" / "model.gguf"
    real_replace = engine.os.replace

    def fake_replace(old, new):
        if str(old).endswith(".part"):
            return real_replace(old, new)
        raise OSError("cross-volume move not permitted")

    monkeypatch.setattr(engine.os, "replace", fake_replace)

    result = engine._move_model_file(src, dst)

    assert result == dst
    assert dst.read_bytes() == b"payload"
    assert not src.exists()
    assert not dst.with_name(dst.name + ".part").exists()


def test_migration_never_truncates_existing_destination(monkeypatch, tmp_path):
    _enable_migration(monkeypatch)
    legacy, dest = _point_models(monkeypatch, tmp_path)
    src = _write(legacy / "model.gguf", b"new")
    dst = _write(dest / "model.gguf", b"existing")

    engine.migrate_llamacpp_models()
    assert dst.read_bytes() == b"existing"
    assert src.read_bytes() == b"new"

    with pytest.raises(FileExistsError):
        engine._move_model_file(src, dst)
    assert dst.read_bytes() == b"existing"
    assert src.read_bytes() == b"new"


def test_migrate_paths_repairs_empty_config(monkeypatch, tmp_path):
    _enable_migration(monkeypatch)
    models = tmp_path / "models"
    monkeypatch.setattr(engine, "LLAMACPP_MODELS_DIR", models)
    monkeypatch.setattr(engine, "USER_DATA_DIR", tmp_path / "data")
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "setup.json").write_text(
        json.dumps({"onboarded": True}), encoding="utf-8"
    )

    gguf_name, mmproj_name = engine.LLAMACPP_GGUF_FILENAMES["qwen2.5vl:7b"]
    gguf = _write(models / gguf_name)
    mmproj = _write(models / mmproj_name)

    cfg = {"model": {"llamacpp": {"gguf_path": "", "mmproj_path": ""}}}
    monkeypatch.setattr(engine, "config", cfg)

    saved: list[int] = []
    monkeypatch.setattr(engine, "save_config", lambda: saved.append(1))

    assert engine.migrate_llamacpp_paths() is True
    assert cfg["model"]["llamacpp"]["gguf_path"] == str(gguf)
    assert cfg["model"]["llamacpp"]["mmproj_path"] == str(mmproj)
    assert saved == [1]


def test_wait_for_migration_timeout(monkeypatch):
    monkeypatch.setattr(engine, "is_model_migration_running", lambda: True)

    started = time.monotonic()
    assert engine.wait_for_model_migration(timeout=0.05) is False
    assert time.monotonic() - started < 5


def test_ensure_server_waits_for_migration(monkeypatch):
    calls: list[float] = []

    def fake_wait(timeout=300):
        calls.append(timeout)
        return True

    monkeypatch.setattr(engine, "wait_for_model_migration", fake_wait)
    monkeypatch.setattr(engine, "_llamacpp_server_running", lambda: True)

    assert engine.ensure_llamacpp_server() is True
    assert calls

    monkeypatch.setattr(engine, "wait_for_model_migration", lambda timeout=300: False)
    assert engine.ensure_llamacpp_server() is False
