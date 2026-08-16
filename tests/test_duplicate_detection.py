"""Duplicate detection tests: find_duplicates, compute_asset_hash."""

from pathlib import Path
from unittest.mock import patch

from engine import _chromaprint_similarity, find_duplicates


def _fake_phash(path):
    """Return a deterministic fake pHash based on filename."""
    name = Path(path).stem
    import hashlib
    return f"phash:{hashlib.md5(name.encode()).hexdigest()[:16]}"


class TestFindDuplicates:
    def test_find_duplicates_empty_input(self):
        """Empty asset list returns empty list."""
        result = find_duplicates([])
        assert result == []

    @patch("engine.compute_asset_hash", side_effect=_fake_phash)
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

    @patch("engine.compute_asset_hash", side_effect=_fake_phash)
    def test_find_duplicates_identical_names(self, mock_hash, tmp_dir):
        """Two assets with the same name produce the same hash -> flagged."""
        img_a = tmp_dir / "sunset.png"
        img_b = tmp_dir / "sunset_copy.png"
        img_a.write_bytes(b"\x00" * 100)
        img_b.write_bytes(b"\x00" * 100)

        def same_hash(path):
            return "phash:aaaa1111bbbb2222"

        mock_hash.side_effect = same_hash

        assets = [
            {"original_path": img_a, "original_name": "sunset.png"},
            {"original_path": img_b, "original_name": "sunset_copy.png"},
        ]
        result = find_duplicates(assets, threshold=10)
        assert len(result) == 1
        assert result[0]["distance"] == 0
        assert result[0]["confidence"] == 100
        assert result[0]["hash_type"] == "phash"

    @patch("engine.compute_asset_hash", side_effect=_fake_phash)
    def test_find_duplicates_threshold_controls_sensitivity(self, mock_hash, tmp_dir):
        """Lower threshold = stricter matching."""
        img_a = tmp_dir / "a.png"
        img_b = tmp_dir / "b.png"
        img_a.write_bytes(b"\x00" * 100)
        img_b.write_bytes(b"\x00" * 100)

        call_count = [0]
        def slightly_different(path):
            call_count[0] += 1
            if call_count[0] == 1:
                return "phash:aaaa1111bbbb2222"
            return "phash:aaaa1111bbbb2233"

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
        xyz_a = tmp_dir / "data_a.xyz"
        xyz_b = tmp_dir / "data_b.xyz"
        xyz_a.write_bytes(b"\x00" * 100)
        xyz_b.write_bytes(b"\x00" * 100)

        assets = [
            {"original_path": xyz_a, "original_name": "data_a.xyz"},
            {"original_path": xyz_b, "original_name": "data_b.xyz"},
        ]
        result = find_duplicates(assets)
        assert result == []

    def test_find_duplicates_sha256_identical_text(self, tmp_dir):
        """Two text files with identical content are flagged as duplicates."""
        txt_a = tmp_dir / "notes_a.txt"
        txt_b = tmp_dir / "notes_b.txt"
        txt_a.write_text("hello world", encoding="utf-8")
        txt_b.write_text("hello world", encoding="utf-8")

        assets = [
            {"original_path": txt_a, "original_name": "notes_a.txt"},
            {"original_path": txt_b, "original_name": "notes_b.txt"},
        ]
        result = find_duplicates(assets)
        assert len(result) == 1
        assert result[0]["hash_type"] == "sha256"
        assert result[0]["confidence"] == 100
        assert result[0]["distance"] == 0

    def test_find_duplicates_sha256_different_text(self, tmp_dir):
        """Two text files with different content are NOT flagged."""
        txt_a = tmp_dir / "notes_a.txt"
        txt_b = tmp_dir / "notes_b.txt"
        txt_a.write_text("hello world", encoding="utf-8")
        txt_b.write_text("goodbye world", encoding="utf-8")

        assets = [
            {"original_path": txt_a, "original_name": "notes_a.txt"},
            {"original_path": txt_b, "original_name": "notes_b.txt"},
        ]
        result = find_duplicates(assets)
        assert result == []

    def test_find_duplicates_mixed_types_no_cross_match(self, tmp_dir):
        """Documents and media hashes are not compared against each other."""
        img = tmp_dir / "photo.png"
        img.write_bytes(b"\x00" * 100)
        txt = tmp_dir / "notes.txt"
        txt.write_text("hello world", encoding="utf-8")

        assets = [
            {"original_path": img, "original_name": "photo.png"},
            {"original_path": txt, "original_name": "notes.txt"},
        ]
        result = find_duplicates(assets)
        assert result == []

    def test_find_duplicates_chromaprint_identical(self):
        """Two identical Chromaprint fingerprints are flagged."""
        fp = "chromaprint:1234,5678,9012:30.0"

        def mock_hash(path):
            return fp

        with patch("engine.compute_asset_hash", side_effect=mock_hash):
            assets = [
                {"original_path": Path("/fake/a.mp3"), "original_name": "a.mp3"},
                {"original_path": Path("/fake/b.mp3"), "original_name": "b.mp3"},
            ]
            result = find_duplicates(assets)
            assert len(result) == 1
            assert result[0]["hash_type"] == "chromaprint"
            assert result[0]["confidence"] == 100

    def test_find_duplicates_chromaprint_similar(self):
        """Two similar Chromaprint fingerprints (>= 0.85) are flagged."""
        def mock_hash(path):
            name = Path(path).stem
            if name == "a":
                return "chromaprint:100,200,300,400,500,600,700:30.0"
            return "chromaprint:100,200,300,400,500,600,999:30.0"

        with patch("engine.compute_asset_hash", side_effect=mock_hash):
            assets = [
                {"original_path": Path("/fake/a.mp3"), "original_name": "a.mp3"},
                {"original_path": Path("/fake/b.mp3"), "original_name": "b.mp3"},
            ]
            result = find_duplicates(assets)
            assert len(result) == 1
            assert result[0]["hash_type"] == "chromaprint"

    def test_find_duplicates_chromaprint_different(self):
        """Two different Chromaprint fingerprints (< 0.85) are NOT flagged."""
        def mock_hash(path):
            name = Path(path).stem
            if name == "a":
                return "chromaprint:1,2,3:30.0"
            return "chromaprint:4,5,6:30.0"

        with patch("engine.compute_asset_hash", side_effect=mock_hash):
            assets = [
                {"original_path": Path("/fake/a.mp3"), "original_name": "a.mp3"},
                {"original_path": Path("/fake/b.mp3"), "original_name": "b.mp3"},
            ]
            result = find_duplicates(assets)
            assert result == []


class TestChromaprintSimilarity:
    def test_identical(self):
        fp = "chromaprint:100,200,300:30.0"
        assert _chromaprint_similarity(fp, fp) == 1.0

    def test_similar(self):
        a = "chromaprint:100,200,300,400,500,600:30.0"
        b = "chromaprint:100,200,300,400,500,999:30.0"
        assert abs(_chromaprint_similarity(a, b) - 5/6) < 0.01

    def test_different(self):
        a = "chromaprint:1,2,3:30.0"
        b = "chromaprint:4,5,6:30.0"
        assert _chromaprint_similarity(a, b) == 0.0

    def test_empty(self):
        a = "chromaprint::30.0"
        b = "chromaprint:1,2,3:30.0"
        assert _chromaprint_similarity(a, b) == 0.0

    def test_malformed(self):
        assert _chromaprint_similarity("bad", "format") == 0.0

    def test_different_lengths(self):
        a = "chromaprint:100,200,300:30.0"
        b = "chromaprint:100,200:30.0"
        assert _chromaprint_similarity(a, b) == 1.0
