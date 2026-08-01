from __future__ import annotations

import base64
import glob
import json
import logging
import os
import shutil
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from engine import (
    ALLOWED_CATEGORIES,
    AUDIO_EXTENSIONS,
    CASE_STYLE_LABELS,
    CASE_STYLE_OPTIONS,
    DEFAULT_CASE_STYLE,
    DEFAULT_MAX_FILENAME_CHARS,
    DEFAULT_TEMPLATE_STRING,
    DOCUMENT_EXTENSIONS,
    EXTRACTION_WORKERS,
    IMAGE_EXTENSIONS,
    LOG_DIR,
    MAX_UPLOAD_SIZE,
    NAMED_TEMPLATES,
    PROMPT_PROFILES,
    VIDEO_EXTENSIONS,
    VERSION,
    ExifToolSession,
    _format_ai_error,
    _is_vision_model,
    analyze_document_with_ai,
    apply_case_style,
    apply_naming_template,
    check_environment,
    check_for_updates,
    check_ollama_health,
    config,
    detect_hw_accel,
    execute_commit,
    export_staging_csv,
    extract_text_from_file,
    find_duplicates,
    get_active_profile,
    get_active_prompt,
    get_provider,
    import_staging_csv,
    list_providers,
    delete_session,
    list_sessions,
    load_api_key,
    load_session,
    log_event,
    normalize_category,
    process_asset_to_base64,
    reload_config,
    restore_default_config,
    sanitize_name,
    save_api_key,
    save_config,
    save_session,
    set_active_profile,
    setup_logging,
    stream_model_download,
    truncate_filename,
    validate_category,
    wipe_local_model,
    log_commit_batch,
    rollback_last_batch,
    list_undo_batches,
    extract_audio_from_video,
    _has_audio_track,
    transcribe_audio,
)

_ICON_PATH = Path(sys._MEIPASS) / "icon.ico" if getattr(sys, "frozen", False) else Path(__file__).parent / "icon.ico"
st.set_page_config(
    page_title="AI Media Renamer",
    page_icon=str(_ICON_PATH) if _ICON_PATH.exists() else "🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Commit success notification sound (0.3s whoosh, base64-encoded WAV)
_COMMIT_BEEP = "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KPds9wT4FfiD99H30ffk99z33/fy9/73A/gg+Dn40vfT9+X33PfV9873hfe899n3tffu98X33/fj99P30PfV97/3xvfj9+H3z/fx98z37PfT9/L3rff/98/37vf99/z33ffy99H39ffs9/f3rfcH+Oz38ff09/D34Pf299v3yvfo99D34vfk98b3r/f097r34ffm99n3rPfj98j38vfj98D39Pfz99D3yPfO98z36Pff9+P3yvfO99z35PfS99D3xPfR9+X32/fZ9+j37Pff98z37/fo9+b3vPfp9/334vf898f37Pf09/z3zvf29+T3y/fz99335vfU99X37vfY98z37PfU9/n39Pfe9/j3//fB9/f37/fz9+f37vfz99T33ffo9+j37vfz98b3+ffj9/b30vf09/D3z/fz9/T3y/fz99z3wffm99j34ffr9+z30/fk99v39vfq9/D36/fg9/D37Pfp99/35vfl99j38ffY9+X37/fo98z3zffo99n37vfe98/37fey9/33sff997X3/fe59/33tff99733/fe19/33uff997X3/fe99/33uff99733/fe99/33uff99733/fe99/33uff99733/fe99/33uff99733/fe99/33uff99733/fe99/33uff99733/fe99/33uff99733/fe99/33uff99733/fe99/33uff99733/fe99/33uff99733/fe99/33gA="

# Handle deferred rerun (used by notification sound — plays audio before rerun)
if st.session_state.pop("_pending_rerun", False):
    st.rerun()

# Hide Streamlit chrome + dark theme global styles + keyboard shortcuts
st.markdown("""
<style>
#MainMenu {visibility: hidden;}
.stAppDeployButton {display: none;}
footer {visibility: hidden;}
[data-testid="stStatusWidget"] {visibility: hidden;}
div[data-testid="stDecoration"] {display: none;}

/* Global dark theme refinements */
[data-testid="stSidebar"] > div:first-child {
    background-color: #09090B;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
    color: #FAFAFA;
}

/* Streamlit toast dark theme fix */
div[data-testid="stToast"] {
    background-color: #27272A;
    color: #FAFAFA;
    border: 1px solid #3F3F46;
}

/* Status badges */
div[data-testid="stStatus"] {
    border: 1px solid #27272A;
}

/* File uploader hover feedback */
[data-testid="stFileUploader"] {
    transition: border-color 0.2s, background-color 0.2s;
    border-radius: 8px;
}
[data-testid="stFileUploader"]:hover {
    border-color: #3B82F6 !important;
    background-color: rgba(59, 130, 246, 0.05);
}
[data-testid="stFileUploader"]:has(.uploadedFile) {
    border-color: #22C55E !important;
}

/* Dataframe responsive overflow */
[data-testid="stDataFrame"] {
    overflow-x: auto;
    max-width: 100%;
    border-radius: 8px;
}
[data-testid="stDataFrameHeader"] {
    background-color: #18181B;
}

/* Column containers prevent page-level horizontal scroll */
.stColumn {
    max-width: 100%;
    overflow: hidden;
}

/* Expander styling */
[data-testid="stExpander"] {
    border: 1px solid #27272A;
    border-radius: 8px;
}

/* Tab styling */
[data-testid="stTabs"] [data-testid="stTab"] {
    border-radius: 8px 8px 0 0;
}

/* Download button subtle style */
.st-key-export_csv_btn button,
[data-testid="stDownloadButton"] button {
    width: 100%;
}
</style>
<script>
// Keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Ctrl+Enter: trigger Run AI Analysis
    if (e.ctrlKey && e.key === 'Enter') {
        e.preventDefault();
        const btns = window.parent.document.querySelectorAll('[data-testid="stButton"] button');
        for (const btn of btns) {
            if (btn.textContent.includes('Run AI Analysis')) {
                btn.click();
                break;
            }
        }
    }
    // Ctrl+Shift+C: trigger Commit Selected
    if (e.ctrlKey && e.shiftKey && e.key === 'C') {
        e.preventDefault();
        const btns = window.parent.document.querySelectorAll('[data-testid="stButton"] button');
        for (const btn of btns) {
            if (btn.textContent.includes('Commit Selected')) {
                btn.click();
                break;
            }
        }
    }
    // Escape: stop analysis
    if (e.key === 'Escape') {
        const btns = window.parent.document.querySelectorAll('[data-testid="stButton"] button');
        for (const btn of btns) {
            if (btn.textContent.includes('Stop Analysis')) {
                btn.click();
                break;
            }
        }
    }
});
</script>
""", unsafe_allow_html=True)

st.title(":material/movie_edit: AI Media Renamer")

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

if "text_cache" not in st.session_state:
    st.session_state.text_cache = {}

if "audio_transcription_cache" not in st.session_state:
    st.session_state.audio_transcription_cache = {}

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

if "provider_info" not in st.session_state:
    st.session_state.provider_info = config.get("model", {}).get("last_provider", "ollama")

if "api_key_stored" not in st.session_state:
    st.session_state.api_key_stored = False

if "env_check" not in st.session_state:
    st.session_state.env_check = None

if "model_downloading" not in st.session_state:
    st.session_state.model_downloading = False

if "model_download_gen" not in st.session_state:
    st.session_state.model_download_gen = None

if "analysis_errors" not in st.session_state:
    st.session_state.analysis_errors = []

if "clear_counter" not in st.session_state:
    st.session_state.clear_counter = 0

if "logger" not in st.session_state:
    st.session_state.logger = setup_logging()

logger = st.session_state.logger

# Allowed categories as list for dropdown use
CATEGORY_LIST = list(ALLOWED_CATEGORIES)

# -----------------------------------------------------------------------------
# Telemetry opt-in dialog (first launch)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Environment check (runs once, cached in session state)
# -----------------------------------------------------------------------------

if st.session_state.env_check is None and not st.session_state.model_downloading:
    st.session_state.env_check = check_environment()

# -----------------------------------------------------------------------------
# Sidebar: AI Provider & Environment
# -----------------------------------------------------------------------------

def _on_api_key_change() -> None:
    """Save the API key entered in the sidebar text input to the system keychain."""
    provider = st.session_state.provider_info
    key = st.session_state.get(f"api_key_{provider}", "")
    save_api_key(provider, key)
    st.session_state.api_key_stored = bool(key)
    prov_inst = get_provider(provider)
    prov_inst.api_key = key


def _on_model_change() -> None:
    """Persist the selected model to config when the model dropdown changes."""
    provider = st.session_state.provider_info
    model = st.session_state.get(f"model_{provider}", "")
    config["model"]["providers"].setdefault(provider, {})["selected_model"] = model
    config["model"]["name"] = model
    save_config()


with st.sidebar:
    st.header(":material/smart_toy: AI Provider")

    analysis_active = st.session_state.get("analysis_in_progress", False)

    # Only the local engine is currently selectable; cloud providers are
    # implemented but disabled (no API keys for testing) — see audit.md §2.
    all_providers = list_providers()
    if st.session_state.provider_info != "ollama":
        st.caption(f"Previously configured provider '{st.session_state.provider_info}' "
                   "is not available — using Local (Ollama).")
        st.session_state.provider_info = "ollama"

    chosen = st.radio(
        "Engine",
        ["Local (Ollama)"],
        index=0,
        key="provider_radio",
        help="Local mode uses Ollama. Cloud modes are not yet available.",
    )
    new_provider = "ollama"

    cloud_names = {
        "gemini": "Gemini", "openai": "OpenAI", "anthropic": "Anthropic",
        "groq": "Groq", "openrouter": "OpenRouter",
    }
    pending = [cloud_names.get(p, p) for p in all_providers if p != "ollama"]
    st.caption(f"Cloud providers (coming soon): {', '.join(pending)}")

    if analysis_active:
        st.caption("Analysis in progress — settings locked")
        st.caption(f"Provider: {st.session_state.provider_info.title()}")
        st.caption(f"Model: {config['model']['name']}")
    else:
        # Model dropdown
        p = get_provider(new_provider)
        models = p.available_models()
        model_key = f"model_{new_provider}"
        if models:
            cur_val = st.session_state.get(model_key, p.model or models[0])
            if new_provider == "ollama" and cur_val and not _is_vision_model(cur_val):
                vl_first = next((m for m in models if _is_vision_model(m)), None)
                if vl_first:
                    cur_val = vl_first
                    config["model"]["providers"].setdefault("ollama", {})["selected_model"] = vl_first
                    config["model"]["name"] = vl_first
                    save_config()
            m_idx = models.index(cur_val) if cur_val in models else 0
            st.selectbox("Model", models, index=m_idx, key=model_key, on_change=_on_model_change)
        else:
            st.caption("No models available.")

        # Warn if selected model is not vision-capable
        if new_provider == "ollama" and models:
            cur_val = st.session_state.get(model_key, p.model or models[0])
            if cur_val and not _is_vision_model(cur_val):
                st.caption(":material/warning: This model may not support vision analysis.")

        # Ollama health status (refreshed via the "Refresh Status" button below)
        if new_provider == "ollama":
            health = st.session_state.get("ollama_health")
            if health is None:
                health = check_ollama_health()
                st.session_state.ollama_health = health
            if health["connected"]:
                st.markdown(f":material/check_circle: **Ollama** — {health['model_count']} models")
            else:
                st.markdown(":material/error: **Ollama** — disconnected")

        # API key (cloud providers only)
        if new_provider != "ollama":
            api_key = load_api_key(new_provider)
            st.text_input(
                "API Key", type="password", key=f"api_key_{new_provider}",
                value=api_key,
                help=f"API key for {new_provider}. Saved to your system keychain.",
                on_change=_on_api_key_change,
            )
            if api_key:
                st.caption(":material/check: Key saved in system keychain")


    st.space()
    st.caption("Environment status")

    env = st.session_state.env_check
    if env:
        if new_provider == "ollama":
            for key, label in [("ffmpeg", "FFmpeg"), ("exiftool", "ExifTool"),
                               ("ollama_running", "Ollama Daemon"), ("model_available", "Vision Model")]:
                ok = env.get(key, False)
                status = "green" if ok else "red"
                st.badge(label, color=status)

            vision_models = env.get("vision_models", [])
            if vision_models:
                names = ", ".join(vision_models[:3])
                if len(vision_models) > 3:
                    names += f" (+{len(vision_models) - 3} more)"
                st.caption(f"Installed: {names}")
            elif not env.get("ollama_running"):
                st.error("Ollama is not running. Start Ollama and click Refresh.")
            elif not env.get("model_available"):
                st.info("No vision model installed yet.")
        else:
            for key, label in [("ffmpeg", "FFmpeg"), ("exiftool", "ExifTool")]:
                ok = env.get(key, False)
                status = "green" if ok else "red"
                st.badge(label, color=status)
            has_key = bool(load_api_key(new_provider))
            pretty_name = new_provider.capitalize()
            st.badge(f"{pretty_name} API Key", color="green" if has_key else "red")
            if has_key:
                st.caption(f"Routing execution via {pretty_name}")

    if st.button(":material/refresh: Refresh Status", key="refresh_status"):
        st.session_state.env_check = None
        st.session_state.ollama_health = None
        st.rerun()

    st.space()
    if st.button(":material/system_update: Check for Updates", key="check_updates"):
        with st.spinner("Checking..."):
            info = check_for_updates()
        if info.get("update_available"):
            st.warning(f"Update available: {info['current']} → {info['latest']}")
            st.markdown(f"[Download Latest Release]({info['download_url']})")
        elif info.get("ok"):
            st.success(f"Up to date ({info['current']})")
        else:
            st.caption(f"Could not check: {info.get('error', 'unknown')}")

    st.space()

    if new_provider == "ollama" and env and env.get("ollama_running") and not env.get("model_available"):
        if st.button(":material/download: Download Vision Model", type="primary", key="download_model"):
            st.session_state.model_downloading = True
            st.rerun()

# -----------------------------------------------------------------------------
# Bootstrap diagnostics panel (blocks upload if critical dependency missing)
# -----------------------------------------------------------------------------

env = st.session_state.env_check

if env and env.get("errors"):
    critical = False
    for err in env["errors"]:
        if "FFmpeg" in err or "ExifTool" in err:
            critical = True
            st.error(err, icon=":material/error:")
    if critical:
        st.stop()

if st.session_state.model_downloading:
    download_model = st.session_state.get("download_model_name", "qwen2.5vl:7b")
    with st.status(f"Downloading {download_model}", expanded=True) as download_status:
        progress_bar = st.progress(0)
        status_text = st.empty()
        st.caption("Model download progress updates every few seconds.")
        if st.button(":material/cancel: Cancel Download", key="cancel_download",
                     help="Cancels UI polling — Ollama download continues in background"):
            st.session_state.model_downloading = False
            st.session_state.model_download_gen = None
            st.rerun()

        gen = st.session_state.model_download_gen
        if gen is None:
            gen = stream_model_download(download_model)
            st.session_state.model_download_gen = gen

        try:
            update = next(gen)
        except StopIteration:
            st.session_state.model_downloading = False
            st.session_state.model_download_gen = None
            st.rerun()

        if update["status"] == "progress":
            pct = update.get("percentage", 0) or 0
            progress_bar.progress(int(pct) / 100.0)
            completed_gb = (update.get("completed") or 0) / (1024 ** 3)
            total_gb = (update.get("total") or 0) / (1024 ** 3)
            status_text.text(f"Downloading: {completed_gb:.1f}GB / {total_gb:.1f}GB ({pct:.0f}%)")
            st.session_state.model_download_gen = gen
            st.rerun()
        elif update["status"] == "status":
            status_text.text(f"{update['detail']}...")
            st.session_state.model_download_gen = gen
            st.rerun()
        elif update["status"] == "success":
            progress_bar.progress(1.0)
            status_text.success("Download complete! Model installed. Refreshing environment...")
            download_status.update(label="Download complete", state="complete")
            st.session_state.model_downloading = False
            st.session_state.model_download_gen = None
            st.session_state.env_check = None
            st.rerun()
        elif update["status"] == "error":
            status_text.error(f"Download failed: {update['message']}")
            st.session_state.model_downloading = False
            st.session_state.model_download_gen = None

    if st.session_state.model_downloading:
        st.stop()

if st.session_state.provider_info == "ollama" and env and not env.get("ollama_running"):
    st.warning("Ollama is not running. Please start the Ollama application, "
               "then click 'Refresh Status' in the sidebar.", icon=":material/warning:")

if st.session_state.provider_info != "ollama":
    stored = load_api_key(st.session_state.provider_info)
    if not stored:
        st.warning(f"Enter your {st.session_state.provider_info} API key in the sidebar.", icon=":material/warning:")

# -----------------------------------------------------------------------------
# Helper: load log data for analytics
# -----------------------------------------------------------------------------

@st.cache_data(ttl=10)
@st.cache_data(ttl=5)
def load_log_entries() -> list[dict[str, Any]]:
    """Load all JSONL log entries from the log directory.

    Returns:
        List of parsed log entry dictionaries, sorted by file then line order.
    """
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
# Confirmation dialogs for destructive actions
# -----------------------------------------------------------------------------

def _reset_app_settings() -> None:
    """Clear pipeline state, temp files, analytics logs, and output dir setting."""
    temp_dir = st.session_state.get("temp_dir")
    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)
    reset_keys = ["base64_cache", "text_cache", "audio_transcription_cache", "staged_assets", "analysis_done", "uploaded_files",
                  "temp_dir", "output_dir", "logger", "analysis_in_progress",
                  "analysis_index", "analysis_aborted", "clear_counter",
                  "analysis_errors"]
    for key in reset_keys:
        st.session_state.pop(key, None)
    for h in logging.getLogger('video_renamer').handlers[:]:
        h.close()
        logging.getLogger('video_renamer').removeHandler(h)
    for log_path in LOG_DIR.glob("renamer_*.jsonl"):
        log_path.unlink(missing_ok=True)
    load_log_entries.clear()


@st.dialog("Reset App and Settings", icon=":material/delete_sweep:")
def confirm_reset() -> None:
    """Confirm dialog: wipe pipeline state, staged files, logs, and output dir."""
    st.write("This clears pipeline state, staged files, analysis progress, "
             "analytics logs, and the output directory setting. This cannot be undone.")
    with st.container(horizontal=True):
        if st.button("Cancel", key="reset_dlg_cancel"):
            st.rerun()
        if st.button("Yes, reset everything", type="primary", key="reset_dlg_confirm"):
            _reset_app_settings()
            st.rerun()


@st.dialog("Clear analytics logs", icon=":material/delete_sweep:")
def confirm_clear_logs() -> None:
    """Confirm dialog: delete all analytics/commit history log entries."""
    st.write("Delete all analytics log entries? Commit history and dashboard stats will be cleared.")
    with st.container(horizontal=True):
        if st.button("Cancel", key="clear_logs_dlg_cancel"):
            st.rerun()
        if st.button("Yes, clear logs", type="primary", key="clear_logs_dlg_confirm"):
            for h in logging.getLogger('video_renamer').handlers[:]:
                h.close()
                logging.getLogger('video_renamer').removeHandler(h)
            for log_path in LOG_DIR.glob("renamer_*.jsonl"):
                log_path.unlink(missing_ok=True)
            load_log_entries.clear()
            st.rerun()


@st.dialog("Delete saved session", icon=":material/delete:")
def confirm_delete_session(path: str, label: str) -> None:
    """Confirm dialog: remove a saved session file."""
    st.write(f"Delete saved session **{label}**? This cannot be undone.")
    with st.container(horizontal=True):
        if st.button("Cancel", key="del_session_dlg_cancel"):
            st.rerun()
        if st.button("Delete session", type="primary", key="del_session_dlg_confirm"):
            delete_session(path)
            st.toast("Session deleted.")
            st.rerun()


@st.dialog("Commit selected assets", icon=":material/send:")
def confirm_commit(count: int, metadata_only: bool) -> None:
    """Confirm dialog: commit the selected staged assets."""
    if metadata_only:
        st.write(f"Write metadata tags to **{count}** selected asset(s) in place? "
                 "Original filenames are preserved.")
    else:
        st.write(f"Rename and tag **{count}** selected asset(s)? This moves files and "
                 "writes metadata — it cannot be undone from the UI.")
    with st.container(horizontal=True):
        if st.button("Cancel", key="commit_dlg_cancel"):
            st.rerun()
        if st.button("Yes, commit", type="primary", key="commit_dlg_confirm"):
            st.session_state.commit_confirmed = True
            st.rerun()


@st.dialog("Undo last commit", icon=":material/undo:")
def confirm_undo() -> None:
    """Confirm dialog: roll back the most recent commit batch."""
    st.write("Move the files from the last commit back to their original locations "
             "and remove the metadata tags?")
    with st.container(horizontal=True):
        if st.button("Cancel", key="undo_dlg_cancel"):
            st.rerun()
        if st.button("Yes, undo last commit", type="primary", key="undo_dlg_confirm"):
            st.session_state.undo_requested = True
            st.rerun()

# -----------------------------------------------------------------------------
# Tab 1: Upload & Analyze
# -----------------------------------------------------------------------------

tab_upload, tab_analytics, tab_config = st.tabs([
    ":material/upload: Upload & Analyze",
    ":material/analytics: Analytics Dashboard",
    ":material/settings: Configuration",
])

with tab_upload:
    st.subheader(":material/upload: Upload files")

    if st.session_state.provider_info == "ollama" and env and not env.get("model_available"):
        st.info("Qwen2.5-VL model is not installed. "
                "Use the download button in the sidebar to install it before uploading files.",
                icon=":material/warning:")
        uploaded_files = None
    else:
        uploaded_files = st.file_uploader(
            "Choose video, image, document, or audio files",
            type=["mp4", "mov", "avi", "mkv", "webm",
                  "jpg", "jpeg", "png", "webp", "gif",
                  "pdf", "docx", "doc", "txt", "md", "rtf",
                  "xlsx", "csv", "pptx",
                  "mp3", "wav", "flac", "aac", "ogg", "m4a",
                  "wma", "opus", "aiff", "alac"],
            accept_multiple_files=True,
            key=f"fu_{st.session_state.clear_counter}",
        )

    if uploaded_files:
        existing = st.session_state.get("uploaded_files", {})
        new_names = {uf.name for uf in uploaded_files}
        if set(existing.keys()) != new_names:
            st.session_state.temp_dir = tempfile.mkdtemp(prefix="renamer_upload_")
            saved = {}
            skipped_size = []
            skipped_ext = []
            valid_exts = set(VIDEO_EXTENSIONS) | set(IMAGE_EXTENSIONS) | set(DOCUMENT_EXTENSIONS) | set(AUDIO_EXTENSIONS)
            all_bytes = sum(uf.size for uf in uploaded_files)
            copied_bytes = 0
            total_files = len(uploaded_files)
            progress_bar = st.progress(0, text="Copying files...") if total_files > 1 else None

            for i, uf in enumerate(uploaded_files):
                ext = Path(uf.name).suffix.lower()
                if ext not in valid_exts:
                    skipped_ext.append(uf.name)
                    log_event(logger, "ERROR", "file_skipped",
                              details={"file": uf.name, "reason": "unsupported_extension"})
                    continue
                if uf.size > MAX_UPLOAD_SIZE:
                    skipped_size.append((uf.name, uf.size))
                    log_event(logger, "ERROR", "file_skipped",
                              details={"file": uf.name, "reason": "exceeds_max_size",
                                       "size": uf.size})
                    continue
                dest = Path(st.session_state.temp_dir) / uf.name
                dest.write_bytes(uf.getbuffer())
                saved[uf.name] = dest
                copied_bytes += uf.size
                if progress_bar:
                    progress_bar.progress(copied_bytes / all_bytes,
                                          text=f"Copying {uf.name} ({i+1}/{total_files})")

            if skipped_ext:
                st.warning(f"Skipped {len(skipped_ext)} file(s) with unsupported extensions: "
                           f"{', '.join(skipped_ext)}")
            if skipped_size:
                for name, size in skipped_size:
                    gb = size / (1024 ** 3)
                    st.warning(f"Skipped {name} ({gb:.1f} GB) — exceeds max upload size.")

            if progress_bar:
                progress_bar.empty()

            st.session_state.uploaded_files = saved
            st.session_state.analysis_done = False
            st.session_state.analysis_in_progress = False
            st.session_state.analysis_aborted = False
            st.session_state.staged_assets = []
            st.session_state.base64_cache = {}
            st.session_state.text_cache = {}
            st.session_state.audio_transcription_cache = {}

    # Clear All button — always visible when files or staged assets exist
    if st.session_state.get("uploaded_files") or st.session_state.staged_assets:
        if st.button(":material/delete: Clear All Files", type="secondary", key="clear_files"):
            temp_dir = st.session_state.get("temp_dir")
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
            for s in list_sessions():
                delete_session(s["path"])
            for key in ["uploaded_files", "base64_cache", "text_cache", "staged_assets", "temp_dir", "analysis_errors"]:
                st.session_state.pop(key, None)
            st.session_state.analysis_done = False
            st.session_state.analysis_in_progress = False
            st.session_state.clear_counter += 1
            st.rerun()

    # Empty-state onboarding hint (nothing uploaded, nothing staged yet)
    if not st.session_state.get("uploaded_files") and not st.session_state.staged_assets:
        st.space()
        step_col1, step_col2, step_col3 = st.columns(3)
        with step_col1:
            st.markdown(":material/upload_file: **Step 1 — Upload**")
            st.caption("Add video, image, document, or audio files using the picker above.")
        with step_col2:
            st.markdown(":material/auto_awesome: **Step 2 — Analyze**")
            st.caption("Run AI analysis to generate filenames, categories, and tags.")
        with step_col3:
            st.markdown(":material/check_circle: **Step 3 — Review & commit**")
            st.caption("Edit the staging table, then commit the changes to your output folder.")

    # Session persistence — save / restore
    has_work = bool(st.session_state.get("staged_assets")) or bool(st.session_state.get("uploaded_files"))
    saved = list_sessions()
    if has_work or saved:
        with st.expander("Session", expanded=False):
            col_save, col_restore, col_delete = st.columns(3)
            with col_save:
                if st.button(":material/save: Save Session", disabled=not has_work, key="save_session"):
                    settings = {
                        "output_dir": st.session_state.get("output_dir", ""),
                        "case_style": st.session_state.get("case_style", "title_case"),
                        "max_filename_chars": st.session_state.get("max_filename_chars", 0),
                        "template_string": st.session_state.get("template_string", ""),
                    }
                    path = save_session(
                        st.session_state.get("staged_assets", []),
                        st.session_state.get("uploaded_files", {}),
                        settings,
                    )
                    st.toast(f"Session saved: {path.name}")
            with col_restore:
                if saved:
                    options = [f"{s['created']}  ({s['asset_count']} assets)" for s in saved]
                    chosen = st.selectbox("Saved sessions", options, key="session_picker")
                    if st.button(":material/history: Restore Session", key="restore_session"):
                        idx = options.index(chosen)
                        result = load_session(saved[idx]["path"])
                        st.session_state.staged_assets = result["staged_assets"]
                        st.session_state.uploaded_files = result["uploaded_files"]
                        s = result["settings"]
                        if s.get("output_dir"):
                            st.session_state.output_dir = s["output_dir"]
                        if s.get("case_style"):
                            st.session_state.case_style = s["case_style"]
                        if s.get("max_filename_chars") is not None:
                            st.session_state.max_filename_chars = s["max_filename_chars"]
                        if s.get("template_string"):
                            st.session_state.template_string = s["template_string"]
                        if result["staged_assets"]:
                            st.session_state.analysis_done = True
                        else:
                            st.session_state.analysis_done = False
                        st.session_state.analysis_in_progress = False
                        st.session_state.analysis_index = 0
                        st.session_state.base64_cache = {}
                        st.session_state.text_cache = {}
                        st.session_state.audio_transcription_cache = {}
                        if not result["staged_assets"] and result["missing_files"]:
                            st.warning(f"All {len(result['missing_files'])} file(s) missing from disk. "
                                       "Session restored with no assets. Re-upload files and re-analyze.",
                                       icon=":material/warning:")
                        else:
                            msg = f"Session restored ({len(result['staged_assets'])} assets)"
                            if result["missing_files"]:
                                msg += f". {len(result['missing_files'])} file(s) missing from disk."
                            st.toast(msg)
                        st.rerun()
            with col_delete:
                if saved:
                    del_options = [f"{s['created']}  ({s['asset_count']} assets)" for s in saved]
                    del_chosen = st.selectbox("Delete session", del_options, key="session_delete_picker")
                    if st.button(":material/delete: Delete", key="delete_session", type="secondary"):
                        idx = del_options.index(del_chosen)
                        confirm_delete_session(saved[idx]["path"], del_chosen)
                else:
                    st.space()

    # ------------------------------------------------------------------
    # Phase 2: Per-asset rerun loop (one AI call per script execution)
    # Uses st.fragment to isolate reruns — only the analysis area re-renders
    # ------------------------------------------------------------------
    if st.session_state.analysis_in_progress:

        @st.fragment
        def _analysis_fragment() -> None:
            """Run all remaining AI analysis steps in a single execution within a Streamlit fragment."""
            b64_items = list(st.session_state.get("base64_cache", {}).items())
            text_items = list(st.session_state.get("text_cache", {}).items())
            audio_items = list(st.session_state.get("audio_transcription_cache", {}).items())
            all_items = [(n, "image", d) for n, d in b64_items] + [(n, "text", d) for n, d in text_items] + [(n, "audio", d) for n, d in audio_items]
            total = len(all_items)
            idx = st.session_state.analysis_index

            st.success(f"Step 1 complete: {len(b64_items)} media + {len(text_items)} documents + {len(audio_items)} audio extracted")

            if total > 0:
                progress_bar = st.progress(idx / total, text=f"Analyzed {idx}/{total} files")

            prov = get_provider(st.session_state.provider_info)
            staged_assets = list(st.session_state.get("staged_assets", []))

            while idx < total:
                name, file_type, data = all_items[idx]
                progress_bar.progress((idx + 1) / total, text=f"Analyzing {name} ({idx+1}/{total})")

                if file_type in ("text", "audio"):
                    ai_result = prov.analyze_text(data, verbose=False)
                else:
                    audio_ctx = st.session_state.get("audio_transcription_cache", {}).get(name, "")
                    prompt_override = None
                    if audio_ctx:
                        prompt_override = (
                            f"Audio transcription (if available):\n{audio_ctx}\n\n---\n\n"
                            f"{get_active_prompt()}"
                        )
                    ai_result = prov.analyze(data, verbose=False, prompt_override=prompt_override)

                if ai_result['ok']:
                    ai_data = ai_result['data']
                    suggested_cat = ai_data.get('suggested_category', '')
                    staged_category, _ = validate_category(suggested_cat)
                    ai_topic = ai_data.get('topic', '')
                    ai_desc = ai_data.get('description', '')
                    safe_name = sanitize_name(ai_data['new_filename'])
                    safe_name = apply_naming_template(
                        st.session_state.template_string,
                        {"category": staged_category, "topic": ai_topic,
                         "description": ai_desc, "new_filename": safe_name},
                    )
                    safe_name = apply_case_style(safe_name, st.session_state.case_style)
                    safe_name = truncate_filename(safe_name, st.session_state.max_filename_chars)

                    file_ext = Path(name).suffix.lower()
                    is_audio = file_ext in AUDIO_EXTENSIONS
                    is_doc = file_ext in DOCUMENT_EXTENSIONS
                    staged_assets.append({
                        "original_path": st.session_state.uploaded_files[name],
                        "original_name": name,
                        "staged_name": safe_name,
                        "category": staged_category,
                        "topic": ai_topic,
                        "description": ai_desc,
                        "tags": ai_data.get('tags', []),
                        "summary": ai_data.get('overall_visual_summary', ''),
                        "suggested_category": suggested_cat,
                        "file_type": "audio" if is_audio else ("document" if is_doc else "media"),
                        "file_ext": file_ext,
                        "audio_transcription": st.session_state.get("audio_transcription_cache", {}).get(name, ""),
                    })

                    log_event(logger, "INFO", "ai_analysis_success", file_name=name, details={
                        "staged_name": safe_name, "category": staged_category
                    })
                else:
                    error_msg = _format_ai_error(ai_result)
                    st.session_state.analysis_errors.append(f"{name}: {error_msg}")
                    log_event(logger, "ERROR", "ai_analysis_failed", file_name=name, details={"error": error_msg})

                idx += 1

            st.session_state.staged_assets = staged_assets
            st.session_state.analysis_index = idx
            st.session_state.analysis_in_progress = False
            st.session_state.analysis_done = True
            n = len(staged_assets)
            errs = st.session_state.analysis_errors
            if n:
                st.success(f"Analysis complete: {n} assets staged.")
            else:
                st.warning(f"No assets were staged ({len(errs)} failure(s)).")
                for e in errs:
                    st.caption(f"  {e}")

        _analysis_fragment()

    # ------------------------------------------------------------------
    # Persistent status (visible after analysis completes)
    # ------------------------------------------------------------------
    if st.session_state.analysis_done:
        n = len(st.session_state.staged_assets)
        if n:
            st.success(f"Analysis complete: {n} asset{'s' if n != 1 else ''} ready for review below.")

    # ------------------------------------------------------------------
    # AI Prompt Profile (before analysis, changeable per run)
    # ------------------------------------------------------------------
    profile_keys = list(PROMPT_PROFILES.keys())
    current_profile = get_active_profile()

    def _on_profile_change() -> None:
        """Update the active AI prompt profile when the profile selector changes."""
        new_p = st.session_state.profile_selector
        set_active_profile(new_p)

    col_prof_label, col_prof_sel = st.columns([1, 3])
    with col_prof_label:
        st.caption("AI prompt profile")
    with col_prof_sel:
        st.selectbox("Profile", profile_keys, format_func=lambda k: PROMPT_PROFILES.get(k, k),
                     index=profile_keys.index(current_profile) if current_profile in profile_keys else 0,
                     key="profile_selector", on_change=_on_profile_change,
                     label_visibility="collapsed")

    current_profile = st.session_state.get("profile_selector", current_profile)

    if current_profile == "custom":
        profile_data = config.get("prompt_profiles", {}).get("profiles", {}).get("custom", {})
        current_custom = profile_data.get("prompt", "")

        def _on_custom_prompt_change() -> None:
            """Save the custom prompt text to config when the text area changes."""
            text = st.session_state.custom_prompt_area
            if "prompt_profiles" not in config:
                config["prompt_profiles"] = {"active": "custom", "profiles": {}}
            if "custom" not in config["prompt_profiles"].setdefault("profiles", {}):
                cfg_custom = {"label": "Custom Prompt", "prompt": "", "allowed_categories": []}
                config["prompt_profiles"]["profiles"]["custom"] = cfg_custom
            config["prompt_profiles"]["profiles"]["custom"]["prompt"] = text
            save_config()

        st.text_area("Write your own prompt", value=current_custom,
                     key="custom_prompt_area", on_change=_on_custom_prompt_change,
                     height=200,
                     help="This prompt is auto-saved to config.json.")

        st.download_button(
            ":material/file_download: Export Custom Prompt",
            data=current_custom,
            file_name="custom_ai_prompt.txt",
            mime="text/plain",
            help="Download your custom prompt as a .txt file.",
        )

    # ------------------------------------------------------------------
    # Analysis trigger: button + Phase 1 (only when idle)
    # ------------------------------------------------------------------
    if not st.session_state.analysis_in_progress and not st.session_state.analysis_done \
            and st.session_state.get("uploaded_files"):
        file_count = len(st.session_state.uploaded_files)
        if file_count >= 200:
            st.warning(f"Large batch ({file_count} files). Consider using the CLI for better "
                       "throughput: `python cli.py \"path/to/dir\"`")
        elif file_count >= 50:
            st.info(f"Batch size: {file_count} files. Extraction may take a few minutes.")

        with st.expander("Advanced features", expanded=False):
            adv_col1, adv_col2, adv_col3 = st.columns(3)
            with adv_col1:
                def _on_adv_case() -> None:
                    """Sync the advanced case style selection to session state."""
                    st.session_state.case_style = st.session_state.adv_case_style
                st.selectbox("Case style", CASE_STYLE_OPTIONS,
                             format_func=lambda s: CASE_STYLE_LABELS.get(s, s),
                             index=CASE_STYLE_OPTIONS.index(st.session_state.case_style),
                             key="adv_case_style", on_change=_on_adv_case)
            with adv_col2:
                def _on_adv_chars() -> None:
                    """Sync the max filename characters setting to session state."""
                    st.session_state.max_filename_chars = st.session_state.adv_max_chars
                st.number_input("Max filename chars", min_value=0, max_value=200, step=5,
                                key="adv_max_chars", on_change=_on_adv_chars,
                                help="0 = no limit")
            with adv_col3:
                template_names = list(NAMED_TEMPLATES.keys())
                def _on_adv_template() -> None:
                    """Sync the naming template selection to session state."""
                    st.session_state.template_string = NAMED_TEMPLATES.get(
                        st.session_state.adv_template, DEFAULT_TEMPLATE_STRING)
                st.selectbox("Naming template", template_names,
                             index=template_names.index(
                                 next((k for k, v in NAMED_TEMPLATES.items()
                                       if v == st.session_state.template_string),
                                      template_names[0])),
                             key="adv_template", on_change=_on_adv_template,
                             help="Template for generated filenames")

        col1, col2 = st.columns([1, 3])
        with col1:
            analyze_btn = st.button(":material/play_arrow: Run AI Analysis", type="primary", key="run_analysis")
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

                # Phase 1: Parallel extraction (skip files already cached)
                st.write("**Step 1:** Preparing content for analysis...")
                progress_bar = st.progress(0, text="Extracting content...")
                base64_results = dict(st.session_state.get("base64_cache", {}))
                text_results = dict(st.session_state.get("text_cache", {}))
                audio_results = dict(st.session_state.get("audio_transcription_cache", {}))
                cached_count = len(base64_results) + len(text_results) + len(audio_results)

                doc_exts = set(DOCUMENT_EXTENSIONS)
                audio_exts = set(AUDIO_EXTENSIONS)
                files_list = list(st.session_state.uploaded_files.values())
                uncached = [fp for fp in files_list
                            if fp.name not in base64_results and fp.name not in text_results and fp.name not in audio_results]
                if cached_count:
                    st.caption(f"{cached_count} file(s) already cached, extracting {len(uncached)} new...")
                with ThreadPoolExecutor(max_workers=EXTRACTION_WORKERS) as executor:
                    future_map = {}
                    for fp in uncached:
                        if fp.suffix.lower() in doc_exts:
                            future_map[executor.submit(extract_text_from_file, fp)] = fp
                        elif fp.suffix.lower() in audio_exts:
                            future_map[executor.submit(transcribe_audio, fp)] = fp
                        else:
                            future_map[executor.submit(process_asset_to_base64, fp, hw_accel)] = fp
                    done_count = 0
                    extract_total = max(len(uncached), 1)
                    for future in as_completed(future_map):
                        fp = future_map[future]
                        result = future.result()
                        if result:
                            if fp.suffix.lower() in doc_exts:
                                text_results[fp.name] = result
                            elif fp.suffix.lower() in audio_exts:
                                audio_results[fp.name] = result.get("text", "") if isinstance(result, dict) else ""
                            else:
                                base64_results[fp.name] = result
                        else:
                            st.warning(f"Extraction failed: {fp.name}")
                            log_event(logger, "ERROR", "extraction_failed", file_name=fp.name)
                        done_count += 1
                        progress_bar.progress(
                            done_count / extract_total,
                            text=f"Extracted {done_count}/{extract_total}"
                        )

                if not base64_results and not text_results:
                    st.error("No files could be extracted. Aborting.")
                    st.stop()

                video_files = [fp for fp in uncached
                               if fp.suffix.lower() in VIDEO_EXTENSIONS and fp.name not in audio_results]
                if video_files:
                    audio_progress = st.progress(0, text="Extracting audio transcriptions...")
                    for i, fp in enumerate(video_files):
                        audio_progress.progress(
                            i / max(len(video_files), 1),
                            text=f"Transcribing {fp.name} ({i+1}/{len(video_files)})"
                        )
                        if _has_audio_track(fp):
                            wav_path = extract_audio_from_video(fp)
                            if wav_path:
                                result = transcribe_audio(wav_path)
                                audio_results[fp.name] = result.get("text", "")
                                try:
                                    wav_path.unlink()
                                except OSError:
                                    pass
                            else:
                                audio_results[fp.name] = ""
                        else:
                            audio_results[fp.name] = ""
                    audio_progress.progress(1.0, text="Audio transcription complete")

                st.session_state.base64_cache = base64_results
                st.session_state.text_cache = text_results
                st.session_state.audio_transcription_cache = audio_results
                st.session_state.staged_assets = []
                st.session_state.analysis_errors = []
                st.session_state.analysis_index = 0
                st.session_state.analysis_in_progress = True
                st.session_state.analysis_done = False
                st.session_state.analysis_aborted = False
                with st.spinner("Starting AI analysis..."):
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
        st.space()
        st.subheader(":material/table_chart: Staging matrix — review and edit before committing")

        col_filter, _ = st.columns([3, 2])
        with col_filter:
            st.text_input("Filter assets", placeholder="Filter assets...", key="staging_filter",
                          label_visibility="collapsed", icon=":material/search:")

        staged_raw = st.session_state.staged_assets
        filter_text = st.session_state.get("staging_filter", "").lower().strip()
        if filter_text:
            staged = [
                a for a in staged_raw
                if filter_text in a.get("original_name", "").lower()
                or filter_text in a.get("staged_name", "").lower()
                or filter_text in a.get("category", "").lower()
                or any(filter_text in t.lower() for t in a.get("tags", []))
            ]
            st.caption(f"Showing {len(staged)} of {len(staged_raw)} assets")
        else:
            staged = staged_raw
            st.caption(f"{len(staged)} assets ready for review")

        with st.expander("Naming settings (edits update previews below)", expanded=True):
            col_tmpl, col_case, col_chars = st.columns(3)
            with col_tmpl:
                st.text_input("Pattern", key="template_string",
                              help="{category}, {topic}, {description}, {date} in any order.")
            with col_case:
                def _on_staging_case() -> None:
                    """Sync the staging case style selection to session state."""
                    st.session_state.case_style = st.session_state.staging_case_style
                st.selectbox("Case style", CASE_STYLE_OPTIONS,
                             format_func=lambda s: CASE_STYLE_LABELS.get(s, s),
                             index=CASE_STYLE_OPTIONS
                             .index(st.session_state.case_style),
                             key="staging_case_style", on_change=_on_staging_case)
            with col_chars:
                def _on_staging_chars() -> None:
                    """Sync the max filename characters setting from staging input."""
                    st.session_state.max_filename_chars = st.session_state.staging_max_chars
                st.number_input("Max chars", min_value=0, max_value=200, step=5,
                                key="staging_max_chars", on_change=_on_staging_chars)

        template = st.session_state.template_string
        case_style = st.session_state.case_style
        max_chars = st.session_state.max_filename_chars

        # Select-all checkbox above table
        select_all = st.checkbox("Select all", key="staging_select_all")

        table_rows = []
        for i, asset in enumerate(staged):
            rendered = apply_naming_template(template, {
                "category": asset.get("category", "uncategorized"),
                "topic": asset.get("topic", ""),
                "description": asset.get("description", ""),
                "new_filename": asset["staged_name"],
            })
            rendered = apply_case_style(rendered, case_style)
            rendered = truncate_filename(rendered, max_chars)
            existing_rating = asset.get("rating", "")
            ft = asset.get("file_type", "media")
            fext = asset.get("file_ext", "")
            if ft == "audio":
                type_label = f"audio ({fext.lstrip('.')})"
            elif ft == "document":
                type_label = f"doc ({fext.lstrip('.')})"
            else:
                type_label = "media"
            summary_text = asset["summary"]
            if ft == "document":
                txt = st.session_state.text_cache.get(asset["original_name"], "")
                if txt:
                    snippet = txt[:200].replace("\n", " ")
                    if len(txt) > 200:
                        snippet += "..."
                    summary_text = snippet
            elif ft == "audio":
                txt = st.session_state.get("audio_transcription_cache", {}).get(asset["original_name"], "")
                if txt:
                    snippet = txt[:200].replace("\n", " ")
                    if len(txt) > 200:
                        snippet += "..."
                    summary_text = f"[Transcription] {snippet}"
            table_rows.append({
                "select": select_all,
                "original_name": asset["original_name"],
                "type": type_label,
                "proposed_filename": rendered,
                "category": asset["category"] or "uncategorized",
                "tags": ", ".join(asset["tags"]),
                "summary": summary_text,
                "rating": existing_rating,
            })

        df = pd.DataFrame(table_rows)

        cat_options_set = set(CATEGORY_LIST)
        for a in st.session_state.staged_assets:
            cat = a.get("category") or ""
            if cat:
                cat_options_set.add(cat)
        cat_options = sorted(cat_options_set) + ["uncategorized"]

        edited_df = st.data_editor(
            df,
            column_config={
                "select": st.column_config.CheckboxColumn("Apply", default=True),
                "original_name": st.column_config.TextColumn("Original File", disabled=True, width="small"),
                "type": st.column_config.TextColumn("Type", disabled=True, width="small"),
                "proposed_filename": st.column_config.TextColumn("Proposed Filename", width="medium"),
                "category": st.column_config.SelectboxColumn(
                    "Category",
                    options=cat_options,
                    width="medium",
                ),
                "tags": st.column_config.TextColumn("Tags (comma-separated)", width="large"),
                "summary": st.column_config.TextColumn("Summary", disabled=True, width="large"),
                "rating": st.column_config.SelectboxColumn(
                    "Rating",
                    options=["", "\U0001f44d", "\U0001f44e"],
                    width="small",
                    help="Rate this AI suggestion",
                ),
            },
            hide_index=True,
            width='stretch',
            num_rows="fixed",
            key="staging_data_editor",
        )

        # Bulk category assignment
        sel_count = int(edited_df["select"].sum())
        st.markdown("**Bulk category**")
        bulk_col_cat, bulk_col_btn = st.columns([3, 1])
        with bulk_col_cat:
            bulk_category = st.selectbox(
                "Apply category to selected",
                [""] + sorted(CATEGORY_LIST) + ["custom"],
                key="bulk_category_sel",
                label_visibility="collapsed",
                help="Choose a category to apply to every selected asset.",
            )
            if bulk_category == "custom":
                custom_cat = st.text_input("Custom category name", key="bulk_custom_cat",
                                           label_visibility="collapsed",
                                           placeholder="Enter a new category name")
                effective_category = custom_cat.strip()
            else:
                effective_category = bulk_category
        with bulk_col_btn:
            st.button(":material/check: Apply", type="secondary", key="bulk_apply_btn",
                      disabled=sel_count == 0 or not effective_category)

        if sel_count:
            preview_cat = effective_category or "—"
            st.caption(f"{sel_count} asset{'s' if sel_count != 1 else ''} selected — "
                       f"apply '{preview_cat}' to all selected rows.")
        else:
            st.caption("Select assets using the checkbox column above.")

        if st.session_state.get("bulk_apply_btn") and effective_category:
            selected = edited_df[edited_df["select"]]
            for idx in selected.index:
                staged[idx]["category"] = effective_category
            st.toast(f"Applied '{effective_category}' to {len(selected)} assets")
            st.rerun()

        # Sync ratings from data editor back to staged_assets
        for i, asset in enumerate(staged):
            new_rating = edited_df.iloc[i]["rating"]
            if new_rating != asset.get("rating", ""):
                asset["rating"] = new_rating

        # Re-analyze button for selected rows
        ra_disabled = sel_count == 0
        if st.button(":material/refresh: Re-analyze Selected", key="reanalyze_btn", disabled=ra_disabled):
            selected_names = set()
            for idx in edited_df[edited_df["select"]].index:
                selected_names.add(staged[idx]["original_name"])

            st.session_state.staged_assets = [
                a for a in st.session_state.staged_assets
                if a["original_name"] not in selected_names
            ]
            st.session_state.base64_cache = {
                k: v for k, v in st.session_state.base64_cache.items()
                if k in selected_names
            }
            st.session_state.text_cache = {
                k: v for k, v in st.session_state.text_cache.items()
                if k in selected_names
            }
            st.session_state.audio_transcription_cache = {
                k: v for k, v in st.session_state.audio_transcription_cache.items()
                if k in selected_names
            }
            st.session_state.analysis_index = 0
            st.session_state.analysis_in_progress = True
            st.session_state.analysis_done = False
            st.session_state.analysis_errors = []
            st.rerun()

        # Duplicate detection
        if st.button(":material/content_copy: Detect Duplicates", key="detect_dupes_btn"):
            with st.spinner("Computing perceptual hashes..."):
                duplicates = find_duplicates(staged, threshold=10)
                st.session_state.duplicate_pairs = duplicates
                if duplicates:
                    st.warning(f"Found {len(duplicates)} potential duplicate pair(s)")
                else:
                    st.success("No duplicates found")

        if st.session_state.get("duplicate_pairs"):
            with st.expander(f"Duplicates ({len(st.session_state.duplicate_pairs)} pairs)", expanded=True):
                dupe_df = pd.DataFrame(st.session_state.duplicate_pairs)
                dupe_df = dupe_df.rename(columns={
                    "name_a": "File A", "name_b": "File B",
                    "confidence": "Similarity %", "distance": "Distance"
                })
                st.dataframe(dupe_df[["File A", "File B", "Similarity %", "Distance"]],
                             hide_index=True, width="stretch")
                if st.button(":material/clear_all: Clear Duplicates", key="clear_dupes"):
                    st.session_state.pop("duplicate_pairs", None)
                    st.rerun()

        # Export and import staging
        csv_data = export_staging_csv(st.session_state.staged_assets)
        st.download_button(":material/file_download: Export Staged Changes", data=csv_data,
                           file_name="staging_export.csv", mime="text/csv",
                           key="export_csv_btn")

        with st.expander("Import staging CSV (overrides current staging)"):
            imported_file = st.file_uploader("Upload CSV", type="csv", key="staging_import_csv")
            if imported_file:
                csv_text = imported_file.read().decode("utf-8")
                imported_assets, warnings = import_staging_csv(csv_text, CATEGORY_LIST)
                if warnings:
                    for w in warnings:
                        st.warning(w)
                if imported_assets:
                    st.session_state.staged_assets = imported_assets
                    st.success(f"Imported {len(imported_assets)} assets from CSV")
                    st.rerun()

        with st.expander("Show preview thumbnails"):
            cols = st.columns(min(len(staged), 5))
            for i, asset in enumerate(staged):
                col_idx = i % 5
                with cols[col_idx]:
                    b64 = st.session_state.base64_cache.get(asset["original_name"])
                    txt = st.session_state.text_cache.get(asset["original_name"])
                    if b64:
                        st.image(base64.b64decode(b64), caption=asset["original_name"], width=150)
                    elif txt:
                        preview = txt[:150] + ("..." if len(txt) > 150 else "")
                        st.caption(f"{asset['original_name']}\n{preview}")
                    else:
                        st.caption(f"No preview: {asset['original_name']}")

        sort_folders = st.checkbox("Sort assets into categorized subfolders", value=True)
        metadata_only = st.checkbox("Metadata only — keep original filenames",
                                    help="Write AI-generated tags and summary to files without renaming them.")

        with st.container(horizontal=True):
            preview_btn = st.button(":material/preview: Preview Commit", key="preview_commit")
            commit_btn = st.button(":material/send: Commit Selected", type="primary", key="commit_selected")
        if metadata_only:
            st.caption("Selected rows will be tagged in-place. Original filenames preserved.")
        else:
            st.caption("Selected rows will be renamed and tagged. Unchecked rows are skipped.")

        if preview_btn:
            selected = edited_df[edited_df["select"]]
            if selected.empty:
                st.info("No assets selected for preview.")
            else:
                target_dir = Path(st.session_state.output_dir)
                preview_rows = []
                for commit_i in range(len(selected)):
                    row = selected.iloc[commit_i]
                    asset = staged[selected.index[commit_i]]
                    suffix = Path(asset["original_name"]).suffix
                    new_name = f"{row['proposed_filename']}{suffix}"
                    if sort_folders:
                        cat = normalize_category(row["category"]) or "uncategorized"
                        new_path = str(target_dir / cat / new_name)
                    else:
                        new_path = str(target_dir / new_name)
                    tags = row["tags"]
                    preview_rows.append({
                        "Original": asset["original_name"],
                        "New Path": new_path,
                        "Category": row["category"],
                        "Tags": tags,
                        "Metadata": "Yes" if tags else "No",
                    })
                preview_df = pd.DataFrame(preview_rows)
                st.dataframe(preview_df, width="stretch", hide_index=True)
                st.caption("Preview only — no files modified.")

        if commit_btn:
            selected = edited_df[edited_df["select"]]
            if selected.empty:
                st.warning("No assets selected. Check the checkbox next to assets to commit.")
            else:
                confirm_commit(len(selected), metadata_only)

        if st.session_state.pop("commit_confirmed", False):
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
                    exif = ExifToolSession()
                    import uuid as _uuid
                    batch_id = str(_uuid.uuid4())[:12]
                    undo_records: list[dict] = []

                    committed_names = set()
                    for commit_i in range(len(selected)):
                        row = selected.iloc[commit_i]
                        asset = staged[selected.index[commit_i]]

                        asset["staged_name"] = row["proposed_filename"]
                        new_cat = row["category"].strip().lower().replace(" ", "_")
                        safe_chars = [c for c in new_cat if c.isalpha() or c.isdigit() or c in ('_', '-')]
                        safe_cat = "".join(safe_chars).strip('_')
                        if safe_cat:
                            asset["category"] = safe_cat
                        asset["tags"] = [t.strip() for t in row["tags"].split(",") if t.strip()]

                        result = execute_commit(asset, target_dir, sort_folders, exif,
                                                 skip_rename=metadata_only)

                        if result and not (isinstance(result, str) and result.startswith("ERROR:")):
                            committed += 1
                            committed_names.add(asset["original_name"])
                            rating = asset.get("rating", "")
                            log_event(logger, "INFO", "file_committed", file_name=asset["original_name"],
                                      details={"new_path": str(result), "category": asset["category"],
                                               "rating": rating if rating else None})
                            new_path_resolved = target_dir / str(result) if not isinstance(result, Path) else target_dir / result
                            injected_tags = [
                                "XMP-dc:Title", "XMP-dc:Description", "Microsoft:Category",
                                "XMP-dc:Subject",
                            ]
                            if asset["original_path"].suffix.lower() in VIDEO_EXTENSIONS:
                                injected_tags += [
                                    "QuickTime:Title", "QuickTime:Description",
                                    "QuickTime:Comment", "QuickTime:Keywords",
                                    "Keys:Description", "Keys:Keywords",
                                ]
                            else:
                                injected_tags += [
                                    "EXIF:XPTitle", "EXIF:XPKeywords",
                                    "Description", "Comment", "Keywords",
                                ]
                            undo_records.append({
                                "original_path": str(asset["original_path"]),
                                "new_path": str(new_path_resolved),
                                "original_name": asset["original_name"],
                                "new_name": asset["staged_name"],
                                "category": asset["category"],
                                "tags": asset.get("tags", []),
                                "injected_tags": injected_tags,
                            })
                        else:
                            failed += 1
                            err = result[6:] if isinstance(result, str) and result.startswith("ERROR:") else "unknown"
                            log_event(logger, "ERROR", "file_commit_failed", file_name=asset["original_name"],
                                      details={"error": err})

                        progress.progress((commit_i + 1) / len(selected))

                    try:
                        exif.close()
                    except Exception:
                        pass

                    log_event(logger, "INFO", "session_end", details={
                        "committed": committed, "failed": failed, "total": len(selected), "mode": "web_batch"
                    })

                    if undo_records:
                        log_commit_batch(batch_id, str(target_dir), undo_records)

                    if committed_names:
                        st.session_state.staged_assets = [
                            a for a in st.session_state.staged_assets
                            if a["original_name"] not in committed_names
                        ]
                        for name in committed_names:
                            st.session_state.base64_cache.pop(name, None)
                            st.session_state.text_cache.pop(name, None)
                            st.session_state.audio_transcription_cache.pop(name, None)

                    if failed:
                        msg = f"Committed {committed} assets. {failed} failed — remaining assets kept for retry."
                        st.toast(msg)
                        st.rerun()
                    else:
                        msg = f"All {committed} assets committed successfully to {target_dir.resolve()}!"
                        st.toast(msg)
                        st.markdown(
                            f'<div style="position:absolute;width:0;height:0;overflow:hidden">'
                            f'<audio id="commit-beep" autoplay>'
                            f'<source src="data:audio/wav;base64,{_COMMIT_BEEP}" type="audio/wav">'
                            f'</audio></div>',
                            unsafe_allow_html=True,
                        )
                        st.session_state._pending_rerun = True
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
    with st.container(horizontal=True):
        st.subheader(":material/analytics: Analytics Dashboard")
        if st.button(":material/delete_sweep: Clear Logs", type="secondary", key="clear_logs"):
            confirm_clear_logs()

    entries = load_log_entries()
    if not entries:
        st.info("No log entries found yet. Process some files to see analytics here.")
    else:
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

        st.divider()
        undo_batches = list_undo_batches()
        if undo_batches:
            last = undo_batches[0]
            n_files = len(last.get("records", []))
            ts = last.get("timestamp", "")[:19].replace("T", " ")
            st.caption(f"Last commit: {n_files} files at {ts}")
            if st.button(":material/undo: Undo Last Commit", type="secondary",
                         help="Moves files back to original locations and removes metadata tags."):
                confirm_undo()
            if st.session_state.pop("undo_requested", False):
                with st.spinner("Rolling back..."):
                    result = rollback_last_batch()
                load_log_entries.clear()
                if result["ok"]:
                    st.success(f"Restored {result['restored']} files.")
                    st.rerun()
                else:
                    st.warning(f"Restored {result['restored']}, failed {result['failed']}. "
                               + "; ".join(result["errors"][:3]))
        else:
            st.caption("No commit history to undo.")

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

        # 7.4 Error rate chart
        error_by_day = Counter()
        total_by_day = Counter()
        for e in entries:
            ts = e.get("timestamp", "")
            day = ts[:10] if ts else ""
            if day:
                total_by_day[day] += 1
                if e.get("level") == "ERROR":
                    error_by_day[day] += 1

        if total_by_day:
            all_days = sorted(set(total_by_day.keys()) | set(error_by_day.keys()))
            err_df = pd.DataFrame({
                "Date": all_days,
                "Errors": [error_by_day.get(d, 0) for d in all_days],
                "Total": [total_by_day.get(d, 0) for d in all_days],
            })
            err_df["Error Rate %"] = (err_df["Errors"] / err_df["Total"].clip(lower=1) * 100).round(1)
            fig_err = px.line(err_df, x="Date", y="Error Rate %",
                              title="Error Rate Over Time",
                              color_discrete_sequence=["#ef4444"])
            fig_err.update_layout(height=300)
            st.plotly_chart(fig_err, width='stretch')

        # 7.3 Storage usage metric
        committed_entries = [e for e in entries if e.get("event") == "file_committed"]
        if committed_entries:
            total_size = 0
            for e in committed_entries:
                details = e.get("details", {}) or {}
                file_path = details.get("new_path") or details.get("original_path", "")
                if file_path and os.path.isfile(file_path):
                    try:
                        total_size += os.path.getsize(file_path)
                    except OSError:
                        pass
            if total_size > 0:
                if total_size >= 1 << 30:
                    size_str = f"{total_size / (1 << 30):.1f} GB"
                elif total_size >= 1 << 20:
                    size_str = f"{total_size / (1 << 20):.1f} MB"
                else:
                    size_str = f"{total_size / (1 << 10):.1f} KB"
                st.metric("Total Committed Storage", size_str)

        # 7.1 Commit history timeline
        if committed_entries:
            st.subheader(":material/history: Commit History")
            commit_rows = []
            for e in committed_entries:
                details = e.get("details", {}) or {}
                commit_rows.append({
                    "Time": e.get("timestamp", ""),
                    "Original": e.get("file", "-"),
                    "New Path": details.get("new_path", "-"),
                    "Category": details.get("category", "-"),
                    "Tags": ", ".join(details.get("tags", [])) if isinstance(details.get("tags"), list) else "-",
                })
            commit_df = pd.DataFrame(commit_rows).sort_values("Time", ascending=False)

            ch_col1, ch_col2 = st.columns(2)
            with ch_col1:
                ch_categories = ["all"] + sorted(commit_df["Category"].unique().tolist())
                ch_cat_filter = st.selectbox("Filter by category", ch_categories,
                                              key="ch_cat_filter")
            with ch_col2:
                if "Time" in commit_df.columns and not commit_df["Time"].empty:
                    try:
                        commit_df["_date"] = commit_df["Time"].str[:10]
                        dates = sorted(commit_df["_date"].dropna().unique().tolist())
                        if len(dates) > 1:
                            ch_date_range = st.selectbox("Filter by date", ["all"] + dates,
                                                          key="ch_date_filter")
                        else:
                            ch_date_range = "all"
                        commit_df.drop(columns=["_date"], inplace=True, errors="ignore")
                    except Exception:
                        ch_date_range = "all"
                else:
                    ch_date_range = "all"

            filtered_commits = commit_df
            if ch_cat_filter != "all":
                filtered_commits = filtered_commits[filtered_commits["Category"] == ch_cat_filter]
            if ch_date_range != "all":
                filtered_commits = filtered_commits[
                    filtered_commits["Time"].str.startswith(ch_date_range)]

            st.dataframe(filtered_commits, width='stretch', hide_index=True)

            # Export buttons
            csv_data = filtered_commits.to_csv(index=False)
            json_data = filtered_commits.to_json(orient="records", indent=2)
            with st.container(horizontal=True):
                st.download_button(":material/file_download: Download CSV", data=csv_data,
                                   file_name="commit_history.csv", mime="text/csv")
                st.download_button(":material/data_object: Download JSON", data=json_data,
                                   file_name="commit_history.json", mime="application/json")

        # Filterable timeline
        st.subheader(":material/timeline: Event Timeline")

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
# Tab 3: Configuration
# -----------------------------------------------------------------------------

with tab_config:
    # Config health badge
    try:
        json.dumps(config)
        config_valid = True
    except Exception:
        config_valid = False
    with st.container(horizontal=True):
        st.subheader(":material/settings: Configuration")
        st.badge("Valid" if config_valid else "Invalid",
                 color="green" if config_valid else "red")

    # -- 6.1 / 6.2: Config editor (read-only + editable) --
    config_col_view, config_col_edit = st.columns([3, 1])
    with config_col_edit:
        config_edit_mode = st.toggle("Edit mode", key="config_edit_toggle",
                                     help="Toggle to edit config.json directly")

    if config_edit_mode:
        config_json_str = json.dumps(config, indent=2)
        edited = st.text_area("config.json", value=config_json_str, height=500,
                              key="config_editor_area",
                              help="Edit the configuration JSON directly.")
        with st.container(horizontal=True):
            if st.button(":material/save: Save Config", type="primary", key="btn_save_config"):
                try:
                    new_cfg = json.loads(edited)
                    config.clear()
                    config.update(new_cfg)
                    save_config()
                    reload_config()
                    st.session_state.env_check = None
                    st.toast("Config saved and reloaded.")
                    log_event(logger, "INFO", "config_saved", details={"source": "editor"})
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON: {e}")
            if st.button(":material/refresh: Reload Config", key="btn_reload_config"):
                reload_config()
                st.session_state.env_check = None
                st.toast("Config reloaded from disk.")
        st.warning("Some changes (model, categories) require re-running analysis to take effect.")
    else:
        with st.expander("View config.json (read-only)", expanded=False):
            st.json(config)

    st.space()

    # -- 6.3: Category management --
    st.subheader(":material/label: Categories")
    st.caption(f"{len(ALLOWED_CATEGORIES)} categories configured")

    edit_cats = st.session_state.get("edit_categories", list(ALLOWED_CATEGORIES))
    cat_df = pd.DataFrame({"Category": edit_cats})
    edited = st.data_editor(
        cat_df,
        num_rows="dynamic",
        hide_index=True,
        height=360,
        width="stretch",
        key="category_editor",
        column_config={
            "Category": st.column_config.TextColumn(
                "Category",
                width="stretch",
                max_chars=80,
            ),
        },
    )
    new_cats = ["" if pd.isna(c) else str(c).strip() for c in edited["Category"].tolist()]
    st.session_state["edit_categories"] = new_cats

    st.caption("Add a row with the '+' button. Select rows and use 'Delete row(s)' to remove them.")

    with st.container(horizontal=True):
        if st.button(":material/save: Save Categories", type="primary", key="btn_save_cats"):
            cleaned = [normalize_category(c) for c in new_cats if c.strip()]
            cleaned = [c for c in cleaned if c]
            if len(cleaned) != len(set(cleaned)):
                st.error("Duplicate categories found. Please remove duplicates.")
            elif any(not c for c in cleaned):
                st.error("Empty category names are not allowed.")
            else:
                config["allowed_categories"] = cleaned
                save_config()
                reload_config()
                st.session_state.pop("edit_categories", None)
                st.session_state.pop("category_editor", None)
                st.success(f"Saved {len(cleaned)} categories.")
                log_event(logger, "INFO", "categories_updated",
                          details={"count": len(cleaned)})
                st.rerun()
        if st.button(":material/restart_alt: Reset", key="btn_reset_cats"):
            st.session_state.pop("edit_categories", None)
            st.session_state.pop("category_editor", None)
            st.rerun()

    st.space()

    # -- 6.4: Extension management --
    st.subheader(":material/format_list_bulleted: Supported Extensions")

    ext_col1, ext_col2, ext_col3, ext_col4 = st.columns(4)
    with ext_col1:
        video_exts = st.multiselect("Video Extensions",
                                     options=[".mp4", ".mov", ".avi", ".mkv", ".webm",
                                              ".flv", ".wmv", ".m4v", ".ts", ".mts"],
                                     default=list(config.get("video_extensions", [])),
                                     key="cfg_video_exts")
    with ext_col2:
        image_exts = st.multiselect("Image Extensions",
                                     options=[".jpg", ".jpeg", ".png", ".webp", ".gif",
                                              ".bmp", ".tiff", ".tif", ".heic", ".raw"],
                                     default=list(config.get("image_extensions", [])),
                                     key="cfg_image_exts")
    with ext_col3:
        doc_exts = st.multiselect("Document Extensions",
                                   options=[".pdf", ".docx", ".doc", ".txt", ".md", ".rtf",
                                            ".xlsx", ".csv", ".pptx"],
                                   default=list(config.get("document_extensions", [])),
                                   key="cfg_doc_exts")
    with ext_col4:
        audio_exts = st.multiselect("Audio Extensions",
                                     options=[".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a",
                                              ".wma", ".opus", ".aiff", ".alac", ".ape", ".wv"],
                                     default=list(config.get("audio_extensions", [])),
                                     key="cfg_audio_exts")

    if st.button(":material/save: Save Extensions", type="primary", key="btn_save_exts"):
        config["video_extensions"] = sorted(set(video_exts))
        config["image_extensions"] = sorted(set(image_exts))
        config["document_extensions"] = sorted(set(doc_exts))
        config["audio_extensions"] = sorted(set(audio_exts))
        save_config()
        reload_config()
        st.success(f"Saved {len(video_exts)} video + {len(image_exts)} image + {len(doc_exts)} document + {len(audio_exts)} audio extensions.")
        log_event(logger, "INFO", "extensions_updated",
                  details={"video": len(video_exts), "image": len(image_exts), "document": len(doc_exts), "audio": len(audio_exts)})

    st.space()

    # -- S.4: Wipe local model cache --
    st.subheader(":material/smart_toy: Model Management")
    st.caption("Manage the local AI model used for analysis")

    with st.expander("Wipe local model cache", expanded=False):
        st.warning("This will permanently delete the local Qwen2.5-VL model (~5GB). "
                   "Re-download will be required to use local mode.")
        confirm_wipe = st.checkbox("I understand this will delete the model", key="confirm_model_wipe")
        if st.button(":material/delete_forever: Wipe Local Model", type="secondary", disabled=not confirm_wipe,
                     key="btn_wipe_model"):
            result = wipe_local_model()
            if result.get("ok"):
                st.success(result.get("message", "Model wiped successfully."))
                st.session_state.env_check = None
                log_event(logger, "INFO", "model_wipe",
                          details={"message": result.get("message", "")})
                st.rerun()
            else:
                st.error(result.get("message", "Failed to wipe model."))

    st.space()

    # -- Reset app state and settings (single home for this action) --
    with st.expander("Reset app state and settings", expanded=False):
        st.warning("Clears pipeline state, staged files, analysis progress, "
                   "analytics logs, and the output directory setting. This cannot be undone.")
        if st.button(":material/delete_sweep: Reset App and Settings", type="secondary",
                     key="config_reset"):
            confirm_reset()

    st.space()

    # -- Restore default config --
    with st.expander("Restore default configuration", expanded=False):
        st.warning("This will replace config.json with the factory default. "
                    "All custom settings, prompts, and categories will be lost.")
        confirm_restore = st.checkbox("I understand — restore factory defaults", key="confirm_restore_cfg")
        if st.button(":material/restore: Restore Default Config", type="primary",
                      disabled=not confirm_restore, key="btn_restore_config"):
            if restore_default_config():
                reload_config()
                st.session_state.env_check = None
                st.toast("Config restored to factory defaults.")
                st.rerun()
            else:
                st.error("config.default.json not found — cannot restore.")

# -----------------------------------------------------------------------------
# Footer — always renders at the bottom
# -----------------------------------------------------------------------------

st.markdown(
    "<hr style='margin-top: 3rem; margin-bottom: 0.5rem; border-color: #27272A;'>"
    "<p style='text-align: center; color: #71717A; font-size: 0.8rem;'>"
    f"AI Media Renamer {VERSION} &mdash; "
    "Made with love from Tanzania by "
    "<a href='https://github.com/Abdulmusawwir/ai-media-renamer' "
    "   style='color: #A1A1AA; text-decoration: none;'>Abdul Musawwir</a>"
    " &mdash; "
    "<a href='https://github.com/sponsors/Abdulmusawwir' "
    "   style='color: #A1A1AA; text-decoration: none;'>Sponsor</a>"
    " &middot; "
    "<a href='https://buymeacoffee.com/abdulmusawwir' "
    "   style='color: #A1A1AA; text-decoration: none;'>Buy Me a Coffee</a>"
    "</p>",
    unsafe_allow_html=True,
)


