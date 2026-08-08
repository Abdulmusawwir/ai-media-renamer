# Implementation Plan — AI Media Renamer

> **Status:** v1.5.0 shipped. All Layers 1-19 complete.

---

## Layer 1: Upload & Ingestion

### 1.1 Upload progress indicator
- [x] Add `st.progress()` bar during the file-copy loop in `app.py`
  - Compute total bytes across all uploaded files (sum `uf.size`)
  - After each file copy, update progress as `cumulative_bytes / total_bytes`
  - Show per-file name in the progress text: `"Copying file_003.mp4 (3/12)"`
- [x] Guard: skip progress rendering if only 1 file (no progress bar needed for single-file uploads)

### 1.2 File size validation
- [x] Add `max_upload_size` to `config.json` logging section (default: 10 GB in bytes)
- [x] In `app.py` upload handler, check each `uploaded_files` item against the limit
- [x] Show `st.warning()` for oversized files with the filename and size
- [x] Log a `file_skipped` event with reason "exceeds_max_size"
- [x] Remove oversized files from the upload set before saving to temp dir

### 1.3 Drag-and-drop visual feedback
- [x] Add custom CSS to `app.py` via `st.markdown()` that highlights the upload zone on dragover
  - Style: dashed border turns solid, background tint changes
- [x] Use Streamlit's built-in `st.file_uploader` hover effects (no JS needed — CSS pseudo-classes on the uploader's rendered container)

### 1.4 File type mismatch warning
- [x] Before the eager-save loop, check each file's extension against `VIDEO_EXTENSIONS | IMAGE_EXTENSIONS`
- [x] For files with unrecognised extensions: show `st.warning()`, skip the file, log `file_skipped` with reason "unsupported_extension"
- [x] Do not abort the entire batch — skip just the offending files

### 1.5 10GB upload limit
- [x] Create `.streamlit/config.toml` with `maxUploadSize = 10240` (removes Streamlit's 200MB default)
- [x] `MAX_UPLOAD_SIZE` is already 10GB in `config.json` via `max_upload_size: 10737418240`
- [x] Effective limit is now 10GB end-to-end

### 1.6 Block upload when model missing
- [x] In upload tab, check `env.get("model_available")` when provider is Ollama
- [x] If model not installed, replace `st.file_uploader()` with info message directing to sidebar download button
- [x] Blocks both click-to-browse and drag-and-drop entry points

---

## Layer 2: AI Analysis Pipeline

### 2.1 Per-asset re-analysis
- [x] Add "Re-analyze All" button above the staging matrix
  - Clears all `staged_assets`, resets `analysis_index` to 0, re-enters the Phase 2 rerun loop
- [x] Add per-asset "Re-analyze" buttons in a column row below the data editor
  - Each button triggers re-analysis from that index onward, truncating subsequent staged assets
  - Reuses the existing per-asset rerun loop — no separate analysis path needed

### 2.2 Model selection dropdown
- [x] **Already implemented** — `st.selectbox("Model", ...)` in sidebar at `app.py:217`
  - Populated by `provider.available_models()` which calls `ollama.list()` for Ollama
  - On change: `_on_model_change()` updates config
  - Model is passed to provider's `analyze()` via `self._model`

### 2.3 Ollama health check
- [x] Create `check_ollama_health()` in `engine.py`:
  - Calls `ollama.list()` wrapped in try/except
  - Returns `{connected: bool, models: list[str], model_count: int, error: str | None}`
- [x] In `app.py` sidebar, show status indicator near the model selector:
  - Green checkmark "Ollama — N models" when connected
  - Red X "Ollama — disconnected" when unreachable
- [x] Add refresh button beside the indicator
- [x] Cache result in `st.session_state.ollama_health`, invalidated on Refresh Status or provider switch

### 2.4 Configurable extraction concurrency
- [x] Add `extraction_workers` to `config.json` preview section (default: 0 = `os.cpu_count()`)
- [x] Use `EXTRACTION_WORKERS` instead of bare `os.cpu_count()` in `ThreadPoolExecutor` at `app.py`
- [x] CLI: add `--workers N` flag to override `extraction_workers` from config
- [x] Add `_resolve_workers()` helper in `engine.py`

### 2.5 Multiple AI prompt profiles
- [x] Restructure `config.json`: replace `ai_prompt` with `prompt_profiles` section
  - Migrate old `ai_prompt` → `general_balanced.profile` (new default)
  - 6 profiles: `general_balanced`, `general_broll`, `cinematography`, `motion_overlays`, `religious_landmarks`, `custom`
  - Each profile has `label`, `prompt`, and `allowed_categories` (empty = use global fallback)
- [x] Add `get_active_prompt()`, `get_active_categories()`, `set_active_profile()`, `get_profile_labels()` in `engine.py`
- [x] All provider `analyze()` methods use `get_active_prompt()` dynamically (not static `AI_PROMPT`)
- [x] In `app.py` sidebar, add profile dropdown with label display
- [x] Custom profile: show `st.text_area()` for user prompt, auto-save to `config.json` via `save_config()`
- [x] Export button: `st.download_button()` downloads custom prompt as `.txt`
- [x] CLI: add `--profile` flag

### 2.6 Multi-provider abstraction
- [x] Create provider interface in `engine.py` with abstract `analyze()` method
- [x] Implement `OllamaProvider` (existing code, refactored)
- [x] Implement `OpenAIProvider` using `openai` Python client (vision API)
- [x] Implement `AnthropicProvider` using `anthropic` Python client
- [x] Implement `GroqProvider` (OpenAI-compatible, custom base URL)
- [x] Implement `OpenRouterProvider` (OpenAI-compatible, custom base URL)
- [x] Add `provider` key to `config.json` model section
- [x] Add keyring-based API key storage (system keychain, never plaintext on disk)
- [x] Add provider selector UI in `app.py` sidebar
- [x] Show API key field for cloud providers (password input, keyring-backed)
- [x] Add `openai`, `anthropic`, and `keyring` to `requirements.txt`
- [!] **Cloud providers are untested** — API keys unavailable for testing. Disabled in UI via `_on_provider_switch()`. Only Ollama is selectable.

### 2.7 Model auto-detection
- [x] On provider change or startup, call `ollama.list()` to auto-populate model dropdown
- [x] If Ollama is unreachable, show red indicator and fall back to `config.json` model list
- [x] For OpenAI/Anthropic, show known model list from config (no auto-detect available)

---

## Layer 3: Staging & Review

### 3.1 Staging table search / filter
- [x] Above the `st.data_editor`, add a `st.text_input("Filter assets...")`
- [x] On every rerun, filter `staged_assets` by substring match against `original_name`, `staged_name`, `category`, or any tag
  - Case-insensitive, partial match
  - Show count: "Showing 5 of 12 assets"
- [x] Filter affects only the displayed table; all assets remain in `st.session_state.staged_assets`

### 3.2 Bulk category assignment
- [x] Add a row-level checkbox column to `st.data_editor` (exists) plus a "Select All" checkbox in the header
- [x] Below the table, add a `st.selectbox("Apply category to selected", CATEGORY_LIST)` + "Apply" button
- [x] On "Apply": iterate selected rows, update their `category` field, rebuild the DataFrame
- [x] Show confirmation: "Updated 5 assets to category 'aerial_drone'"

### 3.3 Staging table column sorting
- [x] Use Streamlit's native click-to-sort on `st.data_editor` column headers (replaces custom sort dropdown)
- [x] Removed redundant sort dropdown — `st.data_editor` in Streamlit 1.59.1 provides built-in column sorting

### 3.4 Export staging as CSV
- [x] Add `export_staging_csv()` and `export_staging_json()` to `engine.py`
- [x] Add "Download CSV" and "Download JSON" buttons below the staging data editor
- [x] CSV columns: `original_name, proposed_filename, category, tags, summary`

### 3.5 Import staging from CSV
- [x] Add `import_staging_csv()` to `engine.py` returning `(assets, warnings)`
- [x] Add collapsed expander with file uploader "Import staging CSV (overrides current)" below export buttons
- [x] Parse CSV columns, validate against category list, populate `st.session_state.staged_assets`
- [x] Show warnings for unknown categories (e.g., "unknown category 'xyz' → fallback to 'uncategorized'")

---

## Layer 4: File Commit & Metadata

### 4.1 Metadata-only mode (commit without rename)
- [x] Add a checkbox in the commit section: "Update metadata only (keep original filename)"
- [x] When checked, pass `skip_rename=True` to `execute_commit()`
- [x] In `engine.py` `execute_commit()`:
  - If `skip_rename`: skip `old_path.rename(new_path)`, use `old_path` as the target
  - Write all metadata tags to the file's current location
  - Return the original path instead of `new_path`
- [x] Update both `app.py` commit handler and `cli.py` commit path

### 4.2 Naming template system
- [x] Add `naming_templates` section to `config.json`:
  ```json
  "naming_templates": {
    "default": "{category}_{topic}_{description}",
    "short": "{topic}_{description}",
    "editorial": "{date}_{category}_{topic}"
  }
  ```
- [x] In `app.py`, add a `st.selectbox("Naming template", list(templates.keys()))` before analysis
- [x] Store selected template in `st.session_state.naming_template`
- [x] In `analyze_asset_with_ai()` or in a new `apply_naming_template()` function in `engine.py`:
  - Parse the AI response's `new_filename` into its semantic components
  - Rebuild the filename according to the selected template
  - Fall back to the AI's raw `new_filename` if template keys are missing

### 4.3 Dry-run commit preview
- [x] Add a "Preview Commit" button next to "Commit Selected"
- [x] When clicked: show a `st.dataframe` with columns: `Original Path`, `New Path`, `Category`, `Tags`, `Metadata Written`
  - Read all data from `staged_assets` and `st.session_state.output_dir`
  - Simulate the full commit path without actually writing files or metadata
- [x] Show a caption: "This is a preview. No files were modified."

### 4.4 Case style selection
- [x] Add `case_style` to `config.json` naming section: `"case_style": "snake_case"` with options: `snake_case`, `camelCase`, `kebab-case`, `pascal_case`, `lowercase`, `original`
- [x] In `app.py`, add the option inside a `st.expander("Advanced Features")` section before analysis
  - Note: consolidated into staging "Naming Settings" expander instead
- [x] In `engine.py`, create `apply_case_style(name, style)` function that transforms the staged filename
- [x] Apply case style in both `app.py` commit flow and `cli.py`

### 4.5 Max filename character limit
- [x] Add `max_filename_chars` to `config.json` naming section (default: 0 = no limit)
- [x] In `app.py`, add the option inside the Advanced Features expander
  - Note: consolidated into staging "Naming Settings" expander instead
- [x] In `engine.py`, create `truncate_filename(name, max_chars)` that truncates smartly (preserves category prefix)
- [x] Apply in both app and CLI

---

## Layer 5: Session Persistence & Recovery

### 5.1 Save session to disk
- [x] Create a `sessions/` directory (gitignored)
- [x] Add "Save Session" button in the Upload & Analyze tab
- [x] Serialize to JSON: `st.session_state.uploaded_files` (paths only, not buffers), `staged_assets`, `analysis_done`, `output_dir`
  - Do NOT serialize `base64_cache` (too large — re-extract on restore)
- [x] Write to `sessions/session_YYYY-MM-DD_HHmmss.json`
- [x] Log a `session_saved` event

### 5.2 Restore session from disk
- [x] Add a file uploader or dropdown in the Upload & Analyze tab: "Restore Session"
  - file uploader: load JSON file, parse, restore state
  - dropdown: list `sessions/*.json` files sorted by date
- [x] On restore:
  - Set `uploaded_files` from saved paths (validate files still exist on disk; warn if missing)
  - Set `staged_assets`, `analysis_done`, `output_dir`
  - Clear `base64_cache` (will be re-extracted on next analysis)
  - Set `analysis_in_progress = False`, `analysis_index = 0`
  - Show `st.success("Session restored from session_20260711_143022.json")`

### 5.3 Auto-save on browser close
- [x] Use Streamlit's `session_state` lifecycle — no reliable hook for browser close
- [x] Alternative: add an auto-save timer (every 60 seconds while `staged_assets` is non-empty)
  - `st_autorefresh` triggers a save function that writes session JSON
  - Only saves if `staged_assets` changed since last save (track via hash or counter)
  - Show a small indicator: "Auto-saved 30s ago"

---

## Layer 6: Configuration & Admin

### 6.1 Config editor tab (read-only view)
- [x] Add a third tab "Configuration" in `app.py`
- [x] Read `config.json`, display as formatted `st.json()` (read-only for v1)
- [x] Show validation: green border if JSON is valid, red if corrupted
- [x] Show a "Reload Config" button that re-calls `load_config()` and refreshes module-level globals
  - Note: this requires `importlib.reload()` or a config refresh mechanism in `engine.py`
  - Add `reload_config()` function that re-reads JSON and re-exports module globals

### 6.2 Config editor tab (editable)
- [x] Add an "Edit" toggle beside the JSON view
- [x] When toggled: replace `st.json()` with a `st.text_area()` pre-filled with formatted JSON
- [x] "Save" button validates JSON, writes to `config.json`, calls `reload_config()`
  - On invalid JSON: show error, do not write
  - On success: show `st.success("Config saved and reloaded")`
- [x] Warn user: "Some changes (model, categories) require re-running analysis to take effect"

### 6.3 Category management UI
- [x] In the Configuration tab, add a "Categories" section
- [x] Show current categories as a list of `st.text_input()` widgets (one per category)
- [x] "Add Category" button appends a new empty input
- [x] "Delete" button per row removes that category
- [x] "Save Categories" button: validate no duplicates, no empty strings, write to `config.json`, call `reload_config()`
- [x] Show count: "40 categories configured"

### 6.4 Extension management UI
- [x] In Configuration tab, add "Supported Extensions" section
- [x] Two `st.multiselect()` widgets: Video Extensions, Image Extensions
  - Pre-populated with current values from config
  - Options: all common extensions + custom text entry
- [x] "Save" button writes to `config.json`, calls `reload_config()`

---

## Layer 7: Analytics & Logging Enhancements

### 7.1 Per-asset commit timeline
- [x] In the Analytics Dashboard tab, add a sub-section "Commit History"
- [x] Read `logs/commits_*.jsonl` files, parse into DataFrame
- [x] Display as `st.dataframe` with columns: Commit Time, Original Name, New Name, Category, Tags
- [x] Add filters: date range (date input), category (multi-select)

### 7.2 Analytics export
- [x] Add "Export as CSV" button below the event timeline
- [x] Build CSV from the currently filtered `timeline_df`, use `st.download_button()`
- [x] Add "Export as JSON" button for the same data
- [x] Add a "Print Report" button that opens a print-friendly view (use `st.markdown()` with a print stylesheet)

### 7.3 Storage usage tracking
- [x] In analytics, add a "Storage" metric card
- [x] Sum file sizes of all committed files (read from commit log or `os.path.getsize()` on committed paths)
- [x] Show human-readable format: "2.4 GB total renamed"
- [x] Add a trend line if historical data is available (daily cumulative storage)

### 7.4 Error rate chart
- [x] Add a line chart to analytics showing error rate over time
  - X-axis: date, Y-axis: error rate (errors / total events) as percentage
- [x] Use a rolling 7-day window if enough data exists
- [x] If daily data is sparse, show raw counts instead of rates

---

## Layer 8: CLI Improvements

### 8.1 Dry-run flag
- [x] Add `--dry-run` flag to `cli.py`
- [x] When set: simulate all commits (print what WOULD happen), write nothing to disk, open no ExifTool session
- [x] Print summary: "Dry-run complete. 12 assets would be renamed. 0 conflicts."

### 8.2 Non-interactive mode
- [x] Add `--non-interactive` / `-y` flag: skip all interactive prompts, use AI suggestions as-is
- [x] Add `--categories-override FILE` flag: load a JSON file mapping asset names to forced categories
- [x] Add `--output FILE` flag: write commit summary to a text or JSON file instead of stdout

### 8.3 Progress bar for CLI
- [x] Replace simple text counters with `rich.progress` or `tqdm` progress bars
  - Phase 1 extraction: per-file progress with filename
  - Phase 2 analysis: per-asset progress with filename and current model
  - Commit phase: per-file progress with destination path
- [x] Add `--no-progress` flag to disable progress bars (for pipe-friendly output)
- [x] Add `rich` to `requirements.txt`

### 8.4 Include subdirectories flag
- [x] Add `--include-subdirectories` / `-r` flag to `cli.py`
- [x] When set, use `target_dir.rglob("*")` instead of `target_dir.iterdir()`
- [x] Maintain the same extension filtering
- [x] Log scanned subdirectory count in `session_start` event: `"subdirs_scanned": N`

---

## Layer 9: Infrastructure & DevOps

### 9.1 Dockerfile
- [x] Create `Dockerfile` with:
  - Base image: `python:3.11-slim`
  - Install system deps: `exiftool`, `ffmpeg`, `curl`
  - Install Python deps from `requirements.txt`
  - Copy app source
  - Expose port 8501
  - Entrypoint: `streamlit run app.py --server.port=8501 --server.address=0.0.0.0`
- [x] Create `docker-compose.yml` with two services:
  - `ollama`: image `ollama/ollama`, volumes for model storage, GPU passthrough
  - `renamer`: build from Dockerfile, depends on ollama, port 8501
- [x] Add a note in `README.md`: "Run `docker compose up` for a fully containerized setup"

### 9.2 Startup validation
- [x] Create `validate_env()` function in `engine.py`:
  - Check `exiftool` is in PATH (run `exiftool -ver`)
  - Check `ffmpeg` is in PATH (run `ffmpeg -version`), detect version
  - Check `ffprobe` is in PATH (run `ffprobe -version`)
  - Check Ollama connectivity (`ollama.list()`)
  - Return dict: `{exiftool: bool, exiftool_version: str, ffmpeg: bool, ffmpeg_version: str, ollama: bool, ollama_models: list}`
- [x] In `app.py`, show validation results as expandable "Environment Check" section in sidebar or config tab
  - Green checkmark / red X per dependency
  - Tooltip with version on hover
- [x] In `cli.py`, run validation at startup, print warnings for missing deps, exit with error code if critical deps are missing

### 9.3 `.gitignore` update
- [x] Add to `.gitignore`:
  ```
  sessions/
  logs/
  __pycache__/
  *.pyc
  .streamlit/
  ```

### 9.4 Streamlit config
- [x] Create `.streamlit/config.toml`:
  ```toml
  [server]
  maxUploadSize = 10000  # 10 GB
  [theme]
  base = "dark"
  primaryColor = "#3b82f6"
  ```
- [x] Create `.streamlit/secrets.toml` (optional, placeholder only — no secrets used yet)

---

## Layer 10: Quality of Life

### 10.1 Dark mode toggle
- [x] Add a sidebar `st.toggle("Dark Mode")` in `app.py`
- [x] Store preference in `st.session_state.dark_mode`
- [x] On toggle: inject custom CSS via `st.markdown()` that overrides Streamlit's theme
  - Alternative: let Streamlit's built-in theme handle it (set `base = "dark"` in config, offer "Light" as opt-out)
- [x] Persist preference across reruns (already handled by session state)

### 10.2 Keyboard shortcuts
- [x] Add JavaScript injection via `st.markdown()` for keyboard shortcuts:
  - `Ctrl+Enter`: Trigger "Run AI Analysis" (click the button via JS)
  - `Ctrl+Shift+C`: Trigger "Commit Selected"
  - `Escape`: Stop Analysis
- [x] These work only when the corresponding button is visible (check via Streamlit's rendered DOM)

### 10.3 Notification on commit complete
- [x] After commit in `app.py`, play a short audio notification
  - Use a base64-encoded WAV beep (tiny file, inline in Python)
  - Play via `st.audio()` with `autoplay=True`
- [x] Only play if the browser tab is visible (no reliable way to detect this in Streamlit — always play)
- [x] Option to disable in sidebar: "🔔 Play sound on commit complete"

### 10.4 Batch size warning
- [x] Before Phase 1 extraction, check `len(uploaded_files)`
- [x] If > 50 files: show `st.warning("Large batch detected (N files). Extraction may take several minutes.")` with a "Continue / Cancel" confirmation
- [x] If > 200 files: show stronger warning + recommend CLI for better throughput
- [x] Thresholds in `config.json`: `batch_warn_threshold: 50`, `batch_recommend_cli: 200`

### 10.5 Footer attribution
- [x] Add a `st.markdown()` footer at the bottom of `app.py`:
  - "Made with love from Tanzania by Abdul Musawwir"
  - Link to GitHub repo: `https://github.com/Abdulmusawwir/ai-media-renamer`
- [x] Use `st.html()` or `st.markdown()` with `unsafe_allow_html=True` for the hyperlink
- [x] Style subtly — small text, muted color, positioned below all tabs

### 10.6 Jargon-free UI text
- [x] Replace all technical/internal status messages in `app.py` with user-friendly alternatives:
  - `"Checking caches and extracting grids into RAM"` → `"Extracting preview frames from videos and images"`
  - `"Injecting RAM streams directly into AI Vision Model"` → `"Analyzing content with AI model"`
  - `"Piping ExifTool commands into metadata containers"` → `"Writing metadata tags to files"`
  - `"Phase 1: Extracting previews into memory..."` → `"Step 1: Preparing previews..."`
  - `"Phase 2: Sequential AI Processing"` → `"Step 2: Analyzing content..."`
- [x] Replace corresponding messages in `cli.py`
- [x] Remove "fast-seeking" and "storyboard grid" references from user-facing text
- [x] Keep technical details in JSONL logs and `--verbose` CLI output only

### 10.7 Dismissible commit summary
- [x] Replace the persistent `st.session_state.commit_message` approach with `st.toast()` or `st.success()` with a close button
- [x] Show a non-blocking summary: "12 assets committed to Desktop/RenamedMedia. 0 failed."
- [x] Auto-dismiss after 8 seconds or on next user interaction
- [x] Keep the detailed log accessible in the Analytics Dashboard tab

### 10.8 Advanced Features expander
- [x] Add a `st.expander("Advanced Features")` in the Upload & Analyze tab, positioned before the analysis trigger
- [x] Group inside: case style selector, max filename chars, custom prompt text area (also linked to profile selection)
- [x] Collapsed by default — clean default experience for most users

---

## Layer 11: Testing & Reliability

### 11.1 Unit tests for engine.py
- [x] Create `tests/` directory
- [x] Write `tests/test_config.py`:
  - `test_load_config_returns_dict`
  - `test_load_config_raises_on_missing_file`
  - `test_video_extensions_are_tuple`
  - `test_allowed_categories_are_tuple`
- [x] Write `tests/test_validation.py`:
  - `test_validate_category_valid`
  - `test_validate_category_invalid_returns_uncategorized`
  - `test_validate_category_empty_returns_uncategorized`
  - `test_sanitize_name_removes_special_chars`
  - `test_sanitize_name_lowercases`
  - `test_sanitize_name_adds_default_suffix_if_too_short`
- [x] Write `tests/test_parse_ai_response.py`:
  - `test_parse_valid_json`
  - `test_parse_codeblock_json`
  - `test_parse_empty_response`
  - `test_parse_malformed_json`

### 11.2 Integration tests
- [x] Write `tests/test_extraction.py` (skipped if ffmpeg not available):
  - Create a tiny synthetic test video (1 second, black frame) via ffmpeg
  - `test_process_video_to_base64_returns_string`
  - `test_process_image_to_base64_returns_string`
- [x] Write `tests/test_commit.py` (skipped if exiftool not available):
  - Create temp dir with test file
  - Run `execute_commit()` with known values
  - Verify file was renamed
  - Verify metadata was written using exiftool session

### 11.3 Test runner config
- [x] Add `pytest` and `pytest-cov` to `requirements.txt`
- [x] Create `pyproject.toml` with pytest config:
  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  markers = ["slow: marks tests as slow (deselect with '-m \"not slow\"')"]
  ```
- [x] Add `test` command to AGENTS.md

---

## Layer 12: Desktop Bundling & Bootstrap Lifecycle (Phase S)

### S.1 Bootstrap 4-Stage Checklist
- [x] Create `check_environment()` in `engine.py` returning structured status dict:
  - `ffmpeg`: bool — check via `_resolve_binary_path("ffmpeg")`
  - `exiftool`: bool — check via `_resolve_binary_path("exiftool")`
  - `ollama_running`: bool — probe `http://localhost:11434/api/tags`
  - `model_available`: bool — parse `/api/tags` for `qwen2.5vl:7b`
  - `cloud_configured`: bool — check config or session state for valid Gemini Flash API key
- [x] Create `_resolve_binary_path(name)` in `engine.py`:
  - Check `sys._MEIPASS / "bin" / name` first (PyInstaller bundled path)
  - Fall back to `shutil.which(name)`
  - Return full path string or `None`
- [x] Create dedicated bootstrap panel in `app.py` that runs `check_environment()` at startup
- [x] Smart routing: if Ollama/model missing but `cloud_configured=True`, show: *"Status: Local engine missing. Routing execution to pre-configured Cloud API."* — bypass download
- [x] If both missing: show interactive local downloader UI (see S.2)
- [x] Store results in `st.session_state.env_check` to avoid re-running on every rerun

### S.2 Interactive Model Download
- [x] Create `stream_model_download(model_name="qwen2.5vl:7b")` generator in `engine.py`:
  - POST `http://localhost:11434/api/pull` with `stream=True`
  - Read JSON chunk stream: yield `{"status": "progress", "completed": int, "total": int, "percentage": float}`
  - On completion: yield `{"status": "success"}`
  - On error: yield `{"status": "error", "message": str}`
- [x] In `app.py` bootstrap panel: iterate generator inside a loop, update `st.progress()` and status text:
  - `f"Downloading Qwen2.5-VL: {completed_gb:.1f}GB / {total_gb:.1f}GB ({percentage:.0f}%)"`
- [x] On success: re-run `check_environment()` to confirm model is now available
- [x] On error: show error message with retry button

### S.3 Hybrid AI Switching
- [x] Create `switch_ai_provider(new_provider, api_key=None)` in `engine.py`:
  - `new_provider`: `"ollama"` | `"gemini"` | `"openai"` | `"anthropic"`
  - **Local → Cloud**: call `ollama.generate(keep_alive=0)` to drop model weights from RAM/VRAM immediately; swap config to cloud provider
  - **Cloud → Local**: re-trigger `check_environment()`; if Ollama/model missing, block pipeline and show `[Initialize Local AI Engine]` button (fires S.2)
  - Update module-level constants (`MODEL_NAME`, provider function pointers)
- [x] In `app.py` settings panel: add provider selector (radio or dropdown) with conditional API key field (password input)
- [x] `[Initialize Local AI Engine]` button appears when cloud→local switch fails due to missing model
- [x] Log provider switches via `log_event()` with event type `"provider_switch"`

### S.4 Storage Lifecycle Utility
- [x] Create `wipe_local_model(model_name="qwen2.5vl:7b")` in `engine.py`:
  - Call `DELETE http://localhost:11434/api/delete` with model name payload
  - Return `{"ok": bool, "message": str}`
- [x] In `app.py` Configuration view: add `[Wipe Local Model Cache]` button
- [x] Guard: show `st.warning("This will permanently delete the ~5GB Qwen2.5-VL model. Re-download required to use local mode.")` + confirmation checkbox
- [x] On success: re-run `check_environment()` to reflect removal
- [x] Log via `log_event()` with event type `"model_wipe"`

### S.5 PyInstaller Distribution Setup
- [x] Create `_resolve_binary_path()` as described in S.1 (single function used by all binary calls)
- [x] Update `detect_hw_accel()` in `engine.py` to use `_resolve_binary_path("ffmpeg")` instead of bare `ffmpeg` command
- [x] Update `process_video_to_base64()` and `process_image_to_base64()` to use resolved ffmpeg/ffprobe paths
- [x] Update `ExifToolSession.__init__()` to use `_resolve_binary_path("exiftool")`
- [x] Create `hooks/hook-ollama.py` for PyInstaller to include ollama client library
- [x] Add `pyinstaller` to `requirements.txt`
- [x] Create `build.spec` with proper binary collection rules (FFmpeg, ExifTool, model data, static assets)

## Layer 13: Duplicate Detection & User Ratings

### 13.1 Perceptual duplicate detection
- [x] Add `imagehash` to `requirements.txt` for perceptual hashing
- [x] In `engine.py`, create `compute_asset_hash(file_path)` function:
  - For images: compute pHash via `imagehash.phash()`
  - For videos: extract middle frame via FFmpeg, then pHash that frame
- [x] In `app.py`, add a "Detect Duplicates" button above the staging matrix
- [x] On click: compute hashes for all staged assets, compare pairwise, assign confidence scores (0-100%)
- [x] Add a duplicate pairs expander showing File A, File B, Similarity %, Distance
- [x] `find_duplicates(staged_assets, threshold=10)` returns list of duplicate pairs with confidence

### 13.2 User rating / feedback on AI suggestions
- [x] Add a rating column to the staging table: thumbs up / thumbs down per asset
- [x] Store ratings in session state alongside staged_assets
- [x] On commit, log ratings: `"rating": "thumbs_up" | "thumbs_down"` in `file_committed` event
- [x] Track `ai_rating` event to telemetry (if opted in) with profile, model, provider

---

## Layer 14: UI/UX Responsiveness & Performance

### 14.1 Streamlit caching (Critical)
- [x] Add `@st.cache_data(ttl=10)` to `load_log_entries()` in `app.py` to avoid re-parsing JSONL on every rerun
- [x] Cache Plotly figure construction (category pie, daily bar, error rate line) with `@st.cache_data`
- [x] Cache `check_environment()` result with `@st.cache_resource` (env doesn't change mid-session)
- [x] Cache `check_ollama_health()` with `@st.cache_data(ttl=30)` to avoid hammering Ollama API
- [x] Move `base64.b64decode(_COMMIT_BEEP)` into `@st.cache_data` so it decodes once, not per-rerun

### 14.2 Reduce unnecessary reruns (Critical)
- [x] Use `st.fragment()` (Streamlit >=1.37) to isolate the per-asset analysis progress indicator — prevents full-page rerun between each AI call
- [x] Guard sidebar rendering: skip sidebar health/model/profile checks when `analysis_in_progress=True` (sidebar doesn't change during analysis)
- [x] Remove redundant `save_config()` calls in `_on_model_change()` — only save when user explicitly changes model, not on initial widget render
- [x] Remove the `if "profile_selector" not in st.session_state` guard (line 728) — use `index=` parameter directly to avoid double evaluation

### 14.3 FFmpeg / subprocess optimization (Important)
- [x] Merge `get_video_duration()` call into `process_video_to_base64()` — extract duration from FFmpeg metadata stream instead of separate ffprobe subprocess
- [x] Use `subprocess.Popen` with persistent pipe for ExifTool sessions instead of repeated `subprocess.run` calls (already done for ExifToolSession, verify no bare `subprocess.run` for exiftool remains)
- [x] Add `ffprobe` path resolution to `_resolve_binary_path()` (already done, verify it's used everywhere)

### 14.4 Loading states & feedback (Important)
- [x] Replace `st.caption("N assets ready for review")` with `st.status()` container for visual weight
- [x] Add `st.spinner("Preparing extraction...")` before Phase 1 rerun to give immediate feedback
- [x] Add `st.toast("Applied category to N assets")` confirmation after bulk category apply
- [x] Replace `st.info("No log entries found...")` with empty-state illustration or inline prompt

### 14.5 Staging table responsiveness (Important)
- [x] Add `st.column_config.Column(width="small")` on Summary and Tags columns to prevent horizontal overflow
- [x] Add CSS `overflow-x: auto` on the data editor container for mobile viewports
- [x] Use `max-width: 100vw` on column containers to prevent page-level horizontal scroll

### 14.6 Keyboard shortcuts (Nice-to-have)
- [x] Inject JavaScript via `st.markdown(unsafe_allow_html=True)` for keyboard shortcuts:
  - `Ctrl+Enter`: trigger "Run AI Analysis" button click
  - `Ctrl+Shift+C`: trigger "Commit Selected" button click
  - `Escape`: set `analysis_aborted=True` to stop analysis loop
- [x] Add `tabindex` attributes to key buttons for keyboard focus

### 14.7 Config tab UX polish (Nice-to-have)
- [x] Collapse read-only `st.json(config)` inside an `st.expander("Config Preview", expanded=False)` to reduce visual clutter
- [x] Add syntax highlighting to the config editor text area
- [x] Show a green/red badge next to "Configuration" tab title indicating config health (valid JSON = green, invalid = red)

### 14.8 Model download UX (Nice-to-have)
- [x] Show download progress in a `st.status()` container with expand/collapse instead of flat progress bar
- [x] Add estimated time remaining based on download speed
- [x] Improve cancel button tooltip: "Cancels UI polling — Ollama download continues in background"

---

## Layer 15: Privacy-First Telemetry

### 15.1 PostHog integration
- [x] Add `posthog>=3.0.0` to `requirements.txt`
- [x] In `engine.py`, create telemetry module: `POSTHOG_API_KEY`, `POSTHOG_HOST`, `TELEMETRY_FILE`
- [x] Create `track_event(event_name, properties)` — appends to local JSONL
- [x] Create `flush_telemetry()` — sends batch to PostHog via SDK, clears local buffer
- [x] Create `_get_install_id()` — random UUID per install, stored in `%APPDATA%/ai-media-renamer/.install_id`
- [x] Create `_get_session_id()` — fresh UUID per app launch

### 15.2 Opt-in dialog (first launch)
- [x] In `app.py`, show privacy dialog on first launch before any tabs render
- [x] Two-column layout: "What's collected" vs "What's NOT collected"
- [x] Checkbox: "Send anonymous usage data" (default: ON)
- [x] Link to PRIVACY.md in GitHub repo
- [x] "Save Preference" button persists to `config.json` telemetry section

### 15.3 Settings toggle
- [x] In Configuration tab, add "Telemetry" section with toggle
- [x] Toggle persists to `config.json` via `set_telemetry_enabled()`
- [x] On disable: sends `opt_out` event, then stops all telemetry
- [x] On enable: sends `opt_in` event

### 15.4 Event tracking
- [x] Track `ai_rating` on commit (outcome, profile, model, provider)
- [x] Track `session_complete` on commit (files_analyzed, files_committed, profile, case_style)
- [x] Track `opt_in` / `opt_out` on preference change
- [x] All events include: install_id, session_id, app_version, os, arch

### 15.5 Privacy documentation
- [x] Create `PRIVACY.md` — dedicated privacy doc with data tables, processing details, opt-out instructions
- [x] Update `README.md` — add "Telemetry" section with 2-sentence summary + link to PRIVACY.md
- [x] Update `.gitignore` — add `telemetry.jsonl`, `.pytest_cache/`, `.ruff_cache/`, `cache/`, `*.log`, `.env`

---

## Layer 16: Document Pipeline Hardening

> Addresses real-world testing failures: RTF categorised as `text_overlays`, MD as `presentation_slides`, PDF as `motion_graphics`. Documents silently skipped by duplicate detection. Metadata-only mode partially broken for non-PDF documents.

### 16.1 Fix document categorization prompt
- [x] In `config.json`, update all prompt profiles that include document categories to explicitly constrain output:
  - Append: `"ONLY use categories from this list: {allowed_categories}. NEVER invent new categories."`
  - Replace generic `"Pick ONE category from the allowed list"` with profile-specific constraint
- [x] In `engine.py`, modify `get_active_prompt()` to inject `allowed_categories` into the prompt string before sending to AI
  - [x] Test: upload RTF, MD, PDF files and verify they categorize as `documents`, `reports`, `contracts`, `invoices`, or `manuals` (not `text_overlays`, `presentation_slides`, `motion_graphics`)

### 16.2 Content-based hash for documents
- [x] In `engine.py`, update `compute_asset_hash()` to handle documents:
  - For PDF/DOCX/XLSX/PPTX: compute SHA-256 of file bytes
  - For text files under 1MB: use extracted text hash (from `extract_text_from_file()`) for finer-grained dedup
- [x] Verify `find_duplicates()` now includes document assets in pairwise comparison
- [x] Add `hashlib` import (stdlib, no new dependency)

### 16.3 Per-format metadata writing
- [x] In `engine.py`, update `execute_commit()` to handle document metadata per format:
  - PDF: ExifTool with Windows EXIF fields (`EXIF:XPTitle`, `EXIF:XPKeywords`) — already works
  - DOCX: Use `python-docx` to write custom properties (`core_properties.title`, `core_properties.keywords`) — add `from docx import Document` import
  - XLSX: Use `openpyxl` to write custom properties — add `from openpyxl import load_workbook` import
  - TXT/MD/RTF: Skip metadata writing, log `metadata_skipped` with reason "no_standard_metadata_format", show `st.info()` in UI
- [x] Add `skip_metadata=False` parameter to `execute_commit()` alongside existing `skip_rename=False`

### 16.4 Suppress FontBBox pdfminer warning
- [x] In `engine.py`, at the top of `extract_text_pdf()`, add:
  ```python
  logging.getLogger("pdfminer").setLevel(logging.ERROR)
  ```
- [x] This suppresses the harmless `FontBBox` warning from pdfminer.six without affecting extraction

---

## Layer 17: Model Selection & First-Time UX

> First-time EXE user sees "Download Qwen2.5-VL Model" with no comparison. Bootstrap hardcodes `qwen2.5vl:7b`. No way to pick a lighter model for low-VRAM machines.

### 17.1 Model selection wizard
- [x] In `bootstrap.py`, after Ollama service starts (Step 3) and before model download (Step 4), add a tkinter dialog:
  - Title: "Select AI Model"
  - Radio buttons for available models with size + quality descriptions:
    - `qwen2.5vl:3b` — 3.2 GB, Good quality, Fast
    - `qwen2.5vl:7b` — 6.0 GB, Best quality, Recommended
    - `qwen3-vl:4b` — ~3 GB, Newer architecture, Good quality
    - `moondream:latest` — 1.8 GB, Basic quality, Very fast
  - "Recommended" badge next to 7B option
  - Default selection: `qwen2.5vl:7b`
  - Store chosen model name in `st.session_state` (or pass as env var to Streamlit child)
- [x] Alternative (if tkinter dialog is too complex): Show model selection in Streamlit UI as a full-page interstitial before the main app loads, when no vision model is detected

### 17.2 Bootstrap downloads chosen model
- [x] In `bootstrap.py`, update Step 4 to use the selected model name instead of hardcoded `"qwen2.5vl:7b"`
- [x] Pass chosen model name to `_stream_model_with_progress()` via the variable from 17.1
- [x] Update `_vision_model_installed()` to check for ANY vision model (already does via `_is_vision_model()`)

### 17.3 Model detection recognizes all supported models
- [x] In `engine.py`, update `check_environment()` to return list of ALL installed vision models (not just check for one)
- [x] In `app.py`, update sidebar model indicator to show count of installed vision models and their names
- [x] Ensure `VISION_MODEL_PREFIXES` list is complete (currently: `qwen2.5vl`, `qwen2-vl`, `llava`, `bakllava`, `moondream`, `xclip`, `qwen3-vl`)
- [x] Update `config.json` `allowed_models` if any new models are added

---

## Layer 18: Safety & Trust

> From Gemini v2.0 analysis: "#1 Reddit/GitHub concern: What if the AI messes up?" Undo/rollback and structured outputs address this directly.

### 18.1 Undo/rollback engine
- [x] In `engine.py`, create `log_commit_batch(batch_data)` that writes to `undo_log.jsonl`:
  - Per asset: `{original_path, new_path, original_metadata, timestamp, batch_id}`
  - Store in `%APPDATA%/ai-media-renamer/undo_log.jsonl`
- [x] In `engine.py`, create `rollback_last_batch()`:
  - Read last `batch_id` from `undo_log.jsonl`
  - Verify all destination paths exist before starting rollback
  - Move files back to original paths via `shutil.move()`
  - Remove metadata injected by the commit (restore original metadata from log)
  - Return `{success: bool, restored: int, failed: int, errors: list}`
- [x] In `cli.py`, add `--rollback` flag:
  - Calls `rollback_last_batch()`, prints result summary
  - Mutually exclusive with normal pipeline
- [x] In `app.py`, add "Undo Last Commit" button in Analytics tab:
  - Shows confirmation dialog with batch summary (N files, timestamp)
  - Calls `rollback_last_batch()` on confirm
  - Shows success/failure toast

### 18.2 Pydantic structured outputs
- [x] Add `pydantic>=2.0.0` to `requirements.txt`
- [x] In `engine.py`, define `AssetAnalysisResponse` Pydantic model:
  ```python
  class AssetAnalysisResponse(BaseModel):
      filename: str
      category: str
      description: str
      tags: list[str]
      confidence: float
  ```
- [x] Update `parse_ai_response()` to use Pydantic validation:
  - Try `AssetAnalysisResponse.model_validate_json(response_text)`
  - On `ValidationError`: attempt regex extraction of JSON block, retry Pydantic validation
  - On second failure: return fallback `{filename: original_name, category: "uncategorized", ...}`
- [x] For cloud providers (OpenAI, Gemini, Groq): pass `response_format={"type": "json_schema", "json_schema": AssetAnalysisResponse}` when supported
- [x] Add retry logic: max 2 retries on malformed response before fallback

### 18.3 ExifTool batching
- [x] In `engine.py`, update `execute_commit()` to batch metadata writes:
  - Collect all metadata dicts into a single JSON file
  - Run `exiftool -json=metadata_batch.json -overwrite_original <all_files>` once
  - Fall back to per-file mode if batch fails
- [x] This reduces IPC overhead from ~200ms × N files to ~200ms total for metadata writing
- [x] Keep per-file mode as fallback for edge cases (mixed formats, partial failures)

---

## Layer 19: Audio & Extended Media

> Privacy-first audio support. Users on Reddit/GitHub value local processing. `faster-whisper` runs locally via CTranslate2, no cloud dependency.

### 19.1 faster-whisper integration
- [x] Add `faster-whisper>=1.0.0` to `requirements.txt`
- [x] In `engine.py`, create `transcribe_audio(audio_path, model_size="base")`:
  - Use `faster_whisper.WhisperModel(model_size)` (lazy-loaded, cached via `@functools.lru_cache`)
  - Model sizes: `tiny` (39MB), `base` (74MB), `small` (244MB), `medium` (769MB), `large-v3` (1.5GB)
  - Return `{text: str, language: str, duration: float}`
  - Handle errors gracefully: return `{text: "", error: str}`
- [x] Add model download on first use (faster-whisper auto-downloads to `~/.cache/huggingface`)

### 19.2 Audio extraction from video
- [x] In `engine.py`, create `extract_audio_from_video(video_path)`:
  - Use FFmpeg to extract audio track: `ffmpeg -i video.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 audio.wav`
  - Output to temp file, return path
  - If no audio track: return `None` with log
- [x] In `engine.py`, update `process_video_to_base64()` to also extract audio (or do it separately in analysis phase)

### 19.3 Audio transcription → text analysis pipeline
- [x] In `engine.py`, update `analyze_asset_with_ai()` flow:
  - After frame extraction, check if video has audio track (via FFprobe)
  - If audio exists: extract → transcribe → append transcription to AI prompt context
  - Update prompt: `"Audio transcription (if available): {transcription}\n\nAnalyze the visual content..."`
- [x] Store transcription in staged assets: `{audio_transcription: str}`
- [x] In `app.py`, show audio transcription preview in staging table Summary column (if available)

---

## Layer 20: Security Checkup & Enhancements

> Requested add-on: full security audit of the shipped app (EXE, web UI, CLI). Every item below is unstarted — plan only.

### 20.1 Dependency & supply-chain audit
- [ ] Run `pip-audit` (or OSV-scanner) against `requirements.txt`; fix or document every reported CVE
- [ ] Freeze exact versions into `requirements.lock` (`pip freeze`) so builds are reproducible and auditable
- [ ] Bootstrap binary downloads (ffmpeg, exiftool, model files): enforce HTTPS-only and verify a published SHA-256 checksum before use — reject mismatches instead of proceeding

### 20.2 Secrets management hardening
- [ ] Audit every log/event/error path: API keys must never reach `config.json`, JSONL logs, telemetry events, or exception messages — add redaction in `log_event()` and `track_event()`
- [ ] Keyring fallback: if the OS keychain is unavailable, fail closed (no plaintext file fallback) and surface a clear warning in UI
- [ ] Mask secret-looking keys (`api_key`, `token`, `password`, `*secret*`) in the Configuration tab JSON view / editor

### 20.3 Local server exposure
- [ ] Desktop EXE must bind Streamlit to `127.0.0.1` by default (never `0.0.0.0`); add a config flag to opt into LAN exposure with an in-UI warning
- [ ] Docker compose: keep `renamer` and `ollama` off exposed host ports unless explicitly requested; document the unauth exposure risk

### 20.4 Input validation & injection
- [ ] Audit all `st.markdown(unsafe_allow_html=True)` call sites — confirm no user-controlled strings (filenames, AI summaries, tags, profile prompts) can reach HTML; sanitize or render as text
- [ ] CSV import: neutralize spreadsheet formula injection (cells starting `=`, `+`, `-`, `@`) and validate imported paths/filenames before use
- [ ] Session restore: schema-validate loaded JSON, reject paths outside expected roots, never follow symlinks
- [ ] Add a test asserting staged filenames can never traverse directories on commit (sanitization already exists — lock it in)

### 20.5 Telemetry & log privacy
- [ ] Confirm telemetry events carry only counts/profiles/versions — never absolute paths, filenames, or AI text; add a redaction pass in `track_event()`
- [ ] Purge `telemetry.jsonl` on opt-out
- [ ] Logs store absolute paths: add a `redact_paths` flag (default on for non-verbose) and document log retention for `undo_log.jsonl`

---

## Execution Order (Recommended)

The phases are ordered by dependency — each phase can be worked on independently but earlier phases unblock later ones.

```
Phase A: 1.1, 9.3, 9.4          → Foundation (progress UI, gitignore, streamlit config) — DONE
Phase B: 2.3, 9.2, 11.1          → Health checks + unit tests (confidence layer) — DONE
Phase C: 1.2, 1.4, 1.3          → Upload hardening — DONE
Phase D: 3.1, 3.2, 3.3          → Staging UX improvements — DONE (sort via native click-to-sort)
Phase E: 4.1, 4.4               → Commit flexibility (metadata-only + dry-run) — DONE (dry-run both CLI + app; naming controls in staging)
Phase F: 5.1, 5.2, 5.3         → Session persistence + recovery — DONE
Phase G: 2.1, 2.2, 2.4          → Analysis flexibility (re-analyze, model select, workers) — DONE
Phase H: 6.1, 6.2, 6.3, 6.4    → Configuration UI — DONE
Phase I: 7.1, 7.2, 7.3, 7.4    → Analytics enhancements — DONE
Phase J: 8.1, 8.2, 8.3         → CLI improvements — DONE (dry-run + export/import CSV; interactive mode enhanced)
Phase K: 9.1, 11.2, 11.3       → Docker + integration tests — DONE (Dockerfile, docker-compose, test_extraction/test_commit)
Phase L: 10.1, 10.2, 10.3, 10.4 → Quality of life (core) — DONE (dark mode skip; keyboard skip; sound done; batch warning done)
Phase M: 3.4, 3.5               → CSV import/export — DONE
Phase N: 4.2                    → Naming templates — DONE (full template system with case style + max chars in staging expander)
Phase O: 10.5, 10.6, 10.7       → Quality of life (polish) — DONE
Phase P: 4.4, 4.5, 10.8         → Advanced Features expander + naming controls — DONE (consolidated into staging Naming Settings)
Phase Q: 2.5                    → Multi-profile AI prompts — DONE
Phase R: 2.6, 2.7               → Multi-provider + model auto-detect — DONE (providers implemented, cloud disabled in UI)
Phase S: S.1–S.5                → Desktop Bundling & Bootstrap Lifecycle Setup — DONE
Phase T: 8.4                    → CLI subdirectories — DONE
Phase U: 13.1, 13.2             → Duplicate detection + feedback — DONE
Phase V: Support                 → Donation / sponsorship links — DEFERRED (no links yet)
Phase W: 14.1, 14.2             → Caching + rerun optimization (Critical performance) — DONE
Phase X: 14.3, 14.4, 14.5       → FFmpeg optimization + loading states + responsive table — DONE
Phase Y: 14.6, 14.7, 14.8       → Keyboard shortcuts + config polish + download UX — DONE
Phase Z: 15.1–15.5              → Privacy-first telemetry (PostHog, opt-in, PRIVACY.md) — DONE
Phase AA: 16.1, 16.4            → Document categorization fix + FontBBox suppression (Critical bugs) — v1.5.0
Phase AB: 17.1, 17.2, 17.3      → Model selection wizard + bootstrap + detection — v1.5.0
Phase AC: 16.2                   → Document duplicate detection — v1.5.0
Phase AD: 18.1                   → Undo/rollback engine — v1.5.0
Phase AE: 18.2                   → Pydantic structured outputs — v1.5.0
Phase AF: 16.3                   → Per-format document metadata — v1.5.0
Phase AG: 18.3                   → ExifTool batching — v1.5.0
Phase AH: 19.1, 19.2, 19.3      → Audio transcription pipeline — v1.5.0
Phase AI: 20.1–20.5             → Security checkup & enhancements — PENDING (only remaining work)
```

> **v1.6.1 (2026-08-08)** — shipped separately ahead of Phase AI as a release-hardening pass: honest model install status (no config-catalog fallback in `available_models()`), wizard use-case/plan dialogs made resizable + scrollable so footer buttons are always reachable, in-app "open setup wizard" CTA when dependencies are missing, `[client] toolbarMode = "minimal"` to kill the Streamlit chrome flash, and a llama.cpp runtime fallback (`LlamaCppProvider`, auto-detected `llamacpp_running`). See CHANGELOG v1.6.1 and audit.md §1.
