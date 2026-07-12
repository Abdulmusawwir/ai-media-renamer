# Changelog

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
