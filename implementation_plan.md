# Implementation Plan — AI Media Renamer

> **Status:** MVP is complete (all items checked in `prd.md`). This plan covers the v1.1 / v2 milestone backlog, organized by technical layer. Each checkbox is a discrete, executable unit of work.

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
- [ ] On provider change or startup, call `ollama.list()` to auto-populate model dropdown
- [ ] If Ollama is unreachable, show red indicator and fall back to `config.json` model list
- [ ] For OpenAI/Anthropic, show known model list from config (no auto-detect available)

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
- [x] Add sort dropdown (Original Name, Proposed Filename, Category, Summary) + Asc/Desc toggle above the table
- [x] Implement server-side sorting: sort `staged_view` in-place by selected key and direction before rendering the data editor

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
- [ ] Add a checkbox in the commit section: "Update metadata only (keep original filename)"
- [ ] When checked, pass `skip_rename=True` to `execute_commit()`
- [ ] In `engine.py` `execute_commit()`:
  - If `skip_rename`: skip `old_path.rename(new_path)`, use `old_path` as the target
  - Write all metadata tags to the file's current location
  - Return the original path instead of `new_path`
- [ ] Update both `app.py` commit handler and `cli.py` commit path

### 4.2 Naming template system
- [ ] Add `naming_templates` section to `config.json`:
  ```json
  "naming_templates": {
    "default": "{category}_{topic}_{description}",
    "short": "{topic}_{description}",
    "editorial": "{date}_{category}_{topic}"
  }
  ```
- [ ] In `app.py`, add a `st.selectbox("Naming template", list(templates.keys()))` before analysis
- [ ] Store selected template in `st.session_state.naming_template`
- [ ] In `analyze_asset_with_ai()` or in a new `apply_naming_template()` function in `engine.py`:
  - Parse the AI response's `new_filename` into its semantic components
  - Rebuild the filename according to the selected template
  - Fall back to the AI's raw `new_filename` if template keys are missing

### 4.3 Dry-run commit preview
- [ ] Add a "Preview Commit" button next to "Commit Selected"
- [ ] When clicked: show a `st.dataframe` with columns: `Original Path`, `New Path`, `Category`, `Tags`, `Metadata Written`
  - Read all data from `staged_assets` and `st.session_state.output_dir`
  - Simulate the full commit path without actually writing files or metadata
- [ ] Show a caption: "This is a preview. No files were modified."

### 4.4 Case style selection
- [ ] Add `case_style` to `config.json` naming section: `"case_style": "snake_case"` with options: `snake_case`, `camelCase`, `kebab-case`, `pascal_case`, `lowercase`, `original`
- [ ] In `app.py`, add the option inside a `st.expander("Advanced Features")` section before analysis
  - `st.selectbox("Filename case style", list(CASE_STYLES.keys()))`
- [ ] In `engine.py`, create `apply_case_style(name, style)` function that transforms the staged filename
- [ ] Apply case style in both `app.py` commit flow and `cli.py`

### 4.5 Max filename character limit
- [ ] Add `max_filename_chars` to `config.json` naming section (default: 0 = no limit)
- [ ] In `app.py`, add the option inside the Advanced Features expander
  - `st.number_input("Max filename characters", min_value=10, max_value=100, value=0)`
- [ ] In `engine.py`, create `truncate_filename(name, max_chars)` that truncates smartly (preserves category prefix)
- [ ] Apply in both app and CLI

---

## Layer 5: Session Persistence & Recovery

### 5.1 Save session to disk
- [ ] Create a `sessions/` directory (gitignored)
- [ ] Add "Save Session" button in the Upload & Analyze tab
- [ ] Serialize to JSON: `st.session_state.uploaded_files` (paths only, not buffers), `staged_assets`, `analysis_done`, `output_dir`
  - Do NOT serialize `base64_cache` (too large — re-extract on restore)
- [ ] Write to `sessions/session_YYYY-MM-DD_HHmmss.json`
- [ ] Log a `session_saved` event

### 5.2 Restore session from disk
- [ ] Add a file uploader or dropdown in the Upload & Analyze tab: "Restore Session"
  - file uploader: load JSON file, parse, restore state
  - dropdown: list `sessions/*.json` files sorted by date
- [ ] On restore:
  - Set `uploaded_files` from saved paths (validate files still exist on disk; warn if missing)
  - Set `staged_assets`, `analysis_done`, `output_dir`
  - Clear `base64_cache` (will be re-extracted on next analysis)
  - Set `analysis_in_progress = False`, `analysis_index = 0`
  - Show `st.success("Session restored from session_20260711_143022.json")`

### 5.3 Auto-save on browser close
- [ ] Use Streamlit's `session_state` lifecycle — no reliable hook for browser close
- [ ] Alternative: add an auto-save timer (every 60 seconds while `staged_assets` is non-empty)
  - `st_autorefresh` triggers a save function that writes session JSON
  - Only saves if `staged_assets` changed since last save (track via hash or counter)
  - Show a small indicator: "Auto-saved 30s ago"

---

## Layer 6: Configuration & Admin

### 6.1 Config editor tab (read-only view)
- [ ] Add a third tab "Configuration" in `app.py`
- [ ] Read `config.json`, display as formatted `st.json()` (read-only for v1)
- [ ] Show validation: green border if JSON is valid, red if corrupted
- [ ] Show a "Reload Config" button that re-calls `load_config()` and refreshes module-level globals
  - Note: this requires `importlib.reload()` or a config refresh mechanism in `engine.py`
  - Add `reload_config()` function that re-reads JSON and re-exports module globals

### 6.2 Config editor tab (editable)
- [ ] Add an "Edit" toggle beside the JSON view
- [ ] When toggled: replace `st.json()` with a `st.text_area()` pre-filled with formatted JSON
- [ ] "Save" button validates JSON, writes to `config.json`, calls `reload_config()`
  - On invalid JSON: show error, do not write
  - On success: show `st.success("Config saved and reloaded")`
- [ ] Warn user: "Some changes (model, categories) require re-running analysis to take effect"

### 6.3 Category management UI
- [ ] In the Configuration tab, add a "Categories" section
- [ ] Show current categories as a list of `st.text_input()` widgets (one per category)
- [ ] "Add Category" button appends a new empty input
- [ ] "Delete" button per row removes that category
- [ ] "Save Categories" button: validate no duplicates, no empty strings, write to `config.json`, call `reload_config()`
- [ ] Show count: "40 categories configured"

### 6.4 Extension management UI
- [ ] In Configuration tab, add "Supported Extensions" section
- [ ] Two `st.multiselect()` widgets: Video Extensions, Image Extensions
  - Pre-populated with current values from config
  - Options: all common extensions + custom text entry
- [ ] "Save" button writes to `config.json`, calls `reload_config()`

---

## Layer 7: Analytics & Logging Enhancements

### 7.1 Per-asset commit timeline
- [ ] In the Analytics Dashboard tab, add a sub-section "Commit History"
- [ ] Read `logs/commits_*.jsonl` files, parse into DataFrame
- [ ] Display as `st.dataframe` with columns: Commit Time, Original Name, New Name, Category, Tags
- [ ] Add filters: date range (date input), category (multi-select)

### 7.2 Analytics export
- [ ] Add "Export as CSV" button below the event timeline
- [ ] Build CSV from the currently filtered `timeline_df`, use `st.download_button()`
- [ ] Add "Export as JSON" button for the same data
- [ ] Add a "Print Report" button that opens a print-friendly view (use `st.markdown()` with a print stylesheet)

### 7.3 Storage usage tracking
- [ ] In analytics, add a "Storage" metric card
- [ ] Sum file sizes of all committed files (read from commit log or `os.path.getsize()` on committed paths)
- [ ] Show human-readable format: "2.4 GB total renamed"
- [ ] Add a trend line if historical data is available (daily cumulative storage)

### 7.4 Error rate chart
- [ ] Add a line chart to analytics showing error rate over time
  - X-axis: date, Y-axis: error rate (errors / total events) as percentage
- [ ] Use a rolling 7-day window if enough data exists
- [ ] If daily data is sparse, show raw counts instead of rates

---

## Layer 8: CLI Improvements

### 8.1 Dry-run flag
- [ ] Add `--dry-run` flag to `cli.py`
- [ ] When set: simulate all commits (print what WOULD happen), write nothing to disk, open no ExifTool session
- [ ] Print summary: "Dry-run complete. 12 assets would be renamed. 0 conflicts."

### 8.2 Non-interactive mode
- [ ] Add `--non-interactive` / `-y` flag: skip all interactive prompts, use AI suggestions as-is
- [ ] Add `--categories-override FILE` flag: load a JSON file mapping asset names to forced categories
- [ ] Add `--output FILE` flag: write commit summary to a text or JSON file instead of stdout

### 8.3 Progress bar for CLI
- [ ] Replace simple text counters with `rich.progress` or `tqdm` progress bars
  - Phase 1 extraction: per-file progress with filename
  - Phase 2 analysis: per-asset progress with filename and current model
  - Commit phase: per-file progress with destination path
- [ ] Add `--no-progress` flag to disable progress bars (for pipe-friendly output)
- [ ] Add `rich` to `requirements.txt`

### 8.4 Include subdirectories flag
- [ ] Add `--include-subdirectories` / `-r` flag to `cli.py`
- [ ] When set, use `target_dir.rglob("*")` instead of `target_dir.iterdir()`
- [ ] Maintain the same extension filtering
- [ ] Log scanned subdirectory count in `session_start` event: `"subdirs_scanned": N`

---

## Layer 9: Infrastructure & DevOps

### 9.1 Dockerfile
- [ ] Create `Dockerfile` with:
  - Base image: `python:3.11-slim`
  - Install system deps: `exiftool`, `ffmpeg`, `curl`
  - Install Python deps from `requirements.txt`
  - Copy app source
  - Expose port 8501
  - Entrypoint: `streamlit run app.py --server.port=8501 --server.address=0.0.0.0`
- [ ] Create `docker-compose.yml` with two services:
  - `ollama`: image `ollama/ollama`, volumes for model storage, GPU passthrough
  - `renamer`: build from Dockerfile, depends on ollama, port 8501
- [ ] Add a note in `README.md`: "Run `docker compose up` for a fully containerized setup"

### 9.2 Startup validation
- [ ] Create `validate_env()` function in `engine.py`:
  - Check `exiftool` is in PATH (run `exiftool -ver`)
  - Check `ffmpeg` is in PATH (run `ffmpeg -version`), detect version
  - Check `ffprobe` is in PATH (run `ffprobe -version`)
  - Check Ollama connectivity (`ollama.list()`)
  - Return dict: `{exiftool: bool, exiftool_version: str, ffmpeg: bool, ffmpeg_version: str, ollama: bool, ollama_models: list}`
- [ ] In `app.py`, show validation results as expandable "Environment Check" section in sidebar or config tab
  - Green checkmark / red X per dependency
  - Tooltip with version on hover
- [ ] In `cli.py`, run validation at startup, print warnings for missing deps, exit with error code if critical deps are missing

### 9.3 `.gitignore` update
- [ ] Add to `.gitignore`:
  ```
  sessions/
  logs/
  __pycache__/
  *.pyc
  .streamlit/
  ```

### 9.4 Streamlit config
- [ ] Create `.streamlit/config.toml`:
  ```toml
  [server]
  maxUploadSize = 10000  # 10 GB
  [theme]
  base = "dark"
  primaryColor = "#3b82f6"
  ```
- [ ] Create `.streamlit/secrets.toml` (optional, placeholder only — no secrets used yet)

---

## Layer 10: Quality of Life

### 10.1 Dark mode toggle
- [ ] Add a sidebar `st.toggle("Dark Mode")` in `app.py`
- [ ] Store preference in `st.session_state.dark_mode`
- [ ] On toggle: inject custom CSS via `st.markdown()` that overrides Streamlit's theme
  - Alternative: let Streamlit's built-in theme handle it (set `base = "dark"` in config, offer "Light" as opt-out)
- [ ] Persist preference across reruns (already handled by session state)

### 10.2 Keyboard shortcuts
- [ ] Add JavaScript injection via `st.markdown()` for keyboard shortcuts:
  - `Ctrl+Enter`: Trigger "Run AI Analysis" (click the button via JS)
  - `Ctrl+Shift+C`: Trigger "Commit Selected"
  - `Escape`: Stop Analysis
- [ ] These work only when the corresponding button is visible (check via Streamlit's rendered DOM)

### 10.3 Notification on commit complete
- [ ] After commit in `app.py`, play a short audio notification
  - Use a base64-encoded WAV beep (tiny file, inline in Python)
  - Play via `st.audio()` with `autoplay=True`
- [ ] Only play if the browser tab is visible (no reliable way to detect this in Streamlit — always play)
- [ ] Option to disable in sidebar: "🔔 Play sound on commit complete"

### 10.4 Batch size warning
- [ ] Before Phase 1 extraction, check `len(uploaded_files)`
- [ ] If > 50 files: show `st.warning("Large batch detected (N files). Extraction may take several minutes.")` with a "Continue / Cancel" confirmation
- [ ] If > 200 files: show stronger warning + recommend CLI for better throughput
- [ ] Thresholds in `config.json`: `batch_warn_threshold: 50`, `batch_recommend_cli: 200`

### 10.5 Footer attribution
- [ ] Add a `st.markdown()` footer at the bottom of `app.py`:
  - "Made with love from Tanzania by Abdul Musawwir"
  - Link to GitHub repo: `https://github.com/Abdulmusawwir/ai-media-renamer`
- [ ] Use `st.html()` or `st.markdown()` with `unsafe_allow_html=True` for the hyperlink
- [ ] Style subtly — small text, muted color, positioned below all tabs

### 10.6 Jargon-free UI text
- [ ] Replace all technical/internal status messages in `app.py` with user-friendly alternatives:
  - `"Checking caches and extracting grids into RAM"` → `"Extracting preview frames from videos and images"`
  - `"Injecting RAM streams directly into AI Vision Model"` → `"Analyzing content with AI model"`
  - `"Piping ExifTool commands into metadata containers"` → `"Writing metadata tags to files"`
  - `"Phase 1: Extracting previews into memory..."` → `"Step 1: Preparing previews..."`
  - `"Phase 2: Sequential AI Processing"` → `"Step 2: Analyzing content..."`
- [ ] Replace corresponding messages in `cli.py`
- [ ] Remove "fast-seeking" and "storyboard grid" references from user-facing text
- [ ] Keep technical details in JSONL logs and `--verbose` CLI output only

### 10.7 Dismissible commit summary
- [ ] Replace the persistent `st.session_state.commit_message` approach with `st.toast()` or `st.success()` with a close button
- [ ] Show a non-blocking summary: "12 assets committed to Desktop/RenamedMedia. 0 failed."
- [ ] Auto-dismiss after 8 seconds or on next user interaction
- [ ] Keep the detailed log accessible in the Analytics Dashboard tab

### 10.8 Advanced Features expander
- [ ] Add a `st.expander("Advanced Features")` in the Upload & Analyze tab, positioned before the analysis trigger
- [ ] Group inside: case style selector, max filename chars, custom prompt text area (also linked to profile selection)
- [ ] Collapsed by default — clean default experience for most users

---

## Layer 11: Testing & Reliability

### 11.1 Unit tests for engine.py
- [ ] Create `tests/` directory
- [ ] Write `tests/test_config.py`:
  - `test_load_config_returns_dict`
  - `test_load_config_raises_on_missing_file`
  - `test_video_extensions_are_tuple`
  - `test_allowed_categories_are_tuple`
- [ ] Write `tests/test_validation.py`:
  - `test_validate_category_valid`
  - `test_validate_category_invalid_returns_uncategorized`
  - `test_validate_category_empty_returns_uncategorized`
  - `test_sanitize_name_removes_special_chars`
  - `test_sanitize_name_lowercases`
  - `test_sanitize_name_adds_default_suffix_if_too_short`
- [ ] Write `tests/test_parse_ai_response.py`:
  - `test_parse_valid_json`
  - `test_parse_codeblock_json`
  - `test_parse_empty_response`
  - `test_parse_malformed_json`

### 11.2 Integration tests
- [ ] Write `tests/test_extraction.py` (skipped if ffmpeg not available):
  - Create a tiny synthetic test video (1 second, black frame) via ffmpeg
  - `test_process_video_to_base64_returns_string`
  - `test_process_image_to_base64_returns_string`
- [ ] Write `tests/test_commit.py` (skipped if exiftool not available):
  - Create temp dir with test file
  - Run `execute_commit()` with known values
  - Verify file was renamed
  - Verify metadata was written using exiftool session

### 11.3 Test runner config
- [ ] Add `pytest` and `pytest-cov` to `requirements.txt`
- [ ] Create `pyproject.toml` with pytest config:
  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  markers = ["slow: marks tests as slow (deselect with '-m \"not slow\"')"]
  ```
- [ ] Add `test` command to AGENTS.md

---

## Layer 12: Desktop Bundling & Bootstrap Lifecycle (Phase S)

### S.1 Bootstrap 4-Stage Checklist
- [ ] Create `check_environment()` in `engine.py` returning structured status dict:
  - `ffmpeg`: bool — check via `_resolve_binary_path("ffmpeg")`
  - `exiftool`: bool — check via `_resolve_binary_path("exiftool")`
  - `ollama_running`: bool — probe `http://localhost:11434/api/tags`
  - `model_available`: bool — parse `/api/tags` for `qwen2.5vl:7b`
  - `cloud_configured`: bool — check config or session state for valid Gemini Flash API key
- [ ] Create `_resolve_binary_path(name)` in `engine.py`:
  - Check `sys._MEIPASS / "bin" / name` first (PyInstaller bundled path)
  - Fall back to `shutil.which(name)`
  - Return full path string or `None`
- [ ] Create dedicated bootstrap panel in `app.py` that runs `check_environment()` at startup
- [ ] Smart routing: if Ollama/model missing but `cloud_configured=True`, show: *"Status: Local engine missing. Routing execution to pre-configured Cloud API."* — bypass download
- [ ] If both missing: show interactive local downloader UI (see S.2)
- [ ] Store results in `st.session_state.env_check` to avoid re-running on every rerun

### S.2 Interactive Model Download
- [ ] Create `stream_model_download(model_name="qwen2.5vl:7b")` generator in `engine.py`:
  - POST `http://localhost:11434/api/pull` with `stream=True`
  - Read JSON chunk stream: yield `{"status": "progress", "completed": int, "total": int, "percentage": float}`
  - On completion: yield `{"status": "success"}`
  - On error: yield `{"status": "error", "message": str}`
- [ ] In `app.py` bootstrap panel: iterate generator inside a loop, update `st.progress()` and status text:
  - `f"Downloading Qwen2.5-VL: {completed_gb:.1f}GB / {total_gb:.1f}GB ({percentage:.0f}%)"`
- [ ] On success: re-run `check_environment()` to confirm model is now available
- [ ] On error: show error message with retry button

### S.3 Hybrid AI Switching
- [ ] Create `switch_ai_provider(new_provider, api_key=None)` in `engine.py`:
  - `new_provider`: `"ollama"` | `"gemini"` | `"openai"` | `"anthropic"`
  - **Local → Cloud**: call `ollama.generate(keep_alive=0)` to drop model weights from RAM/VRAM immediately; swap config to cloud provider
  - **Cloud → Local**: re-trigger `check_environment()`; if Ollama/model missing, block pipeline and show `[Initialize Local AI Engine]` button (fires S.2)
  - Update module-level constants (`MODEL_NAME`, provider function pointers)
- [ ] In `app.py` settings panel: add provider selector (radio or dropdown) with conditional API key field (password input)
- [ ] `[Initialize Local AI Engine]` button appears when cloud→local switch fails due to missing model
- [ ] Log provider switches via `log_event()` with event type `"provider_switch"`

### S.4 Storage Lifecycle Utility
- [ ] Create `wipe_local_model(model_name="qwen2.5vl:7b")` in `engine.py`:
  - Call `DELETE http://localhost:11434/api/delete` with model name payload
  - Return `{"ok": bool, "message": str}`
- [ ] In `app.py` Configuration view: add `[Wipe Local Model Cache]` button
- [ ] Guard: show `st.warning("This will permanently delete the ~5GB Qwen2.5-VL model. Re-download required to use local mode.")` + confirmation checkbox
- [ ] On success: re-run `check_environment()` to reflect removal
- [ ] Log via `log_event()` with event type `"model_wipe"`

### S.5 PyInstaller Distribution Setup
- [ ] Create `_resolve_binary_path()` as described in S.1 (single function used by all binary calls)
- [ ] Update `detect_hw_accel()` in `engine.py` to use `_resolve_binary_path("ffmpeg")` instead of bare `ffmpeg` command
- [ ] Update `process_video_to_base64()` and `process_image_to_base64()` to use resolved ffmpeg/ffprobe paths
- [ ] Update `ExifToolSession.__init__()` to use `_resolve_binary_path("exiftool")`
- [ ] Create `hooks/hook-ollama.py` for PyInstaller to include ollama client library
- [ ] Add `pyinstaller` to `requirements.txt`
- [ ] Create `build.spec` with proper binary collection rules (FFmpeg, ExifTool, model data, static assets)

## Layer 13: (Reserved — Phase U in execution order)

### 13.1 Perceptual duplicate detection
- [ ] Add `imagehash` to `requirements.txt` for perceptual hashing
- [ ] In `engine.py`, create `compute_asset_hash(file_path)` function:
  - For images: compute pHash via `imagehash.phash()`
  - For videos: extract middle frame via FFmpeg, then pHash that frame
- [ ] In `app.py`, add a "Detect Duplicates" button above the staging matrix
- [ ] On click: compute hashes for all staged assets, compare pairwise, assign confidence scores (0-100%)
- [ ] Add a new read-only column to the staging table: "Duplicate"
  - Display: `"File_X.mp4 (92%)"` if duplicate found, otherwise `"-"`
- [ ] Add checkbox option: "Include audio track in comparison" — if unchecked, compare video frames only
- [ ] Add option to auto-check lower-confidence duplicates for skipping during commit
- [ ] Log duplicate detection results: `"duplicates_found": N, "pairs": [{"a": "...", "b": "...", "confidence": 92}]`

### 13.2 User rating / feedback on AI suggestions
- [ ] Add a rating column to the staging table: thumbs up / thumbs down per asset
- [ ] Store ratings in session state alongside staged_assets
- [ ] On commit, log ratings: `"rating": "positive" | "negative"` in `file_committed` event
- [ ] Show a small aggregate in analytics: "Positive ratings: 42 / 50 (84%)"
- [ ] Future: use ratings to filter or prioritize certain prompt strategies

---

## Execution Order (Recommended)

The phases are ordered by dependency — each phase can be worked on independently but earlier phases unblock later ones.

```
Phase A: 1.1, 9.3, 9.4          → Foundation (progress UI, gitignore, streamlit config)
Phase B: 2.3, 9.2, 11.1          → Health checks + unit tests (confidence layer)
Phase C: 1.2, 1.4, 1.3          → Upload hardening
Phase D: 3.1, 3.2, 3.3          → Staging UX improvements — DONE
Phase E: 4.1, 4.4               → Commit flexibility (metadata-only + dry-run)
Phase F: 5.1, 5.2, 5.3         → Session persistence + recovery
Phase G: 2.1, 2.2, 2.4          → Analysis flexibility (re-analyze, model select, workers)
Phase H: 6.1, 6.2, 6.3, 6.4    → Configuration UI
Phase I: 7.1, 7.2, 7.3, 7.4    → Analytics enhancements
Phase J: 8.1, 8.2, 8.3         → CLI improvements
Phase K: 9.1, 11.2, 11.3       → Docker + integration tests
Phase L: 10.1, 10.2, 10.3, 10.4 → Quality of life (core)
Phase M: 3.4, 3.5               → CSV import/export — DONE
Phase N: 4.2                    → Naming templates
Phase O: 10.5, 10.6, 10.7       → Quality of life (polish)
Phase P: 4.4, 4.5, 10.8         → Advanced Features expander + naming controls
Phase Q: 2.5                    → Multi-profile AI prompts
Phase R: 2.6, 2.7               → Multi-provider + model auto-detect
Phase S: S.1–S.5                → Desktop Bundling & Bootstrap Lifecycle Setup
Phase T: 8.4                    → CLI subdirectories
Phase U: 12.1, 12.2             → Duplicate detection + feedback
Phase V: Support                 → Donation / sponsorship links, "Buy me a coffee" button
```
