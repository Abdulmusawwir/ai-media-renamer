# Product Requirements Document — AI Media Renamer

## Core Vision & Objectives

**Vision:** Eliminate the manual drudgery of organizing, renaming, and tagging large media libraries. Editors, VFX artists, and content creators spend hours naming files and applying metadata — this product automates that entire pipeline using local AI vision models, all without uploading content to third-party services.

**Objectives:**
- Automatically generate descriptive, human-readable filenames from visual content analysis
- Classify every asset into a structured 40-category taxonomy
- Inject industry-standard metadata (XMP description, keywords, QuickTime tags) so files are searchable in NLEs (DaVinci Resolve, Premiere Pro) and DAM systems
- Support parallel batch processing without user babysitting
- Provide both a CLI for power users and a Streamlit web UI for interactive review

## Target Audience & Core User Personas

### Persona 1: Video Editor / Post-Production Lead
Works in DaVinci Resolve or Premiere Pro. Manages thousands of stock clips, B-roll, motion graphics, and VFX elements. Needs files named by content (not camera-generated filenames like `DJI_0001.MP4`) and tagged with searchable keywords. Values metadata that survives into their NLE's bin search.

**Pain point:** Manual renaming of 500+ clips per project takes hours. Metadata entry is repetitive and error-prone.  
**Success criterion:** Import renamed/tagged files into Resolve — keywords and descriptions appear in the Metadata panel and are searchable in the Edit page.

### Persona 2: Solo Content Creator / YouTuber
Manages their own footage library. Not a metadata expert. Needs a simple drag-and-drop interface that "just works" — upload files, get intelligently named assets, commit with one click.

**Pain point:** Doesn't know (and shouldn't need to know) about XMP vs EXIF vs QuickTime atoms. Wants files on their Desktop named properly.  
**Success criterion:** One-click commit, files land on Desktop sorted by category, descriptive filenames that make sense when dragged into a timeline.

### Persona 3: Studio Operations / Media Asset Manager
Processes bulk deliveries from multiple shooters. Needs to enforce consistent naming conventions and taxonomy across the entire library. Reviews AI suggestions before committing. Requires logging and audit trails.

**Pain point:** Contractors and freelancers name files inconsistently. Manual QC and rename is a bottleneck.  
**Success criterion:** Editable staging matrix for review, category override per asset, full JSONL audit log for every rename operation.

## MVP Features Checklist

### Upload & Ingestion
- [x] Drag-and-drop file upload via browser (Streamlit file uploader)
- [x] Support video formats: MP4, MOV, AVI, MKV, WebM
- [x] Support image formats: JPG, JPEG, PNG, WebP, GIF
- [x] Eager file saving to temp directory (files survive Streamlit reruns)
- [x] "Clear All Files" button to reset upload state
- [ ] Progress indicator during upload / file copy
- [ ] `--include-subdirectories` flag for CLI scanning

### AI Analysis Pipeline
- [x] Phase 1 — Parallel FFmpeg frame extraction with hardware acceleration detection (NVIDIA, Intel QSV, AMF, CPU fallback)
- [x] High-resolution image downscaling in memory (1024px max edge, no temp files)
- [x] Video storyboard extraction (10 frames, 5x2 grid, fast-seeking)
- [x] Phase 2 — Sequential AI analysis via Ollama vision model (qwen2.5vl:7b)
- [x] Per-asset rerun loop: one AI call per script execution, advanced via `st.rerun()`
- [x] Structured AI response parsing with typed error handling
- [x] Configurable AI prompt with cinematography analysis (shot type, camera movement, lighting, color palette, composition, mood)
- [x] 40-category taxonomy validation — invalid suggestions fall back to uncategorized
- [x] Stop Analysis button (immediate abort, preserves already-analyzed assets)
- [x] Progress bar during extraction and analysis phases
- [ ] Multiple AI prompt profiles (Religious, General, Videography, Custom) — selectable in web UI and CLI
- [ ] Multi-provider AI support (Ollama, OpenAI, Anthropic, LM Studio) with provider abstraction layer
- [ ] Auto-detect available Ollama models via `ollama.list()` and populate dropdown
- [ ] Per-asset re-analysis button + "Re-analyze All"
- [ ] Ollama health check with status indicator in web UI

### Staging & Review
- [x] Editable `st.data_editor` with columns: select checkbox, original filename, proposed filename, category (dropdown), tags (comma-separated), summary (read-only)
- [x] Per-asset category override via dropdown with all 40 categories + custom text entry
- [x] Preview thumbnails in expandable section
- [x] "Sort into categorized subfolders" checkbox
- [x] "Commit Selected" button — only checked rows are processed
- [x] Collision-safe renaming (appends `_1`, `_2` etc. if target filename exists)
- [ ] Naming template system (configurable `{category}_{topic}_{description}` patterns)
- [ ] Case style selection (snake_case, camelCase, kebab-case, etc.) — under Advanced Features expander
- [ ] Max filename character limit — under Advanced Features expander

### Metadata & File Commit
- [x] In-place `Path.rename()` (no copy — fast, no duplication)
- [x] Persistent ExifTool subprocess (`-stay_open True`) for fast batch metadata injection
- [x] XMP tags: `dc:description`, `dc:subject` (individual array elements), `Microsoft:Category`
- [x] QuickTime tags for video: `Description`, `Comment`, `Keywords`
- [x] Keys tags for video: `Description`, `Keywords`
- [x] EXIF tags for images: `ImageDescription`, `UserComment`, `XPKeywords`, IPTC `Keywords`
- [x] Commit success message persists across reruns
- [x] Default output directory: `~/Desktop/RenamedMedia`

### Analytics & Logging
- [x] Auto-refreshing analytics dashboard (every 10 seconds)
- [x] Stats cards: total events, committed, errors, skipped
- [x] Category distribution pie chart (Plotly)
- [x] Daily activity bar chart
- [x] Filterable event timeline — filter by level (INFO/ERROR) and event type
- [x] JSONL logging to `logs/renamer_YYYY-MM-DD.jsonl`
- [x] Events: session_start, file_skipped, extraction_failed, ai_analysis_success/failed, category_override, file_committed/failed, session_end
- [x] Reset All button (clears all state, logs, and log files)

### CLI (Power User Path)
- [x] `python cli.py <directory>` — full pipeline: scan, analyze, stage, commit
- [x] `--verbose` flag for raw AI response debug output
- [x] Interactive staging prompts with manual override per asset
- [x] Batch mode with parallel commit workers (ThreadPoolExecutor)
- [x] `is_already_processed()` skip logic — avoids re-processing already-tagged files

### Configuration
- [x] Single `config.json` as source of truth for all tunable parameters
- [x] Configurable: AI prompt, categories, model name/temperature/context/keep_alive, extensions, preview settings, logging limits
- [x] No hardcoded constants in Python code
- [ ] Config editor tab (read-only + editable modes) in web UI
- [ ] In-app category management (add/delete/rename categories via UI)
- [ ] In-app extension management (video/image extension lists via UI)

## Out of Scope (v1)

- **Multi-user / server mode** — No authentication, no shared sessions, no backend database. Single-user per browser tab.
- **Persistent storage** — No file database or asset library. State is ephemeral (Streamlit session + OS temp dir). No re-import of previously renamed files with their metadata.
- **Drag-and-drop reordering** — Staging matrix lists assets in upload order. No manual reorder via drag.
- **Video transcoding** — No format conversion, resolution change, or re-encoding. Files keep their original codec/container.
- **Sidecar files** — No XMP sidecar creation. Metadata is written directly into file headers.
- **Watch folders / automation** — No folder monitoring or auto-processing. Manual trigger via CLI or web UI.
- **Mobile / tablet UI** — Streamlit web app is desktop-only in practice. No responsive mobile layout.
- **Internationalization** -- English-only UI. Filenames and metadata are always lowercase ASCII per AI prompt instructions.
- **Plugin / extensibility system** — No hook system for custom metadata sources, naming rules, or output formats.
- **Face / object / scene detection** — AI analyzes the full visual context but does not detect specific faces, identify objects, or segment scenes.
- **AI-generated content detection** — No reliable way to detect AI content from frame analysis alone.
- **Subtitle/audio track analysis** — Frame extraction only; no audio stream processing.
- **Desktop app / Electron bundler** — Stays as Streamlit web app + Python CLI only.

## Core Tech Stack & Assumptions

### Stack
| Layer | Technology | Rationale |
|---|---|---|
| **Frontend / UI** | Streamlit | Fastest path to interactive data-editor UI with file upload, progress bars, and charts |
| **Backend** | Pure Python 3.10+ | Single-process, no web framework needed beyond Streamlit |
| **AI Model / Providers** | Ollama (primary), OpenAI, Anthropic, LM Studio | Local + cloud vision models via abstracted provider interface. Multiple prompt profiles per use case |
| **Metadata Engine** | ExifTool 12+ | Industry standard for cross-format metadata; `-stay_open` mode for persistent subprocess performance |
| **Media Decoding** | FFmpeg 6+ | Hardware-accelerated frame extraction, downscaling, video storyboard grid generation |
| **Config** | JSON (`config.json`) | Human-editable, no parser needed beyond stdlib `json` |
| **Logging** | JSON Lines | Append-only, trivially parseable into Pandas for analytics dashboard |
| **Charts** | Plotly + Pandas | Interactive charts, readable from JSONL logs |
| **OS** | Windows 10/11 | Primary target (NLE ecosystem). Linux/macOS secondary (compatible but untested) |

### Assumptions
- **AI provider available.** For Ollama/LM Studio: app must be running locally. For OpenAI/Anthropic: valid API key required. Auto-detection of available Ollama models at startup.
- **ExifTool and FFmpeg are in `PATH`.** Not bundled. Users install them independently.
- **Single user per session.** No state shared between browser tabs or users.
- **Files are under 4 GB typical.** `LargeFileSupport=1` is enabled in ExifTool args for oversized files, but very large files (>10 GB) may cause longer processing times.
- **Network reliability for Ollama.** AI inference runs over localhost HTTP; transient failures are retried once.
- **No concurrent file modification.** The app assumes exclusive access to files during the commit phase. External modifications during processing may cause `PermissionError`.
- **Windows file system.** Paths use backslashes, `PermissionError` is the primary failure mode (locked by Explorer preview pane), `Path.rename()` works within the same drive only.
