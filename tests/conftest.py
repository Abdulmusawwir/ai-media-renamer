"""Shared fixtures for ai-media-renamer tests."""

import json
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def sample_config(tmp_dir):
    """Return a minimal valid config dict (not written to disk)."""
    return {
        "allowed_categories": ["landscapes_broll", "aerial_drone", "abstract_art"],
        "video_extensions": [".mp4", ".mov", ".avi"],
        "image_extensions": [".jpg", ".jpeg", ".png"],
        "model": {
            "name": "qwen2.5vl:7b",
            "temperature": 0.15,
            "num_ctx": 8192,
            "keep_alive": "1h",
        },
        "naming": {"case_style": "title_case", "max_filename_chars": 0},
        "naming_templates": {
            "default": "{topic}_{description}",
            "short": "{topic}_{description}",
        },
        "preview": {"extraction_workers": 0, "image_max_edge": 1024},
        "logging": {"directory": str(tmp_dir / "logs"), "max_upload_size": 10737418240},
        "prompt_profiles": {
            "active": "general_balanced",
            "profiles": {
                "general_balanced": {
                    "label": "General Purpose",
                    "prompt": "Describe the scene.",
                    "allowed_categories": [],
                },
                "custom": {
                    "label": "Custom Prompt",
                    "prompt": "",
                    "allowed_categories": [],
                },
            },
        },
        "telemetry": {"enabled": False, "api_key": ""},
    }


@pytest.fixture
def sample_staged_assets(tmp_dir):
    """Return a list of two sample staged asset dicts with real files."""
    file_a = tmp_dir / "sunset.mp4"
    file_b = tmp_dir / "ocean.jpg"
    file_a.write_bytes(b"\x00" * 100)
    file_b.write_bytes(b"\x00" * 100)

    return [
        {
            "original_name": "sunset.mp4",
            "original_path": file_a,
            "staged_name": "golden_hour_coast",
            "category": "landscapes_broll",
            "tags": ["sunset", "golden_hour", "coast"],
            "summary": "A warm sunset over the ocean.",
            "selected": True,
        },
        {
            "original_name": "ocean.jpg",
            "original_path": file_b,
            "staged_name": "deep_blue_waves",
            "category": "landscapes_broll",
            "tags": ["ocean", "waves", "blue"],
            "summary": "Deep blue ocean waves crashing.",
            "selected": True,
        },
    ]


@pytest.fixture
def write_config_json(tmp_dir, sample_config):
    """Write sample_config to tmp_dir/config.json and return the path."""
    cfg_path = tmp_dir / "config.json"
    cfg_path.write_text(json.dumps(sample_config, indent=2), encoding="utf-8")
    return cfg_path
