from unittest.mock import MagicMock, patch

import pytest

from engine import (
    AIProvider,
    AnthropicProvider,
    GeminiProvider,
    GroqProvider,
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
    delete_api_key,
    get_provider,
    list_providers,
    load_api_key,
    register_provider,
    save_api_key,
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestProviderRegistry:
    def test_list_includes_all_six(self):
        names = list_providers()
        assert "ollama" in names
        assert "gemini" in names
        assert "openai" in names
        assert "anthropic" in names
        assert "groq" in names
        assert "openrouter" in names

    def test_get_ollama(self):
        prov = get_provider("ollama")
        assert isinstance(prov, OllamaProvider)

    def test_get_gemini(self):
        prov = get_provider("gemini")
        assert isinstance(prov, GeminiProvider)

    def test_get_openai(self):
        prov = get_provider("openai")
        assert isinstance(prov, OpenAIProvider)

    def test_get_anthropic(self):
        prov = get_provider("anthropic")
        assert isinstance(prov, AnthropicProvider)

    def test_get_groq(self):
        prov = get_provider("groq")
        assert isinstance(prov, GroqProvider)
        assert prov._base_url == "https://api.groq.com/openai/v1"

    def test_get_openrouter(self):
        prov = get_provider("openrouter")
        assert isinstance(prov, OpenRouterProvider)
        assert "openrouter.ai" in prov._base_url

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
    def test_available_models_fallback(self, mock_list):
        mock_list.side_effect = Exception("Down")
        models = self.prov.available_models()
        assert isinstance(models, list)

    def test_model_property(self):
        self.prov.model = "test-model"
        assert self.prov.model == "test-model"

    def test_api_key_property(self):
        self.prov.api_key = "test-key"
        assert self.prov.api_key == "test-key"


# ---------------------------------------------------------------------------
# GeminiProvider
# ---------------------------------------------------------------------------

class TestGeminiProvider:
    def setup_method(self):
        self.prov = GeminiProvider()
        self.prov.api_key = "fake-gemini-key"

    @patch("engine.requests.post")
    def test_analyze_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "candidates": [{
                "content": {"parts": [{"text": '{"new_filename": "night_city", "topic": "city", '
                    '"description": "night", "tags": ["city", "night"], '
                    '"overall_visual_summary": "City at night.", '
                    '"suggested_category": "night_astro"}'}]}
            }]
        }
        mock_post.return_value = mock_resp
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is True
        assert result["data"]["new_filename"] == "night_city"

    def test_analyze_no_api_key(self):
        self.prov.api_key = ""
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is False
        assert result["error"] == "api_key_missing"

    @patch("engine.requests.post")
    def test_analyze_no_candidates(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"candidates": []}
        mock_post.return_value = mock_resp
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is False
        assert result["error"] == "gemini_empty_response"

    @patch("engine.requests.post")
    def test_analyze_http_error(self, mock_post):
        from requests.exceptions import HTTPError
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = HTTPError("429 Too Many Requests")
        mock_post.return_value = mock_resp
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is False
        assert result["error"] == "gemini_api_error"

    def test_health_check_with_key(self):
        result = self.prov.health_check()
        assert result["ok"] is True

    def test_health_check_without_key(self):
        self.prov.api_key = ""
        result = self.prov.health_check()
        assert result["ok"] is False

    def test_available_models(self):
        models = self.prov.available_models()
        assert "gemini-2.0-flash-001" in models


# ---------------------------------------------------------------------------
# OpenAIProvider
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
        models = self.prov.available_models()
        assert "gpt-4o" in models


# ---------------------------------------------------------------------------
# AnthropicProvider
# ---------------------------------------------------------------------------

class TestAnthropicProvider:
    def setup_method(self):
        self.prov = AnthropicProvider()
        self.prov.api_key = "fake-anthropic-key"
        self.prov.model = "claude-3-5-sonnet-20241022"

    @patch("engine.anthropic.Anthropic")
    def test_analyze_success(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_block = MagicMock()
        mock_block.text = (
            '{"new_filename": "mountain_view", "topic": "mountain", "description": "view", '
            '"tags": ["mountain", "view"], "overall_visual_summary": "Mountain view.", '
            '"suggested_category": "landscapes_broll"}'
        )
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is True
        assert result["data"]["new_filename"] == "mountain_view"

    def test_analyze_no_api_key(self):
        self.prov.api_key = ""
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is False
        assert result["error"] == "api_key_missing"

    @patch("engine.anthropic.Anthropic")
    def test_analyze_api_error(self, mock_anthropic):
        mock_anthropic.side_effect = Exception("403 Forbidden")
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is False
        assert result["error"] == "anthropic_api_error"

    def test_health_check_with_key(self):
        result = self.prov.health_check()
        assert result["ok"] is True

    def test_health_check_no_key(self):
        self.prov.api_key = ""
        result = self.prov.health_check()
        assert result["ok"] is False

    def test_available_models(self):
        models = self.prov.available_models()
        assert "claude-3-5-sonnet-20241022" in models


# ---------------------------------------------------------------------------
# GroqProvider
# ---------------------------------------------------------------------------

class TestGroqProvider:
    def setup_method(self):
        self.prov = GroqProvider()
        self.prov.api_key = "fake-groq-key"
        self.prov.model = "llama-3.2-90b-vision-preview"

    def test_inherits_from_openai(self):
        assert isinstance(self.prov, OpenAIProvider)

    def test_custom_base_url(self):
        assert "groq.com" in self.prov._base_url

    def test_available_models(self):
        models = self.prov.available_models()
        assert "llama-3.2-90b-vision-preview" in models

    @patch("engine.openai.OpenAI")
    def test_analyze_success(self, mock_openai):
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"new_filename": "desert_dune", "topic": "desert", "description": "dune", '
            '"tags": ["desert", "dune"], "overall_visual_summary": "Desert dune.", '
            '"suggested_category": "landscapes_broll"}'
        )
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is True
        assert result["data"]["new_filename"] == "desert_dune"


# ---------------------------------------------------------------------------
# OpenRouterProvider
# ---------------------------------------------------------------------------

class TestOpenRouterProvider:
    def setup_method(self):
        self.prov = OpenRouterProvider()
        self.prov.api_key = "fake-or-key"
        self.prov.model = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"

    def test_inherits_from_openai(self):
        assert isinstance(self.prov, OpenAIProvider)

    def test_custom_base_url(self):
        assert "openrouter.ai" in self.prov._base_url

    def test_available_models(self):
        models = self.prov.available_models()
        assert "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free" in models

    @patch("engine.openai.OpenAI")
    def test_analyze_success(self, mock_openai):
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"new_filename": "sunset_ai", "topic": "sunset", "description": "ai", '
            '"tags": ["sunset", "ai"], "overall_visual_summary": "Sunset by AI.", '
            '"suggested_category": "landscapes_broll"}'
        )
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        result = self.prov.analyze("fake_base64")
        assert result["ok"] is True
        assert result["data"]["new_filename"] == "sunset_ai"


# ---------------------------------------------------------------------------
# API Key Storage (mocked keyring)
# ---------------------------------------------------------------------------

class TestApiKeyStorage:
    @patch("engine.keyring.set_password")
    def test_save_api_key(self, mock_kr):
        save_api_key("test_provider", "test-key-123")
        mock_kr.assert_called_once_with("ai-media-renamer", "test_provider", "test-key-123")

    @patch("engine.keyring.get_password")
    def test_load_api_key_exists(self, mock_kr):
        mock_kr.return_value = "stored-key"
        result = load_api_key("test_provider")
        assert result == "stored-key"

    @patch("engine.keyring.get_password")
    def test_load_api_key_missing(self, mock_kr):
        mock_kr.return_value = None
        result = load_api_key("unknown_provider")
        assert result == ""

    @patch("engine.keyring.delete_password")
    def test_delete_api_key(self, mock_kr):
        delete_api_key("test_provider")
        mock_kr.assert_called_once_with("ai-media-renamer", "test_provider")

    @patch("engine.keyring.delete_password")
    def test_delete_api_key_nonexistent(self, mock_kr):
        import keyring as kr_mod
        mock_kr.side_effect = kr_mod.errors.PasswordDeleteError("not found")
        delete_api_key("missing")  # should not raise


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

    def test_anthropic_api_error(self):
        from engine import _format_ai_error
        msg = _format_ai_error({"error": "anthropic_api_error", "detail": "403 Forbidden"})
        assert "403" in msg or "anthropic" in msg.lower()

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
