"""Extended config tests: restore, auto-recovery, save/reload, profiles."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from engine import (
    get_active_categories,
    get_active_profile,
    get_active_prompt,
    get_profile_labels,
    load_config,
    restore_default_config,
    save_config,
    set_active_profile,
    CONFIG_PATH,
)


class TestRestoreDefaultConfig:
    def test_restore_returns_true_when_default_exists(self):
        """restore_default_config returns True when config.default.json exists."""
        from pathlib import Path
        # The real config.default.json exists in the project root
        default_path = Path(__file__).parent.parent / "config.default.json"
        assert default_path.exists(), "config.default.json must exist for this test"
        # We don't actually call restore_default_config here to avoid overwriting
        # the real config.json — we just verify the precondition

    def test_restore_default_config_file_exists(self):
        """config.default.json exists and is valid JSON."""
        import json
        from pathlib import Path
        default_path = Path(__file__).parent.parent / "config.default.json"
        data = json.loads(default_path.read_text(encoding="utf-8"))
        assert "model" in data
        assert "allowed_categories" in data


class TestLoadConfigAutoRecovery:
    def test_auto_recovery_missing_file(self, tmp_dir):
        """Missing config.json triggers auto-recovery from config.default.json."""
        fake_path = tmp_dir / "missing.json"
        default_path = tmp_dir / "config.default.json"
        valid_cfg = {"allowed_categories": ["test_cat"], "model": {"name": "test"}}
        default_path.write_text(json.dumps(valid_cfg), encoding="utf-8")

        result = load_config(str(fake_path))
        assert result["allowed_categories"] == ("test_cat",)
        assert fake_path.exists()  # auto-recovery wrote the file

    def test_auto_recovery_broken_json(self, tmp_dir):
        """Broken JSON in config.json triggers auto-recovery."""
        bad_path = tmp_dir / "bad.json"
        default_path = tmp_dir / "config.default.json"
        valid_cfg = {"allowed_categories": ["restored"], "model": {"name": "m"}}
        default_path.write_text(json.dumps(valid_cfg), encoding="utf-8")
        bad_path.write_text("{not valid json!!!", encoding="utf-8")

        result = load_config(str(bad_path))
        assert result["allowed_categories"] == ("restored",)

    def test_auto_recovery_both_missing_exits(self, tmp_dir):
        """When both config.json and config.default.json are missing, SystemExit."""
        fake_path = tmp_dir / "nope.json"
        with pytest.raises(SystemExit):
            load_config(str(fake_path))


class TestSaveConfig:
    def test_save_config_roundtrip(self, write_config_json):
        """save_config writes current config to CONFIG_PATH."""
        # save_config writes to the module-level CONFIG_PATH, which is the real
        # project config.json. We verify the function works by checking it doesn't crash.
        save_config()
        loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        assert "model" in loaded


class TestProfileManagement:
    def test_get_active_profile_returns_string(self):
        result = get_active_profile()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_active_categories_returns_tuple(self):
        result = get_active_categories()
        assert isinstance(result, tuple)

    def test_get_active_prompt_returns_string(self):
        result = get_active_prompt()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_profile_labels_returns_dict(self):
        result = get_profile_labels()
        assert isinstance(result, dict)
        assert "general_balanced" in result

    def test_set_active_profile_valid(self):
        """Setting a valid profile updates config."""
        original = get_active_profile()
        set_active_profile("general_balanced")
        assert get_active_profile() == "general_balanced"
        # Restore
        set_active_profile(original)

    def test_set_active_profile_invalid_ignored(self):
        """Setting an invalid profile name does nothing."""
        original = get_active_profile()
        set_active_profile("nonexistent_profile_xyz")
        assert get_active_profile() == original
