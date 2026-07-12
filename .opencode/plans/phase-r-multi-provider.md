# Phase R — Multi-Provider Implementation Plan

## Branch
`feat/phase-r-multi-provider` (created from `main`)

## Summary
Refactor ad-hoc `analyze_asset_with_ai()` / `analyze_asset_with_gemini()` into a proper provider abstraction with secure key storage, model auto-detection, and 5 providers.

---

## Step 1 — requirements.txt

Add:
```
openai>=1.0.0
anthropic>=0.30.0
keyring>=24.0.0
```

---

## Step 2 — config.json

### Changes to `"model"` section:
```json
"model": {
    "name": "qwen2.5vl:7b",
    "temperature": 0.15,
    "num_ctx": 8192,
    "keep_alive": "1h",
    "last_provider": "ollama",
    "providers": {
        "ollama": {"models": ["qwen2.5vl:7b", "qwen2.5vl:32b", "llava:13b"]},
        "gemini": {"models": ["gemini-2.0-flash-001", "gemini-2.0-flash-lite-001",
                               "gemini-1.5-flash-001", "gemini-1.5-flash-002",
                               "gemini-1.5-pro-001", "gemini-2.5-pro-exp-03-25"]},
        "openai": {"models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo",
                               "gpt-4o-2024-08-06", "o1", "o3-mini"]},
        "anthropic": {"models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
                                  "claude-3-opus-20240229", "claude-3-sonnet-20240229",
                                  "claude-3-haiku-20240307"]},
        "groq": {"models": ["llama-3.2-90b-vision-preview", "llama-3.2-11b-vision-preview"],
                  "base_url": "https://api.groq.com/openai/v1"}
    }
}
```

### Remove from `"cloud"` section:
Keep `"cloud": {"providers": ["gemini", "openai", "anthropic", "groq"]}` but this becomes secondary — the authoritative list is now `model.providers`.

---

## Step 3 — engine.py (BIGGEST CHANGE)

### 3a — New imports
```python
import keyring
from abc import ABC, abstractmethod
import openai
import anthropic
```

### 3b — New globals
```python
KEYRING_SERVICE = "ai-media-renamer"
PROVIDER_REGISTRY: dict[str, type] = {}
CURRENT_PROVIDER_INSTANCE = None  # Will hold the active AIProvider instance
```

### 3c — New functions

#### `save_config()`
```python
def save_config():
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
```

#### Keyring helpers
```python
def save_api_key(provider_name, key):
    keyring.set_password(KEYRING_SERVICE, provider_name, key)

def load_api_key(provider_name):
    return keyring.get_password(KEYRING_SERVICE, provider_name) or ""

def delete_api_key(provider_name):
    try:
        keyring.delete_password(KEYRING_SERVICE, provider_name)
    except keyring.errors.PasswordDeleteError:
        pass
```

### 3d — AIProvider ABC

```python
class AIProvider(ABC):
    def __init__(self):
        self._model = ""
        self._api_key = ""

    @abstractmethod
    def analyze(self, base64_img, verbose=False):
        ...

    @abstractmethod
    def health_check(self):
        ...

    @abstractmethod
    def available_models(self):
        ...

    @property
    def model(self):
        return self._model

    @model.setter
    def model(self, value):
        self._model = value

    @property
    def api_key(self):
        return self._api_key

    @api_key.setter
    def api_key(self, value):
        self._api_key = value
```

### 3e — OllamaProvider

Refactor from existing `analyze_asset_with_ai()`:

- `analyze()` — same logic: `ollama.generate()`, retry logic, `_parse_ai_response()`, same result dict
- `health_check()` — try `ollama.list()`, return `{"ok": True/False, "message": ...}`
- `available_models()` — call `ollama.list()`, extract model names; fall back to config list if Ollama down
- `model` — defaults to `config["model"]["name"]`

### 3f — GeminiProvider

Refactor from existing `analyze_asset_with_gemini()`:

- `analyze()` — same: `requests.post()` to Gemini API, parse candidates, `_parse_ai_response()`
- `health_check()` — check if `self.api_key` is non-empty
- `available_models()` — return `config["model"]["providers"]["gemini"]["models"]`
- `model` — defaults to first in list

### 3g — OpenAIProvider (new)

```python
class OpenAIProvider(AIProvider):
    def analyze(self, base64_img, verbose=False):
        result = {...}  # same format
        if not self.api_key:
            result["error"] = "api_key_missing"
            return result
        try:
            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": AI_PROMPT},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_img}"}}
                    ]
                }],
                max_tokens=1024
            )
            raw_text = response.choices[0].message.content or ""
            # parse + validate via _parse_ai_response()
            ...
        except Exception as exc:
            result["error"] = "openai_api_error"
            result["detail"] = str(exc)
        return result

    def health_check(self):
        return {"ok": bool(self.api_key),
                "message": "API key set" if self.api_key else "No API key"}

    def available_models(self):
        return config["model"]["providers"]["openai"]["models"]
```

### 3h — AnthropicProvider (new)

```python
class AnthropicProvider(AIProvider):
    def analyze(self, base64_img, verbose=False):
        if not self.api_key:
            return {"ok": False, "error": "api_key_missing", ...}
        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": AI_PROMPT},
                        {"type": "image", "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64_img}}
                    ]
                }]
            )
            raw_text = response.content[0].text
            # parse + validate
            ...
        except Exception as exc:
            result["error"] = "anthropic_api_error"
            result["detail"] = str(exc)
        return result

    def health_check(self):
        return {"ok": bool(self.api_key), "message": ...}

    def available_models(self):
        return config["model"]["providers"]["anthropic"]["models"]
```

### 3i — GroqProvider (extends OpenAIProvider)

Minimal — just override `available_models()` and set `base_url`. Since Groq is OpenAI-compatible, the `analyze()` method from `OpenAIProvider` works with a different `base_url`:

```python
class GroqProvider(OpenAIProvider):
    @property
    def model(self):
        return self._model

    @model.setter
    def model(self, value):
        self._model = value

    def available_models(self):
        return config["model"]["providers"]["groq"]["models"]

    def _make_client(self):
        base = config["model"]["providers"]["groq"].get("base_url",
              "https://api.groq.com/openai/v1")
        return openai.OpenAI(api_key=self.api_key, base_url=base)
```

Actually, to keep OpenAIProvider clean, I'll refactor it to accept a `base_url` parameter:

```python
class OpenAIProvider(AIProvider):
    def __init__(self, base_url=None):
        super().__init__()
        self._base_url = base_url

    def _make_client(self):
        kwargs = {"api_key": self.api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return openai.OpenAI(**kwargs)

class GroqProvider(OpenAIProvider):
    def __init__(self):
        base = config["model"]["providers"]["groq"].get("base_url",
              "https://api.groq.com/openai/v1")
        super().__init__(base_url=base)

    def available_models(self):
        return config["model"]["providers"]["groq"]["models"]
```

### 3j — Provider Registry

```python
def register_provider(name, cls):
    PROVIDER_REGISTRY[name] = cls

def get_provider(name):
    cls = PROVIDER_REGISTRY.get(name)
    if not cls:
        raise ValueError(f"Unknown provider: {name}")
    return cls()

def list_providers():
    return list(PROVIDER_REGISTRY.keys())
```

Register at module load:
```python
register_provider("ollama", OllamaProvider)
register_provider("gemini", GeminiProvider)
register_provider("openai", OpenAIProvider)
register_provider("anthropic", AnthropicProvider)
register_provider("groq", GroqProvider)
```

### 3k — Update switch_ai_provider()

```python
def switch_ai_provider(new_provider, api_key=None):
    global CURRENT_PROVIDER, CURRENT_PROVIDER_INSTANCE

    # Release Ollama model from VRAM if leaving local
    if CURRENT_PROVIDER == "ollama" and new_provider != "ollama":
        try:
            ollama.generate(model=config["model"]["name"], keep_alive=0)
        except Exception:
            pass

    CURRENT_PROVIDER = new_provider
    provider = get_provider(new_provider)
    
    # Load API key from keyring for cloud providers
    if new_provider != "ollama":
        key = api_key or load_api_key(new_provider)
        provider.api_key = key
    else:
        # Set model for Ollama
        provider.model = config["model"]["name"]

    CURRENT_PROVIDER_INSTANCE = provider
    config["model"]["last_provider"] = new_provider
    save_config()

    return {"ok": True, "message": f"Switched to {new_provider}."}
```

### 3l — Update analyze_asset_with_ai() as wrapper

```python
def analyze_asset_with_ai(base64_img, verbose=False, retry=True):
    provider = get_provider("ollama")
    provider.model = config["model"]["name"]
    return provider.analyze(base64_img, verbose=verbose, retry=retry)
```

### 3m — Update analyze_asset_with_gemini() as wrapper

```python
def analyze_asset_with_gemini(base64_img, verbose=False):
    provider = get_provider("gemini")
    provider.api_key = CURRENT_API_KEY or load_api_key("gemini")
    return provider.analyze(base64_img, verbose=verbose)
```

### 3n — Remove set_api_key()

Delete `set_api_key()` — replaced by `save_api_key()` + provider instance.

### 3o — Update _format_ai_error()

Add to messages dict:
```python
'api_key_missing': detail,
'gemini_empty_response': detail,
'gemini_api_error': detail,
'openai_api_error': detail,
'anthropic_api_error': detail,
```

---

## Step 4 — app.py

### 4a — Update imports
- Remove: `analyze_asset_with_ai`, `analyze_asset_with_gemini`, `set_api_key`, `CURRENT_PROVIDER`
- Add: `get_provider`, `list_providers`, `save_api_key`, `load_api_key`, `CURRENT_PROVIDER_INSTANCE`

### 4b — Update sidebar provider section

The sidebar already has provider radio and API key input. Changes:

1. **Provider radio** — Keep, but update `new_provider` mapping to include all 5:
   ```python
   if new_provider != st.session_state.provider:
       result = switch_ai_provider(new_provider)
       st.session_state.provider = new_provider
       st.session_state.api_key = load_api_key(new_provider)
       st.session_state.env_check = None
       st.rerun()
   ```

2. **Model dropdown** — Add below provider radio:
   ```python
   prov = get_provider(st.session_state.provider)
   models = prov.available_models()
   if models:
       current_model = prov.model or models[0]
       idx = models.index(current_model) if current_model in models else 0
       chosen_model = st.selectbox("Model", models, index=idx, key="provider_model",
                                   on_change=_on_model_change)
   ```

3. **API key** — When cloud provider selected:
   ```python
   if new_provider != "ollama":
       st.text_input("API Key", type="password", key="api_key_input",
                     value=st.session_state.get("api_key", ""),
                     on_change=_on_api_key_change)
   ```

4. **Helper callbacks**:
   ```python
   def _on_api_key_change():
       key = st.session_state.api_key_input
       save_api_key(st.session_state.provider, key)
       st.session_state.api_key = key

   def _on_model_change():
       curr = get_provider(st.session_state.provider)
       curr.model = st.session_state.provider_model
       config["model"]["name"] = st.session_state.provider_model
       save_config()
   ```

### 4c — Update analysis routing

Replace:
```python
if st.session_state.provider == "ollama":
    ai_result = analyze_asset_with_ai(b64, verbose=False)
else:
    ai_result = analyze_asset_with_gemini(b64, verbose=False)
```

With:
```python
prov = get_provider(st.session_state.provider)
ai_result = prov.analyze(b64, verbose=False)
```

### 4d — Update environment check gating

The existing gates that check `ollama_running` / `model_available` should only apply when provider is "ollama". For cloud providers, just check API key is set. This already partially exists — just ensure the model-specific gate only fires for "ollama".

---

## Step 5 — Tests

Write `tests/test_providers.py` with these test classes (all use mocking, no real API calls):

| Test Class | What it mocks |
|---|---|
| `TestProviderRegistry` | Registry operations |
| `TestOllamaProvider` | `ollama.generate()`, `ollama.list()` |
| `TestGeminiProvider` | `requests.post()` |
| `TestOpenAIProvider` | `openai.OpenAI` client chat completions |
| `TestAnthropicProvider` | `anthropic.Anthropic` client messages |
| `TestGroqProvider` | Same OpenAI mock, check base_url differs |
| `TestProviderRouting` | `switch_ai_provider()`, `get_provider()` |
| `TestApiKeyStorage` | `keyring.get_password`, `keyring.set_password` (mock keyring) |
| `TestHealthChecks` | Each provider's health_check with various states |

Test scenarios per provider:
- Successful analysis → returns `{"ok": True, "data": {...}}`
- Empty response from AI → returns error
- JSON parse failure → returns `json_parse_error`
- Network error / timeout → returns provider-specific error with detail
- Missing API key → returns `api_key_missing`
- Invalid API key (401) → returns provider-specific error

Expected: ~50 new tests, plus existing 38 must still pass.

---

## Step 6 — Verification

```bash
ruff check --fix .
python -m pytest           # Expected: 88+ tests pass
python -m py_compile engine.py
python -m py_compile app.py
streamlit run app.py       # Manual: Ollama mode works identically
```

---

## Step 7 — Git

```bash
git add -A
git commit -m "feat: Phase R - multi-provider abstraction with Ollama, Gemini, OpenAI, Anthropic, Groq"
git push origin feat/phase-r-multi-provider
```
