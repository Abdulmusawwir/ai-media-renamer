import tempfile
from pathlib import Path

import pytest

from engine import ALLOWED_CATEGORIES, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, load_config


class TestLoadConfig:
    def test_load_config_returns_dict(self):
        cfg = load_config()
        assert isinstance(cfg, dict)
        assert "allowed_categories" in cfg
        assert "model" in cfg

    def test_load_config_raises_on_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_path = Path(tmp) / "does_not_exist.json"
            with pytest.raises(SystemExit):
                load_config(str(fake_path))

    def test_load_config_invalid_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_file = Path(tmp) / "bad.json"
            bad_file.write_text("{invalid json}", encoding="utf-8")
            with pytest.raises(SystemExit):
                load_config(str(bad_file))


class TestExtensionsAndCategories:
    def test_video_extensions_are_tuple(self):
        assert isinstance(VIDEO_EXTENSIONS, tuple)

    def test_image_extensions_are_tuple(self):
        assert isinstance(IMAGE_EXTENSIONS, tuple)

    def test_allowed_categories_are_tuple(self):
        assert isinstance(ALLOWED_CATEGORIES, tuple)
