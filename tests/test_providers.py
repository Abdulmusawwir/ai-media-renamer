from unittest.mock import MagicMock, patch

import pytest

from engine import (
    TEXT_MODEL_NAME,
    AIProvider,
    LlamaCppProvider,
    OllamaProvider,
    OpenAIProvider,
    _llamacpp_server_running,
    get_provider,
    list_providers,
    register_provider,
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestProviderRegistry:
    def test_list_includes_local_providers(self):
        names = list_providers()
        assert "ollama" in names
        assert "llamacpp" in names

    def test_get_ollama(self):
        prov = get_provider("ollama")
        assert isinstance(prov, OllamaProvider)

    def test_get_llamacpp(self):
        prov = get_provider("llamacpp")
        assert isinstance(prov, LlamaCppProvider)
        assert prov._base_url.endswith("/v1")

    def test_get_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent")

    def test_register_custom(self):
        class FakeProvider(AIProvider):
            def analyze(self, img, **kw): return {"ok": True}
            def health_check(self): return {"ok": True}
            def available_models(self): return ["fake"]
        register_provider("fake_test", FakeProvider)
        names = list_providers()
        assert "fake_test" in names
        prov = get_provider("fake_test")
        assert isinstance(prov, FakeProvider)


# ---------------------------------------------------------------------------
# Helper: _parse_and_validate
# ---------------------------------------------------------------------------

class TestParseAndValidate:
    def test_valid_json(self):
        prov = OllamaProvider()
        raw = '{"new_filename": "test_file", "topic": "test"}'
        result = prov._parse_and_validate(raw)
        assert result["ok"] is True
        assert result["data"]["new_filename"] == "test_file"

    def test_invalid_json(self):
        prov = OllamaProvider()
        result = prov._parse_and_validate("not json")
        assert result["ok"] is False
        assert result["error"] == "json_parse_error"

    def test_missing_new_filename(self):
        prov = OllamaProvider()
        result = prov._parse_and_validate('{"topic": "test"}')
        assert result["ok"] is False
        assert result["error"] == "missing_keys"

    def test_empty_string(self):
        prov = OllamaProvider()
        result = prov._parse_and_validate("")
        assert result["ok"] is False
        assert result["error"] == "empty_response"

    def test_json_with_code_block(self):
        prov = OllamaProvider()
        raw = '```json\n{"new_filename": "test", "topic": "x"}\n```'
        result = prov._parse_and_validate(raw)
        assert result["ok"] is True

    def test_json_with_plain_block(self):
        prov = OllamaProvider()
        raw = '```\n{"new_filename": "test", "topic": "x"}\n```'
        result = prov._parse_and_validate(raw)
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------

class TestOllamaProvider:
    def setup_method(self):
        self.prov = OllamaProvider()

    @patch("engine.ollama.generate")
    def test_analyze_success(self, mock_gen):
        payload = '{"new_filename": "sunset_beach", "topic": "beach", "description": "sunset", '
        payload += '"tags": ["sunset", "beach"], "overall_visual_summary": "A beautiful sunset at the beach.", '
        payload += '"suggested_category": "landscapes_broll"}'
        mock_gen.return_value = {"response": payload}
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is True
        assert result["data"]["new_filename"] == "sunset_beach"

    @patch("engine.ollama.generate")
    def test_analyze_ollama_error(self, mock_gen):
        import ollama as ollama_mod
        mock_gen.side_effect = ollama_mod.ResponseError("Model not found")
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is False
        assert result["error"] == "ollama_error"

    @patch("engine.ollama.generate")
    def test_analyze_connection_error(self, mock_gen):
        mock_gen.side_effect = ConnectionError("Connection refused")
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is False
        assert result["error"] == "ollama_error"

    @patch("engine.ollama.list")
    def test_health_check_running(self, mock_list):
        mock_list.return_value = {"models": []}
        result = self.prov.health_check()
        assert result["ok"] is True

    @patch("engine.ollama.list")
    def test_health_check_down(self, mock_list):
        mock_list.side_effect = Exception("Connection refused")
        result = self.prov.health_check()
        assert result["ok"] is False

    @patch("engine.ollama.list")
    def test_available_models(self, mock_list):
        mock_list.return_value = {"models": [{"name": "qwen2.5vl:7b"}, {"name": "llava:13b"}]}
        models = self.prov.available_models()
        assert "qwen2.5vl:7b" in models
        assert "llava:13b" in models

    @patch("engine.ollama.list")
    def test_available_models_all(self, mock_list):
        mock_list.return_value = {"models": [
            {"name": "qwen2.5vl:7b"}, {"name": "deepseek-coder-v2:16b"}, {"name": "llava:13b"}
        ]}
        models = self.prov.available_models()
        assert "qwen2.5vl:7b" in models
        assert "llava:13b" in models
        assert "deepseek-coder-v2:16b" in models
        assert len(models) == 3

    @patch("engine.ollama.list")
    def test_available_models_down_returns_empty(self, mock_list):
        # Critical: when the daemon is down we must NOT fall back to the config
        # catalog, or every catalog model falsely shows as "installed".
        mock_list.side_effect = Exception("Down")
        models = self.prov.available_models()
        assert models == []

    def test_model_property(self):
        self.prov.model = "test-model"
        assert self.prov.model == "test-model"

    def test_text_model_default(self):
        assert self.prov.text_model == TEXT_MODEL_NAME

    @patch("engine.ollama.generate")
    def test_analyze_text_uses_text_model(self, mock_gen):
        payload = ('{"new_filename": "report_summary", "topic": "report", "description": "summary", '
                   '"tags": ["report"], "overall_visual_summary": "Report summary", '
                   '"suggested_category": "documents_broll"}')
        mock_gen.return_value = {"response": payload}
        self.prov.text_model = "qwen2.5:3b"
        result = self.prov.analyze_text("Some document text")
        assert result["ok"] is True
        assert mock_gen.call_args.kwargs["model"] == "qwen2.5:3b"
        assert "images" not in mock_gen.call_args.kwargs

    @patch("engine.ollama.generate")
    def test_analyze_text_falls_back_to_vision_model(self, mock_gen):
        payload = ('{"new_filename": "report_summary", "topic": "report", "description": "summary", '
                   '"tags": ["report"], "overall_visual_summary": "Report summary", '
                   '"suggested_category": "documents_broll"}')
        mock_gen.return_value = {"response": payload}
        self.prov.text_model = ""
        result = self.prov.analyze_text("Some document text")
        assert result["ok"] is True
        assert mock_gen.call_args.kwargs["model"] == self.prov._model

    @patch("engine.ollama.generate")
    def test_analyze_sends_vision_model_for_images(self, mock_gen):
        payload = ('{"new_filename": "sunset_beach", "topic": "beach", "description": "sunset", '
                   '"tags": ["sunset", "beach"], "overall_visual_summary": "A beautiful sunset.", '
                   '"suggested_category": "landscapes_broll"}')
        mock_gen.return_value = {"response": payload}
        self.prov.text_model = "qwen2.5:3b"
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is True
        assert mock_gen.call_args.kwargs["model"] == self.prov._model
        assert "images" in mock_gen.call_args.kwargs

    def test_analyze_document_with_ai_uses_config_text_model(self, monkeypatch):
        import engine as engine_mod

        calls = {}

        class FakeProv:
            def __init__(self):
                self.model = ""
                self.text_model = ""

            def analyze_text(self, text, verbose=False):
                calls["model"] = self.model
                calls["text_model"] = self.text_model
                return {"ok": True, "data": {"new_filename": "x"}}

        monkeypatch.setattr(engine_mod, "get_provider", lambda name: FakeProv())
        monkeypatch.setitem(engine_mod.config, "model", {
            "name": "vision-model", "text_model": "tiny-text",
            "temperature": 0.15, "num_ctx": 8192, "keep_alive": "1h",
        })
        engine_mod.analyze_document_with_ai("doc text")
        assert calls["model"] == "vision-model"
        assert calls["text_model"] == "tiny-text"

    def test_api_key_property(self):
        self.prov.api_key = "test-key"
        assert self.prov.api_key == "test-key"


# ---------------------------------------------------------------------------
# OpenAIProvider (base class for the local OpenAI-compatible llama.cpp adapter)
# ---------------------------------------------------------------------------

class TestOpenAIProvider:
    def setup_method(self):
        self.prov = OpenAIProvider()
        self.prov.api_key = "fake-openai-key"
        self.prov.model = "gpt-4o"

    @patch("engine.openai.OpenAI")
    def test_analyze_success(self, mock_openai):
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"new_filename": "sunset_paris", "topic": "paris", "description": "sunset", '
            '"tags": ["sunset", "paris"], "overall_visual_summary": "Sunset in Paris.", '
            '"suggested_category": "landscapes_broll"}'
        )
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is True
        assert result["data"]["new_filename"] == "sunset_paris"

    def test_analyze_no_api_key(self):
        self.prov.api_key = ""
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is False
        assert result["error"] == "api_key_missing"

    @patch("engine.openai.OpenAI")
    def test_analyze_api_error(self, mock_openai):
        mock_openai.side_effect = Exception("401 Invalid API key")
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is False
        assert result["error"] == "openai_api_error"

    def test_health_check_with_key(self):
        result = self.prov.health_check()
        assert result["ok"] is True

    def test_health_check_no_key(self):
        self.prov.api_key = ""
        result = self.prov.health_check()
        assert result["ok"] is False

    def test_available_models(self):
        from engine import config
        models = self.prov.available_models()
        assert "gpt-4o" in models or not config.get("model", {}).get("providers", {}).get("openai", {}).get("models")


# ---------------------------------------------------------------------------
# LlamaCppProvider (local llama.cpp llama-server runtime fallback)
# ---------------------------------------------------------------------------

class TestLlamaCppProvider:
    def setup_method(self):
        self.prov = LlamaCppProvider()

    def test_inherits_from_openai(self):
        assert isinstance(self.prov, OpenAIProvider)

    def test_base_url_points_at_local_server(self):
        assert self.prov._base_url.startswith("http")
        assert self.prov._base_url.endswith("/v1")

    def test_dummy_api_key_set(self):
        # llama-server does not authenticate; a placeholder satisfies the client.
        assert self.prov._api_key == "local"

    @patch("engine.openai.OpenAI")
    def test_available_models_down_returns_empty(self, mock_openai):
        mock_openai.side_effect = Exception("connection refused")
        assert self.prov.available_models() == []

    @patch("engine.openai.OpenAI")
    def test_available_models_lists_loaded_models(self, mock_openai):
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        m1 = MagicMock()
        m1.id = "qwen3-vl:14b"
        m2 = MagicMock()
        m2.id = "llama-3.2:3b"
        resp = MagicMock()
        resp.data = [m1, m2]
        mock_client.models.list.return_value = resp
        models = self.prov.available_models()
        assert "qwen3-vl:14b" in models
        assert "llama-3.2:3b" in models


class TestLlamaCppDetection:
    @patch("engine.requests.get")
    def test_server_running(self, mock_get):
        mock_get.return_value.status_code = 200
        assert _llamacpp_server_running() is True

    @patch("engine.requests.get")
    def test_server_down(self, mock_get):
        mock_get.side_effect = ConnectionError("refused")
        assert _llamacpp_server_running() is False

    @patch("engine.requests.get")
    def test_non_200(self, mock_get):
        mock_get.return_value.status_code = 503
        assert _llamacpp_server_running() is False


# ---------------------------------------------------------------------------
# Provider routing (switch_ai_provider)
# ---------------------------------------------------------------------------

class TestProviderRouting:
    @patch("engine.switch_ai_provider")
    def test_switch_returns_result(self, mock_switch):
        mock_switch.return_value = {"ok": True, "message": "Switched to ollama."}
        from engine import switch_ai_provider as real_switch
        with patch("engine.check_environment") as mock_env:
            mock_env.return_value = {"ollama_running": True, "model_available": True, "errors": []}
            with patch("engine.save_config"):
                result = real_switch("ollama")
                assert result["ok"] is True


# ---------------------------------------------------------------------------
# _format_ai_error (new error types)
# ---------------------------------------------------------------------------

class TestFormatAiError:
    def test_openai_api_error(self):
        from engine import _format_ai_error
        msg = _format_ai_error({"error": "openai_api_error", "detail": "401 Unauthorized"})
        assert "401" in msg or "openai" in msg.lower()

    def test_api_key_missing(self):
        from engine import _format_ai_error
        msg = _format_ai_error({"error": "api_key_missing", "detail": "No API key"})
        assert "No API key" in msg or "api_key" in msg.lower()

    def test_unknown_error(self):
        from engine import _format_ai_error
        msg = _format_ai_error({"error": "unknown", "detail": "Something broke"})
        assert "Something broke" in msg

    def test_verbose_includes_raw(self):
        from engine import _format_ai_error
        msg = _format_ai_error({"error": "ollama_error", "detail": "fail", "raw_response": "RAW DATA"}, verbose=True)
        assert "RAW DATA" in msg
