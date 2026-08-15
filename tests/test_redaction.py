"""Redaction tests: secrets, API-key query strings, and absolute path masking."""

from unittest.mock import patch

from engine import (
    _redact_paths_in_text,
    _redact_recursive,
    _redact_sensitive,
    log_event,
    register_secret,
)


class TestRedactSensitive:
    def test_known_secret_masked(self):
        register_secret("sk-abcdef123456")
        out = _redact_sensitive("key=sk-abcdef123456 used")
        assert "sk-abcdef123456" not in out
        assert "[REDACTED]" in out

    def test_query_string_key_masked(self):
        out = _redact_sensitive("http://x/?api_key=ABC123&a=1")
        assert "ABC123" not in out
        assert "[REDACTED]" in out

    def test_empty_returns_empty(self):
        assert _redact_sensitive(None) == ""
        assert _redact_sensitive("") == ""

    def test_plain_text_unchanged(self):
        assert _redact_sensitive("hello world") == "hello world"


class TestRedactPaths:
    def test_windows_absolute_path_masked(self):
        out = _redact_paths_in_text("file at C:\\Users\\bob\\videos\\clip.mp4")
        assert "C:\\Users\\bob" not in out
        assert "[PATH]" in out

    def test_unix_absolute_path_masked(self):
        out = _redact_paths_in_text("file at /home/bob/videos/clip.mp4")
        assert "/home/bob" not in out
        assert "[PATH]" in out

    def test_bare_filename_not_masked(self):
        assert _redact_paths_in_text("clip.mp4") == "clip.mp4"

    def test_recursive_masks_nested_paths(self):
        data = {"asset": "clip.mp4", "new_path": "C:\\Users\\bob\\out\\clip.mp4"}
        with patch("engine.config", {"logging": {"redact_paths": True}}):
            out = _redact_recursive(data)
        assert out["asset"] == "clip.mp4"
        assert "C:\\Users\\bob" not in out["new_path"]
        assert "[PATH]" in out["new_path"]

    def test_recursive_respects_flag_off(self):
        data = {"new_path": "C:\\Users\\bob\\out\\clip.mp4"}
        with patch("engine.config", {"logging": {"redact_paths": False}}):
            out = _redact_recursive(data)
        assert "C:\\Users\\bob" in out["new_path"]


class TestLogEventRedaction:
    def test_log_event_redacts_absolute_path_in_file(self, caplog):
        import logging

        logger = logging.getLogger("test_log_event_path")
        logger.propagate = True
        logger.setLevel(logging.INFO)
        with caplog.at_level(logging.INFO):
            with patch("engine.config", {"logging": {"redact_paths": True}}):
                log_event(logger, "INFO", "file_committed",
                          file_name="C:\\Users\\bob\\videos\\clip.mp4",
                          details={"new_path": "C:\\Users\\bob\\out\\clip.mp4"})
        text = caplog.text
        assert "C:\\Users\\bob" not in text
        assert "[PATH]" in text
