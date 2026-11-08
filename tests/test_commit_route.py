"""Tests for POST /api/commit destination handling and undo logging."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import engine
from server.main import app


class _FakeExifToolSession:
    def execute(self, _args):
        return ""

    def execute_batch(self, args):
        return ["" for _ in args]

    def close(self):
        pass


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(engine, "ExifToolSession", lambda: _FakeExifToolSession())
    monkeypatch.setattr(engine, "UNDO_DIR", tmp_path / "undo")
    monkeypatch.setattr(engine, "UNDO_LOG_FILE", tmp_path / "undo" / "undo.jsonl")
    return TestClient(app)


def _asset(path: Path, staged_name: str, category: str = "clips") -> dict:
    return {
        "original_name": path.name,
        "original_path": str(path),
        "staged_name": staged_name,
        "category": category,
        "tags": ["tag"],
        "summary": "summary",
    }


def _file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * 32)
    return path


def test_commit_without_target_renames_in_place(client, tmp_path: Path):
    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    clip = _file(a_dir / "clip.mp4")
    photo = _file(b_dir / "photo.jpg")

    res = client.post(
        "/api/commit",
        json={
            "assets": [_asset(clip, "clip_two"), _asset(photo, "photo_two")],
            "sort_folders": False,
            "skip_metadata": True,
        },
    )

    assert res.status_code == 200
    body = res.json()
    assert body["committed"] == 2
    assert (a_dir / "clip_two.mp4").exists()
    assert (b_dir / "photo_two.jpg").exists()
    assert not clip.exists()
    assert not photo.exists()
    assert not (Path.cwd() / "clip_two.mp4").exists()


def test_commit_without_target_logs_undo_batch(client, tmp_path: Path):
    a_dir = tmp_path / "a"
    clip = _file(a_dir / "clip.mp4")

    client.post(
        "/api/commit",
        json={
            "assets": [_asset(clip, "clip_two")],
            "sort_folders": False,
            "skip_metadata": True,
        },
    )

    batches = engine.list_undo_batches()
    assert len(batches) == 1
    records = batches[0]["records"]
    assert len(records) == 1
    assert records[0]["original_path"] == str(clip)
    assert records[0]["new_path"].endswith("clip_two.mp4")
    assert records[0]["injected_tags"] == []


def test_rollback_restores_in_place_commit(client, tmp_path: Path):
    a_dir = tmp_path / "a"
    clip = _file(a_dir / "clip.mp4")

    client.post(
        "/api/commit",
        json={
            "assets": [_asset(clip, "clip_two")],
            "sort_folders": False,
            "skip_metadata": True,
        },
    )
    assert (a_dir / "clip_two.mp4").exists()

    res = client.post("/api/rollback")

    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert clip.exists()
    assert not (a_dir / "clip_two.mp4").exists()


def test_commit_with_explicit_target_dir(client, tmp_path: Path):
    a_dir = tmp_path / "a"
    out_dir = tmp_path / "out"
    clip = _file(a_dir / "clip.mp4")

    res = client.post(
        "/api/commit",
        json={
            "assets": [_asset(clip, "clip_two", category="drone")],
            "target_dir": str(out_dir),
            "sort_folders": True,
            "skip_metadata": True,
        },
    )

    assert res.status_code == 200
    assert (out_dir / "drone" / "clip_two.mp4").exists()
    assert not clip.exists()
