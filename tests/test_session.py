"""Session persistence tests: save, load, list."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from engine import SESSION_DIR, load_session, list_sessions, save_session


class TestSaveSession:
    def test_save_session_creates_file(self, tmp_dir, sample_staged_assets):
        """save_session writes a JSON file to SESSION_DIR."""
        with patch("engine.SESSION_DIR", tmp_dir):
            settings = {"case_style": "title_case", "template": "{topic}_{description}"}
            uploaded_files = {"sunset.mp4": Path("/fake/sunset.mp4")}
            save_session(sample_staged_assets, uploaded_files, settings)

            sessions = list(tmp_dir.glob("session_*.json"))
            assert len(sessions) == 1

            data = json.loads(sessions[0].read_text(encoding="utf-8"))
            assert data["version"] == 1
            assert "created" in data
            assert len(data["staged_assets"]) == 2
            assert data["settings"]["case_style"] == "title_case"

    def test_save_session_serializes_paths(self, tmp_dir, sample_staged_assets):
        """Original paths are serialized as strings (not Path objects)."""
        with patch("engine.SESSION_DIR", tmp_dir):
            save_session(sample_staged_assets, {}, {})
            sessions = list(tmp_dir.glob("session_*.json"))
            data = json.loads(sessions[0].read_text(encoding="utf-8"))
            for asset in data["staged_assets"]:
                assert isinstance(asset["original_path"], str)


class TestLoadSession:
    def test_load_session_roundtrip(self, tmp_dir, sample_staged_assets):
        """Save then load returns matching data."""
        with patch("engine.SESSION_DIR", tmp_dir):
            save_session(sample_staged_assets, {}, {"case_style": "snake_case"})
            sessions = list(tmp_dir.glob("session_*.json"))
            result = load_session(sessions[0])

            assert len(result["staged_assets"]) == 2
            assert result["settings"]["case_style"] == "snake_case"
            assert result["missing_files"] == []

    def test_load_session_missing_files(self, tmp_dir):
        """Load session with files that no longer exist reports missing_files."""
        fake_path = tmp_dir / "deleted_video.mp4"
        asset = {
            "original_name": "deleted_video.mp4",
            "original_path": str(fake_path),  # doesn't exist on disk
            "staged_name": "test",
            "category": "test",
            "tags": [],
            "summary": "test",
            "selected": True,
        }
        with patch("engine.SESSION_DIR", tmp_dir):
            save_session([asset], {}, {})
            sessions = list(tmp_dir.glob("session_*.json"))
            result = load_session(sessions[0])

            assert len(result["staged_assets"]) == 0
            assert "deleted_video.mp4" in result["missing_files"]


class TestListSessions:
    def test_list_sessions_empty_dir(self, tmp_dir):
        """list_sessions returns empty list when no sessions exist."""
        with patch("engine.SESSION_DIR", tmp_dir):
            result = list_sessions()
            assert result == []

    def test_list_sessions_sorted_newest_first(self, tmp_dir, sample_staged_assets):
        """Sessions are returned newest first."""
        with patch("engine.SESSION_DIR", tmp_dir):
            save_session(sample_staged_assets, {}, {})
            # Create a second session with a slight delay in filename
            (tmp_dir / "session_2025-01-01_000000.json").write_text(
                json.dumps({"staged_assets": [], "created": "2025-01-01_000000"}), encoding="utf-8"
            )
            result = list_sessions()
            assert len(result) >= 2
            # Newest first: the auto-named one (today) should be before 2025-01-01
            assert result[0]["created"] >= result[-1]["created"]

    def test_list_sessions_skips_corrupt(self, tmp_dir):
        """Corrupt session files are silently skipped."""
        with patch("engine.SESSION_DIR", tmp_dir):
            (tmp_dir / "session_bad.json").write_text("NOT JSON!!!", encoding="utf-8")
            (tmp_dir / "session_good.json").write_text(
                json.dumps({"staged_assets": [], "created": "2025-06-01_120000"}), encoding="utf-8"
            )
            result = list_sessions()
            assert len(result) == 1
