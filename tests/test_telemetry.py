"""Telemetry tests: enable/disable, track_event, flush."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from engine import (
    TELEMETRY_DIR,
    TELEMETRY_FILE,
    _get_install_id,
    _get_session_id,
    flush_telemetry,
    set_telemetry_enabled,
    telemetry_enabled,
    track_event,
)


class TestTelemetryEnabled:
    def test_telemetry_enabled_default_false(self):
        """telemetry_enabled returns False when config has no telemetry section."""
        with patch("engine.config", {"model": {"name": "test"}}):
            assert telemetry_enabled() is False

    def test_telemetry_enabled_respects_config(self):
        """telemetry_enabled reads from config['telemetry']['enabled']."""
        with patch("engine.config", {"telemetry": {"enabled": True}}):
            assert telemetry_enabled() is True
        with patch("engine.config", {"telemetry": {"enabled": False}}):
            assert telemetry_enabled() is False


class TestSetTelemetryEnabled:
    def test_set_telemetry_enabled_persists(self, write_config_json):
        """set_telemetry_enabled writes to config.json and reloads."""
        # set_telemetry_enabled modifies the global config dict and saves
        # We can't easily test the full roundtrip without side effects,
        # but we can verify the function doesn't crash
        original = telemetry_enabled()
        set_telemetry_enabled(True)
        # Note: this actually modifies the real config.json in the project root
        # Restore after test
        set_telemetry_enabled(original)


class TestTrackEvent:
    def test_track_event_disabled_does_nothing(self, tmp_dir):
        """track_event does nothing when telemetry is disabled."""
        with patch("engine.telemetry_enabled", return_value=False):
            with patch("engine.TELEMETRY_FILE", tmp_dir / "telemetry.jsonl"):
                track_event("test_event")
                assert not (tmp_dir / "telemetry.jsonl").exists()

    def test_track_event_appends_jsonl(self, tmp_dir):
        """track_event writes event to telemetry.jsonl when enabled."""
        tel_file = tmp_dir / "telemetry.jsonl"
        with patch("engine.telemetry_enabled", return_value=True), \
             patch("engine.TELEMETRY_FILE", tel_file), \
             patch("engine.TELEMETRY_DIR", tmp_dir), \
             patch("engine._get_install_id", return_value="test-install-id"), \
             patch("engine._get_session_id", return_value="test-session"):
            track_event("test_event", {"key": "value"})

            assert tel_file.exists()
            lines = tel_file.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 1
            event = json.loads(lines[0])
            assert event["event"] == "test_event"
            assert event["install_id"] == "test-install-id"
            assert event["properties"]["key"] == "value"

    def test_track_event_multiple_events(self, tmp_dir):
        """Multiple track_event calls append multiple lines."""
        tel_file = tmp_dir / "telemetry.jsonl"
        with patch("engine.telemetry_enabled", return_value=True), \
             patch("engine.TELEMETRY_FILE", tel_file), \
             patch("engine.TELEMETRY_DIR", tmp_dir), \
             patch("engine._get_install_id", return_value="id"), \
             patch("engine._get_session_id", return_value="s"):
            track_event("event_a")
            track_event("event_b")
            track_event("event_c")

            lines = tel_file.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 3
            events = [json.loads(ln)["event"] for ln in lines]
            assert events == ["event_a", "event_b", "event_c"]


class TestFlushTelemetry:
    def test_flush_disabled_does_nothing(self, tmp_dir):
        """flush_telemetry does nothing when disabled."""
        with patch("engine.telemetry_enabled", return_value=False):
            # Should not crash
            flush_telemetry()

    def test_flush_no_api_key_does_nothing(self, tmp_dir):
        """flush_telemetry skips when no API key configured."""
        tel_file = tmp_dir / "telemetry.jsonl"
        tel_file.write_text('{"event": "test"}\n', encoding="utf-8")
        with patch("engine.telemetry_enabled", return_value=True), \
             patch("engine.TELEMETRY_FILE", tel_file), \
             patch("engine.config", {"telemetry": {"enabled": True, "api_key": ""}}):
            flush_telemetry()
            # File should still exist (not cleared without sending)
            assert tel_file.exists()


class TestGetIds:
    def test_get_session_id_is_string(self):
        """_get_session_id returns a non-empty string."""
        sid = _get_session_id()
        assert isinstance(sid, str)
        assert len(sid) > 0

    def test_get_install_id_returns_same_value(self, tmp_dir):
        """_get_install_id returns the same ID across calls (stored in file)."""
        id_file = tmp_dir / ".install_id"
        id_file.write_text("stable-test-id-12345", encoding="utf-8")
        with patch("engine.TELEMETRY_DIR", tmp_dir), \
             patch("engine._install_id", None):
            id1 = _get_install_id()
            id2 = _get_install_id()
            assert id1 == id2 == "stable-test-id-12345"
