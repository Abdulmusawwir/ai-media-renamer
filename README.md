# AI Media Renamer

Automatically organize, rename, and tag video/image assets using local AI vision models. 6 prompt profiles for different use cases. Comes with both a **CLI** and a **Streamlit web app**.

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Prerequisites
- **Ollama** with a vision model (e.g. `qwen2.5vl:7b`) — [ollama.com](https://ollama.com)
- **ExifTool 12+** — [exiftool.org](https://exiftool.org)
- **FFmpeg 6+** (including ffprobe) — [ffmpeg.org](https://ffmpeg.org)

### CLI
```bash
python cli.py "path/to/your/assets" [--verbose] [--profile cinematography] [--case-style snake_case] [--max-chars 60] [--force] [--export-csv staging.csv] [--dry-run]
```

### CLI Flags
| Flag | Description |
|---|---|
| `dir` | Path to directory containing media files |
| `--verbose` / `-v` | Debug output (raw AI responses) |
| `--profile` / `-p` | AI prompt profile: `general_balanced`, `general_broll`, `cinematography`, `motion_overlays`, `religious_landmarks`, `custom` |
| `--template` / `-t` | Naming template preset (`default`, `short`, `editorial`) or raw pattern |
| `--case-style` / `--style` | Case style: `snake_case` (default), `camelCase`, `kebab-case`, `pascal_case`, `lowercase` |
| `--max-chars` / `--max` | Max filename length (0 = no limit) |
| `--force` | Re-analyze all files, including previously processed ones |
| `--workers` / `-w` | Parallel extraction workers (default: CPU count) |
| `--export-csv <file>` | Export staging data to CSV after analysis |
| `--import-csv <file>` | Skip AI analysis, load staging from CSV |
| `--dry-run` | Preview commits without modifying files |

### CLI Workflow
1. **Extraction** — Parallel FFmpeg frame extraction with HW acceleration detection
2. **Analysis** — Sequential per-asset AI analysis with progress indicators
3. **Staging Review** — Summary table, category override for uncategorized assets
4. **Execution** — Choose: `[A]pply All`, `[I]nteractive mode`, `[D]ry-run preview`, or `[C]ancel`

Interactive mode per-asset options: `[A]ccept`, `[S]kip`, `[R]e-analyze`, `[E]dit name`, `[B]ulk-apply category to remaining`, or type a custom name override.

## Modules

| File | Purpose |
|---|---|
| `engine.py` | Core importable functions — config, ExifTool sessions, FFmpeg frame extraction, AI analysis, environment checks, file commits |
| `app.py` | Streamlit web app — Upload & Analyze tab (file upload, per-asset AI analysis, editable staging matrix, commit), Analytics Dashboard |
| `cli.py` | CLI workflow — scan, extract, analyze, stage, commit |
| `config.json` | Single source of truth — prompt profiles (6), categories (40), model settings, naming templates, providers, logging |

## Web App Features

- **Upload & Analyze** — Drag-and-drop upload with extension/file-size validation, parallel FFmpeg frame extraction (single midpoint frame per video, hardware-accelerated), sequential per-asset AI analysis with progress bars
- **Editable Staging Matrix** — `st.data_editor` with columns: select checkbox, original filename, editable proposed filename, category dropdown (with custom entry), comma-separated tags, read-only summary. Search/filter above the table. Native click-to-sort column headers.
- **Bulk Category Assignment** — Select assets, pick a category (or type a custom one), apply to all checked rows at once
- **AI Prompt Profiles** — 6 built-in profiles (General Balanced, General B-Roll, Cinematography, Motion Overlays, Religious Landmarks, Custom) selectable right before analysis. Changeable per run.
- **Naming Settings** — Configurable `{category}_{topic}_{description}` pattern, case style (snake_case, camelCase, etc.), max filename length — all with live preview updates in the staging table
- **Re-analyze Selected** — Check specific rows and re-analyze only those assets without re-processing the entire batch
- **CSV Import/Export** — Export staging table as CSV ("Export Staged Changes"), re-import later to restore or modify
- **Commit** — Write metadata (XMP, QuickTime, EXIF, IPTC) and optionally sort into categorized subfolders
- **Analytics Dashboard** — Auto-refreshing stats cards, Plotly charts, filterable event timeline from JSONL logs, Reset All button
- **Sidebar** — Provider (Ollama) + model selection, API key management, environment health check indicators

## Output Directory

Renamed files land in `~/Desktop/RenamedMedia` by default. With `sort_folders` enabled, files are sorted into subdirectories by category (e.g. `~/Desktop/RenamedMedia/aerial_drone/`).

## Metadata

After renaming, every file receives structured metadata written directly into its headers:

| Tag | File Type | Description |
|---|---|---|
| `XMP-dc:Description` | All | Visual summary from AI analysis |
| `XMP-dc:Subject` | All | Keywords as individual array elements |
| `Microsoft:Category` | All | Assigned taxonomy category |
| `QuickTime:Description/Comment/Keywords` | MP4/MOV/MKV | Video-specific metadata |
| `Keys:Description/Keywords` | MP4/MOV/MKV | Additional video metadata |
| `EXIF:XPKeywords` | JPG/PNG | Windows Explorer "Tags" column |
| `IPTC:Keywords` | JPG/PNG | Individual keyword entries |
| `EXIF:ImageDescription/UserComment` | JPG/PNG | EXIF description fields |

Compatible with **DaVinci Resolve** and **Adobe Premiere Pro**.

## Configuration (`config.json`)

- **`prompt_profiles`** — 6 AI prompt profiles with per-profile allowed categories
- **`allowed_categories`** — 40 taxonomy entries
- **`cinematography`** — Reference tables for shot types, camera moves, lighting, color palettes, composition, moods
- **`model`** — Provider, model name, temperature, num_ctx, keep_alive
- **`preview`** — Image max edge (1024px), video frame scale (300px)
- **`naming_templates`** — Preset filename patterns with `{category}`, `{topic}`, `{description}`, `{date}`
- **`cloud`** — Provider list with base URLs (Ollama active; Gemini, OpenAI, Anthropic, Groq, OpenRouter implemented but untested)
- **`logging`** — Log directory, file rotation, max upload size (10 GB)

## Logging

Events logged as JSON Lines to `logs/renamer_YYYY-MM-DD.jsonl`. Each line: timestamp (UTC), level, event type, filename, structured details.

## System Requirements

- **Python 3.10+**
- **Ollama** with a vision model (e.g. `qwen2.5vl:7b`)
- **ExifTool 12+** in PATH
- **FFmpeg 6+** (including ffprobe) in PATH
- **Windows 10/11** (primary target; Linux/macOS compatible but untested)
