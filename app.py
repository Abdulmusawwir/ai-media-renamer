import base64
import glob
import json
import logging
import os
import shutil
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from engine import (
    ALLOWED_CATEGORIES,
    DEFAULT_CASE_STYLE,
    DEFAULT_MAX_FILENAME_CHARS,
    DEFAULT_TEMPLATE_STRING,
    LOG_DIR,
    NAMED_TEMPLATES,
    ExifToolSession,
    _format_ai_error,
    analyze_asset_with_ai,
    apply_case_style,
    apply_naming_template,
    detect_hw_accel,
    execute_commit,
    log_event,
    process_asset_to_base64,
    sanitize_name,
    setup_logging,
    truncate_filename,
    validate_category,
)

st.set_page_config(page_title="AI Media Renamer", layout="wide")
st.title("AI Media Renamer")

# -----------------------------------------------------------------------------
# Session state initialisation
# -----------------------------------------------------------------------------

if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = {}

if "staged_assets" not in st.session_state:
    st.session_state.staged_assets = []

if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False

if "base64_cache" not in st.session_state:
    st.session_state.base64_cache = {}

if "hw_accel" not in st.session_state:
    st.session_state.hw_accel = None

if "output_dir" not in st.session_state:
    st.session_state.output_dir = str(Path.home() / "Desktop" / "RenamedMedia")

if "analysis_in_progress" not in st.session_state:
    st.session_state.analysis_in_progress = False

if "analysis_index" not in st.session_state:
    st.session_state.analysis_index = 0

if "analysis_aborted" not in st.session_state:
    st.session_state.analysis_aborted = False

if "case_style" not in st.session_state:
    st.session_state.case_style = DEFAULT_CASE_STYLE

if "max_filename_chars" not in st.session_state:
    st.session_state.max_filename_chars = DEFAULT_MAX_FILENAME_CHARS

if "template_string" not in st.session_state:
    st.session_state.template_string = DEFAULT_TEMPLATE_STRING

if "clear_counter" not in st.session_state:
    st.session_state.clear_counter = 0

if "logger" not in st.session_state:
    st.session_state.logger = setup_logging()

logger = st.session_state.logger

# Allowed categories as list for dropdown use
CATEGORY_LIST = list(ALLOWED_CATEGORIES)

# -----------------------------------------------------------------------------
# Helper: load log data for analytics
# -----------------------------------------------------------------------------

def load_log_entries():
    log_dir = LOG_DIR
    if not log_dir.exists():
        return []
    entries = []
    for log_path in sorted(glob.glob(str(log_dir / "renamer_*.jsonl"))):
        with open(log_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return entries

# -----------------------------------------------------------------------------
# Tab 1: Upload & Analyze
# -----------------------------------------------------------------------------

tab_upload, tab_analytics = st.tabs(
    ["Upload & Analyze", "Analytics Dashboard"]
)

with tab_upload:
    st.subheader("Upload Media Files")

    uploaded_files = st.file_uploader(
        "Choose video or image files",
        type=["mp4", "mov", "avi", "mkv", "webm", "jpg", "jpeg", "png", "webp", "gif"],
        accept_multiple_files=True,
        key=f"fu_{st.session_state.clear_counter}",
    )

    if uploaded_files:
        existing = st.session_state.get("uploaded_files", {})
        new_names = {uf.name for uf in uploaded_files}
        if set(existing.keys()) != new_names:
            st.session_state.temp_dir = tempfile.mkdtemp(prefix="renamer_upload_")
            saved = {}
            for uf in uploaded_files:
                dest = Path(st.session_state.temp_dir) / uf.name
                dest.write_bytes(uf.getbuffer())
                saved[uf.name] = dest
            st.session_state.uploaded_files = saved
            st.session_state.analysis_done = False
            st.session_state.analysis_in_progress = False
            st.session_state.analysis_aborted = False
            st.session_state.staged_assets = []
            st.session_state.base64_cache = {}

    # Clear All button — always visible when files or staged assets exist
    if st.session_state.get("uploaded_files") or st.session_state.staged_assets:
        if st.button("Clear All Files", type="secondary"):
            temp_dir = st.session_state.get("temp_dir")
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
            for key in ["uploaded_files", "base64_cache", "staged_assets", "temp_dir"]:
                st.session_state.pop(key, None)
            st.session_state.analysis_done = False
            st.session_state.analysis_in_progress = False
            st.session_state.clear_counter += 1
            st.rerun()

    # ------------------------------------------------------------------
    # Phase 2: Per-asset rerun loop (one AI call per script execution)
    # ------------------------------------------------------------------
    if st.session_state.analysis_in_progress:
        items = list(st.session_state.get("base64_cache", {}).items())
        total = len(items)
        idx = st.session_state.analysis_index

        if total > 0:
            st.progress(idx / total, text=f"Analyzed {idx}/{total} assets")

        if 0 <= idx < total:
            name, b64 = items[idx]
            st.info(f"**Analyzing:** {name} ({idx+1}/{total})")

            col_stop, _ = st.columns([1, 4])
            with col_stop:
                if st.button("Stop Analysis"):
                    st.session_state.analysis_aborted = True

            if st.session_state.analysis_aborted:
                st.warning(f"Analysis stopped at {idx}/{total} assets.")
                st.session_state.analysis_in_progress = False
                st.session_state.analysis_done = bool(st.session_state.staged_assets)
            else:
                ai_result = analyze_asset_with_ai(b64, verbose=False)

                if ai_result['ok']:
                    ai_data = ai_result['data']
                    safe_name = sanitize_name(ai_data['new_filename'])
                    safe_name = apply_case_style(safe_name, st.session_state.case_style)
                    safe_name = truncate_filename(safe_name, st.session_state.max_filename_chars)
                    suggested_cat = ai_data.get('suggested_category', '')
                    staged_category, _ = validate_category(suggested_cat)

                    staged_assets = st.session_state.get("staged_assets", [])
                    staged_assets.append({
                        "original_path": st.session_state.uploaded_files[name],
                        "original_name": name,
                        "staged_name": safe_name,
                        "category": staged_category,
                        "tags": ai_data.get('tags', []),
                        "summary": ai_data.get('overall_visual_summary', ''),
                        "suggested_category": suggested_cat,
                    })
                    st.session_state.staged_assets = staged_assets

                    log_event(logger, "INFO", "ai_analysis_success", file_name=name, details={
                        "staged_name": safe_name, "category": staged_category
                    })
                else:
                    error_msg = _format_ai_error(ai_result)
                    st.warning(f"AI analysis failed for {name}: {error_msg}")
                    log_event(logger, "ERROR", "ai_analysis_failed", file_name=name, details={"error": error_msg})

                st.session_state.analysis_index = idx + 1
                st.rerun()
        else:
            st.session_state.analysis_in_progress = False
            st.session_state.analysis_done = True
            n = len(st.session_state.get("staged_assets", []))
            if n:
                st.success(f"Analysis complete: {n} assets staged.")
            else:
                st.warning("No assets were staged.")

    # ------------------------------------------------------------------
    # Persistent status (visible after analysis completes)
    # ------------------------------------------------------------------
    if st.session_state.analysis_done:
        n = len(st.session_state.staged_assets)
        if n:
            st.success(f"✅ Analysis complete: {n} asset{'s' if n != 1 else ''} ready for review below.")

    # ------------------------------------------------------------------
    # Advanced Features (collapsed by default)
    # ------------------------------------------------------------------
    if not st.session_state.analysis_in_progress and not st.session_state.analysis_done \
            and st.session_state.get("uploaded_files"):
        with st.expander("Advanced Features"):
            preset_names = list(NAMED_TEMPLATES.keys())
            template_presets = preset_names + ["custom"]

            current_pattern = st.session_state.template_string
            matched = "custom"
            for name, pat in NAMED_TEMPLATES.items():
                if pat == current_pattern:
                    matched = name
                    break
            preset_idx = template_presets.index(matched)

            def _on_template_preset():
                name = st.session_state.template_preset_sel
                if name in NAMED_TEMPLATES:
                    st.session_state.template_string = NAMED_TEMPLATES[name]

            def _template_label(name):
                return f"{name}  ({NAMED_TEMPLATES[name]})" if name in NAMED_TEMPLATES else name

            col_tmpl, col_pat = st.columns([1, 2])
            with col_tmpl:
                st.selectbox(
                    "Naming template",
                    template_presets,
                    index=preset_idx,
                    key="template_preset_sel",
                    on_change=_on_template_preset,
                    format_func=_template_label,
                    help="Choose a preset or select 'custom' to type your own pattern. "
                         "The template generates the raw name; then the case style below transforms it.",
                )
            with col_pat:
                st.text_input(
                    "Pattern",
                    key="template_string",
                    help="{category}, {topic}, {description}, {date} \u2014 in any order. "
                         "Example: {category}_{topic}_{description}. "
                         "The case style below overrides any capitalisation in this pattern.",
                )
                _demo = {"category": "aerial_drone", "topic": "golden_hour",
                         "description": "aerial_coastline", "new_filename": "golden_hour_aerial_coastline"}
                _raw = apply_naming_template(st.session_state.template_string, _demo)
                _styled = apply_case_style(_raw, st.session_state.case_style)
                _final = truncate_filename(_styled, st.session_state.max_filename_chars)
                st.caption(f"Preview: {_final}")

            col_case, col_chars = st.columns(2)
            with col_case:
                st.selectbox(
                    "Filename case style",
                    ["snake_case", "camelCase", "kebab-case", "pascal_case", "lowercase"],
                    index=["snake_case", "camelCase", "kebab-case", "pascal_case", "lowercase"]
                    .index(st.session_state.case_style),
                    key="case_style",
                    help="Applied AFTER the naming template. "
                         "Overrides letter case from the pattern output. "
                         "snake_case: golden_hour_aerial | "
                         "camelCase: goldenHourAerial | "
                         "kebab-case: golden-hour-aerial | "
                         "pascal_case: GoldenHourAerial | "
                         "lowercase: goldenhouraerial",
                )
            with col_chars:
                st.number_input(
                    "Max filename characters (0 = no limit)",
                    min_value=0, max_value=200, step=5,
                    key="max_filename_chars",
                    help="Truncates the filename to this many characters (applied last). "
                         "0 = no limit.",
                )

    # ------------------------------------------------------------------
    # Analysis trigger: button + Phase 1 (only when idle)
    # ------------------------------------------------------------------
    if not st.session_state.analysis_in_progress and not st.session_state.analysis_done \
            and st.session_state.get("uploaded_files"):
        col1, col2 = st.columns([1, 3])
        with col1:
            analyze_btn = st.button("Run AI Analysis", type="primary")
        with col2:
            st.caption("Upload media files above, then click 'Run AI Analysis' to begin.")

        if analyze_btn:
            try:
                hw_accel = detect_hw_accel()
                st.session_state.hw_accel = hw_accel
                if hw_accel:
                    st.info(f"Hardware Acceleration: FFmpeg will use '{hw_accel}'")
                else:
                    st.info("No hardware acceleration detected, using CPU fallback.")

                # Phase 1: Parallel extraction
                st.write("**Step 1:** Preparing preview frames...")
                progress_bar = st.progress(0, text="Extracting frames...")
                base64_results = {}

                files_list = list(st.session_state.uploaded_files.values())
                with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
                    future_map = {
                        executor.submit(process_asset_to_base64, fp, hw_accel): fp
                        for fp in files_list
                    }
                    done_count = 0
                    for future in as_completed(future_map):
                        fp = future_map[future]
                        b64 = future.result()
                        if b64:
                            base64_results[fp.name] = b64
                        else:
                            st.warning(f"Extraction failed: {fp.name}")
                            log_event(logger, "ERROR", "extraction_failed", file_name=fp.name)
                        done_count += 1
                        progress_bar.progress(
                            done_count / len(files_list),
                            text=f"Extracted {done_count}/{len(files_list)}"
                        )

                if not base64_results:
                    st.error("No files could be extracted. Aborting.")
                    st.stop()

                st.session_state.base64_cache = base64_results
                st.session_state.staged_assets = []
                st.session_state.analysis_index = 0
                st.session_state.analysis_in_progress = True
                st.session_state.analysis_done = False
                st.session_state.analysis_aborted = False
                st.rerun()
            except Exception as exc:
                import traceback
                st.error(f"Analysis crashed: {exc}")
                with st.expander("Show full traceback"):
                    st.code(traceback.format_exc(), language="python")
                log_event(logger, "ERROR", "analysis_crashed",
                          details={"error": str(exc), "traceback": traceback.format_exc()})

    # Inline staging matrix (shown after analysis)
    if st.session_state.analysis_done and st.session_state.staged_assets:
        st.divider()
        st.subheader("Staging Matrix \u2014 Review & Edit Before Committing")
        st.caption("Edit filename, category, or tags for any asset. "
                   "Use the dropdown for common categories or type a custom one.")

        staged = st.session_state.staged_assets
        template = st.session_state.template_string
        case_style = st.session_state.case_style
        max_chars = st.session_state.max_filename_chars

        table_rows = []
        for asset in staged:
            rendered = apply_naming_template(template, {
                "category": asset.get("category", "uncategorized"),
                "topic": asset.get("topic", ""),
                "description": asset.get("description", ""),
                "new_filename": asset["staged_name"],
            })
            rendered = apply_case_style(rendered, case_style)
            rendered = truncate_filename(rendered, max_chars)
            table_rows.append({
                "select": True,
                "original_name": asset["original_name"],
                "proposed_filename": rendered,
                "category": asset["category"] if asset["category"] != "uncategorized"
            else asset.get("suggested_category", "uncategorized"),
                "tags": ", ".join(asset["tags"]),
                "summary": asset["summary"],
            })

        df = pd.DataFrame(table_rows)

        edited_df = st.data_editor(
            df,
            column_config={
                "select": st.column_config.CheckboxColumn("Apply", default=True),
                "original_name": st.column_config.TextColumn("Original File", disabled=True, width="small"),
                "proposed_filename": st.column_config.TextColumn("Proposed Filename", width="medium"),
                "category": st.column_config.SelectboxColumn(
                    "Category",
                    options=sorted(CATEGORY_LIST) + ["uncategorized"],
                    width="medium",
                ),
                "tags": st.column_config.TextColumn("Tags (comma-separated)", width="large"),
                "summary": st.column_config.TextColumn("Summary", disabled=True, width="large"),
            },
            hide_index=True,
            width='stretch',
            num_rows="fixed",
        )

        with st.expander("Show preview thumbnails"):
            cols = st.columns(min(len(staged), 5))
            for i, asset in enumerate(staged):
                col_idx = i % 5
                with cols[col_idx]:
                    b64 = st.session_state.base64_cache.get(asset["original_name"])
                    if b64:
                        st.image(base64.b64decode(b64), caption=asset["original_name"], width=150)
                    else:
                        st.caption(f"No preview: {asset['original_name']}")

        sort_folders = st.checkbox("Sort assets into categorized subfolders", value=True)

        col_commit, col_refresh = st.columns([1, 3])
        with col_commit:
            commit_btn = st.button("Commit Selected", type="primary")
        with col_refresh:
            st.caption("Selected rows will be renamed and tagged. Unchecked rows are skipped.")

        if commit_btn:
            try:
                selected = edited_df[edited_df["select"]]
                if selected.empty:
                    st.warning("No assets selected. Check the checkbox next to assets to commit.")
                else:
                    target_dir = Path(st.session_state.output_dir)
                    target_dir.mkdir(parents=True, exist_ok=True)
                    committed = 0
                    failed = 0
                    progress = st.progress(0, text="Committing...")

                    for idx, row in selected.iterrows():
                        asset = staged[idx]

                        asset["staged_name"] = row["proposed_filename"]
                        new_cat = row["category"].strip().lower().replace(" ", "_")
                        safe_chars = [c for c in new_cat if c.isalpha() or c.isdigit() or c in ('_', '-')]
                        safe_cat = "".join(safe_chars).strip('_')
                        if safe_cat:
                            asset["category"] = safe_cat
                        asset["tags"] = [t.strip() for t in row["tags"].split(",") if t.strip()]

                        exif = ExifToolSession()
                        result = execute_commit(asset, target_dir, sort_folders, exif)
                        exif.close()

                        if result and not (isinstance(result, str) and result.startswith("ERROR:")):
                            committed += 1
                            log_event(logger, "INFO", "file_committed", file_name=asset["original_name"],
                                      details={"new_path": str(result), "category": asset["category"]})
                        else:
                            failed += 1
                            err = result[6:] if isinstance(result, str) and result.startswith("ERROR:") else "unknown"
                            log_event(logger, "ERROR", "file_commit_failed", file_name=asset["original_name"],
                                      details={"error": err})

                        progress.progress((idx + 1) / len(selected))

                    log_event(logger, "INFO", "session_end", details={
                        "committed": committed, "failed": failed, "total": len(selected), "mode": "web_batch"
                    })

                    temp_dir = st.session_state.get("temp_dir")
                    if temp_dir:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    st.session_state.pop("temp_dir", None)

                    if failed:
                        msg = f"Committed {committed} assets. {failed} failed."
                        st.toast(msg)
                    else:
                        msg = f"All {committed} assets committed successfully to {target_dir.resolve()}!"
                        st.toast(msg)
                        st.session_state.staged_assets = []
                        st.session_state.analysis_done = False
            except Exception as exc:
                import traceback
                st.error(f"Commit crashed: {exc}")
                with st.expander("Show full traceback"):
                    st.code(traceback.format_exc(), language="python")
                log_event(logger, "ERROR", "commit_crashed",
                          details={"error": str(exc), "traceback": traceback.format_exc()})

# -----------------------------------------------------------------------------
# Tab 2: Analytics Dashboard
# -----------------------------------------------------------------------------

with tab_analytics:
    col_title, col_reset = st.columns([3, 1])
    with col_title:
        st.subheader("Analytics Dashboard")
    with col_reset:
        if st.button("Reset All", type="secondary"):
            temp_dir = st.session_state.get("temp_dir")
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
            reset_keys = ["base64_cache", "staged_assets", "analysis_done", "uploaded_files",
                          "temp_dir", "output_dir", "logger", "analysis_in_progress",
                          "analysis_index", "analysis_aborted", "clear_counter"]
            for key in reset_keys:
                st.session_state.pop(key, None)
            for h in logging.getLogger('video_renamer').handlers[:]:
                h.close()
                logging.getLogger('video_renamer').removeHandler(h)
            for log_path in LOG_DIR.glob("renamer_*.jsonl"):
                log_path.unlink(missing_ok=True)
            st.rerun()

    # Auto-refresh every 10 seconds
    st_autorefresh(interval=10000, key="analytics_autorefresh")

    entries = load_log_entries()
    if not entries:
        st.info("No log entries found yet. Process some files to see analytics here.")
        st.stop()

    # Stats cards
    total = len(entries)
    committed = sum(1 for e in entries if e.get("event") == "file_committed")
    errors = sum(1 for e in entries if e.get("level") == "ERROR")
    skipped = sum(1 for e in entries if e.get("event") == "file_skipped")

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("Total Events", total)
    sc2.metric("Committed", committed)
    sc3.metric("Errors", errors)
    sc4.metric("Skipped", skipped)

    # Category distribution
    cat_counter = Counter()
    for e in entries:
        if e.get("event") == "file_committed":
            details = e.get("details", {}) or {}
            cat = details.get("category", "unknown")
            cat_counter[cat] += 1

    if cat_counter:
        cat_df = pd.DataFrame(
            cat_counter.most_common(),
            columns=["Category", "Count"]
        )
        fig_pie = px.pie(cat_df, names="Category", values="Count",
                         title="Category Distribution",
                         color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_pie.update_layout(height=350)
        st.plotly_chart(fig_pie, width='stretch')

    # Daily activity
    day_counter = Counter()
    for e in entries:
        ts = e.get("timestamp", "")
        day = ts[:10] if ts else ""
        if day:
            day_counter[day] += 1

    if day_counter:
        day_df = pd.DataFrame(
            sorted(day_counter.items()),
            columns=["Date", "Events"]
        )
        fig_bar = px.bar(day_df, x="Date", y="Events",
                         title="Daily Activity",
                         color_discrete_sequence=["#3b82f6"])
        fig_bar.update_layout(height=350)
        st.plotly_chart(fig_bar, width='stretch')

    # Filterable timeline
    st.subheader("Event Timeline")

    levels = ["all"] + sorted(set(e.get("level", "INFO") for e in entries))
    events = ["all"] + sorted(set(e.get("event", "") for e in entries))

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        filter_level = st.selectbox("Filter by level", levels, key="ana_level")
    with col_f2:
        filter_event = st.selectbox("Filter by event", events, key="ana_event")

    filtered = entries
    if filter_level != "all":
        filtered = [e for e in filtered if e.get("level") == filter_level]
    if filter_event != "all":
        filtered = [e for e in filtered if e.get("event") == filter_event]

    if filtered:
        rows = []
        for e in filtered:
            details = e.get("details", {}) or {}
            rows.append({
                "Timestamp": e.get("timestamp", ""),
                "Level": e.get("level", ""),
                "Event": e.get("event", ""),
                "File": e.get("file", "-"),
                "Details": json.dumps(details)[:120],
            })
        timeline_df = pd.DataFrame(rows)
        timeline_df = timeline_df.sort_values("Timestamp", ascending=False)
        st.dataframe(timeline_df, width='stretch', hide_index=True)
    else:
        st.info("No matching entries.")

# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------

st.markdown(
    "<hr style='margin-top: 3rem; margin-bottom: 0.5rem; border-color: #334155;'>"
    "<p style='text-align: center; color: #94a3b8; font-size: 0.8rem;'>"
    "Made with love from Tanzania by "
    "<a href='https://github.com/Abdulmusawwir/ai-media-renamer' "
    "   style='color: #60a5fa; text-decoration: none;'>Abdul Musawwir</a>"
    "</p>",
    unsafe_allow_html=True,
)
