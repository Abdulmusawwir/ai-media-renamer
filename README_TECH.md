# AI Media Renamer — Technical Reference

Automatically organize, rename, and tag video, image, document, and audio assets using AI. 9 prompt profiles for different use cases. Comes with both a **CLI** and a **web app** (FastAPI backend + React SPA).

> This is the deep-dive reference: full feature list, CLI flags, config reference, module map, metadata tables, and system requirements.
>
> For the plain-language pitch, screenshots, and quick start, see [README.md](README.md).

### Download the EXE

Pre-built binaries are available on the [Releases page](https://github.com/Abdulmusawwir/ai-media-renamer/releases/latest). The EXE is self-contained — on first run it checks for FFmpeg, ExifTool, and the llama.cpp runtime and downloads any missing components automatically (including the ~18 MB llama.cpp runtime and a GGUF vision model).

### Building from Source

Node.js 18+ is required to build the SPA; `build_v2.spec` bundles `frontend/dist`.

```bash
pip install -r requirements.txt
pip install pyinstaller
cd frontend && npm ci && npm run build && cd ..
pyinstaller build_v2.spec --noconfirm
# Output: dist/AIMediaRenamer.exe
```

---

## Quick Start

```bash
pip install -r requirements.txt
python launch.py
```

### Prerequisites
- **A local AI runtime** — **llama.cpp** (the only supported runtime) — `llama-server` + a GGUF vision model (7B Qwen2-VL, or lighter 2B on CPU), auto-downloaded by the setup wizard; documents/audio route to a compact text model (Qwen2.5-3B)
- **ExifTool 12+** — [exiftool.org](https://exiftool.org)
- **FFmpeg 6+** (including ffprobe) — [ffmpeg.org](https://ffmpeg.org)
- **fpcalc** (Chromaprint) — optional; enables audio fingerprint duplicate detection when present (`_resolve_binary_path("fpcalc")`)

---

## Why Use This?

- **No more "final_v3_actual_use_this.mp4"** — every file gets a descriptive, consistent name
- **Metadata written to the file** — not a separate spreadsheet. Your NLE reads it natively
- **Works offline** — uses the local llama.cpp runtime; no cloud API needed
- **Bulk operations** — apply categories, edit names, filter, sort — all in one table
- **Safe & reversible** — dry-run mode shows what will happen before anything changes, and the last commit batch can be rolled back
- **Duplicate detection** — visual hash (pHash), document hash (SHA-256), and audio fingerprint (Chromaprint) catch near-identical files before they clutter your library

---

## Features

### AI Analysis
- **9 prompt profiles** — General Balanced, General B-Roll, Cinematography, Motion & Overlays, Religious Landmarks, Document Naming, Spreadsheet Naming, Audio Files, and Custom
- **Automatic profile routing** — documents, spreadsheets, and audio are analyzed with their own naming profile even when a visual profile is selected (disable via `prompt_profiles.auto_route`)
- **One local AI runtime** — llama.cpp (`llama-server`, OpenAI-compatible API). Fully offline: no cloud models, no API keys, no keychain required.
- **Single-frame extraction** — one representative frame per video for accurate analysis
- **Image analysis** — downscaled in memory, no disk writes
- **Audio transcription** — local Whisper transcription for audio files and video audio tracks
- **Document analysis** — text extraction from PDF, DOCX, XLSX, CSV, PPTX, TXT, MD, RTF

### Staging & Editing
- **Spreadsheet-like table** — edit filenames, categories, and tags inline
- **Bulk operations** — apply categories, case styles, and naming templates to selected rows
- **Search & filter** — find files by name, category, or tags instantly
- **Duplicate detection** — visual hash (pHash), document hash (SHA-256), and audio fingerprint (Chromaprint) comparison

### Naming & Organization
- **Naming templates** — `{topic}_{description}`, `{date}_{topic}`, or custom patterns
- **Case styles** — snake_case, camelCase, kebab-case, PascalCase, lowercase, title case
- **Category folders** — sort committed files into category subdirectories (on by default via `naming.sort_folders`; `--sort-folders` / `--no-sort-folders` in the CLI)
- **Metadata writing** — XMP, EXIF, ID3, Vorbis, and QuickTime tags written directly into file headers (verified in DaVinci Resolve and Premiere Pro; Windows Explorer surfaces EXIF keywords for images, not XMP for MP4)

### Configuration
- **Web-based config editor** — the Settings page reads and writes `config.json` (models, categories, extensions, prompt profiles) through `GET`/`PUT /api/config`
- **Config reset** — restore defaults from the web UI, CLI flag (`--reset-config`), or automatic recovery
- **Session persistence** — save and resume analysis sessions across app restarts
- **Undo/rollback** — revert the last commit batch (move files back, remove metadata)

### Telemetry

There is **no telemetry**. The app never collects or transmits usage data — no analytics SDK, no PostHog, no tracking events. Privacy is documented in [PRIVACY.md](PRIVACY.md).

### Security (v1.6.3)

- **Checksum-verified downloads** — every binary the setup wizard fetches (FFmpeg, ExifTool, llama.cpp runtime, GGUF models) is verified against its published SHA-256 digest before use; plain-HTTP URLs are rejected.
- **Secret redaction** — sensitive values are masked in exception messages, JSONL logs, and the Configuration-tab JSON view.
- **No secrets stored** — the app is entirely local (llama.cpp) and stores no API keys; the OS-keychain layer was removed in v1.7.0 along with all cloud providers.
- **Loopback-only by default** — `launch.py` binds both `127.0.0.1` and `::1` and picks a free port in 8000–8010. Set `config.server.lan_expose` (or `AMR_AUTH_ENABLED=1`) for LAN use; mutating routes then require a bearer token issued at `/api/auth/token`, and the analysis WebSocket takes it as `?token=`.
- **CORS and rate limiting** — `server.cors_origins` overrides the default allow-list; `AMR_RATE_LIMIT` (requests/minute, per IP) enables the optional limiter in `server/security.py`.
- **Input validation** — CSV import/export neutralizes spreadsheet formula injection; session restore schema-validates and rejects symlinks; staged filenames can never traverse directories on commit.
- **Log path privacy** — absolute paths are redacted from JSONL logs by default (`config.logging.redact_paths`).

### Reliability

- **Atomic config writes** — `save_config()` writes to a temp file and `os.replace`s it, so a crash mid-save can never leave a truncated `config.json`.
- **Import-safe startup** — config load/validation is deferred and non-fatal; a broken config degrades gracefully (`CONFIG_LOAD_ERROR` + a minimal fallback) instead of crashing the process at import time.
- **Single-job analysis** — the server streams one `analyze_asset_with_ai()` result per asset over the WebSocket, with one shared cancellation `threading.Event` (`server/deps.py`). Re-analysis restarts the same loop for selected files only.
- **Fail-fast** — if the llama.cpp server is not answering, `run_analysis()` emits an `error` event and completes with `count=0` instead of staging an empty batch.
- **Server startup** — `launch.py` picks the first free port in 8000–8010, binds `127.0.0.1` and `::1`, and opens the browser.
- **ExifTool lifecycle** — each commit opens one `ExifToolSession` and closes it in a `finally`; the batch path sends one `-execute` per file with a bounded read timeout.
- **CLI validation** — mutually-exclusive argument groups (`--export-csv`/`--import-csv`, `--rollback`/`--reset-config`, `--sort-folders`/`--no-sort-folders`) and a config-synced default case style.

---

## CLI Reference

```bash
python cli.py "path/to/your/assets" [options]
```

| Flag | Description |
|---|---|
| `dir` | Path to directory containing media files |
| `--verbose` / `-v` | Debug output (raw AI responses) |
| `--profile` / `-p` | AI prompt profile: `general_balanced`, `general_broll`, `cinematography`, `motion_overlays`, `religious_landmarks`, `document_naming`, `spreadsheet_naming`, `audio_naming`, `custom` |
| `--template` / `-t` | Naming template preset (`default`, `short`, `editorial`) or raw pattern |
| `--case-style` / `--style` | Case style (default: config `naming.case_style`, `title_case`): `snake_case`, `camelCase`, `kebab-case`, `pascal_case`, `lowercase`, `title_case` |
| `--max-chars` / `--max` | Max filename length (0 = no limit) |
| `--force` | Re-analyze all files, including previously processed ones |
| `--workers` / `-w` | Parallel extraction workers (default: CPU count) |
| `--export-csv <file>` | Export staging data to CSV after analysis |
| `--import-csv <file>` | Skip AI analysis, load staging from CSV |
| `--dry-run` | Preview commits without modifying files |
| `--metadata-only` | Write metadata without renaming |
| `--sort-folders` / `--no-sort-folders` | Override `naming.sort_folders` for this run |
| `--categories-override <file>` | JSON map of filename → forced category (used with `-y`) |
| `--rollback` | Undo the last commit batch (move files back, remove metadata) |
| `--non-interactive` / `-y` | Skip interactive prompts, auto-accept all |
| `--output <file>` | Write the commit summary JSON to `<file>` |
| `--no-progress` | Disable progress bars (pipe-friendly output) |
| `--reset-config` | Reset config.json to factory defaults and exit |
| `-r` / `--include-subdirectories` | Scan subdirectories recursively |

### CLI Workflow
1. **Extraction** — Parallel FFmpeg frame extraction with HW acceleration detection; text extraction for documents; audio transcription for audio files
2. **Analysis** — Sequential per-asset AI analysis with progress indicators
3. **Staging Review** — Summary table, category override for uncategorized assets
4. **Execution** — Choose: `[A]pply All`, `[I]nteractive mode`, `[D]ry-run preview`, or `[C]ancel`

Interactive mode per-asset options: `[A]ccept`, `[S]kip`, `[R]e-analyze`, `[E]dit name`, `[B]ulk-apply category to remaining`, or type a custom name override.

---

## Modules

| File | Purpose |
|---|---|
| `engine.py` | Core importable functions — config, ExifTool sessions, FFmpeg frame extraction, AI analysis, environment checks, file commits, duplicate detection, audio transcription |
| `launch.py` | Desktop entrypoint — picks a free loopback port, spawns uvicorn, opens the browser |
| `server/` | FastAPI backend — REST routes, WebSocket analysis streaming, auth, in-memory staging |
| `frontend/` | React (Vite + TypeScript) SPA — Analysis, Staging, Commit & Export, Sessions, Settings, Models |
| `cli.py` | CLI workflow — scan, extract, analyze, stage, commit |
| `config.json` | Single source of truth — prompt profiles (9), categories (54), model settings, naming templates, logging |

---

## Web App Features

- **Upload & Analyze** — Drag-and-drop upload with extension/file-size validation, parallel FFmpeg frame extraction (single midpoint frame per video, hardware-accelerated), sequential per-asset AI analysis with progress bars
- **Audio Transcription** — Local Whisper transcription for audio files and video audio tracks, fed into AI analysis context
- **Document Analysis** — Text extraction from PDF, DOCX, XLSX, CSV, PPTX, TXT, MD, RTF for AI analysis
- **Editable Staging Matrix** — columns: select checkbox, original filename, type (media/doc/audio), editable proposed filename, category dropdown (with custom entry), comma-separated tags, read-only summary. Search/filter above the table. Native click-to-sort column headers.
- **Bulk Category Assignment** — Select assets, pick a category (or type a custom one), apply to all checked rows at once
- **AI Prompt Profiles** — 9 built-in profiles selectable right before analysis. Changeable per run. Text assets auto-route to document/spreadsheet/audio profiles unless disabled.
- **Naming Settings** — Configurable `{category}_{topic}_{description}` pattern, case style (snake_case, camelCase, etc.), max filename length — all with live preview updates in the staging table
- **Re-analyze Selected** — Check specific rows and re-analyze only those assets without re-processing the entire batch
- **CSV Import/Export** — Export the staging table as CSV (`GET /api/staging/export`), re-import later to restore or modify
- **Commit & Export** — Write metadata (XMP, QuickTime, EXIF, IPTC, ID3, Vorbis), optionally sort into category subfolders, then export CSV
- **Undo/Rollback** — "Rollback last batch" on the Commit & Export page (`POST /api/rollback`)
- **Sessions** — Save, load, and delete analysis sessions
- **Settings** — Read/write `config.json` (models, categories, extensions, prompt profiles)
- **Models** — llama.cpp runtime status and GGUF model download with progress polling

### Pages

`Analysis` · `Staging` · `Commit & Export` · `Sessions` · `Settings` · `Models`

### Output Directory

The CLI commits in place, into the scanned directory (or its category subfolders when `naming.sort_folders` is on). `POST /api/commit` behaves the same way when `target_dir` is omitted: each asset is renamed next to its original file. Send an explicit `target_dir` to move everything into one destination folder. Every successful server commit is recorded in the undo log, so "Rollback last batch" works for web commits too.

---

## Metadata Reference

After renaming, every file receives structured metadata written directly into its headers:

### Video & Image Metadata

| Tag | File Type | Description |
|---|---|---|
| `XMP-dc:Title` | All | File title |
| `XMP-dc:Description` | All | Visual summary from AI analysis |
| `XMP-dc:Subject` | All | Keywords as individual array elements |
| `Microsoft:Category` | All | Assigned taxonomy category |
| `QuickTime:Title/Description/Comment/Keywords` | MP4/MOV/MKV | Video-specific metadata |
| `Keys:Description/Keywords` | MP4/MOV/MKV | Additional video metadata |
| `EXIF:XPTitle/XPKeywords` | JPG/PNG | Windows Explorer tags |
| `IPTC:Keywords` | JPG/PNG | Individual keyword entries |

### Audio Metadata

| Tag | File Type | Description |
|---|---|---|
| `ID3:TIT2` | MP3, AIFF, APE | Title |
| `ID3:TALB` | MP3, AIFF, APE | Summary/description |
| `ID3:TCOM` | MP3 | Composer |
| `ID3:TSRC` | MP3, AIFF, APE | Keywords |
| `XMP-dc:Title/Description/Subject` | WAV, FLAC, OGG, WV | Title and keywords |
| `QuickTime:Title/Comment/Keywords` | M4A, AAC | Title and keywords |

### Document Metadata

| Format | Method | Notes |
|---|---|---|
| PDF | ExifTool | Title, description, keywords via EXIF fields |
| DOCX | python-docx | Title, subject, keywords via core properties |
| XLSX | openpyxl | Title, subject, keywords via document properties |
| TXT, MD, RTF, CSV, PPTX | Skip | No standard metadata support |

Compatible with **DaVinci Resolve** and **Adobe Premiere Pro**.

---

## Configuration (`config.json`)

- **`prompt_profiles`** — 9 AI prompt profiles with per-profile allowed categories, plus `active` and `auto_route` (default `true`: text assets route by type — document, spreadsheet, audio — while video/image keep the selected profile)
- **`allowed_categories`** — 54 taxonomy entries (including audio categories)
- **`cinematography`** — Reference tables for shot types, camera moves, lighting, color palettes, composition, moods
- **`model`** — Vision + text model names, temperature, `num_ctx`, `last_provider`, and the `llamacpp` block (`base_url`, `gguf_name`, `gguf_path`, `mmproj_path` — the projector is required for vision)
- **`preview`** — `image_max_edge` (1024), `video_grid_scale` (300), `extraction_workers` (0 = CPU count)
- **`naming`** — `case_style` (`title_case`), `max_filename_chars` (0 = unlimited), `sort_folders` (`true`)
- **`naming_templates`** — `default`/`short` = `{topic}_{description}`, `editorial` = `{date}_{topic}`; supports `{category}`, `{topic}`, `{description}`, `{date}`
- **`video_extensions`** / `image_extensions` / `document_extensions` / `audio_extensions` — Configurable file type lists (10 / 10 / 9 / 12)
- **`server`** — `lan_expose` (default `false`); optional `cors_origins` (list) overrides the default CORS allow-list. Setting `AMR_AUTH_ENABLED=1` requires a bearer token from `/api/auth/token` on mutating routes, and `AMR_RATE_LIMIT` enables per-IP rate limiting.
- **`logging`** — Log directory, file rotation (5 MB × 3 backups), max upload size (10 GB), `redact_paths` (default `true`)

---

## Logging

Events logged as JSON Lines to `logs/renamer_YYYY-MM-DD.jsonl`. Each line: timestamp (UTC), level, event type, filename, structured details.

---

## System Requirements

- **Python 3.10+**
- **A local AI runtime** — llama.cpp, installed by the setup wizard on fresh installs (vision GGUF + required `mmproj` projector, plus a compact text model for documents/audio)
- **ExifTool 12+** in PATH (auto-installed by the wizard/EXE)
- **FFmpeg 6+** (including ffprobe) in PATH (auto-installed by the wizard/EXE)
- **fpcalc** (Chromaprint) — optional; audio fingerprint duplicate detection
- **Windows 10/11** (primary target; Linux/macOS compatible but untested)

---

## Support

If this tool saves you time, consider supporting further development. Donation links coming soon.
