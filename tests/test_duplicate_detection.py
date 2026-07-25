"""Duplicate detection tests: find_duplicates, compute_asset_hash."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from engine import find_duplicates


def _fake_hash(path):
    """Return a deterministic fake hash based on filename."""
    name = Path(path).stem
    # Same name = same hash; different names = different hashes
    import hashlib
    return hashlib.md5(name.encode()).hexdigest()[:16]


class TestFindDuplicates:
    def test_find_duplicates_empty_input(self):
        """Empty asset list returns empty list."""
        result = find_duplicates([])
        assert result == []

    @patch("engine.compute_asset_hash", side_effect=_fake_hash)
    def test_find_duplicates_different_assets(self, mock_hash, tmp_dir):
        """Two different assets should not be flagged as duplicates."""
        img_a = tmp_dir / "red.png"
        img_b = tmp_dir / "blue.png"
        img_a.write_bytes(b"\x00" * 100)
        img_b.write_bytes(b"\x00" * 100)

        assets = [
            {"original_path": img_a, "original_name": "red.png"},
            {"original_path": img_b, "original_name": "blue.png"},
        ]
        result = find_duplicates(assets, threshold=5)
        assert result == []

    @patch("engine.compute_asset_hash", side_effect=_fake_hash)
    def test_find_duplicates_identical_names(self, mock_hash, tmp_dir):
        """Two assets with the same name produce the same hash → flagged."""
        img_a = tmp_dir / "sunset.png"
        img_b = tmp_dir / "sunset_copy.png"
        img_a.write_bytes(b"\x00" * 100)
        img_b.write_bytes(b"\x00" * 100)

        # Override: make both return same hash
        def same_hash(path):
            return "aaaa1111bbbb2222"

        mock_hash.side_effect = same_hash

        assets = [
            {"original_path": img_a, "original_name": "sunset.png"},
            {"original_path": img_b, "original_name": "sunset_copy.png"},
        ]
        result = find_duplicates(assets, threshold=10)
        assert len(result) == 1
        assert result[0]["distance"] == 0
        assert result[0]["confidence"] == 100

    @patch("engine.compute_asset_hash", side_effect=_fake_hash)
    def test_find_duplicates_threshold_controls_sensitivity(self, mock_hash, tmp_dir):
        """Lower threshold = stricter matching."""
        img_a = tmp_dir / "a.png"
        img_b = tmp_dir / "b.png"
        img_a.write_bytes(b"\x00" * 100)
        img_b.write_bytes(b"\x00" * 100)

        # Make hashes slightly different (distance ~5)
        call_count = [0]
        def slightly_different(path):
            call_count[0] += 1
            if call_count[0] == 1:
                return "aaaa1111bbbb2222"
            return "aaaa1111bbbb2233"  # 1 bit different

        mock_hash.side_effect = slightly_different

        assets = [
            {"original_path": img_a, "original_name": "a.png"},
            {"original_path": img_b, "original_name": "b.png"},
        ]
        strict = find_duplicates(assets, threshold=0)
        loose = find_duplicates(assets, threshold=10)
        assert len(strict) <= len(loose)

    def test_find_duplicates_unsupported_extension(self, tmp_dir):
        """Files with unsupported extensions return no hash, thus no duplicates."""
        txt_a = tmp_dir / "notes_a.txt"
        txt_b = tmp_dir / "notes_b.txt"
        txt_a.write_text("hello world", encoding="utf-8")
        txt_b.write_text("hello world", encoding="utf-8")

        assets = [
            {"original_path": txt_a, "original_name": "notes_a.txt"},
            {"original_path": txt_b, "original_name": "notes_b.txt"},
        ]
        result = find_duplicates(assets)
        assert result == []
