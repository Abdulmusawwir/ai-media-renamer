"""Integration tests for FFmpeg/ExifTool extraction (skipped if tools missing)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from engine import (
    _NO_WINDOW,
    _has_audio_track,
    extract_audio_from_video,
    process_image_to_base64,
    process_video_to_base64,
    transcribe_audio,
)

_HAS_FFMPEG = shutil.which("ffmpeg") is not None
_HAS_EXIFTOOL = shutil.which("exiftool") is not None


def _create_test_video(path: Path, duration: float = 2.0, with_audio: bool = True) -> bool:
    """Create a tiny synthetic test video via FFmpeg."""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=black:s=64x64:d={duration}",
    ]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"]
        cmd += ["-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if with_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k"]
    cmd += [str(path)]
    try:
        result = subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW)
        return result.returncode == 0 and path.exists()
    except Exception:
        return False


def _create_test_image(path: Path) -> bool:
    """Create a tiny synthetic test image via FFmpeg."""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=32x32:d=1",
        "-frames:v", "1",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW)
        return result.returncode == 0 and path.exists()
    except Exception:
        return False


@pytest.mark.skipif(not _HAS_FFMPEG, reason="FFmpeg not installed")
class TestVideoExtraction:
    def test_process_video_to_base64_returns_string(self, tmp_path: Path):
        video = tmp_path / "test.mp4"
        assert _create_test_video(video)
        result = process_video_to_base64(video, hw_accel=None)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_process_video_no_audio(self, tmp_path: Path):
        video = tmp_path / "test_no_audio.mp4"
        assert _create_test_video(video, with_audio=False)
        result = process_video_to_base64(video, hw_accel=None)
        assert isinstance(result, str)

    def test_has_audio_track_true(self, tmp_path: Path):
        video = tmp_path / "test_audio.mp4"
        assert _create_test_video(video, with_audio=True)
        assert _has_audio_track(video) is True

    def test_has_audio_track_false(self, tmp_path: Path):
        video = tmp_path / "test_no_audio.mp4"
        assert _create_test_video(video, with_audio=False)
        assert _has_audio_track(video) is False

    def test_extract_audio_from_video(self, tmp_path: Path):
        video = tmp_path / "test.mp4"
        assert _create_test_video(video, with_audio=True)
        wav = extract_audio_from_video(video)
        assert wav is not None
        assert wav.exists()
        assert wav.suffix == ".wav"
        wav.unlink()

    def test_extract_audio_no_track(self, tmp_path: Path):
        video = tmp_path / "test_no_audio.mp4"
        assert _create_test_video(video, with_audio=False)
        wav = extract_audio_from_video(video)
        assert wav is None


@pytest.mark.skipif(not _HAS_FFMPEG, reason="FFmpeg not installed")
class TestVideoCpuFallback:
    def test_fallback_retries_cpu_and_logs(self, tmp_path: Path, monkeypatch):
        video = tmp_path / "test.mp4"
        fallback_log: dict[str, bool] = {}
        attempts = []

        def fake_extract(path, hw_accel):
            attempts.append(hw_accel)
            return None if hw_accel == "cuda" else "ZmFrZQ=="

        monkeypatch.setattr("engine._extract_frame_to_base64", fake_extract)
        monkeypatch.setattr("engine.get_video_duration", lambda p: 10.0)

        result = process_video_to_base64(video, "cuda", fallback_log)

        assert result == "ZmFrZQ=="
        assert attempts == ["cuda", None]
        assert video.name in fallback_log

    def test_no_fallback_when_hw_succeeds(self, tmp_path: Path, monkeypatch):
        video = tmp_path / "test.mp4"
        fallback_log: dict[str, bool] = {}
        attempts = []

        def fake_extract(path, hw_accel):
            attempts.append(hw_accel)
            return "ZmFrZQ=="

        monkeypatch.setattr("engine._extract_frame_to_base64", fake_extract)
        monkeypatch.setattr("engine.get_video_duration", lambda p: 10.0)

        result = process_video_to_base64(video, "cuda", fallback_log)

        assert result == "ZmFrZQ=="
        assert attempts == ["cuda"]
        assert fallback_log == {}

    def test_plain_cpu_does_not_log_fallback(self, tmp_path: Path, monkeypatch):
        video = tmp_path / "test.mp4"
        fallback_log: dict[str, bool] = {}

        def fake_extract(path, hw_accel):
            return "ZmFrZQ=="

        monkeypatch.setattr("engine._extract_frame_to_base64", fake_extract)
        monkeypatch.setattr("engine.get_video_duration", lambda p: 10.0)

        result = process_video_to_base64(video, None, fallback_log)

        assert result == "ZmFrZQ=="
        assert fallback_log == {}


@pytest.mark.skipif(not _HAS_FFMPEG, reason="FFmpeg not installed")
class TestImageExtraction:
    def test_process_image_to_base64_returns_string(self, tmp_path: Path):
        img = tmp_path / "test.png"
        assert _create_test_image(img)
        result = process_image_to_base64(img)
        assert isinstance(result, str)
        assert len(result) > 100


@pytest.mark.skipif(not _HAS_FFMPEG, reason="FFmpeg not installed")
class TestTranscribeAudio:
    def test_transcribe_missing_file(self):
        result = transcribe_audio("/nonexistent/path.wav")
        assert result["text"] == ""
        assert "error" in result

    def test_transcribe_returns_dict(self, tmp_path: Path):
        video = tmp_path / "test.mp4"
        assert _create_test_video(video, with_audio=True, duration=2.0)
        wav = extract_audio_from_video(video)
        assert wav is not None
        result = transcribe_audio(wav, model_size="tiny")
        assert "text" in result
        assert "language" in result
        assert "duration" in result
        wav.unlink()
