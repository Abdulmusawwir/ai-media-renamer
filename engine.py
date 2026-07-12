import base64
import datetime
import json
import logging
import os
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path

import anthropic
import keyring
import ollama
import openai
import requests

# -----------------------------------------------------------------------------
# 0. HELPER: resolve worker count
# -----------------------------------------------------------------------------

def _resolve_workers(cfg_value):
    if isinstance(cfg_value, int) and cfg_value > 0:
        return cfg_value
    return os.cpu_count() or 4

# -----------------------------------------------------------------------------
# 1. CONFIGURATION & LOGGING
# -----------------------------------------------------------------------------

def load_config(config_path="config.json"):
    script_dir = Path(__file__).parent
    full_path = script_dir / config_path
    try:
        with open(full_path, encoding='utf-8') as f:
            cfg = json.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file '{full_path}' not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}")
        sys.exit(1)

    cfg['video_extensions'] = tuple(cfg.get('video_extensions', ['.mp4', '.mov', '.avi', '.mkv', '.webm']))
    cfg['image_extensions'] = tuple(cfg.get('image_extensions', ['.jpg', '.jpeg', '.png', '.webp', '.gif']))
    cfg['allowed_categories'] = tuple(cfg.get('allowed_categories', []))
    return cfg


config = load_config()

ALLOWED_CATEGORIES = config['allowed_categories']

CATEGORY_LIST_STR = "\n".join(f'   - "{c}"' for c in ALLOWED_CATEGORIES)


def get_active_profile():
    return config.get('prompt_profiles', {}).get('active', 'general_balanced')


def get_active_categories():
    profile_name = get_active_profile()
    profile = config.get('prompt_profiles', {}).get('profiles', {}).get(profile_name, {})
    cats = profile.get('allowed_categories', [])
    return tuple(cats) if cats else ALLOWED_CATEGORIES


def get_active_prompt():
    profile_name = get_active_profile()
    profile = config.get('prompt_profiles', {}).get('profiles', {}).get(profile_name, {})
    raw = profile.get('prompt', '')
    cats = get_active_categories()
    cat_str = "\n".join(f'   - "{c}"' for c in cats)
    return raw.replace("the allowed categories list", f"this list:\n{cat_str}")


def set_active_profile(name):
    profiles = config.get('prompt_profiles', {}).get('profiles', {})
    if name in profiles:
        config['prompt_profiles']['active'] = name
        save_config()


def get_profile_labels():
    profiles = config.get('prompt_profiles', {}).get('profiles', {})
    return {k: v.get('label', k) for k, v in profiles.items()}


PROMPT_PROFILES = get_profile_labels()

VIDEO_EXTENSIONS = config['video_extensions']
IMAGE_EXTENSIONS = config['image_extensions']
MODEL_NAME = config['model']['name']
MODEL_TEMPERATURE = config['model']['temperature']
MODEL_NUM_CTX = config['model']['num_ctx']
MODEL_KEEP_ALIVE = config['model']['keep_alive']
IMAGE_PREVIEW_MAX_EDGE = config['preview']['image_max_edge']
VIDEO_GRID_TILE = config['preview']['video_grid_tile']
VIDEO_GRID_SCALE = config['preview']['video_grid_scale']
EXTRACTION_WORKERS = _resolve_workers(config['preview'].get('extraction_workers', 0))

DEFAULT_CASE_STYLE = config.get('naming', {}).get('case_style', 'snake_case')
DEFAULT_MAX_FILENAME_CHARS = config.get('naming', {}).get('max_filename_chars', 0)

CLOUD_PROVIDERS = tuple(config.get('cloud', {}).get('providers', ['gemini', 'openai', 'anthropic', 'groq']))
CURRENT_PROVIDER = config.get('model', {}).get('last_provider', 'ollama')
CURRENT_API_KEY = ""

NAMED_TEMPLATES = config.get('naming_templates', {
    "default": "{category}_{topic}_{description}",
    "short": "{topic}_{description}",
    "editorial": "{date}_{category}_{topic}"
})
DEFAULT_TEMPLATE_STRING = NAMED_TEMPLATES.get("default", "{category}_{topic}_{description}")

LOG_DIR = Path(config['logging']['directory'])
MAX_UPLOAD_SIZE = int(config['logging'].get('max_upload_size', 10737418240))
CONFIG_PATH = Path(__file__).parent / "config.json"
KEYRING_SERVICE = "ai-media-renamer"
PROVIDER_REGISTRY = {}
CURRENT_PROVIDER_INSTANCE = None


def save_config():
    global config
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)


def save_api_key(provider_name, key):
    keyring.set_password(KEYRING_SERVICE, provider_name, key)


def load_api_key(provider_name):
    return keyring.get_password(KEYRING_SERVICE, provider_name) or ""


def delete_api_key(provider_name):
    try:
        keyring.delete_password(KEYRING_SERVICE, provider_name)
    except keyring.errors.PasswordDeleteError:
        pass


def setup_logging(verbose=False):
    log_dir = LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"renamer_{datetime.datetime.now().astimezone().date().isoformat()}.jsonl"

    logger = logging.getLogger('video_renamer')
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
    file_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(file_handler)

    return logger


def log_event(logger, level, event, file_name=None, details=None):
    record = {
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
        "level": level,
        "event": event,
        "file": file_name,
    }
    if details:
        record["details"] = details
    msg = json.dumps(record)
    if level == "DEBUG":
        logger.debug(msg)
    elif level == "WARNING":
        logger.warning(msg)
    elif level == "ERROR":
        logger.error(msg)
    else:
        logger.info(msg)


# -----------------------------------------------------------------------------
# 2. EXIFTOOL PERSISTENT BACKGROUND PROCESS (stay_open)
# -----------------------------------------------------------------------------

class ExifToolSession:
    def __init__(self):
        try:
            self.process = subprocess.Popen(
                ['exiftool', '-stay_open', 'True', '-@', '-'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', bufsize=1
            )
        except FileNotFoundError:
            print("Error: ExifTool is not installed or not in system PATH.")
            sys.exit(1)

    def execute(self, args):
        for arg in args:
            self.process.stdin.write(f"{arg}\n")
        self.process.stdin.write("-execute\n")
        self.process.stdin.flush()

        output = ""
        for line in self.process.stdout:
            if "{ready}" in line:
                break
            output += line
        return output

    def close(self):
        if hasattr(self, 'process'):
            self.process.stdin.write("-stay_open\nFalse\n")
            self.process.stdin.flush()
            self.process.wait()


# -----------------------------------------------------------------------------
# 3. HARDWARE & CACHE MANAGERS
# -----------------------------------------------------------------------------

def detect_hw_accel():
    for hw in ['cuda', 'qsv', 'amf']:
        try:
            cmd = ['ffmpeg', '-hwaccel', hw, '-f', 'lavfi', '-i', 'color=c=black:s=16x16:d=1', '-f', 'null', '-']
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode == 0:
                return hw
        except Exception:
            pass
    return None


def is_already_processed(file_path, exiftool_session):
    output = exiftool_session.execute(["-XMP-dc:Description", "-s3", str(file_path)])
    return len(output.strip()) > 0


# -----------------------------------------------------------------------------
# 4. ZERO-I/O PIPELINE (MEMORY-BASED ASSET EXTRACTION)
# -----------------------------------------------------------------------------

def get_video_duration(video_path):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
           '-of', 'default=noprint_wrappers=1:nokey=1', str(video_path)]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
        return float(output)
    except Exception:
        return 10.0


def process_video_to_base64(video_path, hw_accel):
    duration = get_video_duration(video_path)
    mid_offset = max(1.0, duration * 0.5)

    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
    if hw_accel:
        cmd.extend(['-hwaccel', hw_accel])

    cmd.extend([
        '-ss', str(mid_offset),
        '-i', str(video_path),
        '-vframes', '1',
        '-vf', f"scale={VIDEO_GRID_SCALE}:-1",
        '-f', 'image2pipe',
        '-vcodec', 'mjpeg',
        '-'
    ])

    try:
        process = subprocess.run(cmd, capture_output=True, check=True)
        return base64.b64encode(process.stdout).decode('utf-8')
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def process_image_to_base64(image_path, max_edge=IMAGE_PREVIEW_MAX_EDGE):
    cmd = [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
        '-i', str(image_path),
        '-vf', f"scale={max_edge}:{max_edge}:force_original_aspect_ratio=decrease",
        '-frames:v', '1',
        '-f', 'image2pipe',
        '-vcodec', 'mjpeg',
        '-q:v', '3',
        '-'
    ]
    try:
        process = subprocess.run(cmd, capture_output=True, check=True)
        return base64.b64encode(process.stdout).decode('utf-8')
    except subprocess.CalledProcessError:
        return None
    except FileNotFoundError:
        return None


def process_asset_to_base64(file_path, hw_accel):
    if file_path.suffix.lower() in VIDEO_EXTENSIONS:
        return process_video_to_base64(file_path, hw_accel)
    return process_image_to_base64(file_path)


# -----------------------------------------------------------------------------
# 5. AI ENGINE & EXECUTION
# -----------------------------------------------------------------------------

def validate_category(raw_category):
    if not raw_category or not str(raw_category).strip():
        return 'uncategorized', True
    normalized = str(raw_category).lower().strip().replace(" ", "_")
    safe_chars = [c for c in normalized if c.isalpha() or c.isdigit() or c in ('_', '-')]
    normalized = "".join(safe_chars).strip('_')
    if not normalized:
        return 'uncategorized', True
    if normalized in ALLOWED_CATEGORIES:
        return normalized, False
    return 'uncategorized', True


def sanitize_name(raw_name):
    cleaned = raw_name.lower().replace("grid", "").replace("sequence", "")
    cleaned = cleaned.replace(" ", "_")
    safe = "".join([c for c in cleaned if c.isalpha() or c.isdigit() or c in ('_', '-')]).strip('_')
    if len(safe.split('_')) < 3:
        safe = f"{safe}_media_asset"
    return safe


def apply_case_style(name, style):
    if style == "snake_case":
        return name.lower().replace("-", "_").replace(" ", "_")
    elif style == "camelCase":
        parts = name.replace("-", "_").replace(" ", "_").split("_")
        return parts[0].lower() + "".join(p.capitalize() for p in parts[1:])
    elif style == "kebab-case":
        return name.lower().replace("_", "-").replace(" ", "-")
    elif style == "pascal_case":
        parts = name.replace("-", "_").replace(" ", "_").split("_")
        return "".join(p.capitalize() for p in parts)
    elif style == "lowercase":
        return name.lower().replace("_", "").replace("-", "").replace(" ", "")
    else:
        return name


def truncate_filename(name, max_chars):
    if max_chars <= 0 or len(name) <= max_chars:
        return name
    return name[:max_chars].rstrip("_-")


def _template_date():
    return datetime.date.today().isoformat()


def apply_naming_template(template_string, asset_data):
    category = asset_data.get('category', 'uncategorized')
    topic = asset_data.get('topic', '') or ''
    description = asset_data.get('description', '') or ''
    fallback = asset_data.get('new_filename', '')

    if not topic and not description:
        return fallback

    result = template_string
    result = result.replace("{category}", category)
    result = result.replace("{topic}", topic)
    result = result.replace("{description}", description)
    result = result.replace("{date}", _template_date())

    while "__" in result:
        result = result.replace("__", "_")
    while "--" in result:
        result = result.replace("--", "-")
    result = result.strip("_-")

    if not result or result == template_string:
        return fallback

    return result


def _parse_ai_response(raw_text):
    clean_res = raw_text.strip()
    if not clean_res:
        return None, 'empty_response', 'Model returned an empty response'

    if clean_res.startswith("```json"):
        clean_res = clean_res.split("```json")[1].split("```")[0].strip()
    elif clean_res.startswith("```"):
        clean_res = clean_res.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(clean_res), None, None
    except json.JSONDecodeError as exc:
        return None, 'json_parse_error', f'JSON decode failed: {exc}'


# -----------------------------------------------------------------------------
# 5b. AI PROVIDERS (Abstract base + implementations)
# -----------------------------------------------------------------------------

VISION_MODEL_PREFIXES = {
    "llava", "bakllava", "qwen2.5vl", "qwen2-vl", "minicpm", "cogvlm", "moondream",
    "yi-vl", "gemma3", "xclip", "llama3.2-vision", "llama3.2-11b-vision",
    "llama3.2-90b-vision", "pixtral",
}


def _is_vision_model(name):
    name_lower = name.lower().replace(":", "-")
    for prefix in VISION_MODEL_PREFIXES:
        if name_lower.startswith(prefix.lower()):
            return True
    return False


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

    def _parse_and_validate(self, raw_text):
        result = {'ok': False, 'data': None, 'error': None, 'detail': None, 'raw_response': raw_text}
        parsed, error_type, detail = _parse_ai_response(raw_text)
        if error_type:
            result['error'] = error_type
            result['detail'] = detail
            return result
        if 'new_filename' not in parsed:
            result['error'] = 'missing_keys'
            result['detail'] = "Response JSON is missing required key 'new_filename'"
            return result
        result['ok'] = True
        result['data'] = parsed
        return result


class OllamaProvider(AIProvider):
    def __init__(self):
        super().__init__()
        self._model = MODEL_NAME
        self._retries = 2

    def analyze(self, base64_img, verbose=False):
        result = {'ok': False, 'data': None, 'error': None, 'detail': None, 'raw_response': None}
        last_exc = None
        for attempt in range(self._retries):
            try:
                response = ollama.generate(
                    model=self._model,
                    prompt=get_active_prompt(),
                    images=[base64_img],
                    keep_alive=MODEL_KEEP_ALIVE,
                    options={"temperature": MODEL_TEMPERATURE, "num_ctx": MODEL_NUM_CTX}
                )
                raw_text = response.get('response', '')
                parsed = self._parse_and_validate(raw_text)
                if parsed['ok'] or attempt == self._retries - 1:
                    return parsed
                last_exc = parsed.get('detail')
            except (ollama.ResponseError, ConnectionError, TimeoutError, OSError) as exc:
                last_exc = exc
                if attempt < self._retries - 1:
                    continue
                result['error'] = 'ollama_error'
                result['detail'] = f'Ollama request failed: {exc}'
                return result
            except Exception as exc:
                result['error'] = 'ollama_error'
                result['detail'] = f'Unexpected AI error: {exc}'
                return result
        if last_exc:
            result['error'] = 'ollama_error'
            result['detail'] = f'Ollama request failed after retry: {last_exc}'
        return result

    def health_check(self):
        try:
            ollama.list()
            return {"ok": True, "message": "Ollama is running."}
        except Exception as exc:
            return {"ok": False, "message": f"Ollama not reachable: {exc}"}

    def available_models(self):
        try:
            tags = ollama.list()
            models = []
            for m in tags.get('models', []):
                if isinstance(m, dict):
                    name = m.get('name', '')
                elif hasattr(m, 'model'):
                    name = m.model
                else:
                    name = str(m)
                if name:
                    models.append(name)
            return models
        except Exception:
            return config.get("model", {}).get("providers", {}).get("ollama", {}).get("models", [])


class GeminiProvider(AIProvider):
    def analyze(self, base64_img, verbose=False):
        result = {'ok': False, 'data': None, 'error': None, 'detail': None, 'raw_response': None}
        if not self._api_key:
            result['error'] = 'api_key_missing'
            result['detail'] = 'Gemini API key not configured.'
            return result
        try:
            model_name = self._model or "gemini-2.0-flash-001"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self._api_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": get_active_prompt()},
                        {"inline_data": {"mime_type": "image/jpeg", "data": base64_img}}
                    ]
                }]
            }
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                result['error'] = 'gemini_empty_response'
                result['detail'] = 'Gemini returned no candidates.'
                return result
            raw_text = ""
            for part in candidates[0].get("content", {}).get("parts", []):
                raw_text += part.get("text", "")
            return self._parse_and_validate(raw_text)
        except requests.exceptions.RequestException as exc:
            result['error'] = 'gemini_api_error'
            result['detail'] = f'Gemini API request failed: {exc}'
            return result
        except Exception as exc:
            result['error'] = 'gemini_api_error'
            result['detail'] = f'Unexpected Gemini error: {exc}'
            return result

    def health_check(self):
        return {"ok": bool(self._api_key), "message": "API key set" if self._api_key else "No API key configured"}

    def available_models(self):
        return config.get("model", {}).get("providers", {}).get("gemini", {}).get("models", [])


class OpenAIProvider(AIProvider):
    def __init__(self, base_url=None):
        super().__init__()
        self._base_url = base_url

    def _make_client(self):
        kwargs = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return openai.OpenAI(**kwargs)

    def analyze(self, base64_img, verbose=False):
        result = {'ok': False, 'data': None, 'error': None, 'detail': None, 'raw_response': None}
        if not self._api_key:
            result['error'] = 'api_key_missing'
            result['detail'] = 'API key not configured.'
            return result
        try:
            client = self._make_client()
            model_name = self._model or "gpt-4o"
            response = client.chat.completions.create(
                model=model_name,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": get_active_prompt()},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                    ]
                }],
                max_tokens=1024
            )
            raw_text = response.choices[0].message.content or ""
            return self._parse_and_validate(raw_text)
        except Exception as exc:
            result['error'] = 'openai_api_error'
            result['detail'] = f'OpenAI API request failed: {exc}'
            return result

    def health_check(self):
        return {"ok": bool(self._api_key), "message": "API key set" if self._api_key else "No API key configured"}

    def available_models(self):
        return config.get("model", {}).get("providers", {}).get("openai", {}).get("models", [])


class AnthropicProvider(AIProvider):
    def analyze(self, base64_img, verbose=False):
        result = {'ok': False, 'data': None, 'error': None, 'detail': None, 'raw_response': None}
        if not self._api_key:
            result['error'] = 'api_key_missing'
            result['detail'] = 'API key not configured.'
            return result
        try:
            client = anthropic.Anthropic(api_key=self._api_key)
            model_name = self._model or "claude-3-5-sonnet-20241022"
            response = client.messages.create(
                model=model_name,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": get_active_prompt()},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64_img}}
                    ]
                }]
            )
            raw_text = response.content[0].text
            return self._parse_and_validate(raw_text)
        except Exception as exc:
            result['error'] = 'anthropic_api_error'
            result['detail'] = f'Anthropic API request failed: {exc}'
            return result

    def health_check(self):
        return {"ok": bool(self._api_key), "message": "API key set" if self._api_key else "No API key configured"}

    def available_models(self):
        return config.get("model", {}).get("providers", {}).get("anthropic", {}).get("models", [])


class GroqProvider(OpenAIProvider):
    def __init__(self):
        base = config.get("model", {}).get("providers", {}).get("groq", {}).get("base_url", "https://api.groq.com/openai/v1")
        super().__init__(base_url=base)

    def available_models(self):
        return config.get("model", {}).get("providers", {}).get("groq", {}).get("models", [])


class OpenRouterProvider(OpenAIProvider):
    def __init__(self):
        base = config.get("model", {}).get("providers", {}).get("openrouter", {}).get("base_url", "https://openrouter.ai/api/v1")
        super().__init__(base_url=base)

    def available_models(self):
        return config.get("model", {}).get("providers", {}).get("openrouter", {}).get("models", [])


def register_provider(name, cls):
    PROVIDER_REGISTRY[name] = cls


def get_provider(name):
    cls = PROVIDER_REGISTRY.get(name)
    if not cls:
        raise ValueError(f"Unknown provider: {name}")
    inst = cls()
    if name != "ollama":
        inst.api_key = load_api_key(name)
    pconf = config.get("model", {}).get("providers", {}).get(name, {})
    valid_models = pconf.get("models", [])
    saved_model = pconf.get("selected_model", "")
    if saved_model and (name == "ollama" or saved_model in valid_models):
        inst.model = saved_model
    elif name != "ollama" and valid_models:
        inst.model = valid_models[0]
    return inst


def list_providers():
    return list(PROVIDER_REGISTRY.keys())


register_provider("ollama", OllamaProvider)
register_provider("gemini", GeminiProvider)
register_provider("openai", OpenAIProvider)
register_provider("anthropic", AnthropicProvider)
register_provider("groq", GroqProvider)
register_provider("openrouter", OpenRouterProvider)


def analyze_asset_with_ai(base64_img, verbose=False, retry=True):
    provider = get_provider("ollama")
    provider.model = MODEL_NAME
    return provider.analyze(base64_img, verbose=verbose)


def analyze_asset_with_gemini(base64_img, verbose=False):
    provider = get_provider("gemini")
    provider.api_key = CURRENT_API_KEY or load_api_key("gemini")
    return provider.analyze(base64_img, verbose=verbose)


def _format_ai_error(ai_result, verbose=False):
    error_type = ai_result.get('error', 'unknown')
    detail = ai_result.get('detail', 'Unknown error')
    messages = {
        'json_parse_error': f'AI response was not valid JSON -- {detail}',
        'missing_keys': detail,
        'empty_response': detail,
        'ollama_error': detail,
        'api_key_missing': detail,
        'gemini_empty_response': detail,
        'gemini_api_error': detail,
        'openai_api_error': detail,
        'anthropic_api_error': detail,
    }
    msg = messages.get(error_type, detail)
    if verbose and ai_result.get('raw_response'):
        snippet = ai_result['raw_response'][:500]
        msg += f"\n    [verbose] Raw model response: {snippet!r}"
    return msg


def execute_commit(asset, target_dir, sort_into_folders, exiftool_session):
    old_path = asset['original_path']
    safe_name = asset['staged_name']
    suffix = old_path.suffix.lower()

    final_folder = target_dir / asset['category'] if sort_into_folders else target_dir
    final_folder.mkdir(parents=True, exist_ok=True)

    new_filename = f"{safe_name}{suffix}"
    new_path = final_folder / new_filename

    counter = 1
    while new_path.exists() and new_path != old_path:
        new_filename = f"{safe_name}_{counter}{suffix}"
        new_path = final_folder / new_filename
        counter += 1

    try:
        old_path.rename(new_path)

        tag_string = ", ".join(asset['tags'])
        summary = asset['summary']
        is_video = suffix in VIDEO_EXTENSIONS

        args = [
            "-overwrite_original",
            "-api", "LargeFileSupport=1",
            f"-XMP-dc:Description={summary}",
            f"-Microsoft:Category={tag_string}"
        ]
        # Write each tag as an individual XMP array element (Windows reads this)
        for t in asset['tags']:
            args.append(f"-XMP-dc:Subject={t}")

        if is_video:
            args.extend([
                f"-QuickTime:Description={summary}",
                f"-QuickTime:Comment={summary}",
                f"-QuickTime:Keywords={tag_string}",
                f"-Keys:Description={summary}",
                f"-Keys:Keywords={tag_string}"
            ])
        else:
            # Windows reads XPKeywords for the "Tags" property in Explorer
            args.append(f"-EXIF:XPKeywords={tag_string}")
            args.extend([
                f"-Description={summary}",
                f"-Comment={summary}",
            ] + [f"-Keywords={t}" for t in asset['tags']])

        args.append(str(new_path))
        exiftool_session.execute(args)

        return new_path.relative_to(target_dir)
    except Exception as e:
        return f"ERROR:{e}"


# -----------------------------------------------------------------------------
# 6. BOOTSTRAP & ENVIRONMENT
# -----------------------------------------------------------------------------


def _resolve_binary_path(name):
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidate = os.path.join(meipass, 'bin', name)
        if os.path.isfile(candidate):
            return candidate
    resolved = shutil.which(name)
    return resolved


def check_ollama_health():
    try:
        tags = ollama.list()
        models = tags.get('models', [])
        model_list = []
        for m in models:
            name = m.get('name', '') if isinstance(m, dict) else str(m)
            if _is_vision_model(name):
                model_list.append(name)
        return {
            "connected": True,
            "models": model_list,
            "model_count": len(models),
            "error": None,
        }
    except Exception as exc:
        return {
            "connected": False,
            "models": [],
            "model_count": 0,
            "error": str(exc),
        }


def check_environment():
    ffmpeg_path = _resolve_binary_path("ffmpeg")
    exiftool_path = _resolve_binary_path("exiftool")
    ollama_running = False
    model_available = False
    errors = []

    if not ffmpeg_path:
        errors.append("FFmpeg not found. Install FFmpeg and add it to your PATH.")

    if not exiftool_path:
        errors.append("ExifTool not found. Install ExifTool and add it to your PATH.")

    try:
        tags = ollama.list()
        ollama_running = True
        models = tags.get('models', [])
        for m in models:
            name = m.get('name', '') if isinstance(m, dict) else str(m)
            if 'qwen2.5vl' in name:
                model_available = True
                break
    except Exception:
        ollama_running = False
        errors.append("Ollama is not running. Start Ollama and try again.")

    cloud_configured = CURRENT_PROVIDER != "ollama"

    return {
        "ffmpeg": bool(ffmpeg_path),
        "exiftool": bool(exiftool_path),
        "ollama_running": ollama_running,
        "model_available": model_available,
        "cloud_configured": cloud_configured,
        "errors": errors,
    }


def stream_model_download(model_name="qwen2.5vl:7b"):
    try:
        current_stream = ollama.pull(model_name, stream=True)
        for chunk in current_stream:
            status = chunk.get('status', '')
            if status == 'success':
                yield {"status": "success", "message": f"Model {model_name} ready"}
                return

            completed = chunk.get('completed', 0) or 0
            total = chunk.get('total', 0) or 0
            if total and completed:
                percentage = (completed / total) * 100.0
                yield {
                    "status": "progress",
                    "completed": completed,
                    "total": total,
                    "percentage": percentage,
                    "detail": status,
                }
            else:
                yield {"status": "status", "detail": status,
                       "completed": completed, "total": total}

        yield {"status": "success", "message": f"Model {model_name} ready"}
    except Exception as exc:
        yield {"status": "error", "message": str(exc)}


def switch_ai_provider(new_provider, api_key=None):
    global CURRENT_PROVIDER, CURRENT_API_KEY, CURRENT_PROVIDER_INSTANCE

    if CURRENT_PROVIDER == "ollama" and new_provider != "ollama":
        try:
            ollama.generate(model=MODEL_NAME, keep_alive=0)
        except Exception:
            pass

    CURRENT_PROVIDER = new_provider

    provider = get_provider(new_provider)
    if api_key:
        CURRENT_API_KEY = api_key
        save_api_key(new_provider, api_key)
        provider.api_key = api_key
    elif new_provider != "ollama":
        stored = load_api_key(new_provider)
        CURRENT_API_KEY = stored
        provider.api_key = stored
    pconf = config.get("model", {}).get("providers", {}).get(new_provider, {})
    provider.model = pconf.get("selected_model", "") or (pconf.get("models") or [None])[0] or MODEL_NAME

    CURRENT_PROVIDER_INSTANCE = provider
    config["model"]["last_provider"] = new_provider
    save_config()

    if new_provider != "ollama":
        return {"ok": True, "message": f"Switched to {new_provider}. Local model weights released from RAM/VRAM."}

    env = check_environment()
    if not env["ollama_running"]:
        return {"ok": False, "require_download": False, "message": "Ollama is not running. Start Ollama first."}
    if not env["model_available"]:
        return {"ok": False, "require_download": True, "message": "Model qwen2.5vl:7b not found. Download required."}
    return {"ok": True, "message": "Switched to local Ollama."}


def set_api_key(key):
    global CURRENT_API_KEY
    CURRENT_API_KEY = key


def wipe_local_model(model_name="qwen2.5vl:7b"):
    try:
        ollama.delete(model_name)
        return {"ok": True, "message": f"Model {model_name} deleted."}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


# -----------------------------------------------------------------------------
# 7. STAGING EXPORT / IMPORT
# -----------------------------------------------------------------------------

def export_staging_csv(staged_assets):
    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["original_name", "proposed_filename", "category", "tags", "summary"])
    for a in staged_assets:
        writer.writerow([
            a.get("original_name", ""),
            a.get("staged_name", ""),
            a.get("category", ""),
            ", ".join(a.get("tags", [])),
            a.get("summary", ""),
        ])
    return output.getvalue()


def export_staging_json(staged_assets):
    clean = []
    for a in staged_assets:
        clean.append({
            "original_name": a.get("original_name", ""),
            "proposed_filename": a.get("staged_name", ""),
            "category": a.get("category", ""),
            "tags": a.get("tags", []),
            "summary": a.get("summary", ""),
        })
    return json.dumps(clean, indent=2)


def import_staging_csv(csv_string, allowed_categories):
    import csv
    import io
    assets = []
    warnings = []
    reader = csv.DictReader(io.StringIO(csv_string))
    allowed = set(allowed_categories)
    for row_num, row in enumerate(reader, start=2):
        tags_raw = row.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        category = row.get("category", "").strip().lower().replace(" ", "_")
        safe_chars = [c for c in category if c.isalpha() or c.isdigit() or c in ("_", "-")]
        category = "".join(safe_chars).strip("_")
        if category and category not in allowed:
            warnings.append(f"Row {row_num}: unknown category '{category}' → fallback to 'uncategorized'")
            category = "uncategorized"
        if not category:
            category = "uncategorized"
        assets.append({
            "original_name": row.get("original_name", ""),
            "staged_name": row.get("proposed_filename", ""),
            "category": category,
            "tags": tags,
            "summary": row.get("summary", ""),
        })
    return assets, warnings
