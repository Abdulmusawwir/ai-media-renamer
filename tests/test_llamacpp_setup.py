"""Tests for the llama.cpp default-runtime setup path: GGUF catalog,
recommendations, runtime URL resolution, config wiring, server lifecycle, and
the OpenAI-compatible text/vision surface used by LlamaCppProvider."""

import copy
from unittest.mock import MagicMock, patch

import pytest

import engine

# ---------------------------------------------------------------------------
# GGUF catalog + recommendations
# ---------------------------------------------------------------------------

class TestLlamaCppGguCatalog:
    def test_vision_and_text_kinds(self):
        kinds = {m["kind"] for m in engine.LLAMACPP_GGUF_CATALOG}
        assert kinds == {"vision", "text"}

    def test_entries_have_fields(self):
        for m in engine.LLAMACPP_GGUF_CATALOG:
            assert m["name"] and ":" in m["name"]
            assert m["label"] and m["size"] and m["desc"]
            assert m["url"].startswith("https://")
            if m["kind"] == "vision":
                assert m["mmproj_url"].startswith("https://")

    def test_vision_aliases_are_vision(self):
        for m in engine.LLAMACPP_GGUF_CATALOG:
            if m["kind"] == "vision":
                assert engine._is_vision_model(m["name"])

    def test_text_aliases_are_not_vision(self):
        for m in engine.LLAMACPP_GGUF_CATALOG:
            if m["kind"] == "text":
                assert not engine._is_vision_model(m["name"])

    def test_gguf_paths_map(self):
        gguf, mmproj = engine._llamacpp_gguf_paths("qwen2.5vl:7b")
        assert gguf.name == "qwen2-vl-7b-q4_k_m.gguf"
        assert mmproj.name == "mmproj-qwen2-vl-7b-q8_0.gguf"
        gguf2, mmproj2 = engine._llamacpp_gguf_paths("qwen2.5:3b")
        assert gguf2.name == "qwen2.5-3b-instruct-q4_k_m.gguf"
        assert mmproj2 == engine.Path("")


class TestRecommendedLlamaCppModels:
    def test_documents_only_recommends_text(self, monkeypatch):
        monkeypatch.setattr(engine, "_has_gpu", lambda: False)
        rec = engine.recommended_llamacpp_models(["documents"])
        assert "vision" not in rec
        assert rec["text"] == "qwen2.5:3b"

    def test_gpu_vision_is_7b(self, monkeypatch):
        monkeypatch.setattr(engine, "_has_gpu", lambda: True)
        rec = engine.recommended_llamacpp_models(["videos"])
        assert rec["vision"] == "qwen2.5vl:7b"

    def test_cpu_vision_is_2b(self, monkeypatch):
        monkeypatch.setattr(engine, "_has_gpu", lambda: False)
        rec = engine.recommended_llamacpp_models(["videos"])
        assert rec["vision"] == "qwen2.5vl:2b"


# ---------------------------------------------------------------------------
# Runtime download URL resolution
# ---------------------------------------------------------------------------

class _FakeReleases:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class TestLlamaRuntimeUrls:
    def test_offline_uses_pinned_fallbacks(self, monkeypatch):
        def boom(url, timeout=10):
            raise OSError("offline")
        monkeypatch.setattr(engine.requests, "get", boom)
        urls = engine._llamacpp_runtime_urls()
        assert urls
        assert all(u.startswith("https://github.com/ggml-org/llama.cpp/releases/download/")
                   for u in urls)
        assert any("-win-cpu-x64" in u for u in urls)

    def test_latest_prefers_win_cpu_zip(self, monkeypatch):
        def fake_get(url, timeout=10):
            return _FakeReleases({"tag_name": "b10327", "assets": [
                {"name": "llama-b10327-bin-win-cpu-x64.zip",
                 "browser_download_url": "https://github.com/x/win-cpu.zip"},
                {"name": "llama-b10327-bin-win-cuda-12.4-x64.zip",
                 "browser_download_url": "https://github.com/x/cuda.zip"},
            ]})
        monkeypatch.setattr(engine.requests, "get", fake_get)
        urls = engine._llamacpp_runtime_urls()
        assert urls[0] == "https://github.com/x/win-cpu.zip"
        assert any("cpu" in u for u in urls)


# ---------------------------------------------------------------------------
# configure_llamacpp_install (config wiring)
# ---------------------------------------------------------------------------

@pytest.fixture
def restore_config():
    backup = copy.deepcopy(engine.config.get("model", {}))
    yield
    engine.config["model"] = copy.deepcopy(backup)


@pytest.fixture
def silent_save(monkeypatch):
    monkeypatch.setattr(engine, "save_config", lambda: None)


class TestConfigureLlamaCppInstall:

    def test_wires_default_runtime(self, tmp_path, monkeypatch, restore_config, silent_save):
        gguf = tmp_path / "qwen2-vl-7b-q4_k_m.gguf"
        engine.configure_llamacpp_install(
            "qwen2.5vl:7b", gguf, mmproj_path=tmp_path / "mmproj.gguf", make_default=True)
        llamacpp = engine.config["model"]["llamacpp"]
        assert llamacpp["gguf_name"] == "qwen2.5vl:7b"
        assert llamacpp["gguf_path"] == str(gguf)
        assert llamacpp["mmproj_path"].endswith("mmproj.gguf")
        assert engine.config["model"]["providers"]["llamacpp"]["selected_model"] == "qwen2.5vl:7b"
        assert engine.config["model"]["name"] == "qwen2.5vl:7b"
        assert engine.config["model"]["text_model"] == "qwen2.5vl:7b"
        assert engine.config["model"]["last_provider"] == "llamacpp"

    def test_non_default_keeps_ollama_model(self, tmp_path, monkeypatch, restore_config, silent_save):
        engine.configure_llamacpp_install("qwen2.5:3b", tmp_path / "text.gguf",
                                          make_default=False)
        assert engine.config["model"]["last_provider"] != "llamacpp"
        assert engine.config["model"]["providers"]["llamacpp"]["selected_model"] == "qwen2.5:3b"


# ---------------------------------------------------------------------------
# Wizard plan runtime awareness (bootstrap._build_plan)
# ---------------------------------------------------------------------------

class TestLlamaBuildPlan:
    def test_no_ollama_defaults_to_llamacpp_runtime(self, monkeypatch, tmp_path):
        import bootstrap
        monkeypatch.setattr(bootstrap, "_ollama_binary", lambda: None)
        monkeypatch.setattr(bootstrap, "_resolve_binary_path", lambda name: None)
        monkeypatch.setattr(bootstrap, "_installed_models", lambda: set())
        monkeypatch.setattr(bootstrap, "_llamacpp_gguf_paths",
                            lambda name: (tmp_path / "x.gguf", tmp_path / "y.gguf"))
        plan = bootstrap._build_plan(
            ["videos"], {"ffmpeg", "exiftool", "vision_model", "whisper"},
            {"vision": "qwen2.5vl:7b"})
        labels = [p["label"] for p in plan]
        assert "llama.cpp runtime (AI server)" in labels
        assert "Ollama runtime" not in labels
        runtime_row = next(p for p in plan if p["label"].startswith("llama.cpp"))
        assert runtime_row["status"] == "download"
        vision_row = next(p for p in plan if p["label"] == "Vision AI model")
        assert vision_row["status"] == "download"

    def test_ollama_installed_reuses_ollama(self, monkeypatch, tmp_path):
        import bootstrap
        monkeypatch.setattr(bootstrap, "_ollama_binary", lambda: "C:/ollama/ollama.exe")
        monkeypatch.setattr(bootstrap, "_resolve_binary_path", lambda name: None)
        monkeypatch.setattr(bootstrap, "_installed_models", lambda: set())
        plan = bootstrap._build_plan(["documents"], {"text_model"}, {"text": "qwen2.5:3b"})
        labels = [p["label"] for p in plan]
        assert "Ollama runtime" in labels
        assert "llama.cpp runtime (AI server)" not in labels
        ollama_row = next(p for p in plan if p["label"] == "Ollama runtime")
        assert ollama_row["status"] == "ready"


# ---------------------------------------------------------------------------
# ensure_llamacpp_server lifecycle
# ---------------------------------------------------------------------------

class TestEnsureLlamaCppServer:
    def test_already_running_returns_true(self, monkeypatch):
        monkeypatch.setattr(engine, "_llamacpp_server_running", lambda: True)
        assert engine.ensure_llamacpp_server() is True

    def test_no_binary_returns_false(self, monkeypatch):
        monkeypatch.setattr(engine, "_llamacpp_server_running", lambda: False)
        monkeypatch.setattr(engine, "_resolve_binary_path",
                            lambda name: None if name == engine.LLAMACPP_SERVER_EXE else "x")
        assert engine.ensure_llamacpp_server() is False

    def test_binary_but_missing_gguf_returns_false(self, tmp_path, monkeypatch, restore_config, silent_save):
        monkeypatch.setattr(engine, "_llamacpp_server_running", lambda: False)
        monkeypatch.setattr(engine, "_resolve_binary_path",
                            lambda name: "C:/tools/llama-server.exe" if name == "llama-server.exe" else None)
        engine.config["model"]["llamacpp"] = {"gguf_path": str(tmp_path / "missing.gguf")}
        assert engine.ensure_llamacpp_server() is False


# ---------------------------------------------------------------------------
# LlamaCppProvider OpenAI-compatible text + override path
# ---------------------------------------------------------------------------

class TestLlamaCppPromptPaths:
    def setup_method(self):
        self.prov = engine.LlamaCppProvider()
        self.prov.api_key = "local"

    @patch("engine.openai.OpenAI")
    def test_text_analysis_hits_chat_endpoint(self, mock_openai):
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"new_filename": "quarterly_report", "category": "reports", '
            '"description": "Q3", "tags": ["report"], '
            '"overall_visual_summary": "A report.", "suggested_category": "reports"}'
        )
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        result = self.prov.analyze_text("Some document text")
        assert result["ok"] is True
        assert result["data"]["new_filename"] == "quarterly_report"
        sent = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert sent[0]["type"] == "text"
        assert "Some document text" in sent[0]["text"]

    def test_text_no_api_key(self):
        self.prov.api_key = ""
        result = self.prov.analyze_text("doc")
        assert result["error"] == "api_key_missing"

    @patch("engine.openai.OpenAI")
    def test_analyze_honors_prompt_override(self, mock_openai):
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"new_filename": "clip", "category": "general", "description": "d", '
            '"tags": [], "overall_visual_summary": "s", "suggested_category": "aerial_drone"}'
        )
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        result = self.prov.analyze("base64", verbose=False, prompt_override="MY CUSTOM CONTEXT")
        assert result["ok"] is True
        sent = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        text = next(p for p in sent if p["type"] == "text")
        assert text["text"] == "MY CUSTOM CONTEXT"
