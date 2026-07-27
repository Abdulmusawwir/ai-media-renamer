<div align="center">

# AI Media Renamer

**Turn messy media folders into a well-organized library — automatically.**

Drop in your videos, images, documents, or audio files, let AI look at each one, and get back neatly renamed files with descriptive filenames, proper categories, and searchable metadata. Works with DaVinci Resolve, Premiere Pro, and Windows Explorer.

</div>

---

## Download

Grab the latest `AIMediaRenamer.exe` from the [Releases page](https://github.com/Abdulmusawwir/ai-media-renamer/releases/latest). No installation needed — download, double-click, and the app sets itself up. It will auto-download any missing dependencies on first launch.

---

## What It Does

1. **You upload or point to a folder** — videos, images, documents, audio — whatever you've got
2. **AI analyzes each file** — identifies the content, suggests a filename, category, and tags
3. **Review and tweak** — edit names, assign categories, add tags in a spreadsheet-like table
4. **Commit** — files are renamed, and metadata is written directly into the file headers so your editing software can read it

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

## Documentation

For detailed technical docs, CLI flags, config reference, system requirements, and feature details, see [README_TECH.md](README_TECH.md).

---

## Support

If this tool helps you stay organized and saves you time, consider supporting further development.

Your support helps cover API testing, new features, and maintenance.

*Donation links coming soon.*
