import base64
import datetime
import json
import logging
import subprocess
import sys
from pathlib import Path

import ollama

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
AI_PROMPT = config['ai_prompt'].replace(
    "the allowed categories list",
    f"this list:\n{CATEGORY_LIST_STR}"
)

VIDEO_EXTENSIONS = config['video_extensions']
IMAGE_EXTENSIONS = config['image_extensions']
MODEL_NAME = config['model']['name']
MODEL_TEMPERATURE = config['model']['temperature']
MODEL_NUM_CTX = config['model']['num_ctx']
MODEL_KEEP_ALIVE = config['model']['keep_alive']
IMAGE_PREVIEW_MAX_EDGE = config['preview']['image_max_edge']
VIDEO_GRID_TILE = config['preview']['video_grid_tile']
VIDEO_GRID_SCALE = config['preview']['video_grid_scale']

LOG_DIR = Path(config['logging']['directory'])


def setup_logging(verbose=False):
    log_dir = LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"renamer_{datetime.datetime.now(datetime.timezone.utc).date().isoformat()}.jsonl"

    logger = logging.getLogger('video_renamer')
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
    file_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(file_handler)

    return logger


def log_event(logger, level, event, file_name=None, details=None):
    record = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
    for hw in ['cuda', 'qsv']:
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
    start_offset = duration * 0.05
    usable_duration = duration * 0.90
    rate = 10 / usable_duration

    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
    if hw_accel:
        cmd.extend(['-hwaccel', hw_accel])

    cmd.extend([
        '-ss', str(start_offset),
        '-i', str(video_path),
        '-t', str(usable_duration),
        '-vf', f"fps={rate},scale={VIDEO_GRID_SCALE}:-1,tile={VIDEO_GRID_TILE}",
        '-frames:v', '1',
        '-f', 'image2pipe',
        '-vcodec', 'mjpeg',
        '-'
    ])

    try:
        process = subprocess.run(cmd, capture_output=True, check=True)
        return base64.b64encode(process.stdout).decode('utf-8')
    except subprocess.CalledProcessError:
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
    if not raw_category:
        return 'uncategorized', True
    normalized = str(raw_category).lower().strip()
    if normalized in ALLOWED_CATEGORIES:
        return normalized, False
    return 'uncategorized', True


def sanitize_name(raw_name):
    cleaned = raw_name.lower().replace("grid", "").replace("sequence", "")
    safe = "".join([c for c in cleaned if c.isalpha() or c.isdigit() or c in ('_', '-')]).strip('_')
    if len(safe.split('_')) < 3:
        safe = f"{safe}_media_asset"
    return safe


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


def analyze_asset_with_ai(base64_img, verbose=False, retry=True):
    result = {
        'ok': False,
        'data': None,
        'error': None,
        'detail': None,
        'raw_response': None,
    }

    attempts = 2 if retry else 1
    last_exc = None

    for attempt in range(attempts):
        try:
            response = ollama.generate(
                model=MODEL_NAME,
                prompt=AI_PROMPT,
                images=[base64_img],
                keep_alive=MODEL_KEEP_ALIVE,
                options={
                    "temperature": MODEL_TEMPERATURE,
                    "num_ctx": MODEL_NUM_CTX
                }
            )

            raw_text = response.get('response', '')
            result['raw_response'] = raw_text

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

        except (ollama.ResponseError, ConnectionError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt < attempts - 1:
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


def _format_ai_error(ai_result, verbose=False):
    error_type = ai_result.get('error', 'unknown')
    detail = ai_result.get('detail', 'Unknown error')
    messages = {
        'json_parse_error': f'AI response was not valid JSON -- {detail}',
        'missing_keys': detail,
        'empty_response': detail,
        'ollama_error': detail,
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
