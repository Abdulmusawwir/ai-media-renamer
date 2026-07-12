# AI Media Renamer

A vibecoded utility that automatically organizes, renames, and tags media assets using local or cloud AI vision models. Comes with both a **CLI** and a **Streamlit web app**.

## Quick Start

```bash
pip install -r requirements.txt
```

### Local Mode (Ollama)
Ensure `ollama` is running with `qwen2.5vl:7b` installed, and `exiftool` + `ffmpeg` are in your PATH.

### Cloud Mode (Gemini)
No local AI model needed. Enter your Gemini API key in the sidebar.

### Web App (recommended)
```bash
streamlit run app.py
```

### CLI
```bash
python cli.py "path/to/your/assets"
python cli.py "path/to/your/assets" --verbose
```

## Modules

| File | Purpose |
|---|---|
| `engine.py` | Core importable functions — config loading, ExifTool sessions, FFmpeg extraction, AI analysis, environment checks, file commits. Never run directly. |
| `cli.py` | CLI workflow — scans directory, extracts, analyzes, stages, and commits with interactive prompts. |
| `app.py` | Streamlit web app — 2 tabs: Upload & Analyze (file upload + inline staging matrix), Analytics Dashboard. |
| `config.json` | All configuration — prompt, 40 categories, model settings, cinematography reference tables, preview params, cloud providers, naming templates. |

## Web App Features (app.py)

- **Upload & Analyze** — Drag-and-drop file upload with progress bar and extension validation, parallel FFmpeg frame extraction with hardware acceleration (CUDA/QSV/CPU/AMF), sequential per-asset AI analysis with progress bars, editable staging matrix (filename, category dropdown, comma-separated tags, checkbox selection), thumbnail previews, commit with optional categorized subfolders
- **AI Provider Panel** — Sidebar toggle between Local (Ollama) and Cloud (Gemini) with environment status indicators, API key input, model download/wipe controls
- **Analytics Dashboard** — Auto-refreshing every 10 seconds, stats cards (total events, committed, errors, skipped), Plotly category pie chart, daily activity bar chart, filterable event timeline from JSONL logs, Reset All button
- **Naming Templates** — Configurable `{category}_{topic}_{description}` patterns with preset templates and custom case styles

## Output Directory

Renamed files land in `~/Desktop/RenamedMedia` by default. When `sort_folders` is enabled, files are sorted into subdirectories by category (e.g., `~/Desktop/RenamedMedia/aerial_drone/`, `~/Desktop/RenamedMedia/particles_dust/`).

## Metadata

After renaming, every file receives structured metadata written directly into its headers:

| Tag | File Type | Description |
|---|---|---|
| `XMP-dc:Description` | All | Visual summary from AI analysis |
| `XMP-dc:Subject` | All | Keywords as individual array elements |
| `Microsoft:Category` | All | Assigned taxonomy category |
| `QuickTime:Description`, `QuickTime:Comment`, `QuickTime:Keywords` | MP4/MOV/MKV | Video-specific metadata |
| `Keys:Description`, `Keys:Keywords` | MP4/MOV/MKV | Additional video metadata |
| `EXIF:XPKeywords` | JPG/PNG | Windows Explorer "Tags" column |
| `IPTC:Keywords` | JPG/PNG | Individual keyword entries |
| `EXIF:ImageDescription`, `EXIF:UserComment` | JPG/PNG | EXIF description fields |

Metadata is confirmed compatible with **DaVinci Resolve** (Description and Keywords in Metadata panel) and **Adobe Premiere Pro** (Description and Dublin Core Keywords columns).

## Configuration (`config.json`)

All tunable settings in one file:
- **`ai_prompt`** — Extended system prompt with full cinematography analysis (shot types, camera movement, lighting, color, composition, mood)
- **`allowed_categories`** — 40 taxonomy entries
- **`cinematography`** — Reference tables for shot types, camera moves, lighting, palettes, composition, moods
- **`model`** — Model name, temperature, num_ctx, keep_alive
- **`preview`** — Image max edge, video grid tile/scale
- **`naming_templates`** — Preset filename patterns with {category}, {topic}, {description}, {date}
- **`cloud`** — Cloud provider list (gemini, openai, anthropic)
- **`logging`** — Log directory, file rotation, max upload size

## Image Preview

High-resolution images are downscaled in memory (max 1024px long edge, JPEG via FFmpeg) before AI analysis. Originals are never modified. Videos use a 5x2 frame grid at 300px scale with fast-seeking.

## Logging

Events are logged as JSON Lines to `logs/renamer_YYYY-MM-DD.jsonl`. Each line: timestamp (UTC), level (INFO/WARNING/ERROR), event type, filename, and structured details.

## System Requirements

- **Python 3.10+**
- **Ollama** with `qwen2.5vl:7b` (or compatible vision model) — for local mode only
- **ExifTool 12+** — in system PATH
- **FFmpeg 6+** (including ffprobe) — in system PATH
- **Windows 10/11** (primary target; Linux/macOS compatible but untested)

---

*If you find this tool useful, consider supporting its development. More details coming soon.*
