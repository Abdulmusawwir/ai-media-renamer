from __future__ import annotations

import atexit
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
from typing import Any, Callable

import anthropic
import keyring
import ollama
import openai
import requests

VERSION = "v1.4.2"

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# -----------------------------------------------------------------------------
# 0. HELPER: resolve worker count
# -----------------------------------------------------------------------------

def _resolve_workers(cfg_value: int | float | None) -> int:
    """Resolve worker count from config value, falling back to CPU count.

    Args:
        cfg_value: Configured worker count from config, or None/0 for auto.

    Returns:
        Positive integer worker count.
    """
    if isinstance(cfg_value, int) and cfg_value > 0:
        return cfg_value
    return os.cpu_count() or 4

# -----------------------------------------------------------------------------
# 1. CONFIGURATION & LOGGING
# -----------------------------------------------------------------------------

def load_config(config_path: str = "config.json") -> dict[str, Any]:
    """Load configuration from JSON file with auto-recovery from default.

    Args:
        config_path: Relative path to the config file from the script directory.

    Returns:
        Parsed configuration dictionary with normalized tuple fields.
    """
    script_dir = Path(__file__).parent
    full_path = script_dir / config_path
    default_path = full_path.parent / "config.default.json"
    try:
        with open(full_path, encoding='utf-8') as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: config.json issue: {e}. Attempting auto-recovery from config.default.json...")
        try:
            import shutil
            shutil.copy2(default_path, full_path)
            with open(full_path, encoding='utf-8') as f:
                cfg = json.load(f)
            print(f"Auto-recovery successful: restored config.json from config.default.json")
        except Exception as recovery_err:
            print(f"Error: Auto-recovery failed: {recovery_err}")
            print(f"To fix: manually copy config.default.json to config.json, or run with --reset-config")
            sys.exit(1)

    cfg['video_extensions'] = tuple(cfg.get('video_extensions', ['.mp4', '.mov', '.avi', '.mkv', '.webm']))
    cfg['image_extensions'] = tuple(cfg.get('image_extensions', ['.jpg', '.jpeg', '.png', '.webp', '.gif']))
    cfg['allowed_categories'] = tuple(cfg.get('allowed_categories', []))
    return cfg


def restore_default_config() -> bool:
    """Overwrite config.json with config.default.json. Returns True on success."""
    import shutil
    script_dir = Path(__file__).parent
    default_path = script_dir / "config.default.json"
    target_path = script_dir / "config.json"
    if not default_path.exists():
        return False
    shutil.copy2(default_path, target_path)
    return True


config = load_config()

ALLOWED_CATEGORIES = config['allowed_categories']

CATEGORY_LIST_STR = "\n".join(f'   - "{c}"' for c in ALLOWED_CATEGORIES)


def get_active_profile() -> str:
    """Return the name of the currently active prompt profile."""
    return config.get('prompt_profiles', {}).get('active', 'general_balanced')


def get_active_categories() -> tuple[str, ...]:
    """Return the allowed categories for the active prompt profile."""
    profile_name = get_active_profile()
    profile = config.get('prompt_profiles', {}).get('profiles', {}).get(profile_name, {})
    cats = profile.get('allowed_categories', [])
    return tuple(cats) if cats else ALLOWED_CATEGORIES


def get_active_prompt() -> str:
    """Return the active prompt text with categories expanded into the template."""
    profile_name = get_active_profile()
    profile = config.get('prompt_profiles', {}).get('profiles', {}).get(profile_name, {})
    raw = profile.get('prompt', '')
    cats = get_active_categories()
    cat_str = "\n".join(f'   - "{c}"' for c in cats)
    return raw.replace("the allowed categories list", f"this list:\n{cat_str}")


def set_active_profile(name: str) -> None:
    """Set the active prompt profile by name and persist to config.

    Args:
        name: Profile key to activate.
    """
    profiles = config.get('prompt_profiles', {}).get('profiles', {})
    if name in profiles:
        config['prompt_profiles']['active'] = name
        save_config()


def get_profile_labels() -> dict[str, str]:
    """Return a mapping of profile keys to their display labels."""
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

DEFAULT_CASE_STYLE = config.get('naming', {}).get('case_style', 'title_case')
DEFAULT_MAX_FILENAME_CHARS = config.get('naming', {}).get('max_filename_chars', 0)

CLOUD_PROVIDERS = tuple(config.get('cloud', {}).get('providers', ['gemini', 'openai', 'anthropic', 'groq']))
CURRENT_PROVIDER = config.get('model', {}).get('last_provider', 'ollama')
CURRENT_API_KEY = ""

NAMED_TEMPLATES = config.get('naming_templates', {
    "default": "{topic}_{description}",
    "short": "{topic}_{description}",
    "editorial": "{date}_{topic}"
})
DEFAULT_TEMPLATE_STRING = NAMED_TEMPLATES.get("default", "{topic}_{description}")

LOG_DIR = Path(config['logging']['directory'])
MAX_UPLOAD_SIZE = int(config['logging'].get('max_upload_size', 10737418240))
CONFIG_PATH = Path(__file__).parent / "config.json"
KEYRING_SERVICE = "ai-media-renamer"
PROVIDER_REGISTRY = {}
CURRENT_PROVIDER_INSTANCE = None


def save_config() -> None:
    """Persist the current in-memory config dict to config.json."""
    global config
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)


def reload_config() -> None:
    """Reload config from disk and refresh all module-level globals."""
    global config, ALLOWED_CATEGORIES, VIDEO_EXTENSIONS, IMAGE_EXTENSIONS
    global MODEL_NAME, MODEL_TEMPERATURE, MODEL_NUM_CTX, MODEL_KEEP_ALIVE
    global EXTRACTION_WORKERS, DEFAULT_CASE_STYLE, DEFAULT_MAX_FILENAME_CHARS
    global NAMED_TEMPLATES, DEFAULT_TEMPLATE_STRING, PROMPT_PROFILES, CURRENT_PROVIDER
    config = load_config()
    ALLOWED_CATEGORIES = config['allowed_categories']
    VIDEO_EXTENSIONS = config['video_extensions']
    IMAGE_EXTENSIONS = config['image_extensions']
    MODEL_NAME = config['model']['name']
    MODEL_TEMPERATURE = config['model']['temperature']
    MODEL_NUM_CTX = config['model']['num_ctx']
    MODEL_KEEP_ALIVE = config['model']['keep_alive']
    EXTRACTION_WORKERS = _resolve_workers(config['preview'].get('extraction_workers', 0))
    DEFAULT_CASE_STYLE = config.get('naming', {}).get('case_style', 'title_case')
    DEFAULT_MAX_FILENAME_CHARS = config.get('naming', {}).get('max_filename_chars', 0)
    NAMED_TEMPLATES = config.get('naming_templates', {
        "default": "{topic}_{description}",
        "short": "{topic}_{description}",
        "editorial": "{date}_{topic}"
    })
    DEFAULT_TEMPLATE_STRING = NAMED_TEMPLATES.get("default", "{topic}_{description}")
    PROMPT_PROFILES = get_profile_labels()
    CURRENT_PROVIDER = config.get('model', {}).get('last_provider', 'ollama')


def save_api_key(provider_name: str, key: str) -> None:
    """Store an API key for a provider in the system keyring.

    Args:
        provider_name: Provider identifier (e.g. 'gemini', 'openai').
        key: API key string to store.
    """
    keyring.set_password(KEYRING_SERVICE, provider_name, key)


def load_api_key(provider_name: str) -> str:
    """Retrieve an API key from the system keyring.

    Args:
        provider_name: Provider identifier to look up.

    Returns:
        The stored API key, or an empty string if not found.
    """
    return keyring.get_password(KEYRING_SERVICE, provider_name) or ""


def delete_api_key(provider_name: str) -> None:
    """Delete an API key from the system keyring, ignoring if absent.

    Args:
        provider_name: Provider identifier whose key to delete.
    """
    try:
        keyring.delete_password(KEYRING_SERVICE, provider_name)
    except keyring.errors.PasswordDeleteError:
        pass


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure and return the application JSONL file logger.

    Args:
        verbose: If True, set log level to DEBUG; otherwise INFO.

    Returns:
        Configured logger instance writing to the daily log file.
    """
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


def log_event(logger: Any, level: str, event: str, file_name: str | None = None, details: dict[str, Any] | None = None) -> None:
    """Write a structured JSON log entry.

    Args:
        logger: Logger instance to write to.
        level: Log level string ('DEBUG', 'INFO', 'WARNING', 'ERROR').
        event: Short event description.
        file_name: Optional name of the file being processed.
        details: Optional dictionary of additional context.
    """
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
    def __init__(self) -> None:
        """Start a persistent ExifTool subprocess in stay_open mode."""
        try:
            self.process = subprocess.Popen(
                ['exiftool', '-stay_open', 'True', '-@', '-'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', bufsize=1,
                creationflags=_NO_WINDOW,
            )
        except FileNotFoundError:
            print("Error: ExifTool is not installed or not in system PATH.")
            sys.exit(1)

    def execute(self, args: list[str]) -> str:
        """Send arguments to ExifTool and return the output.

        Args:
            args: List of ExifTool arguments (flags and file paths).

        Returns:
            Raw text output from ExifTool.
        """
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

    def close(self) -> None:
        """Shut down the persistent ExifTool subprocess."""
        if hasattr(self, 'process'):
            self.process.stdin.write("-stay_open\nFalse\n")
            self.process.stdin.flush()
            self.process.wait()


# -----------------------------------------------------------------------------
# 3. HARDWARE & CACHE MANAGERS
# -----------------------------------------------------------------------------

def detect_hw_accel() -> str | None:
    """Probe for available hardware-accelerated FFmpeg decoders.

    Returns:
        Hardware accelerator name ('cuda', 'qsv', 'amf') or None.
    """
    for hw in ['cuda', 'qsv', 'amf']:
        try:
            cmd = ['ffmpeg', '-hwaccel', hw, '-f', 'lavfi', '-i', 'color=c=black:s=16x16:d=1', '-f', 'null', '-']
            res = subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW)
            if res.returncode == 0:
                return hw
        except Exception:
            pass
    return None


def is_already_processed(file_path: str | Path, exiftool_session: Any) -> bool:
    """Check if a file already has XMP Description metadata written.

    Args:
        file_path: Path to the media file.
        exiftool_session: Active ExifToolSession instance.

    Returns:
        True if the file already has a DC:Description tag.
    """
    output = exiftool_session.execute(["-XMP-dc:Description", "-json", str(file_path)])
    try:
        data = json.loads(output.strip())
        if isinstance(data, list) and len(data) > 0:
            return "XMP-dc:Description" in data[0]
    except (json.JSONDecodeError, TypeError, IndexError):
        pass
    return False


# -----------------------------------------------------------------------------
# 4. ZERO-I/O PIPELINE (MEMORY-BASED ASSET EXTRACTION)
# -----------------------------------------------------------------------------

def get_video_duration(video_path: str | Path) -> float:
    """Return the duration in seconds of a video file, with internal caching.

    Args:
        video_path: Path to the video file.

    Returns:
        Duration in seconds, defaulting to 10.0 on probe failure.
    """
    cache_key = str(video_path)
    if not hasattr(get_video_duration, '_cache'):
        get_video_duration._cache = {}
    if cache_key in get_video_duration._cache:
        return get_video_duration._cache[cache_key]
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
           '-of', 'default=noprint_wrappers=1:nokey=1', str(video_path)]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, creationflags=_NO_WINDOW).decode().strip()
        duration = float(output)
    except Exception:
        duration = 10.0
    get_video_duration._cache[cache_key] = duration
    return duration


def process_video_to_base64(video_path: str | Path, hw_accel: str | None) -> str | None:
    """Extract the midpoint frame of a video and return as base64 JPEG.

    Args:
        video_path: Path to the video file.
        hw_accel: Hardware accelerator name or None for software decoding.

    Returns:
        Base64-encoded JPEG string, or None on failure.
    """
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
        process = subprocess.run(cmd, capture_output=True, check=True, creationflags=_NO_WINDOW)
        return base64.b64encode(process.stdout).decode('utf-8')
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def process_image_to_base64(image_path: str | Path, max_edge: int = IMAGE_PREVIEW_MAX_EDGE) -> str | None:
    """Downscale an image and return as base64 JPEG.

    Args:
        image_path: Path to the image file.
        max_edge: Maximum pixel dimension for the longest edge.

    Returns:
        Base64-encoded JPEG string, or None on failure.
    """
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
        process = subprocess.run(cmd, capture_output=True, check=True, creationflags=_NO_WINDOW)
        return base64.b64encode(process.stdout).decode('utf-8')
    except subprocess.CalledProcessError:
        return None
    except FileNotFoundError:
        return None


def process_asset_to_base64(file_path: Path, hw_accel: str | None) -> str | None:
    """Route a media file to the appropriate base64 encoder.

    Args:
        file_path: Path to the video or image file.
        hw_accel: Hardware accelerator name or None.

    Returns:
        Base64-encoded JPEG string, or None on failure.
    """
    if file_path.suffix.lower() in VIDEO_EXTENSIONS:
        return process_video_to_base64(file_path, hw_accel)
    return process_image_to_base64(file_path)


# -----------------------------------------------------------------------------
# 5. AI ENGINE & EXECUTION
# -----------------------------------------------------------------------------

def validate_category(raw_category: str | None) -> tuple[str, bool]:
    """Normalize and validate a category name against the allowed list.

    Args:
        raw_category: User-provided category string (may be None or empty).

    Returns:
        A tuple of (normalized_category, was_invalid). was_invalid is True
        if the input fell back to 'uncategorized'.
    """
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


def sanitize_name(raw_name: str) -> str:
    """Convert a raw AI-generated name into a safe snake_case filename stem.

    Args:
        raw_name: Unprocessed name string from the AI response.

    Returns:
        Cleaned, lowercase, underscore-separated name.
    """
    cleaned = raw_name.lower().replace("grid", "").replace("sequence", "")
    cleaned = cleaned.replace(" ", "_")
    safe = "".join([c for c in cleaned if c.isalpha() or c.isdigit() or c in ('_', '-')]).strip('_')
    if len(safe.split('_')) < 3:
        safe = f"{safe}_media_asset"
    return safe


def apply_case_style(name: str, style: str) -> str:
    """Transform a name string to the specified case style.

    Args:
        name: Input name to transform.
        style: One of 'snake_case', 'camelCase', 'kebab-case', 'pascal_case',
               'lowercase', or 'title_case'.

    Returns:
        Name formatted in the requested case style.
    """
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
    elif style == "title_case":
        parts = name.replace("-", "_").replace(" ", "_").split("_")
        return " ".join(p.capitalize() for p in parts if p)
    else:
        return name


CASE_STYLE_OPTIONS = ["snake_case", "camelCase", "kebab-case", "pascal_case", "lowercase", "title_case"]

CASE_STYLE_LABELS = {
    "snake_case": "snake_case",
    "camelCase": "camelCase",
    "kebab-case": "kebab-case",
    "pascal_case": "PascalCase",
    "lowercase": "lowercase",
    "title_case": "Title Case",
}


def truncate_filename(name: str, max_chars: int) -> str:
    """Truncate a filename stem to max_chars, stripping trailing separators.

    Args:
        name: Filename stem to truncate.
        max_chars: Maximum character count; 0 or negative means no limit.

    Returns:
        Possibly truncated name with trailing underscores/hyphens removed.
    """
    if max_chars <= 0 or len(name) <= max_chars:
        return name
    return name[:max_chars].rstrip("_-")


def _template_date() -> str:
    """Return today's date in ISO format for use in naming templates."""
    return datetime.date.today().isoformat()


def apply_naming_template(template_string: str, asset_data: dict[str, Any]) -> str:
    """Apply a naming template by substituting placeholders from asset data.

    Args:
        template_string: Template with {category}, {topic}, {description}, {date}.
        asset_data: Dictionary containing asset metadata keys.

    Returns:
        Formatted filename stem, or the fallback name if template produces nothing.
    """
    category = asset_data.get('category', 'uncategorized')
    topic = asset_data.get('topic', '') or ''
    description = asset_data.get('description', '') or ''
    fallback = asset_data.get('new_filename', '')

    if not topic and not description:
        # Strip category prefix from fallback if present
        if fallback.lower().startswith(category.lower() + "_"):
            fallback = fallback[len(category) + 1:]
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


def _parse_ai_response(raw_text: str) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Parse and extract JSON from an AI model's raw text response.

    Args:
        raw_text: Raw text returned by the AI model.

    Returns:
        A tuple of (parsed_dict, error_type, error_detail). On success,
        error_type and error_detail are None. On failure, parsed_dict is None.
    """
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


def _is_vision_model(name: str) -> bool:
    """Check if a model name matches a known vision-capable model prefix.

    Args:
        name: Model name string to check.

    Returns:
        True if the name starts with a recognized vision model prefix.
    """
    name_lower = name.lower().replace(":", "-")
    for prefix in VISION_MODEL_PREFIXES:
        if name_lower.startswith(prefix.lower()):
            return True
    return False


class AIProvider(ABC):
    def __init__(self) -> None:
        """Initialize default model and API key slots."""
        self._model = ""
        self._api_key = ""

    @abstractmethod
    def analyze(self, base64_img: str, verbose: bool = False) -> dict[str, Any]:
        ...

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def available_models(self) -> list[str]:
        ...

    @property
    def model(self) -> str:
        """Return the current model name."""
        return self._model

    @model.setter
    def model(self, value: str) -> None:
        """Set the model name."""
        self._model = value

    @property
    def api_key(self) -> str:
        """Return the current API key."""
        return self._api_key

    @api_key.setter
    def api_key(self, value: str) -> None:
        """Set the API key."""
        self._api_key = value

    def _parse_and_validate(self, raw_text: str) -> dict[str, Any]:
        """Parse raw AI text and validate required response keys.

        Args:
            raw_text: Raw text response from the AI model.

        Returns:
            Result dict with keys 'ok', 'data', 'error', 'detail', 'raw_response'.
        """
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
    def __init__(self) -> None:
        """Initialize Ollama provider with the configured model name."""
        super().__init__()
        self._model = MODEL_NAME
        self._retries = 2

    def analyze(self, base64_img: str, verbose: bool = False) -> dict[str, Any]:
        """Send a base64 image to Ollama for AI analysis with retry logic.

        Args:
            base64_img: Base64-encoded JPEG image data.
            verbose: If True, include raw response in error details.

        Returns:
            Result dict with parsed data or error information.
        """
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

    def health_check(self) -> dict[str, Any]:
        """Verify Ollama server is reachable and responsive.

        Returns:
            Dict with 'ok' boolean and 'message' string.
        """
        try:
            ollama.list()
            return {"ok": True, "message": "Ollama is running."}
        except Exception as exc:
            return {"ok": False, "message": f"Ollama not reachable: {exc}"}

    def available_models(self) -> list[str]:
        """List all models available on the Ollama server.

        Returns:
            List of model name strings.
        """
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
    def analyze(self, base64_img: str, verbose: bool = False) -> dict[str, Any]:
        """Analyze an image using the Google Gemini API.

        Args:
            base64_img: Base64-encoded JPEG image data.
            verbose: If True, include raw response in error details.

        Returns:
            Result dict with parsed data or error information.
        """
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

    def health_check(self) -> dict[str, Any]:
        """Check if a Gemini API key is configured.

        Returns:
            Dict with 'ok' boolean and 'message' string.
        """
        return {"ok": bool(self._api_key), "message": "API key set" if self._api_key else "No API key configured"}

    def available_models(self) -> list[str]:
        """List models available for the Gemini provider.

        Returns:
            List of model name strings from config.
        """
        return config.get("model", {}).get("providers", {}).get("gemini", {}).get("models", [])


class OpenAIProvider(AIProvider):
    def __init__(self, base_url: str | None = None) -> None:
        """Initialize OpenAI provider with optional base URL override.

        Args:
            base_url: Custom API base URL, or None for the default OpenAI endpoint.
        """
        super().__init__()
        self._base_url = base_url

    def _make_client(self) -> Any:
        """Create and return an OpenAI client instance.

        Returns:
            Configured openai.OpenAI client.
        """
        kwargs = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return openai.OpenAI(**kwargs)

    def analyze(self, base64_img: str, verbose: bool = False) -> dict[str, Any]:
        """Analyze an image using the OpenAI vision API.

        Args:
            base64_img: Base64-encoded JPEG image data.
            verbose: If True, include raw response in error details.

        Returns:
            Result dict with parsed data or error information.
        """
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

    def health_check(self) -> dict[str, Any]:
        """Check if an OpenAI API key is configured.

        Returns:
            Dict with 'ok' boolean and 'message' string.
        """
        return {"ok": bool(self._api_key), "message": "API key set" if self._api_key else "No API key configured"}

    def available_models(self) -> list[str]:
        """List models available for the OpenAI provider.

        Returns:
            List of model name strings from config.
        """
        return config.get("model", {}).get("providers", {}).get("openai", {}).get("models", [])


class AnthropicProvider(AIProvider):
    def analyze(self, base64_img: str, verbose: bool = False) -> dict[str, Any]:
        """Analyze an image using the Anthropic Claude vision API.

        Args:
            base64_img: Base64-encoded JPEG image data.
            verbose: If True, include raw response in error details.

        Returns:
            Result dict with parsed data or error information.
        """
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

    def health_check(self) -> dict[str, Any]:
        """Check if an Anthropic API key is configured.

        Returns:
            Dict with 'ok' boolean and 'message' string.
        """
        return {"ok": bool(self._api_key), "message": "API key set" if self._api_key else "No API key configured"}

    def available_models(self) -> list[str]:
        """List models available for the Anthropic provider.

        Returns:
            List of model name strings from config.
        """
        return config.get("model", {}).get("providers", {}).get("anthropic", {}).get("models", [])


class GroqProvider(OpenAIProvider):
    def __init__(self) -> None:
        """Initialize Groq provider with its configured base URL."""
        base = config.get("model", {}).get("providers", {}).get("groq", {}).get("base_url", "https://api.groq.com/openai/v1")
        super().__init__(base_url=base)

    def available_models(self) -> list[str]:
        """List models available for the Groq provider.

        Returns:
            List of model name strings from config.
        """
        return config.get("model", {}).get("providers", {}).get("groq", {}).get("models", [])


class OpenRouterProvider(OpenAIProvider):
    def __init__(self) -> None:
        """Initialize OpenRouter provider with its configured base URL."""
        base = config.get("model", {}).get("providers", {}).get("openrouter", {}).get("base_url", "https://openrouter.ai/api/v1")
        super().__init__(base_url=base)

    def available_models(self) -> list[str]:
        """List models available for the OpenRouter provider.

        Returns:
            List of model name strings from config.
        """
        return config.get("model", {}).get("providers", {}).get("openrouter", {}).get("models", [])


def register_provider(name: str, cls: type[AIProvider]) -> None:
    """Register a provider class in the global provider registry.

    Args:
        name: Short identifier for the provider (e.g. 'ollama').
        cls: Provider class that subclasses AIProvider.
    """
    PROVIDER_REGISTRY[name] = cls


def get_provider(name: str) -> AIProvider:
    """Instantiate and configure a registered provider by name.

    Args:
        name: Provider identifier registered via register_provider.

    Returns:
        Configured AIProvider instance with API key and model set.

    Raises:
        ValueError: If name is not in the provider registry.
    """
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


def list_providers() -> list[str]:
    """Return all registered provider names."""
    return list(PROVIDER_REGISTRY.keys())


register_provider("ollama", OllamaProvider)
register_provider("gemini", GeminiProvider)
register_provider("openai", OpenAIProvider)
register_provider("anthropic", AnthropicProvider)
register_provider("groq", GroqProvider)
register_provider("openrouter", OpenRouterProvider)


def analyze_asset_with_ai(base64_img: str, verbose: bool = False, retry: bool = True) -> dict[str, Any]:
    """Analyze an image using the default Ollama provider.

    Args:
        base64_img: Base64-encoded JPEG image data.
        verbose: If True, include raw response in error details.
        retry: Unused, kept for API compatibility.

    Returns:
        Result dict with parsed data or error information.
    """
    provider = get_provider("ollama")
    provider.model = config["model"]["name"]
    return provider.analyze(base64_img, verbose=verbose)


def analyze_asset_with_gemini(base64_img: str, verbose: bool = False) -> dict[str, Any]:
    """Analyze an image using the Gemini provider.

    Args:
        base64_img: Base64-encoded JPEG image data.
        verbose: If True, include raw response in error details.

    Returns:
        Result dict with parsed data or error information.
    """
    provider = get_provider("gemini")
    provider.api_key = CURRENT_API_KEY or load_api_key("gemini")
    return provider.analyze(base64_img, verbose=verbose)


def _format_ai_error(ai_result: dict[str, Any], verbose: bool = False) -> str:
    """Format an AI result error into a human-readable message string.

    Args:
        ai_result: Result dict from an AI provider analyze() call.
        verbose: If True, append a snippet of the raw model response.

    Returns:
        Formatted error message string.
    """
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


def execute_commit(
    asset: dict[str, Any],
    target_dir: Path,
    sort_into_folders: bool,
    exiftool_session: Any,
    skip_rename: bool = False,
) -> str | Path:
    """Rename/move a staged asset to the target directory and write metadata.

    Args:
        asset: Staged asset dict with original_path, staged_name, category, tags, summary.
        target_dir: Destination directory for the file.
        sort_into_folders: If True, create a subfolder named after the category.
        exiftool_session: Active ExifToolSession for writing metadata.
        skip_rename: If True, copy instead of rename (keeps original name).

    Returns:
        Relative path to the committed file, or 'ERROR:<message>' on failure.
    """
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
        if skip_rename:
            final_folder.mkdir(parents=True, exist_ok=True)
            target_file = final_folder / old_path.name
            if old_path != target_file:
                shutil.copy2(str(old_path), str(target_file))
        else:
            old_path.rename(new_path)
            target_file = new_path

        tag_string = ", ".join(asset['tags'])
        summary = asset['summary']
        title = asset['staged_name'].replace("_", " ").replace("-", " ").title()
        is_video = suffix in VIDEO_EXTENSIONS

        args = [
            "-overwrite_original",
            "-api", "LargeFileSupport=1",
            f"-XMP-dc:Title={title}",
            f"-XMP-dc:Description={summary}",
            f"-Microsoft:Category={tag_string}"
        ]
        for t in asset['tags']:
            args.append(f"-XMP-dc:Subject={t}")

        if is_video:
            args.extend([
                f"-QuickTime:Title={title}",
                f"-QuickTime:Description={summary}",
                f"-QuickTime:Comment={summary}",
                f"-QuickTime:Keywords={tag_string}",
                f"-Keys:Description={summary}",
                f"-Keys:Keywords={tag_string}"
            ])
        else:
            args.extend([
                f"-EXIF:XPTitle={title}",
                f"-EXIF:XPKeywords={tag_string}",
                f"-Description={summary}",
                f"-Comment={summary}",
            ] + [f"-Keywords={t}" for t in asset['tags']])

        args.append(str(target_file))
        exiftool_session.execute(args)

        if skip_rename:
            return target_file
        return new_path.relative_to(target_dir)
    except Exception as e:
        return f"ERROR:{e}"


# -----------------------------------------------------------------------------
# 5b. SESSION PERSISTENCE
# -----------------------------------------------------------------------------

SESSION_DIR = Path(os.environ.get('APPDATA', Path.home())) / "ai-media-renamer" / "sessions"


def save_session(staged_assets: list[dict[str, Any]], uploaded_files: dict[str, Path], settings: dict[str, Any]) -> Path:
    """Save session state to a JSON file for later restoration."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    session_path = SESSION_DIR / f"session_{ts}.json"

    serializable_assets = []
    for a in staged_assets:
        entry = dict(a)
        entry["original_path"] = str(entry["original_path"])
        serializable_assets.append(entry)

    serializable_files = {name: str(p) for name, p in uploaded_files.items()}

    data = {
        "version": 1,
        "created": ts,
        "staged_assets": serializable_assets,
        "uploaded_files": serializable_files,
        "settings": settings,
    }
    session_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return session_path


def list_sessions() -> list[dict[str, Any]]:
    """Return list of saved sessions sorted by date (newest first)."""
    if not SESSION_DIR.exists():
        return []
    sessions = sorted(SESSION_DIR.glob("session_*.json"), reverse=True)
    result = []
    for s in sessions:
        try:
            data = json.loads(s.read_text(encoding="utf-8"))
            asset_count = len(data.get("staged_assets", []))
            created = data.get("created", s.stem.replace("session_", ""))
            result.append({"path": s, "created": created, "asset_count": asset_count})
        except Exception:
            continue
    return result


def delete_session(session_path: str | Path) -> bool:
    """Delete a saved session file. Returns True on success."""
    try:
        Path(session_path).unlink(missing_ok=True)
        return True
    except Exception:
        return False


def load_session(session_path: str | Path) -> dict[str, Any]:
    """Load a saved session, validating that original files still exist on disk."""
    data = json.loads(Path(session_path).read_text(encoding="utf-8"))

    staged_assets = []
    missing_files = []
    for a in data.get("staged_assets", []):
        a["original_path"] = Path(a["original_path"])
        if a["original_path"].exists():
            staged_assets.append(a)
        else:
            missing_files.append(a["original_name"])

    uploaded_files = {}
    for name, path_str in data.get("uploaded_files", {}).items():
        p = Path(path_str)
        if p.exists():
            uploaded_files[name] = p

    settings = data.get("settings", {})
    return {
        "staged_assets": staged_assets,
        "uploaded_files": uploaded_files,
        "settings": settings,
        "missing_files": missing_files,
    }


# -----------------------------------------------------------------------------
# 5c. DUPLICATE DETECTION
# -----------------------------------------------------------------------------

def compute_asset_hash(file_path: str | Path) -> str | None:
    """Compute perceptual hash for an asset. For images, hashes directly.
    For videos, extracts the midpoint frame and hashes that."""
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        return None

    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in VIDEO_EXTENSIONS:
        return _compute_video_hash(path, imagehash)
    elif suffix in IMAGE_EXTENSIONS:
        return _compute_image_hash(path, imagehash, Image)
    return None


def _compute_image_hash(path: Path, imagehash: Any, pil_image: Any) -> str | None:
    """Hash a single image file."""
    cmd = [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
        '-i', str(path),
        '-vf', 'scale=256:256:force_original_aspect_ratio=decrease',
        '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-'
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW)
        if proc.returncode != 0 or not proc.stdout:
            return None
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(proc.stdout))
        return str(imagehash.phash(img))
    except Exception:
        return None


def _compute_video_hash(path: Path, imagehash: Any) -> str | None:
    """Extract midpoint frame from video and compute pHash."""
    duration = get_video_duration(path)
    mid = max(1.0, duration * 0.5)
    cmd = [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
        '-ss', str(mid),
        '-i', str(path),
        '-vframes', '1',
        '-vf', 'scale=256:256:force_original_aspect_ratio=decrease',
        '-f', 'image2pipe', '-vcodec', 'mjpeg', '-'
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW)
        if proc.returncode != 0 or not proc.stdout:
            return None
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(proc.stdout))
        return str(imagehash.phash(img))
    except Exception:
        return None


def find_duplicates(staged_assets: list[dict[str, Any]], threshold: int = 10) -> list[dict[str, Any]]:
    """Compare all staged assets pairwise. Returns list of duplicate pairs.
    threshold: Hamming distance threshold (0-64). Lower = stricter match.
    Default 10 means ~84% similarity required."""
    try:
        import imagehash as _ih
    except ImportError:
        return []

    hashes = {}
    for i, asset in enumerate(staged_assets):
        h = compute_asset_hash(asset["original_path"])
        if h:
            hashes[i] = _ih.hex_to_hash(h)

    duplicates = []
    indices = sorted(hashes.keys())
    for i in range(len(indices)):
        for j in range(i + 1, len(indices)):
            idx_a, idx_b = indices[i], indices[j]
            dist = hashes[idx_a] - hashes[idx_b]
            if dist <= threshold:
                confidence = max(0, round((1 - dist / 64) * 100))
                duplicates.append({
                    "index_a": idx_a,
                    "index_b": idx_b,
                    "name_a": staged_assets[idx_a]["original_name"],
                    "name_b": staged_assets[idx_b]["original_name"],
                    "distance": dist,
                    "confidence": confidence,
                })

    return duplicates


# -----------------------------------------------------------------------------
# 6. BOOTSTRAP & ENVIRONMENT
# -----------------------------------------------------------------------------


def _resolve_binary_path(name: str) -> str | None:
    """Resolve the filesystem path of a binary, checking PyInstaller bundle first.

    Args:
        name: Binary name (e.g. 'ffmpeg', 'exiftool').

    Returns:
        Absolute path to the binary, or None if not found.
    """
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidate = os.path.join(meipass, 'bin', name)
        if os.path.isfile(candidate):
            return candidate
    resolved = shutil.which(name)
    return resolved


def check_ollama_health() -> dict[str, Any]:
    """Probe the Ollama server for connectivity and list vision-capable models.

    Returns:
        Dict with 'connected', 'models', 'all_models', counts, and 'error'.
    """
    try:
        tags = ollama.list()
        models = tags.get('models', [])
        all_names = []
        vision_names = []
        for m in models:
            name = m.get('name', '') if isinstance(m, dict) else str(m)
            if name:
                all_names.append(name)
                if _is_vision_model(name):
                    vision_names.append(name)
        return {
            "connected": True,
            "models": vision_names,
            "all_models": all_names,
            "model_count": len(all_names),
            "vision_count": len(vision_names),
            "error": None,
        }
    except Exception as exc:
        return {
            "connected": False,
            "models": [],
            "all_models": [],
            "model_count": 0,
            "vision_count": 0,
            "error": str(exc),
        }


def check_environment() -> dict[str, Any]:
    """Verify all required tools and services are available.

    Returns:
        Dict with availability flags for ffmpeg, exiftool, Ollama, and error list.
    """
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


def stream_model_download(model_name: str = "qwen2.5vl:7b") -> Any:
    """Stream download progress for an Ollama model pull.

    Args:
        model_name: Ollama model tag to download.

    Yields:
        Dicts with 'status' key and progress/message details.
    """
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


def check_for_updates() -> dict[str, Any]:
    """Check GitHub releases for a newer version of the application.

    Returns:
        Dict with 'current', 'latest', 'update_available', 'download_url', 'ok'.
    """
    try:
        resp = requests.get(
            "https://api.github.com/repos/Abdulmusawwir/ai-media-renamer/releases/latest",
            timeout=5
        )
        data = resp.json()
        latest = data.get("tag_name", "")
        return {
            "current": VERSION,
            "latest": latest,
            "update_available": latest != VERSION,
            "download_url": data.get("html_url", ""),
            "ok": True,
        }
    except Exception as exc:
        return {"ok": False, "current": VERSION, "latest": "", "update_available": False,
                "download_url": "", "error": str(exc)}


def download_file(url: str, dest: Path, progress_callback: Callable[[int, int], None] | None = None, chunk_size: int = 8192) -> bool:
    """Download a file from a URL with optional progress callback.

    Args:
        url: HTTP(S) URL to download.
        dest: Destination file path.
        progress_callback: Optional function receiving (bytes_downloaded, total_bytes).
        chunk_size: Read chunk size in bytes.

    Returns:
        True on successful download.

    Raises:
        requests exceptions on network failure.
    """
    tmp = dest.with_suffix(".part")
    try:
        resp = requests.get(url, stream=True, timeout=30)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total:
                        progress_callback(downloaded, total)
        tmp.rename(dest)
        return True
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def wait_for_ollama_service(timeout: int = 120) -> bool:
    """Poll the Ollama HTTP endpoint until it responds or timeout is reached.

    Args:
        timeout: Maximum seconds to wait.

    Returns:
        True if Ollama responded within the timeout.
    """
    import time
    url = "http://localhost:11434/api/tags"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        time.sleep(2)
    return False


def switch_ai_provider(new_provider: str, api_key: str | None = None) -> dict[str, Any]:
    """Switch the active AI provider, release old resources, and persist choice.

    Args:
        new_provider: Provider name to switch to (e.g. 'ollama', 'gemini').
        api_key: Optional API key to store for the new provider.

    Returns:
        Dict with 'ok', 'message', and optionally 'require_download'.
    """
    global CURRENT_PROVIDER, CURRENT_API_KEY, CURRENT_PROVIDER_INSTANCE

    if CURRENT_PROVIDER == "ollama" and new_provider != "ollama":
        try:
            ollama.generate(model=config["model"]["name"], keep_alive=0)
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
    provider.model = pconf.get("selected_model", "") or (pconf.get("models") or [None])[0] or config["model"]["name"]

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


def set_api_key(key: str) -> None:
    """Set the global in-memory API key for the current session.

    Args:
        key: API key string to set.
    """
    global CURRENT_API_KEY
    CURRENT_API_KEY = key


def wipe_local_model(model_name: str = "qwen2.5vl:7b") -> dict[str, Any]:
    """Delete a local Ollama model to free disk space.

    Args:
        model_name: Ollama model tag to remove.

    Returns:
        Dict with 'ok' and 'message'.
    """
    try:
        ollama.delete(model_name)
        return {"ok": True, "message": f"Model {model_name} deleted."}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


# -----------------------------------------------------------------------------
# 7. STAGING EXPORT / IMPORT
# -----------------------------------------------------------------------------

def export_staging_csv(staged_assets: list[dict[str, Any]]) -> str:
    """Serialize staged assets to a CSV string for export.

    Args:
        staged_assets: List of staged asset dicts.

    Returns:
        CSV-formatted string with all asset fields.
    """
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


def export_staging_json(staged_assets: list[dict[str, Any]]) -> str:
    """Serialize staged assets to a JSON string for export.

    Args:
        staged_assets: List of staged asset dicts.

    Returns:
        Pretty-printed JSON string.
    """
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


def import_staging_csv(csv_string: str, allowed_categories: tuple[str, ...] | list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse a CSV string into staged asset dicts with category validation.

    Args:
        csv_string: CSV-formatted string with asset rows.
        allowed_categories: Valid category names for validation.

    Returns:
        A tuple of (assets_list, warnings_list) where warnings describe
        any category mismatches that fell back to 'uncategorized'.
    """
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


# -----------------------------------------------------------------------------
# 8. TELEMETRY (opt-in, anonymous, privacy-first)
# -----------------------------------------------------------------------------

POSTHOG_API_KEY = os.environ.get('POSTHOG_PROJECT_TOKEN', "")
POSTHOG_HOST = os.environ.get('POSTHOG_HOST', "https://us.i.posthog.com")
TELEMETRY_DIR = Path(os.environ.get('APPDATA', Path.home())) / "ai-media-renamer"
TELEMETRY_FILE = TELEMETRY_DIR / "telemetry.jsonl"
_install_id = None


def _get_install_id() -> str:
    """Random UUID per install, stored locally. Never tied to identity."""
    global _install_id
    if _install_id:
        return _install_id
    id_file = TELEMETRY_DIR / ".install_id"
    if id_file.exists():
        _install_id = id_file.read_text(encoding="utf-8").strip()
    else:
        import uuid
        _install_id = str(uuid.uuid4())
        id_file.parent.mkdir(parents=True, exist_ok=True)
        id_file.write_text(_install_id, encoding="utf-8")
    return _install_id


def _get_session_id() -> str:
    """Fresh UUID per app launch. Non-persistent."""
    import uuid
    return str(uuid.uuid4())[:8]


def telemetry_enabled() -> bool:
    """Check if telemetry is opted-in via config.json."""
    return config.get("telemetry", {}).get("enabled", False)


def set_telemetry_enabled(enabled: bool) -> None:
    """Update telemetry preference in config.json."""
    config.setdefault("telemetry", {})["enabled"] = enabled
    save_config()
    reload_config()


def track_event(event_name: str, properties: dict[str, Any] | None = None) -> None:
    """Queue a telemetry event. Writes to local JSONL.
    PostHog flush happens on app exit or batch threshold."""
    if not telemetry_enabled():
        return

    entry = {
        "event": event_name,
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
        "install_id": _get_install_id(),
        "session_id": _get_session_id(),
        "app_version": VERSION,
        "os": sys.platform,
        "arch": "AMD64",
    }
    if properties:
        entry["properties"] = properties

    try:
        TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
        with open(TELEMETRY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def flush_telemetry() -> None:
    """Send buffered telemetry events to PostHog, then clear local buffer."""
    if not telemetry_enabled():
        return

    api_key = POSTHOG_API_KEY or config.get("telemetry", {}).get("api_key", "")
    if not api_key:
        return

    if not TELEMETRY_FILE.exists():
        return

    try:
        lines = TELEMETRY_FILE.read_text(encoding="utf-8").strip().split("\n")
        lines = [ln for ln in lines if ln.strip()]
        if not lines:
            return

        from posthog import Posthog as _Posthog
        posthog_client = _Posthog(
            api_key,
            host=POSTHOG_HOST,
            enable_exception_autocapture=True,
        )
        try:
            for line in lines:
                try:
                    event = json.loads(line)
                    posthog_client.capture(
                        distinct_id=event.get("install_id", "unknown"),
                        event=event["event"],
                        properties=event.get("properties", {}),
                        timestamp=event.get("timestamp"),
                    )
                except Exception:
                    continue
            posthog_client.flush()
            TELEMETRY_FILE.unlink(missing_ok=True)
        finally:
            posthog_client.shutdown()
    except ImportError:
        pass
    except Exception:
        pass


def send_opt_out_event() -> None:
    """Send a final opt-out event before disabling telemetry."""
    api_key = POSTHOG_API_KEY or config.get("telemetry", {}).get("api_key", "")
    if not api_key:
        return
    try:
        from posthog import Posthog as _Posthog
        posthog_client = _Posthog(
            api_key,
            host=POSTHOG_HOST,
            enable_exception_autocapture=True,
        )
        try:
            posthog_client.capture(
                distinct_id=_get_install_id(),
                event="opt_out",
                properties={"app_version": VERSION},
            )
            posthog_client.flush()
        finally:
            posthog_client.shutdown()
    except Exception:
        pass


if os.environ.get('POSTHOG_DEBUG', '').lower() == 'true' and not POSTHOG_API_KEY:
    print(
        "WARNING: POSTHOG_PROJECT_TOKEN variable required by PostHog is missing or "
        "un-configured, this causes events to be silently missed. "
        "This error stops appearing once POSTHOG_PROJECT_TOKEN is configured"
    )

atexit.register(flush_telemetry)
