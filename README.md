# AI Media Renamer

**Turn messy media folders into a well-organized library — automatically.**

Drop in your videos and images, let AI look at each one, and get back neatly renamed files with descriptive filenames, proper categories, and searchable metadata. Works with DaVinci Resolve, Premiere Pro, and Windows Explorer.

## Download the EXE

Grab the latest `AIMediaRenamer.exe` from the [Releases page](https://github.com/Abdulmusawwir/ai-media-renamer/releases/latest). No installation needed — download, double-click, and the app sets itself up. It will auto-download any missing dependencies (FFmpeg, ExifTool, Ollama) on first launch.

> 🛠️ For detailed technical docs, CLI flags, config reference, and system requirements, see [README_TECH.md](README_TECH.md).

---

## What It Does

1. **You upload or point to a folder** — videos, images, whatever you've got
2. **AI analyzes each file** — identifies the content, suggests a filename, category, and tags
3. **Review and tweak** — edit names, assign categories, add tags in a spreadsheet-like table
4. **Commit** — files are renamed with their new names, and metadata is written directly into the file headers so your editing software can read it

---

## Web App (Streamlit)

The main way to use it. Open in your browser, drag and drop files, see everything visually.

```bash
pip install -r requirements.txt
streamlit run app.py
```

### What You Can Do

- **Drag-and-drop upload** — files land in a temp directory, ready for analysis
- **AI analysis** — one file at a time with a progress bar. Choose from 6 prompt profiles (General, Cinematography, Religious Landmarks, etc.)
- **Staging table** — see all files in a grid. Edit proposed names, change categories, apply bulk changes
- **Naming settings** — pick your filename pattern (`{category}_{topic}_{description}`), case style (snake_case, camelCase, etc.), and max length
- **Re-analyze** — if the AI got it wrong, re-analyze just that file (or a selection)
- **Commit** — files are renamed and metadata is written. Optionally sort into category folders
- **Analytics dashboard** — track what's been renamed, view stats and charts

---

## CLI

For batch processing or scripting. Same engine, no GUI.

```bash
python cli.py "path/to/folder" --dry-run
python cli.py "path/to/folder" --profile cinematography --case-style kebab-case
```

See [README_TECH.md](README_TECH.md#cli-reference) for the full flag reference.

---

## Quick Start

### 1. Install prerequisites

- [Ollama](https://ollama.com) with a vision model (`ollama pull qwen2.5vl:7b`)
- [ExifTool 12+](https://exiftool.org)
- [FFmpeg 6+](https://ffmpeg.org)

### 2. Install the app

```bash
pip install -r requirements.txt
streamlit run app.py
```

### 3. Done

Upload files, run analysis, review, commit. Your renamed files land on the Desktop in `~/Desktop/RenamedMedia/`.

---

## Why Use This?

- **No more "final_v3_actual_use_this.mp4"** — every file gets a descriptive, consistent name
- **Metadata written to the file** — not a separate spreadsheet. Your NLE reads it natively
- **Works offline** — uses local Ollama models, no cloud API needed
- **Bulk operations** — apply categories, edit names, filter, sort — all in one table
- **Safe** — originals are preserved, dry-run mode shows what will happen before anything changes

---

## Support the Project

If this tool helps you stay organized and saves you time, consider supporting further development.

Your support helps cover API testing, new features, and maintenance.

*Donation links coming soon.*
