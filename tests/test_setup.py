"""Tests for the onboarding/setup features: use-case dependency matrix,
model catalog + recommendations, registry validation, whisper pre-download,
setup-profile persistence, and profile-aware environment checks."""

import json
import sys
import types

import pytest

import engine

# ---------------------------------------------------------------------------
# Use-case dependency matrix
# ---------------------------------------------------------------------------

class TestUseCasesNeeds:
    def test_documents_need_only_text_model(self):
        needs = engine.use_cases_needs(["documents"])
        assert needs == {"text_model"}

    def test_spreadsheets_need_only_text_model(self):
        needs = engine.use_cases_needs(["spreadsheets"])
        assert needs == {"text_model"}

    def test_videos_need_media_toolchain(self):
        needs = engine.use_cases_needs(["videos"])
        assert {"ffmpeg", "exiftool", "vision_model", "whisper"} <= needs

    def test_photos_need_ffmpeg_exiftool_vision(self):
        needs = engine.use_cases_needs(["photos"])
        assert needs == {"ffmpeg", "exiftool", "vision_model"}

    def test_audio_need_exiftool_text_whisper(self):
        needs = engine.use_cases_needs(["audio"])
        assert needs == {"exiftool", "text_model", "whisper"}

    def test_empty_profile_needs_nothing(self):
        assert engine.use_cases_needs([]) == set()

    def test_unknown_key_is_ignored(self):
        assert engine.use_cases_needs(["not-a-use-case"]) == set()

    def test_documents_do_not_require_exiftool(self):
        # The user-facing guarantee: documents-only users skip ExifTool (and FFmpeg).
        needs = engine.use_cases_needs(["documents"])
        assert "exiftool" not in needs
        assert "ffmpeg" not in needs

    def test_combined_profile_unions_needs(self):
        needs = engine.use_cases_needs(["photos", "documents"])
        assert "vision_model" in needs
        assert "text_model" in needs


# ---------------------------------------------------------------------------
# Model catalog
# ---------------------------------------------------------------------------

class TestModelCatalog:
    def test_catalog_has_vision_and_text_kinds(self):
        kinds = {m["kind"] for m in engine.MODEL_CATALOG}
        assert kinds == {"vision", "text"}

    def test_every_entry_has_required_fields(self):
        for m in engine.MODEL_CATALOG:
            assert m["name"] and ":" in m["name"]
            assert m["label"] and m["size"] and m["desc"]
            assert m["quality"] in ("Best", "Good", "Basic")
            assert m["speed"]

    def test_vision_and_text_recs_exist(self):
        rec = engine.recommended_models(["videos", "documents"])
        assert rec["vision"] in {m["name"] for m in engine.MODEL_CATALOG if m["kind"] == "vision"}
        assert rec["text"] in {m["name"] for m in engine.MODEL_CATALOG if m["kind"] == "text"}


# ---------------------------------------------------------------------------
# recommended_models / _has_gpu
# ---------------------------------------------------------------------------

class TestRecommendedModels:
    def test_documents_only_recommends_text(self, monkeypatch):
        monkeypatch.setattr(engine, "_has_gpu", lambda: False)
        rec = engine.recommended_models(["documents"])
        assert "vision" not in rec
        assert rec["text"] == "qwen2.5:3b"

    def test_gpu_vision_recommendation_is_7b(self, monkeypatch):
        monkeypatch.setattr(engine, "_has_gpu", lambda: True)
        rec = engine.recommended_models(["videos"])
        assert rec["vision"] == "qwen2.5vl:7b"

    def test_no_gpu_vision_recommendation_is_3b(self, monkeypatch):
        monkeypatch.setattr(engine, "_has_gpu", lambda: False)
        rec = engine.recommended_models(["videos"])
        assert rec["vision"] == "qwen2.5vl:3b"


# ---------------------------------------------------------------------------
# validate_ollama_model (registry tag existence)
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class TestValidateOllamaModel:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        engine._model_tag_exists.cache_clear()
        yield
        engine._model_tag_exists.cache_clear()

    def test_tag_exists(self, monkeypatch):
        monkeypatch.setattr(engine.requests, "get",
                            lambda url, timeout=10: _FakeResp(200, {"tags": ["7b", "3b"]}))
        assert engine.validate_ollama_model("qwen2.5vl:7b") is True

    def test_tag_missing(self, monkeypatch):
        monkeypatch.setattr(engine.requests, "get",
                            lambda url, timeout=10: _FakeResp(200, {"tags": ["3b"]}))
        assert engine.validate_ollama_model("qwen2.5vl:7b") is False

    def test_offline_returns_none(self, monkeypatch):
        def boom(url, timeout=10):
            raise OSError("offline")
        monkeypatch.setattr(engine.requests, "get", boom)
        assert engine.validate_ollama_model("qwen2.5vl:7b") is None

    def test_latest_fallback(self, monkeypatch):
        monkeypatch.setattr(engine.requests, "get",
                            lambda url, timeout=10: _FakeResp(200, {"tags": ["latest"]}))
        assert engine.validate_ollama_model("moondream") is True


# ---------------------------------------------------------------------------
# pre_download_whisper
# ---------------------------------------------------------------------------

class TestPreDownloadWhisper:
    @pytest.fixture(autouse=True)
    def _fake_hf_hub(self, monkeypatch):
        fake = types.ModuleType("huggingface_hub")
        fake.snapshot_download = lambda repo_id: "/cache/dir"
        monkeypatch.setitem(sys.modules, "huggingface_hub", fake)
        yield
        monkeypatch.delitem(sys.modules, "huggingface_hub", raising=False)

    def test_success(self, monkeypatch):
        called = {}

        def fake_snapshot(repo_id):
            called["repo"] = repo_id
            return "/some/cache/dir"
        monkeypatch.setattr(sys.modules["huggingface_hub"], "snapshot_download", fake_snapshot)
        assert engine.pre_download_whisper("base") is True
        assert called["repo"] == "Systran/faster-whisper-base"

    def test_failure_returns_false(self, monkeypatch):
        def boom(repo_id):
            raise OSError("network")
        monkeypatch.setattr(sys.modules["huggingface_hub"], "snapshot_download", boom)
        assert engine.pre_download_whisper("base") is False


# ---------------------------------------------------------------------------
# Setup profile persistence
# ---------------------------------------------------------------------------

class TestSetupProfile:
    def test_load_default_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(engine, "USER_DATA_DIR", tmp_path)
        data = engine.load_setup_profile()
        assert data["onboarded"] is False
        assert data["profile"] == []

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(engine, "USER_DATA_DIR", tmp_path)
        engine.save_setup_profile(profile=["documents", "photos"], onboarded=True)
        data = engine.load_setup_profile()
        assert data["onboarded"] is True
        assert data["profile"] == ["documents", "photos"]

    def test_save_is_json_serializable(self, tmp_path, monkeypatch):
        monkeypatch.setattr(engine, "USER_DATA_DIR", tmp_path)
        engine.save_setup_profile(profile=["audio"], onboarded=True)
        raw = (tmp_path / "setup.json").read_text(encoding="utf-8")
        assert json.loads(raw)["profile"] == ["audio"]

    def test_corrupt_file_falls_back(self, tmp_path, monkeypatch):
        monkeypatch.setattr(engine, "USER_DATA_DIR", tmp_path)
        (tmp_path / "setup.json").write_text("{not json", encoding="utf-8")
        data = engine.load_setup_profile()
        assert data["onboarded"] is False


# ---------------------------------------------------------------------------
# Setup wizard plan sizing (bootstrap helper)
# ---------------------------------------------------------------------------

class TestPlanSizes:
    def test_model_kind_shows_range_across_catalog(self):
        import bootstrap
        sizes = bootstrap._plan_sizes({"vision": "qwen2.5vl:7b",
                                       "text": "qwen2.5:3b"})
        # Ranges must be honest regardless of which model the user picks next.
        assert sizes["vision_model"] == "1.8–6.0 GB"
        assert sizes["text_model"] == "1.0–4.7 GB"

    def test_fixed_deps_have_single_sizes(self):
        import bootstrap
        sizes = bootstrap._plan_sizes({})
        assert sizes["ollama"] == "~1.5 GB"
        assert sizes["ffmpeg"] == "~109 MB"
        assert sizes["exiftool"] == "~10 MB"
        assert sizes["whisper"] == "~74 MB"

    def test_build_plan_marks_model_downloads(self, monkeypatch):
        import bootstrap
        monkeypatch.setattr(bootstrap, "_ollama_binary", lambda: "ollama")
        monkeypatch.setattr(bootstrap, "_resolve_binary_path", lambda name: None)
        monkeypatch.setattr(bootstrap, "_installed_models", lambda: set())
        plan = bootstrap._build_plan(["documents"],
                                     {"text_model"},
                                     {"text": "qwen2.5:3b"})
        labels = {p["label"] for p in plan}
        assert "Text AI model" in labels
        assert "FFmpeg" not in labels, "documents-only must not need FFmpeg"
        text_row = next(p for p in plan if p["label"] == "Text AI model")
        assert text_row["status"] == "download"
        assert text_row["size"] == "1.0–4.7 GB"


# ---------------------------------------------------------------------------
# Profile-aware environment checks
# ---------------------------------------------------------------------------

class TestCheckEnvironmentProfile:
    def test_documents_profile_ignores_missing_media_tools(self, monkeypatch):
        monkeypatch.setattr(engine, "_resolve_binary_path", lambda name: None)
        monkeypatch.setattr(engine.ollama, "list",
                            lambda: {"models": [{"name": "qwen2.5:3b"}]})
        env = engine.check_environment(profile=["documents"])
        assert env["errors"] == []
        assert env["model_available"] is True

    def test_videos_profile_flags_missing_ffmpeg(self, monkeypatch):
        monkeypatch.setattr(engine, "_resolve_binary_path", lambda name: None)
        monkeypatch.setattr(engine.ollama, "list",
                            lambda: {"models": [{"name": "qwen2.5vl:7b"}]})
        env = engine.check_environment(profile=["videos"])
        assert any("FFmpeg" in e for e in env["errors"])
        assert any("ExifTool" in e for e in env["errors"])

    def test_no_profile_defaults_to_media_toolchain(self, monkeypatch):
        monkeypatch.setattr(engine, "_resolve_binary_path", lambda name: None)
        monkeypatch.setattr(engine.ollama, "list",
                            lambda: {"models": [{"name": "qwen2.5vl:7b"}]})
        env = engine.check_environment()
        assert any("FFmpeg" in e for e in env["errors"])
        assert any("ExifTool" in e for e in env["errors"])

    def test_legacy_keep_alive(self, monkeypatch):
        """No-profile check must behave exactly like the old signature/result."""
        monkeypatch.setattr(engine, "_resolve_binary_path", lambda name: None)
        monkeypatch.setattr(engine.ollama, "list",
                            lambda: {"models": [{"name": "qwen2.5vl:7b"}]})
        env = engine.check_environment()
        for key in ("ffmpeg", "exiftool", "ollama_running", "model_available",
                    "vision_models", "text_models", "text_model_available",
                    "errors"):
            assert key in env

    def test_text_model_detected(self, monkeypatch):
        monkeypatch.setattr(engine, "_resolve_binary_path", lambda name: "found")
        monkeypatch.setattr(engine.ollama, "list",
                            lambda: {"models": [{"name": "qwen2.5:3b"},
                                                {"name": "qwen2.5vl:7b"}]})
        env = engine.check_environment(profile=["documents"])
        assert env["text_models"] == ["qwen2.5:3b"]
        assert env["text_model_available"] is True

    def test_no_text_model_available_flag_false(self, monkeypatch):
        monkeypatch.setattr(engine, "_resolve_binary_path", lambda name: None)
        monkeypatch.setattr(engine.ollama, "list",
                            lambda: {"models": [{"name": "qwen2.5vl:7b"}]})
        env = engine.check_environment(profile=["documents"])
        assert env["text_models"] == []
        assert env["text_model_available"] is False

    def test_text_only_profile_not_blocked_without_ffmpeg(self, monkeypatch):
        monkeypatch.setattr(engine, "_resolve_binary_path", lambda name: None)
        monkeypatch.setattr(engine.ollama, "list",
                            lambda: {"models": [{"name": "qwen2.5:3b"}]})
        env = engine.check_environment(profile=["spreadsheets"])
        assert env["errors"] == []
        assert env["text_model_available"] is True
