"""Data survival when an existing 2.1.x profile is opened by 2.2.x.

The desktop installer upgrades in place: it must never replace an existing
config, sessions or undo log with bundled defaults. This test simulates that
upgrade by pointing ``engine.CONFIG_PATH`` at a pre-existing data directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import engine

ROOT = Path(__file__).resolve().parent.parent


def test_existing_config_and_sessions_survive_upgrade(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    cfg = json.loads((ROOT / "config.default.json").read_text(encoding="utf-8"))
    cfg["naming"]["case_style"] = "kebab-case"
    cfg["model"]["llamacpp"]["gguf_path"] = str(tmp_path / "models" / "vision.gguf")
    cfg["prompt_profiles"]["active"] = "cinematography"
    (data / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    sessions = data / "sessions"
    sessions.mkdir()
    (sessions / "old-session.json").write_text(
        json.dumps({"staged_assets": [], "created": "2026-11-01T00:00:00"}),
        encoding="utf-8",
    )
    undo = data / "undo_log.jsonl"
    undo.write_text(json.dumps({"batch_id": "old", "records": []}) + "\n", encoding="utf-8")

    monkeypatch.setattr(engine, "CONFIG_PATH", data / "config.json")
    loaded = engine.load_config(quiet=True)

    assert loaded["naming"]["case_style"] == "kebab-case"
    assert loaded["model"]["llamacpp"]["gguf_path"] == str(tmp_path / "models" / "vision.gguf")
    assert loaded["prompt_profiles"]["active"] == "cinematography"
    assert (sessions / "old-session.json").is_file()
    assert undo.read_text(encoding="utf-8").strip()
