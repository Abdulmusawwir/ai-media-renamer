# Changelog

## [v1.7.0] — 2026-08-16

### Breaking Change: fully local & offline
- **Cloud providers removed** — `GeminiProvider`, `AnthropicProvider`, `GroqProvider`, and `OpenRouterProvider` are deleted from `engine.py`; the provider registry is now `ollama` + `llamacpp` only. `OpenAIProvider` (the OpenAI-compatible base) is kept solely as the local `LlamaCppProvider` engine. No API keys, no keychain, no cloud.
- **Keyring/API-key layer removed** — `save_api_key`/`load_api_key`/`delete_api_key`/`CURRENT_API_KEY`/`KEYRING_SERVICE` and `import keyring` are gone; `app.py` no longer renders the cloud caption, API-key input, keyring warning, or `has_key` badges. `get_provider`/`switch_ai_provider` (no longer takes `api_key`) and `_format_ai_error` are local-only; `check_environment()` no longer reports `cloud_configured`.
- **Config scrubbed** — `config.json` / `config.default.json` drop the cloud provider blocks, the `cloud` list, and the dead `preview.video_grid_tile` / `video_frame_count` keys; the missing `model.llamacpp` block was added back to `config.json`.
- **Dependencies trimmed** — `anthropic` and `keyring` (plus transitive `jaraco.*` / `more-itertools`) removed from `requirements.txt`, `requirements.lock`, `build.spec`, and `pyproject.toml`.
- **CLI crash fix** — `transcribe_audio` / `extract_text_from_file` were used but never imported (real F821 runtime `NameError` when analyzing audio/documents via CLI); `--import-csv` no longer requires a positional `dir` (defaults to the CSV's folder); `--categories-override` is validated as a string→string dict.
- **Tests** — `test_providers.py` rewritten for the local-only registry (cloud + keyring classes removed, LlamaCpp/OpenAICompat local tests kept); `test_setup.py` no longer expects `cloud_configured`. 298 passed, 1 skipped. Ruff down to 21 repo-wide findings (all pre-existing test E501), below the 27-engine/app/cli baseline.
- **Wave 3 hygiene** — `save_session` handles timestamp collisions (`_1`, `_2`, … suffixes); `load_session` / `list_sessions` tolerate malformed non-list/dict blocks instead of raising.

---

## [v1.6.4] — 2026-08-16

### Code Quality
- **Remediation Wave 2 (Medium backlog) complete.** Engine hardening: atomic `save_config` (temp + `fsync` + `os.replace`), import-safe `load_config` (`RuntimeError`, `CONFIG_LOAD_ERROR` + `_minimal_config()` fallback, `reload_config` keeps old config on failure), thread-safe lazy whisper-model load, provider selection respects `config.model.last_provider`, `validate_category` against the active categories, `sanitize_name` no longer strips `grid`/`sequence`, `.doc` handled truthfully (unsupported), Ollama/llama.cpp ports from config/env (`OLLAMA_HOST`, `model.ollama.base_url`), `ExifToolSession` raises instead of `print`+`sys.exit`, `tempfile.mkstemp` replaces `mktemp`.
- **Web app:** engine switch moved into an `on_change` callback (`_on_engine_change`, radio disabled during analysis), single `_reset_analysis_state()` helper shared by file-change / Clear All / session restore (also clears `analysis_index` + `duplicate_pairs`), Clear All no longer deletes saved sessions (explicit Delete control remains), `exif.close()` in a `finally`, stale upload `temp_dir` rmtree'd before re-extract, thumbnail decode + duplicate table behind explicit load toggles.
- **CLI:** argparse mutually-exclusive groups (`--export-csv`/`--import-csv`, `--rollback`/`--reset-config`), `--case-style` default synced to `DEFAULT_CASE_STYLE` from config.
- **Docs:** `REMEDIATION.md` Wave 2 marked DONE; `audit.md` notes updated; `task.md` repointed at Wave 3.
- Tests: 333 passing, 1 skipped (unchanged); ruff unchanged from pre-existing baseline (27 findings on engine/app/cli).

---

## [v1.6.3] — 2026-08-15

### Security
- **Supply-chain hardening for bootstrap downloads (Phase AI 20.1):** every binary the wizard fetches — FFmpeg, ExifTool, the llama.cpp runtime, and GGUF models — is now verified against its published SHA-256 digest before use. `download_file()` rejects plain-HTTP URLs outright and deletes any file that fails checksum verification. Digests come from the publishers themselves: gyan.dev's `.sha256` file for FFmpeg, exiftool.org's per-version checksums file for ExifTool, the GitHub release API `digest` field plus pinned fallback digests for llama.cpp, and HuggingFace LFS OIDs baked into the GGUF catalog. A build with no published digest is skipped, never installed.
- **Dependency audit (Phase AI 20.1):** `cryptography>=50.0.0` floor added for PYSEC-2026-3552 (transitive dep of pywebview); `requirements.lock` now freezes exact build versions.
- **Secret redaction everywhere (Phase AI 20.2):** API keys can no longer leak into exception messages, `log_event()` records, or `_format_ai_error()` output. Keys are registered in an in-memory secret cache and masked (including `?key=`/`api_key=`/`token=` query strings) before anything is logged or shown. The Configuration tab's read-only JSON view masks secret-looking keys (`api_key`, `token`, `password`, `*secret*`).
- **Keychain failures fail closed (Phase AI 20.2):** if the OS keychain is unavailable, the app never falls back to a plaintext file. A new health probe surfaces a clear sidebar warning and guarded error captions wherever keys are saved/read/switched.
- **Local server exposure (Phase AI 20.3):** the app now binds to `127.0.0.1` explicitly, so it is never reachable from the LAN by default. Opt in via `config.json` `server.lan_expose` (or the "Expose on local network" toggle in Configuration) — with an in-UI warning that LAN exposure has no authentication. Docker Compose host ports are likewise bound to loopback.
- **Input validation & injection (Phase AI 20.4):** all `unsafe_allow_html` call sites audited (static content only). CSV import/export neutralize spreadsheet formula injection (`=`, `+`, `-`, `@` leading cells) and reject path separators in imported filenames. Session restore schema-validates loaded JSON, drops malformed entries, and never follows symlinks. Staged filenames can no longer traverse directories on commit (`_safe_stem`).
- **Log path privacy (Phase AI 20.5):** absolute paths are redacted from JSONL logs by default (`config.logging.redact_paths`).

### Fixed
- **Cross-drive + race-safe commits:** `_commit_move()` falls back to copy+delete when `rename` fails across Windows drives and retries with a `_N` suffix on name collisions — shared by both commit paths. The `skip_rename` copy target is deduped too (no silent overwrites).
- **Rollback retained on partial failure:** a failed rollback keeps its undo-log batch so it can be retried.
- **`reload_config()` refreshed all globals:** text model, extensions, preview settings, profiles, and provider now update immediately after a config save.
- **Strict AI response parsing:** non-object JSON (`null`, arrays, bare strings) is rejected; `tags` must be a list.
- **ExifTool hardening:** reader-thread + 60s timeout prevents IPC deadlocks; `execute_batch()` returns one output per file; metadata-write failures are surfaced as `ERROR:...` instead of silently reported as committed.
- **Ollama health check:** vision-model detection now handles model objects via the same 3-branch extraction as `check_environment()`, with one retry on transient failures.
- **Keyring exceptions no longer crash the UI** (see Keychain failures above).

### Code Quality
- **28 new tests** (SHA-256 helpers, HTTPS enforcement, checksum handling, redaction, CSV formula injection, session schema/symlink, traversal lock-in, keyring probe); 333 total, all passing. Ruff unchanged (pre-existing baseline only).

---

## [v1.6.2] — 2026-08-08

### New
- **llama.cpp is now the default local AI runtime for new installs:** the desktop setup wizard downloads the `llama-server` runtime (~18 MB) plus a GGUF vision or text model, configures the app, and starts the daemon automatically — no manual setup. If Ollama is already installed, it's detected and reused and you're never asked to install llama.cpp too. Both runtimes stay supported.
- **GGUF model selection in the wizard:** GPU machines are recommended a 7B vision model (Qwen2-VL 7B Q4_K_M + mmproj), CPU machines a lighter 2B vision model, and document/audio workflows a compact text model (Qwen2.5-3B). Verified HuggingFace download URLs with an `hf-mirror.com` fallback.
- **In-app engine switch boots llama.cpp:** switching the engine radio to "Local (llama.cpp)" starts the server if it was installed but idle.

### Code Quality
- **21 new tests** (GGUF catalog, model recommendations, runtime URL resolution, config wiring, wizard plan runtime-awareness, server lifecycle, OpenAI-compatible text/override paths); 290 total, all passing. Ruff clean (pre-existing baseline only).

---

## [v1.6.1] — 2026-08-08

### Fixed
- **Honest model status:** `OllamaProvider.available_models()` no longer falls back to the config catalog, so models can't show as "(installed)" while the Ollama daemon is down. Download buttons now appear for every model that isn't actually installed (reported in v1.6.0 first-run).
- **Wizard buttons always reachable:** the use-case questionnaire and the one-time download plan dialogs are now resizable with a screen-clamped height and a scrollable list, so the Continue/Cancel (and Start setup/Back) buttons can never be pushed off-screen. Enter/Escape keys work.
- **In-app dependency setup:** when FFmpeg/ExifTool are missing or the local runtime is down, the app now surfaces a "Setup incomplete — open setup wizard" button that re-runs `bootstrap --setup`, instead of leaving you with red badges and no way forward.
- **No Streamlit chrome flash:** `[client] toolbarMode = "minimal"` in `.streamlit/config.toml` stops the Run/Deploy toolbar from flashing before the CSS injection strips it.

### New
- **llama.cpp runtime fallback:** a local `llama-server` (OpenAI-compatible, `localhost:8080`) is auto-detected and appears as a "Local (llama.cpp)" engine option when Ollama is absent — vision and text analysis route through the same provider interface (`LlamaCppProvider`). Ollama remains the bundled default; llama.cpp is for users who run it. Override the endpoint with `LLAMACPP_BASE_URL` or `model.llamacpp.base_url`.

### Code Quality
- **7 new tests** (provider registry, llama.cpp provider + detection); 269 total, all passing. Ruff clean (29 pre-existing baseline).

---

## [v1.6.0] — 2026-08-02

### New Features
- **Marketing-focused README:** Rewrote `README.md` as a user-first pitch — problem framing, benefit-led copy, screenshots, who-it's-for, and roadmap. Added a branded header banner (`assets/header.png` + `assets/header.svg`) and UI previews (`assets/screenshot-staging.png`, `assets/screenshot-dashboard.png`, `assets/screenshot-wizard.png`). Technical depth now lives in `README_TECH.md`.
- **First-run onboarding wizard:** Use-case questionnaire (videos / photos / documents / spreadsheets / audio) → dependency + model install plan → Ollama registry-validated model picker. Profile persists to `%APPDATA%\ai-media-renamer\setup.json`. "Skip" launches the app without installing. `--setup` re-runs the wizard.
- **In-app model download:** sidebar dropdowns list all catalog models with `(installed)` / `(not installed)` markers and per-model download buttons with live progress; Configuration tab "Setup & onboarding" re-launches the wizard.
- **Separate text model for documents & audio:** `config.model.text_model` (default `qwen2.5:3b`); document/audio prompts no longer go through the big vision model. Sidebar text-model selector (non-vision models only, download button). `check_environment()` reports `text_models` / `text_model_available`.
- **Audio file upload & analysis:** Audio files (MP3, WAV, FLAC, AAC, OGG, M4A, WMA, OPUS, AIFF, ALAC, APE, WV) can now be uploaded and analyzed. Transcription fed into AI analysis context. New `audio_naming` prompt profile.
- **Audio fingerprint duplicate detection:** Chromaprint-based audio fingerprinting detects files with same audio but different visuals. Cross-modal detection: video vs video (pHash), audio vs audio (Chromaprint), and mixed-type isolation (SHA-256).
- **CLI document & audio support:** CLI now processes documents (text extraction) and audio files (transcription) alongside video and images. `valid_exts` includes all 4 media types.
- **Audio metadata writing:** ExifTool metadata for audio files — ID3 tags for MP3/AIFF/APE, XMP for WAV/FLAC/OGG/WV, QuickTime atoms for M4A/AAC.

### Improvements
- **Wizard UX:** modern dark theme (accent `#4f8cff`), row-click checkbox toggles, Select all / Clear, honest model-size ranges ("1.8–6.0 GB" / "1.0–4.7 GB"), scrollable resizable model dialog with pinned header/footer, themed progressbar.
- **No more wizard freeze:** registry checks go through a queue drained by a main-thread poll; dialogs close via `_close_dialog()`; `main()` uses `_show_modal()` (update loop) instead of `wait_window()`. Closing mid-registry-check returns <0.5s.
- **Extension management:** Audio extensions configurable in Configuration tab (4th column). Default list in config.json/config.default.json.
- **Staging table:** Type column now shows "audio", "doc", or "media" with file extension. Audio files show transcription snippet in summary column.
- **Duplicate detection expanded:** `find_duplicates()` now handles 3 hash types: pHash (visual), SHA-256 (document), Chromaprint (audio). `_chromaprint_similarity()` computes pairwise audio fingerprint similarity (0.85 threshold).
- **GPU→CPU fallback:** video frame extraction retries with software decoding when hardware decode fails; app shows a durable "GPU decoding failed … fell back to CPU" warning.

### Code Quality
- **13 new tests:** Audio build_commit_args, chromaprint similarity, duplicate detection with audio fingerprints. 220 total tests, all passing.
- **README simplified:** Features, CLI details, and "Why Use This?" moved to README_TECH.md. README.md is now a concise landing page.

---

## [v1.5.0] — 2026-07-27

### New Features
- **Undo/rollback engine (18.1):** `log_commit_batch()`, `rollback_last_batch()`, `list_undo_batches()` in engine.py. CLI `--rollback` flag. "Undo Last Commit" button in Analytics tab. All commit paths log undo records.
- **Pydantic structured outputs (18.2):** `AssetAnalysisResponse` model validates AI responses. OpenAI/Groq/OpenRouter use `response_format` for structured output. Fallback chain: Pydantic → raw JSON → error.
- **ExifTool batching (18.3):** `_build_commit_args()` helper, `execute_commit_batch()` for single-IPC batch writes, `execute_batch()` on ExifToolSession. Reduces metadata write overhead from ~200ms × N to ~200ms total.
- **Audio transcription (19.1-19.3):** `faster-whisper` integration for local audio transcription. `extract_audio_from_video()` via FFmpeg. Phase 1 extracts+transcribes audio for all video files. Transcription fed into AI prompt context.
- **Per-format document metadata (16.3):** DOCX metadata via python-docx, XLSX via openpyxl. TXT/MD/RTF/CSV/PPTX skip metadata with no error. `skip_metadata` param on `execute_commit()`.
- **Model selection wizard (17.1-17.3):** tkinter dialog with 4 model options (Qwen2.5-VL 7B recommended, 3B, Qwen3-VL 4B, Moondream 2). Bootstrap downloads user-chosen model. Vision model detection returns installed model list.

### Removed
- **All PostHog telemetry:** the opt-in analytics system introduced in v1.4.0 was removed in full — `track_event()`, the PostHog SDK, `TELEMETRY_FILE`, and the opt-in dialog/toggle no longer exist. The app collects no usage data. PRIVACY.md documents "no telemetry". (v1.4.0 changelog entries below describe the system as it existed at that release.)

### Improvements
- **Document categorization fix (16.1):** `get_active_prompt()` now appends explicit IMPORTANT constraint listing only profile-specific categories. Multiple needle replacement patterns for robustness.
- **Document duplicate detection (16.2):** `compute_asset_hash()` returns `sha256:{hash}` for documents (text content for small text files, raw bytes for binary). `find_duplicates()` groups by hash type, compares within groups only.
- **FontBBox suppression (16.4):** pdfminer.six warning suppressed in `extract_text_pdf()`.
- **Vision model detection fixed:** Added `qwen2.5-vl` and `qwen3-vl` prefixes to `VISION_MODEL_PREFIXES`. Fixes "no vision model installed" false negative when Ollama returns hyphenated model names.

### Code Quality
- **Pydantic:** `pydantic>=2.0.0` added to requirements.txt. `AssetAnalysisResponse` BaseModel with validation.
- **faster-whisper:** `faster-whisper>=1.0.0` added to requirements.txt. Lazy-loaded model cache.
- **Test count:** 176 tests passing (up from 158).

## [v1.4.0] — 2026-07-25

### New Features
- **Duplicate detection (13.1):** `compute_asset_hash()` uses FFmpeg + imagehash to generate perceptual hashes. `find_duplicates()` compares all staged assets with configurable threshold. UI button flags near-identical assets before commit.
- **User ratings (13.2):** Thumbs up/down column in staging table. Ratings sync to session state, logged to JSONL, and tracked in PostHog (if opted in).
- **Session persistence:** `save_session()`, `load_session()`, `list_sessions()` in engine.py. Sessions saved to `%APPDATA%/ai-media-renamer/sessions/`. Resume analysis across app restarts.
- **Config reset mechanism (3 levels):** Auto-recovery from `config.default.json` on corruption. `--reset-config` CLI flag. "Restore Default Configuration" button in Configuration tab.
- **Config editor tab:** Edit AI models, categories, extensions, and prompt profiles directly in the web UI.
- **Category management:** Add, remove, and rename categories in-app. Changes persist to config.json.
- **Extension management:** Add custom video/image file extensions in the Configuration tab.
- **Telemetry system (opt-in):** PostHog integration for anonymous usage analytics. First-launch opt-in dialog. Toggle in Configuration tab. Privacy policy in PRIVACY.md.

### Improvements
- **Commit beep:** Whoosh WAV sound replaces sine tone. Plays via hidden `<audio>` element (no visible player UI).
- **Sidebar cleanup:** Redundant delete button removed. Model wipe consolidated in Configuration tab.
- **CLI batch size warnings:** Warns when processing very large directories.
- **CLI advanced features expander:** Donation links and advanced options in CLI mode.
- **PRD checkbox sync:** Lines 114-116 marked complete (config editor, category mgmt, extension mgmt).
- **PostHog host comment:** Clarifying comment added to `POSTHOG_HOST` constant.

### Code Quality
- **Type hints:** All 118 functions across engine.py, app.py, and cli.py annotated with return types and parameter types.
- **Docstrings:** Google-style docstrings added to ~84 functions that lacked them.
- **mypy configuration:** `pyproject.toml` updated with `[tool.mypy]` section and third-party overrides.
- **Test infrastructure:** pytest-cov added, `tests/conftest.py` with shared fixtures.
- **New test files:** test_config_extended.py (12), test_session.py (7), test_duplicate_detection.py (5), test_telemetry.py (10), test_cli_helpers.py (8) — 42 new tests.
- **Total test count:** 158 tests passing (up from 116).
- **Coverage baseline:** 60% on engine.py.

### Bug Fixes
- **F821 Image import:** Added missing `from PIL import Image` in `_compute_image_hash()`.
- **CLI return in main:** Fixed bare `return` → `sys.exit(0)` in `if __name__ == "__main__"` block.
- **config.default.json:** Created factory-default config bundled in EXE for auto-recovery.
- **load_config default path:** `default_path` now derived from `full_path.parent` (not `script_dir`), preventing accidental config file discovery.

---

## [EXE Delivery] — 2026-07-12
- **PyInstaller build pipeline:** `build.spec` with `console=False`, `hooks/hook-ollama.py`, bundles app + deps into `AIMediaRenamer.exe`
- **Bootstrap launcher (`bootstrap.py`):** Dark tkinter GUI with 6-step setup — checks for ExifTool, FFmpeg, Ollama, and the AI vision model; auto-downloads and installs any missing dependencies silently. Progress bars with download speed/ETA. Runs Streamlit as a hidden background process (`DETACHED_PROCESS | CREATE_NO_WINDOW`). Exits completely on launch — no tray icon, no lingering process.
- **First-run port check:** Detects if Streamlit is already running on `localhost:8501` → opens browser without launching a second instance.
- **Streamlit branding hidden:** CSS injection removes Streamlit hamburger menu, deploy button, footer, header, toolbar, and status widget from the app. Config set to `headless=true`, `gatherUsageStats=false`.
- **Update checker (`engine.py`):** `check_for_updates()` hits GitHub API to compare `VERSION` against latest release tag. Used in both bootstrap (step 5 with [Download Update] button) and in-app sidebar ("🔍 Check for Updates" button).
- **`VERSION` constant (`engine.py`):** `"v1.2.0"` — single source of truth for update comparisons.
- **Auto-download helpers (`engine.py`):** `download_file()` streams with progress callbacks, `wait_for_ollama_service()` polls localhost:11434 until ready.
- **Icon:** Placeholder `icon.ico` generated via PIL (blue gradient + play triangle + pencil overlay, 16-256px sizes).
- **CI/CD:** `.github/workflows/build.yml` — builds EXE on `v*` tag push, uploads to GitHub Release.
- **Docs:** README.md and README_TECH.md updated with "Download the EXE" / "Building from Source" sections.
- `.opencode/plans/phase-r-multi-provider.md` deleted (Phase R complete).

## [CLI Phase 1-5] — 2026-07-12
- **CLI: `--case-style` / `--style` flag** — Choose from `snake_case`, `camelCase`, `kebab-case`, `pascal_case`, `lowercase`. Replaces the hardcoded `snake_case`.
- **CLI: `--max-chars` / `--max` flag** — Set max filename length (0 = no limit).
- **CLI: `--force` flag** — Re-analyze all files, skipping the `is_already_processed()` check.
- **CLI: `--export-csv <file>`** — Export staging data to CSV after AI analysis.
- **CLI: `--import-csv <file>`** — Skip extraction + analysis entirely; load staging from CSV.
- **CLI: `--dry-run`** — Preview all file operations without modifying anything.
- **CLI: Interactive mode enhanced** — Per-asset options: `[A]ccept`, `[S]kip`, `[R]e-analyze` (cached frame, no re-extraction), `[E]dit name`, `[B]ulk-apply category` to remaining assets.
- **CLI: Restructured into helper functions** — `_run_staging_phase()`, `_commit_all()`, `_interactive_commit()`, `_preview_dry_run()` extracted for clarity.
- **`is_already_processed()` bug fix** — Changed from `-s3` raw output (catches ExifTool errors/warnings as false positives) to `-json` structured parsing. Only returns True when the specific `XMP-dc:Description` key exists in the JSON output.
- **config.json religious_landmarks prompt expanded** — Added 30+ specific landmarks (Masjid al-Aqsa vs Dome of the Rock distinguished, Ghawth al-A'zam Baghdad, Aala Hazrat Bareilly, Imam Ali Najaf, Imam Hussein Karbala, Al-Askari Samarra, Fatima Masumeh Qom, Shah Cheragh Shiraz, Nasir al-Mulk, Hagia Sophia, Suleymaniye, Al-Azhar, Muhammad Ali, Sultan Hassan, Kairouan, Djenne, Umayyad, Al-Nuri, Sultan Qaboos, Putra Mosque, Istiqlal, and more). Added Islamic art/geometry/architecture reference section.
- **config.json general_balanced prompt updated** — Landmark identification rule added. Grid instructions removed from all 5 non-custom profiles (single-frame extraction).

## [Layer 3 Complete] — 2026-07-12
- **Staging search/filter:** `st.text_input` above the data editor filters by name, category, or tags with instant matching. "Showing N of M" caption.
- **Bulk category assignment:** Select-all checkbox + dropdown apply to checked rows. Custom category entry via "custom" option with inline text input.
- **Column sorting:** Removed redundant sort dropdown — Streamlit's `st.data_editor` provides native click-to-sort column headers.
- **CSV export/import:** `export_staging_csv()` / `import_staging_csv()` in engine.py. "Export Staged Changes" button and import expander.
- **Single-frame extraction:** `process_video_to_base64()` now extracts one frame at the video midpoint instead of a 5×2 storyboard grid. Eliminates "series of frames" / "grid of" descriptions in AI summaries. Previews show a single frame.
- **AI Prompt Profile moved to main interface:** Removed from sidebar, placed right before the "Run AI Analysis" button — changeable per analysis run.
- **Custom categories in data editor:** SelectboxColumn options dynamically include all categories found in staged assets (including previously applied custom ones).
- **Pre-analysis Advanced Features expander removed:** Case style, max chars, and naming pattern controls consolidated into the staging "Naming Settings" expander with live preview updates.
- **Re-analyze UX simplified:** Replaced per-asset row buttons + "Re-analyze All" with a single "Re-analyze Selected" button below the table. Filters `base64_cache` to checked rows and restarts Phase 2.
- **Export JSON removed:** Only "Export Staged Changes" (CSV) remains.
- **Commit cleanup:** Clears `uploaded_files`, `base64_cache`, `staged_assets`, `temp_dir`, and `analysis_done` so re-analysis works without re-upload.
- **Blank category display fixed:** `asset.get("suggested_category") or "uncategorized"` handles empty strings properly.
- **Vision model warning on first render:** Uses `cur_val` instead of `st.session_state.get(model_key, "")`, fixing the false warning on default model selection.
- **Extraction status visibility:** `st.success("✅ Step 1 complete: N files extracted")` displayed at start of Phase 2 so progress doesn't appear empty during analysis.
- **Apply button alignment:** Caption + collapsed selectbox + button in 3-column layout for proper alignment.

## [Bugfix batch 1] — 2026-07-12
- **VISION_MODEL_PREFIXES narrowed:** `"qwen2"` matched `qwen2.5-coder` (non-vision). Changed to `"qwen2.5vl"` and `"qwen2-vl"`.
- **Model dropdown shows all models:** Removed vision filter from `available_models()` so all installed Ollama models appear in the dropdown.
- **Non-vision model warning:** Sidebar now shows `⚠️ This model may not support vision analysis.` when a non-vision model is selected.
- **Duplicate emoji fixed:** Upload warning no longer renders `⚠️` twice (`icon` param vs message text).
- **Profile selector widget conflict:** Removed `index` param; uses session state init instead.
- **config.json prompts fixed:** 3 profiles (`general_broll`, `cinematography`, `motion_overlays`) stored as JSON arrays instead of strings — `get_active_prompt().replace()` would crash on those profiles. Converted to single strings.

## [Milestone 4.2] — 2026-07-11
- **Planning & Documentation overhaul:**
  - `prd.md` expanded with ~20 new feature checkboxes: prompt profiles, multi-provider AI, case styling, duplicate detection, Advanced Features expander, subdirectory CLI flag, config editor, naming templates, and more
  - `implementation_plan.md` grew from 53 to ~80 tasks across 12 layers (new Layer 12: Duplicate Detection & Feedback)
  - `audit.md` updated with 3 new bugs: static images→motion_graphics, grid description bleed, HW accel AMD AMF gap
  - `task.md` reset to point at Phase O (QoL Polish): footer, jargon removal, dismissible summary, HW accel fix
  - Out-of-scope section updated: removed items now in-scope, added new out-of-scope items (AI content detection, audio analysis, desktop app bundling)

## [Milestone 4.1] — 2026-07-11
- **Per-asset rerun loop:** Phase 2 now processes one AI call per `st.rerun()` — eliminated browser disconnection on large batches. Phase 1 (parallel extraction) still runs once.
- **Metadata fixes for Windows:**
  - `XMP-dc:Subject` split into individual `-XMP-dc:Subject=tag` args per tag (prevents Windows reading comma-separated string as a single literal tag)
  - Added `-EXIF:XPKeywords=tag_string` for images (Windows Explorer reads this for the "Tags" column in Properties)
- **Clear All button:** Dynamic `key=f"fu_{clear_counter}"` on file uploader so it forgets files when cleared. Counter incremented in the Clear All handler.
- **Output directory default:** Changed from `"."` (project root) to `~/Desktop/RenamedMedia`. Removed editable output_dir widget to prevent caching conflicts.
- **Source directory input removed:** The separate "Local folder path" text input and scanner logic eliminated. File uploader is now the sole input method.
- **Commit message persistence:** Commit result stored in `st.session_state.commit_message` so it survives reruns. Inline `st.success()`/`st.warning()` removed to prevent double messages.
- **Persistent commit message:** Simplified condition from `and not analysis_done and not analysis_in_progress` to bare `if commit_message:`.
- **`st.text_input` widget caching fix:** Dynamic `key` parameter forces widget to re-read `value` when source context changes — prevents stale output_dir display.
- **Context documentation files:**
  - Added `AGENTS.md`, `prd.md`, `implementation_plan.md`, `audit.md`, `task.md`
  - Updated `PROJECT.md`, `README.md`, `CHANGELOG.md`

## [Milestone 4.0] — 2026-07-11
- **Web application:** New `app.py` using Streamlit with 2 tabs — Upload & Analyze (with inline staging matrix) and Analytics Dashboard.
- **Module split:** Core engine extracted to `engine.py`. CLI workflow moved to `cli.py`.
- **Extended AI prompt:** Full cinematography analysis instructions (shot types, camera movement, lighting, color, composition, mood).
- **Cinematography config:** Reference tables for shot types, camera moves, lighting, color palettes, composition, moods.
- **Editable staging table:** `st.data_editor` with dropdown category, editable filename, editable tags, checkbox selection.
- **Live analytics dashboard:** Auto-refreshing stats cards, Plotly charts, filterable event timeline.
- **File upload workflow:** Upload via Streamlit, save to temp dir, parallel extraction + sequential AI analysis.

## [Milestone 3.3] — 2026-07-11
- **External configuration:** All constants moved from hardcoded globals into `config.json`.
- **Expanded categories:** Category taxonomy grew from 12 to 38 entries.
- **Custom category override:** Uncategorized assets prompt user to assign a custom category.
- **File logging:** JSON Lines logging to `logs/renamer_YYYY-MM-DD.jsonl`.
- **CLI & UX:** Cleaner startup with config validation.

## [Milestone 3.2] — 2026-07-11
- **Category validation:** AI `suggested_category` validated against allowed taxonomy; invalid values fall back to `uncategorized`.
- **Image preview downscaling:** Hi-res images downscaled in memory via FFmpeg (1024px max edge).
- **Structured AI error handling:** Typed error results with actionable messages; `--verbose` debug flag; one automatic retry on transient failures.
- **Parallel metadata commits:** `ThreadPoolExecutor` with one `ExifToolSession` per worker thread.
- **Documentation:** README, PROJECT.md, requirements.txt.

## [Milestone 3.1] — 2026-07-08
- Fixed hi-res image analysis error — num_ctx increased from 4096 to 8192.

## [Milestone 3] — 2026-07-08
- High-performance memory-based processing.
- Persistent ExifTool background processes.
- Automated hardware acceleration with CPU fallback.
