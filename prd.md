# Product Requirements Document — AI Media Renamer

## Core Vision & Objectives

**Vision:** Eliminate the manual drudgery of organizing, renaming, and tagging large media libraries. Editors, VFX artists, and content creators spend hours naming files and applying metadata — this product automates that entire pipeline using local AI vision models, all without uploading content to third-party services.

**Objectives:**
- Automatically generate descriptive, human-readable filenames from visual content analysis
- Classify every asset into a structured taxonomy (54 categories, including audio)
- Inject industry-standard metadata (XMP description, keywords, QuickTime tags) so files are searchable in NLEs (DaVinci Resolve, Premiere Pro) and DAM systems
- Support parallel batch processing without user babysitting
- Provide both a CLI for power users and a React SPA (FastAPI backend) for interactive review

## Target Audience & Core User Personas

### Persona 1: Video Editor / Post-Production Lead
Works in DaVinci Resolve or Premiere Pro. Manages thousands of stock clips, B-roll, motion graphics, and VFX elements. Needs files named by content (not camera-generated filenames like `DJI_0001.MP4`) and tagged with searchable keywords. Values metadata that survives into their NLE's bin search.

**Pain point:** Manual renaming of 500+ clips per project takes hours. Metadata entry is repetitive and error-prone.  
**Success criterion:** Import renamed/tagged files into Resolve — keywords and descriptions appear in the Metadata panel and are searchable in the Edit page.

### Persona 2: Solo Content Creator / YouTuber
Manages their own footage library. Not a metadata expert. Needs a simple drag-and-drop interface that "just works" — upload files, get intelligently named assets, commit with one click.

**Pain point:** Doesn't know (and shouldn't need to know) about XMP vs EXIF vs QuickTime atoms. Wants files named properly without moving them around.  
**Success criterion:** One-click commit, files renamed in place and sorted into category subfolders, descriptive filenames that make sense when dragged into a timeline.

### Persona 3: Studio Operations / Media Asset Manager
Processes bulk deliveries from multiple shooters. Needs to enforce consistent naming conventions and taxonomy across the entire library. Reviews AI suggestions before committing. Requires logging and audit trails.

**Pain point:** Contractors and freelancers name files inconsistently. Manual QC and rename is a bottleneck.  
**Success criterion:** Editable staging matrix for review, category override per asset, full JSONL audit log for every rename operation.

## MVP Features Checklist

### Upload & Ingestion
- [x] Drag-and-drop file upload via browser (extension + file-size validation)
- [x] Support video formats: MP4, M4V, MOV, AVI, MKV, WebM, FLV, WMV, MTS, TS
- [x] Support image formats: JPG, JPEG, PNG, WebP, GIF, BMP, TIFF, TIF, HEIC, RAW
- [x] Support document formats: PDF, DOCX, XLSX, CSV, PPTX, TXT, MD, RTF (text extraction, no frame extraction)
- [x] Support audio formats: MP3, WAV, FLAC, AAC, OGG, M4A, WMA, OPUS, AIFF, ALAC, APE, WV (12 total; transcription, no visual extraction)
- [x] "Clear All Files" button to reset upload state
- [x] Progress indicator during upload / file copy
- [x] `--include-subdirectories` flag for CLI scanning

### AI Analysis Pipeline
- [x] Phase 1 — Parallel FFmpeg frame extraction with hardware acceleration detection (NVIDIA, Intel QSV, AMF, CPU fallback)
- [x] High-resolution image downscaling in memory (1024px max edge, no temp files)
- [x] Single frame extraction (midpoint, fast-seeking via ffmpeg)
- [x] Phase 2 — Sequential AI analysis via the local llama.cpp runtime (`llama-server`, OpenAI-compatible API); one result streamed per asset over the WebSocket
- [x] Model selection wizard for first-time users (Qwen2.5-VL 7B/2B + Qwen2.5 3B text model for documents/audio)
- [x] Structured AI response parsing with typed error handling
- [x] Pydantic structured outputs — response schema, `response_format`, retry with fallback
- [x] Configurable AI prompt with cinematography analysis (shot type, camera movement, lighting, color palette, composition, mood)
- [x] 54-category taxonomy validation — invalid suggestions fall back to uncategorized
- [x] Stop Analysis button (immediate abort, preserves already-analyzed assets)
- [x] Progress bar during extraction and analysis phases
- [x] 9 AI prompt profiles (General Balanced, General B-Roll, Cinematography, Motion Overlays, Religious Landmarks, Document Naming, Spreadsheet Naming, Audio Files, Custom) — selectable in the web UI before analysis and via CLI `--profile`
- [x] Automatic profile routing (`prompt_profiles.auto_route`, default on) — text assets override the selected profile by type (`document` → Document Naming, `spreadsheet` → Spreadsheet Naming, `audio` → Audio Files) via a bounded `profile_scope()`; video/image keep the selected profile
- [x] llama.cpp is the only local runtime — the wizard downloads `llama-server` + a GGUF vision/text model (verified HuggingFace URLs, `hf-mirror` fallback); the `mmproj` projector is required for vision
- [x] llama.cpp health check; analysis fails fast with an error event when the server is unreachable
- [x] "Re-analyze Selected" button (replaces per-asset and Re-analyze All buttons)
- [x] Audio transcription via `faster-whisper` — extract audio track from video, transcribe locally, feed into text analysis pipeline

### Boot Diagnostics & Environment Lifecycle
- [x] First-run setup wizard (`bootstrap.py`) downloads ExifTool, FFmpeg, the llama.cpp runtime, and the selected GGUF models with a live progress step label
- [x] Settings profile persists the chosen runtime (`runtime: "llamacpp"`) and model selection
- [x] Models page lists installed GGUF models, starts downloads, and polls `/api/models/{name}/download-status`
- [x] Controlled `llama-server` lifecycle: `ensure_llamacpp_server()` starts it windowless, logs to `logs/llamacpp_server.log`, and `stop_llamacpp_server()` shuts it down
- [x] `/api/environment` reports binary/model readiness for the UI
- [x] PyInstaller bundle with embedded binary path resolution (`_resolve_binary_path()`)

### Staging & Review
- [x] Editable React staging matrix with columns: select checkbox, original filename, type (media/doc/audio), proposed filename, category (dropdown with dynamic options including custom categories), tags (comma-separated), summary (read-only)
- [x] Per-asset category override via dropdown with all 54 categories + custom text entry
- [x] Search/filter input above the table (instant match by name, category, tags)
- [x] Bulk category assignment — select-all checkbox + dropdown apply with custom category inline entry
- [x] Native click-to-sort column headers
- [x] CSV export (`GET /api/staging/export`) + CSV import (`POST /api/staging/import`)
- [x] Preview thumbnails (single midpoint frame per video)
- [x] "Sort into categorized subfolders" toggle (`naming.sort_folders`, on by default)
- [x] "Commit Selected" — only checked rows are processed
- [x] Collision-safe renaming (appends `_1`, `_2` etc. if target filename exists)
- [x] Naming template system: presets `default`/`short` (`{topic}_{description}`) and `editorial` (`{date}_{topic}`), case styles (snake_case, camelCase, kebab-case, pascal_case, lowercase, title_case), max filename length — with live preview

### Metadata & File Commit
- [x] In-place `Path.rename()` (no copy — fast, no duplication)
- [x] Persistent ExifTool subprocess (`-stay_open True`) for fast batch metadata injection
- [x] XMP tags: `dc:description`, `dc:subject` (individual array elements), `Microsoft:Category`
- [x] QuickTime tags for video: `Description`, `Comment`, `Keywords`
- [x] Keys tags for video: `Description`, `Keywords`
- [x] EXIF tags for images: `ImageDescription`, `UserComment`, `XPKeywords`, IPTC `Keywords`
- [x] Commit writes in place into the scanned directory (CLI) or the request's `target_dir` (API), optionally into category subfolders
- [x] Collision-safe renames; per-asset commit status and error surfaced back into staging
- [x] Undo/rollback engine — `undo_log.jsonl`, `--rollback` CLI flag, "Rollback last batch" on the Commit & Export page

### Logging & Sessions
- [x] JSONL logging to `logs/renamer_YYYY-MM-DD.jsonl`
- [x] Events: session_start, file_skipped, extraction_failed, ai_analysis_success/failed, category_override, file_committed/failed, session_end
- [x] Saved sessions (`GET/POST /api/sessions`, `GET/DELETE /api/sessions/{id}`) restore staging across restarts
- [x] Config reset from Settings, `--reset-config`, or automatic recovery

### CLI (Power User Path)
- [x] `python cli.py <directory>` — full pipeline: scan, analyze, stage, commit
- [x] `--verbose` flag for raw AI response debug output
- [x] Interactive staging prompts with manual override per asset
- [x] Batch mode with parallel commit workers (ThreadPoolExecutor)
- [x] `is_already_processed()` skip logic — avoids re-processing already-tagged files

### Configuration
- [x] Single `config.json` as source of truth for all tunable parameters
- [x] Configurable: 9 AI prompt profiles, 54 categories, model/ provider settings, extensions (video/image/document/audio), preview params, naming templates, logging limits
- [x] No hardcoded constants in Python code
- [x] Settings page edits `config.json` as validated JSON (`GET`/`PUT /api/config`)
- [x] Category, extension, and prompt-profile changes are made in that config document

## Out of Scope (v1)

- **Multi-user accounts** — Optional bearer-token LAN auth (`AMR_AUTH_ENABLED=1`) exists, but there are no user accounts, roles, or shared sessions. One analysis job runs at a time against a single in-memory staging set.
- **Persistent asset database** — No file database or library index. Saved sessions persist staging rows only; there is no re-import of previously renamed files with their metadata.
- **Drag-and-drop reordering** — Staging matrix lists assets in scan order. No manual reorder via drag.
- **Video transcoding** — No format conversion, resolution change, or re-encoding. Files keep their original codec/container.
- **Sidecar files** — No XMP sidecar creation. Metadata is written directly into file headers.
- **Watch folders / automation** — No folder monitoring or auto-processing. Manual trigger via CLI or web UI.
- **Mobile / tablet UI** — The SPA is desktop-first; no dedicated mobile layout.
- **Internationalization** — English-only UI. Filenames are normalized to the configured case style (default `title_case`).
- **Plugin / extensibility system** — No hook system for custom metadata sources, naming rules, or output formats.
- **Face / object / scene detection** — AI analyzes the full visual context but does not detect specific faces, identify objects, or segment scenes.
- **AI-generated content detection** — No reliable way to detect AI content from frame analysis alone.
- **NLE XML exports** — No DaVinci Resolve CSV or FCPXML export. Users rely on OS-level file tags and NLE metadata panel.
- **Cloud API support** — No cloud model providers. Analysis runs 100% locally via llama.cpp; no API keys, no uploads, no subscriptions.

## Core Tech Stack & Assumptions

### Stack
| Layer | Technology | Rationale |
|---|---|---|
| **Frontend / UI** | React 19 + Vite + TypeScript + Tailwind | Editable staging matrix, live WebSocket progress, SPA routing |
| **Backend** | FastAPI + uvicorn (Python 3.10+) | REST routes + WebSocket analysis streaming; no engine logic duplicated |
| **AI Model / Runtime** | llama.cpp only (`llama-server`, OpenAI-compatible API) | Fully local vision/text models; vision requires the `mmproj` projector. Multiple prompt profiles with per-type auto-routing |
| **Metadata Engine** | ExifTool 12+ | Industry standard for cross-format metadata; `-stay_open` mode for persistent subprocess performance |
| **Media Decoding** | FFmpeg 6+ | Hardware-accelerated single-frame extraction and in-memory image downscaling |
| **Desktop Bundler** | PyInstaller 6+ (`build_v2.spec`) | Single-file executable that bundles the built SPA, FFmpeg/ExifTool, and llama.cpp; `_resolve_binary_path()` |
| **Config** | JSON (`config.json`) | Human-editable, no parser needed beyond stdlib `json` |
| **Logging** | JSON Lines | Append-only, redacted paths by default |
| **OS** | Windows 10/11 | Primary target (NLE ecosystem). Linux/macOS secondary (compatible but untested) |

### Assumptions
- **Local AI runtime available.** `llama-server` runs on `http://127.0.0.1:8080/v1`, started by the wizard/EXE or `ensure_llamacpp_server()`. The vision model and its `mmproj` projector must both be present; documents/audio use the compact text model.
- **ExifTool and FFmpeg are in `PATH`.** The wizard and EXE install both into `bin/`; source users can install them independently.
- **Single analysis job.** The server keeps one in-memory staging set and one cancellation event; no state is shared between browser tabs.
- **Files are under 4 GB typical.** `LargeFileSupport=1` is enabled in ExifTool args for oversized files, but very large files (>10 GB) may cause longer processing times.
- **Network reliability for the local AI.** Inference runs over loopback HTTP; transient failures are retried once.
- **No concurrent file modification.** The app assumes exclusive access to files during the commit phase. External modifications during processing may cause `PermissionError`.
- **Windows file system.** Paths use backslashes, `PermissionError` is the primary failure mode (locked by Explorer preview pane), `Path.rename()` works within the same drive only.
- **Privacy-first audio.** Audio transcription runs locally via `faster-whisper` (CTranslate2). No cloud API calls for audio processing.
