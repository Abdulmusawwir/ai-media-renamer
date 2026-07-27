# AI Media Renamer

**Turn messy media folders into a well-organized library — automatically.**

Drop in your videos and images, let AI look at each one, and get back neatly renamed files with descriptive filenames, proper categories, and searchable metadata. Works with DaVinci Resolve, Premiere Pro, and Windows Explorer.

## Download the EXE

Grab the latest `AIMediaRenamer.exe` from the [Releases page](https://github.com/Abdulmusawwir/ai-media-renamer/releases/latest). No installation needed — download, double-click, and the app sets itself up. It will auto-download any missing dependencies (FFmpeg, ExifTool, Ollama) on first launch.

> For detailed technical docs, CLI flags, config reference, and system requirements, see [README_TECH.md](README_TECH.md).

---

## What It Does

1. **You upload or point to a folder** — videos, images, whatever you've got
2. **AI analyzes each file** — identifies the content, suggests a filename, category, and tags
3. **Review and tweak** — edit names, assign categories, add tags in a spreadsheet-like table
4. **Commit** — files are renamed with their new names, and metadata is written directly into the file headers so your editing software can read it

---

## Features

### AI Analysis
- **7 prompt profiles** — General, B-Roll, Cinematography, Motion & Overlays, Religious Landmarks, Document Naming, Spreadsheet Naming, and Custom
- **6 AI providers** — Ollama (local), Gemini, OpenAI, Anthropic, Groq, OpenRouter
- **Single-frame extraction** — one representative frame per video for accurate analysis
- **Image analysis** — downscaled in memory, no disk writes

### Staging & Editing
- **Spreadsheet-like table** — edit filenames, categories, tags, and ratings inline
- **Bulk operations** — apply categories, case styles, and naming templates to selected rows
- **Search & filter** — find files by name, category, or tags instantly
- **Duplicate detection** — visual hash comparison flags near-identical assets before commit
- **User ratings** — thumbs up/down on AI suggestions to track quality over time

### Naming & Organization
- **Naming templates** — `{topic}_{description}`, `{date}_{topic}`, or custom patterns
- **Case styles** — snake_case, camelCase, kebab-case, PascalCase, lowercase, title case
- **Category folders** — optionally sort committed files into category subdirectories
- **Metadata writing** — XMP and EXIF tags written directly into file headers (DaVinci Resolve, Premiere Pro, Windows Explorer compatible)

### Configuration
- **Web-based config editor** — edit AI models, categories, extensions, and prompt profiles in-app
- **Config reset** — restore defaults from the web UI, CLI flag (`--reset-config`), or automatic recovery
- **Session persistence** — save and resume analysis sessions across app restarts

### Telemetry (Optional)
- **Anonymous usage data** — opt-in to send non-identifying events (ratings, session stats, errors) to help improve the app
- **Full control** — toggle on/off anytime in Configuration tab. See [PRIVACY.md](PRIVACY.md) for details

---

## Web App (Streamlit)

The main way to use it. Open in your browser, drag and drop files, see everything visually.

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## CLI

For batch processing or scripting. Same engine, no GUI.

```bash
python cli.py "path/to/folder" --dry-run
python cli.py "path/to/folder" --profile cinematography --case-style kebab-case
python cli.py "path/to/folder" --force                    # re-analyze all files
python cli.py "path/to/folder" --export-csv staging.csv   # export to CSV
python cli.py "path/to/folder" --import-csv staging.csv   # load from CSV
```

See [README_TECH.md](README_TECH.md#cli-reference) for the full flag reference.

---

## Quick Start

### EXE (Recommended)

1. Download `AIMediaRenamer.exe` from [Releases](https://github.com/Abdulmusawwir/ai-media-renamer/releases/latest)
2. Double-click to launch — dependencies auto-install on first run
3. Upload files, run analysis, review, commit

### From Source

1. Install prerequisites: [Ollama](https://ollama.com) + vision model (`ollama pull qwen2.5vl:7b`), [ExifTool 12+](https://exiftool.org), [FFmpeg 6+](https://ffmpeg.org)
2. `pip install -r requirements.txt`
3. `streamlit run app.py`

### Docker

Run `docker compose up` for a fully containerized setup (includes Ollama + GPU passthrough).

---

## Why Use This?

- **No more "final_v3_actual_use_this.mp4"** — every file gets a descriptive, consistent name
- **Metadata written to the file** — not a separate spreadsheet. Your NLE reads it natively
- **Works offline** — uses local Ollama models, no cloud API needed
- **Bulk operations** — apply categories, edit names, filter, sort — all in one table
- **Safe** — originals are preserved, dry-run mode shows what will happen before anything changes
- **Duplicate detection** — catches near-identical files before they clutter your library

---

## Support the Project

If this tool helps you stay organized and saves you time, consider supporting further development.

Your support helps cover API testing, new features, and maintenance.

*Donation links coming soon.*
