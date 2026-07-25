"""CLI helper function tests."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Import from cli.py - these are module-level functions
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from cli import _sanitize_category


class TestSanitizeCategory:
    def test_sanitize_category_normal(self):
        """Normal category name passes through."""
        assert _sanitize_category("landscapes_broll") == "landscapes_broll"

    def test_sanitize_category_lowercases(self):
        """Input is lowercased."""
        assert _sanitize_category("AERIAL_DRONE") == "aerial_drone"

    def test_sanitize_category_strips_special_chars(self):
        """Special characters are removed."""
        assert _sanitize_category("hello@world!") == "helloworld"

    def test_sanitize_category_empty_returns_none(self):
        """Empty result returns None."""
        assert _sanitize_category("!!!") is None
        assert _sanitize_category("") is None

    def test_sanitize_category_strips_leading_trailing_underscores(self):
        """Leading/trailing underscores are stripped."""
        assert _sanitize_category("_test_") == "test"

    def test_sanitize_category_preserves_hyphens(self):
        """Hyphens are preserved as valid chars."""
        assert _sanitize_category("my-category") == "my-category"


class TestPreviewDryRun:
    def test_preview_dry_run_no_crash(self, tmp_dir):
        """_preview_dry_run doesn't crash with valid inputs."""
        from cli import _preview_dry_run
        fake_file = tmp_dir / "test.mp4"
        fake_file.write_bytes(b"\x00")
        assets = [
            {
                "original_name": "test.mp4",
                "original_path": fake_file,
                "staged_name": "golden_hour_sunset",
                "category": "landscapes_broll",
                "tags": ["sunset", "golden"],
                "selected": True,
            }
        ]
        _preview_dry_run(assets, tmp_dir, False)


class TestCommitAll:
    def test_commit_all_no_assets_dry_run(self, tmp_dir):
        """_commit_all with empty list in dry_run mode returns without error."""
        from cli import _commit_all
        result = _commit_all([], tmp_dir, False, None, dry_run=True)
        # dry_run with empty list just prints preview and returns None
        assert result is None
