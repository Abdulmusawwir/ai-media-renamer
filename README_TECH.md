# AI Media Renamer — Technical Reference

Automatically organize, rename, and tag video, image, document, and audio assets using AI. 9 prompt profiles for different use cases. Comes with both a **CLI** and a **Streamlit web app**.

> This is the deep-dive reference: full feature list, CLI flags, config reference, module map, metadata tables, and system requirements.
>
> For the plain-language pitch, screenshots, and quick start, see [README.md](README.md).

### Download the EXE

Pre-built binaries are available on the [Releases page](https://github.com/Abdulmusawwir/ai-media-renamer/releases/latest). The EXE is self-contained — on first run it checks for FFmpeg, ExifTool, and a local AI runtime and downloads any missing components automatically (including the ~18 MB llama.cpp runtime and a GGUF vision model when Ollama isn't already installed).

### Building from Source

```bash
pip install -r requirements.txt
pip install pyinstaller
pyinstaller build.spec
# Output: dist/AIMediaRenamer.exe
```

---

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Prerequisites
- **A local AI runtime** — one of:
  - **llama.cpp** (default for fresh installs) — `llama-server` + a GGUF vision model (7B Qwen2-VL, or lighter 2B on CPU), auto-downloaded by the setup wizard; documents/audio route to a compact text model (Qwen2.5-3B)
  - **Ollama** with a vision model (e.g. `qwen2.5vl:7b`) — [ollama.com](https://ollama.com); auto-detected and reused when already installed
- **ExifTool 12+** — [exiftool.org](https://exiftool.org)
- **FFmpeg 6+** (including ffprobe) — [ffmpeg.org](https://ffmpeg.org)
- **fpcalc** (Chromaprint) — for audio fingerprint duplicate detection (auto-downloaded by EXE)

---

## Why Use This?

- **No more "final_v3_actual_use_this.mp4"** — every file gets a descriptive, consistent name
- **Metadata written to the file** — not a separate spreadsheet. Your NLE reads it natively
- **Works offline** — uses a local runtime (llama.cpp on fresh installs, or Ollama), no cloud API needed
- **Bulk operations** — apply categories, edit names, filter, sort — all in one table
- **Safe** — originals are preserved, dry-run mode shows what will happen before anything changes
- **Duplicate detection** — visual hash (pHash), document hash (SHA-256), and audio fingerprint (Chromaprint) catch near-identical files before they clutter your library

---

## Features

### AI Analysis
- **9 prompt profiles** — General Balanced, General B-Roll, Cinematography, Motion & Overlays, Religious Landmarks, Document Naming, Spreadsheet Naming, Audio Files, and Custom
- **2 local AI providers** — Ollama and llama.cpp (default for new installs). Fully offline: no cloud models, no API keys, no keychain required.
- **Single-frame extraction** — one representative frame per video for accurate analysis
- **Image analysis** — downscaled in memory, no disk writes
- **Audio transcription** — local Whisper transcription for audio files and video audio tracks
- **Document analysis** — text extraction from PDF, DOCX, XLSX, CSV, PPTX, TXT, MD, RTF

### Staging & Editing
- **Spreadsheet-like table** — edit filenames, categories, tags, and ratings inline
- **Bulk operations** — apply categories, case styles, and naming templates to selected rows
- **Search & filter** — find files by name, category, or tags instantly
- **Duplicate detection** — visual hash (pHash), document hash (SHA-256), and audio fingerprint (Chromaprint) comparison
- **User ratings** — thumbs up/down on AI suggestions to track quality over time

### Naming & Organization
- **Naming templates** — `{topic}_{description}`, `{date}_{topic}`, or custom patterns
- **Case styles** — snake_case, camelCase, kebab-case, PascalCase, lowercase, title case
- **Category folders** — optionally sort committed files into category subdirectories
- **Metadata writing** — XMP, EXIF, ID3, Vorbis, and QuickTime tags written directly into file headers (DaVinci Resolve, Premiere Pro, Windows Explorer compatible)

### Configuration
- **Web-based config editor** — edit AI models, categories, extensions, and prompt profiles in-app
- **Config reset** — restore defaults from the web UI, CLI flag (`--reset-config`), or automatic recovery
- **Session persistence** — save and resume analysis sessions across app restarts
- **Undo/rollback** — revert the last commit batch (move files back, remove metadata)

### Telemetry

There is **no telemetry**. The app never collects or transmits usage data — no analytics SDK, no PostHog, no tracking events. Privacy is documented in [PRIVACY.md](PRIVACY.md).

### Security (v1.6.3)

- **Checksum-verified downloads** — every binary the setup wizard fetches (FFmpeg, ExifTool, llama.cpp runtime, GGUF models) is verified against its published SHA-256 digest before use; plain-HTTP URLs are rejected.
- **Secret redaction** — sensitive values are masked in exception messages, JSONL logs, and the Configuration-tab JSON view.
- **No secrets stored** — the app is entirely local (Ollama / llama.cpp) and stores no API keys; the OS-keychain layer was removed in v1.7.0 along with all cloud providers.
- **Loopback-only by default** — the server binds `127.0.0.1` unless you opt into LAN exposure via `config.server.lan_expose` (an in-UI toggle with a warning). Docker Compose host ports also bind to loopback unless changed.
- **Input validation** — CSV import/export neutralizes spreadsheet formula injection; session restore schema-validates and rejects symlinks; staged filenames can never traverse directories on commit.
- **Log path privacy** — absolute paths are redacted from JSONL logs by default (`config.logging.redact_paths`).

### Reliability (v1.6.4)

- **Atomic config writes** — `save_config()` writes to a temp file and `os.replace`s it, so a crash mid-save can never leave a truncated `config.json`.
- **Import-safe startup** — config load/validation is deferred and non-fatal; a broken config degrades gracefully (`CONFIG_LOAD_ERROR` + a minimal fallback) instead of crashing the process at import time.
- **Callback-driven settings** — the engine switcher runs in a Streamlit `on_change` callback (radio disabled while analysis is running) instead of mutating provider/config state mid-render.
- **Safer Clear All** — never deletes saved sessions; sessions are removed only via the explicit Delete control. A shared `_reset_analysis_state()` helper keeps every reset path consistent (also clears the analysis index and duplicate results).
- **ExifTool lifecycle** — the batch session is closed in a `finally`, and stale upload temp-dirs are cleaned up before re-extraction.
- **Lazy previews** — thumbnail decoding and the duplicate table are built on demand instead of on every rerun.
- **CLI validation** — mutually-exclusive argument groups (`--export-csv`/`--import-csv`, `--rollback`/`--reset-config`) and a config-synced default case style.

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
| `--case-style` / `--style` | Case style (default: config `naming.case_style`, `title_case`): `snake_case`, `camelCase`, `kebab-case`, `pascal_case`, `lowercase` |
| `--max-chars` / `--max` | Max filename length (0 = no limit) |
| `--force` | Re-analyze all files, including previously processed ones |
| `--workers` / `-w` | Parallel extraction workers (default: CPU count) |
| `--export-csv <file>` | Export staging data to CSV after analysis |
| `--import-csv <file>` | Skip AI analysis, load staging from CSV |
| `--dry-run` | Preview commits without modifying files |
| `--rollback` | Undo the last commit batch (move files back, remove metadata) |
| `--non-interactive` / `-y` | Skip interactive prompts, auto-accept all |
| `--output` / `-o` | Output directory (default: `~/Desktop/RenamedMedia`) |
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
| `app.py` | Streamlit web app — Upload & Analyze tab (file upload, per-asset AI analysis, editable staging matrix, commit), Analytics Dashboard |
| `cli.py` | CLI workflow — scan, extract, analyze, stage, commit |
| `config.json` | Single source of truth — prompt profiles (9), categories (54), model settings, naming templates, providers, logging |

---

## Web App Features

- **Upload & Analyze** — Drag-and-drop upload with extension/file-size validation, parallel FFmpeg frame extraction (single midpoint frame per video, hardware-accelerated), sequential per-asset AI analysis with progress bars
- **Audio Transcription** — Local Whisper transcription for audio files and video audio tracks, fed into AI analysis context
- **Document Analysis** — Text extraction from PDF, DOCX, XLSX, CSV, PPTX, TXT, MD, RTF for AI analysis
- **Editable Staging Matrix** — `st.data_editor` with columns: select checkbox, original filename, type (media/doc/audio), editable proposed filename, category dropdown (with custom entry), comma-separated tags, read-only summary. Search/filter above the table. Native click-to-sort column headers.
- **Bulk Category Assignment** — Select assets, pick a category (or type a custom one), apply to all checked rows at once
- **AI Prompt Profiles** — 8 built-in profiles selectable right before analysis. Changeable per run.
- **Naming Settings** — Configurable `{category}_{topic}_{description}` pattern, case style (snake_case, camelCase, etc.), max filename length — all with live preview updates in the staging table
- **Re-analyze Selected** — Check specific rows and re-analyze only those assets without re-processing the entire batch
- **CSV Import/Export** — Export staging table as CSV ("Export Staged Changes"), re-import later to restore or modify
- **Commit** — Write metadata (XMP, QuickTime, EXIF, IPTC, ID3, Vorbis) and optionally sort into categorized subfolders
- **Undo/Rollback** — Revert the last commit batch from the Analytics tab
- **Analytics Dashboard** — Auto-refreshing stats cards, Plotly charts, filterable event timeline from JSONL logs, Reset All button
- **Sidebar** — Engine (Ollama / llama.cpp) + model selection, environment health check indicators

### Output Directory

Renamed files land in `~/Desktop/RenamedMedia` by default. With `sort_folders` enabled, files are sorted into subdirectories by category (e.g. `~/Desktop/RenamedMedia/aerial_drone/`).

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

- **`prompt_profiles`** — 9 AI prompt profiles with per-profile allowed categories
- **`allowed_categories`** — 54 taxonomy entries (including audio categories)
- **`cinematography`** — Reference tables for shot types, camera moves, lighting, color palettes, composition, moods
- **`model`** — Engine (Ollama / llama.cpp), model name, text model, temperature, num_ctx, keep_alive, runtime config (llama.cpp base URL + GGUF paths)
- **`preview`** — Image max edge (1024px), video frame scale (300px)
- **`naming_templates`** — Preset filename patterns with `{category}`, `{topic}`, `{description}`, `{date}`
- **`video_extensions`** / `image_extensions` / `document_extensions` / `audio_extensions` — Configurable file type lists
- **`server`** — `lan_expose` (default `false`): when enabled the web server binds `0.0.0.0` instead of loopback-only `127.0.0.1` (no authentication — only enable on trusted networks)
- **`logging`** — Log directory, file rotation, max upload size (10 GB), `redact_paths` (default `true`)

---

## Logging

Events logged as JSON Lines to `logs/renamer_YYYY-MM-DD.jsonl`. Each line: timestamp (UTC), level, event type, filename, structured details.

---

## System Requirements

- **Python 3.10+**
- **A local AI runtime** — llama.cpp (auto-installed by the wizard on fresh setups) or Ollama with a vision model (e.g. `qwen2.5vl:7b`)
- **ExifTool 12+** in PATH
- **FFmpeg 6+** (including ffprobe) in PATH
- **fpcalc** (Chromaprint) — for audio fingerprint duplicate detection
- **Windows 10/11** (primary target; Linux/macOS compatible but untested)

---

## Support

If this tool saves you time, consider supporting further development. Donation links coming soon.
