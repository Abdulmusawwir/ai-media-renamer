# Changelog

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
  - Added `AGENTS.md` — master orchestrator with mandatory file read order and verification gate
  - Added `system_prompt.md` — codified language, architecture, naming, and framework rules
  - Added `prd.md` — product requirements with MVP checklist and explicit out-of-scope list
  - Added `implementation_plan.md` — 53-task milestone backlog across 11 technical layers
  - Added `audit.md` — bug tracker, orphaned code, and PRD divergence log
  - Added `task.md` — active session scratchpad
  - Updated `PROJECT.md`, `README.md`, `CHANGELOG.md` to reflect current architecture

## [Milestone 4.0] — 2026-07-11
- **Web application:** New `app.py` using Streamlit with 2 tabs — Upload & Analyze (with inline staging matrix) and Analytics Dashboard (auto-refreshing charts and timeline).
- **Module split:** Core engine extracted to `engine.py`. CLI workflow moved to `cli.py`. Old monolithic script deleted.
- **Extended AI prompt:** Added 9 more Islamic landmarks (Blue Mosque, Sheikh Zayed, Al-Aqsa, Imam Reza, Hassan II, Badshahi, Faisal, Cordoba, Wazir Khan) and full cinematography analysis instructions (shot types, camera movement, lighting, color, composition, mood).
- **Cinematography config:** New `cinematography` section in `config.json` with categorized lookup tables for shot types, camera moves, lighting, color palettes, composition techniques, and moods.
- **Editable staging table:** `st.data_editor` with dropdown category, editable filename, editable tags, and checkbox selection. Category override available for every asset, not just uncategorized.
- **Live analytics dashboard:** Auto-refreshing every 10 seconds with stats cards, Plotly category pie chart, daily bar chart, and filterable event timeline reading from JSONL logs.
- **File upload workflow:** Users upload files via Streamlit's file uploader. Files saved to temp directory. Parallel extraction + sequential AI analysis with progress bars.

## [Milestone 3.3] — 2026-07-11
- **External configuration:** All configurable constants (AI prompt, categories, model settings, preview params) moved from hardcoded globals into `config.json`.
- **Expanded categories:** Category taxonomy grew from 12 to 38 entries, covering footage, graphics, VFX, and media types.
- **Custom category override:** Uncategorized assets now prompt the user to assign a custom category during staging review.
- **File logging:** Pipeline logs every event (AI analysis, commits, errors, skips) as JSON Lines to `logs/renamer_YYYY-MM-DD.jsonl`.
- **Streamlit analytics dashboard:** Consolidated into `app.py` Tab 2 — auto-refreshing stats cards, Plotly charts, and filterable event timeline from JSONL logs.
- **CLI & UX:** Cleaner startup with config validation, more informative progress messages.

## [Milestone 3.2] — 2026-07-11
- **Category validation:** AI `suggested_category` is validated against the allowed taxonomy; invalid or missing values fall back to `uncategorized` with optional verbose logging.
- **Image preview downscaling:** Hi-res images are downscaled in memory via FFmpeg (1024px max edge, JPEG) before AI analysis; original files on disk are never modified.
- **Structured AI error handling:** `analyze_asset_with_ai` returns typed error results (JSON parse, missing keys, Ollama errors) with actionable messages; added `--verbose` / `-v` CLI flag for raw model response debug output; one automatic retry on transient Ollama failures.
- **Parallel metadata commits:** Apply All path uses `ThreadPoolExecutor` with one `ExifToolSession` per worker thread; interactive mode stays sequential.
- **Documentation:** Updated README, PROJECT.md, and added `requirements.txt`.

## [Milestone 3.1] — 2026-07-08
- Fixed error when analyzing hi-res images which caused an AI parse verification mismatch error — by changing num_ctx from 4096 to 8192 in the `analyze_asset_with_ai(base64_img)` function.

## [Milestone 3] — 2026-07-08
- Implemented high-performance memory-based processing.
- Switched to persistent ExifTool background processes.
- Simplified terminal output for a user-friendly experience.
- Added automated hardware acceleration with CPU fallback.
