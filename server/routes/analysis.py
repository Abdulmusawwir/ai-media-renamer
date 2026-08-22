"""POST /api/analyze and WS /api/analyze/stream — AI analysis pipeline.

The WS endpoint is the primary flow: the client connects, sends
``{files, profile, settings}`` and receives a stream of
``extraction_progress`` / ``asset_analyzed`` / ``complete`` (or ``cancelled``)
events. The client may send ``{action:"cancel"}`` to abort the run.

``POST /api/analyze`` delegates to the same core ``run_analysis`` function in a
background thread and accepts the job immediately (the WS is used for live
progress). Both flows accumulate staged assets into ``deps.ACTIVE_STAGING``.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import engine
from server import deps
from server.schemas import AnalyzeRequest
from server.ws import make_event, manager

router = APIRouter(prefix="/api", tags=["analysis"])


def _classify(path: Path) -> tuple[str, bool]:
    """Return (encoder_kind, is_text) for a media file path.

    ``is_text`` is True for audio (transcription) and document (text) assets,
    which are analyzed with the text/document AI path instead of vision.
    """
    suffix = path.suffix.lower()
    if suffix in engine.VIDEO_EXTENSIONS:
        return "video", False
    if suffix in engine.AUDIO_EXTENSIONS:
        return "audio", True
    if suffix in engine.DOCUMENT_EXTENSIONS:
        return "document", True
    return "image", False


def _extract(path: Path, kind: str):
    """Extract a preview/base64 (or text) for the asset."""
    hw_accel = engine.detect_hw_accel()
    if kind == "video":
        return engine.process_video_to_base64(path, hw_accel)
    if kind == "audio":
        result = engine.transcribe_audio(path)
        if isinstance(result, dict):
            return result.get("text", "")
        return ""
    if kind == "document":
        return engine.extract_text_from_file(path) or ""
    return engine.process_image_to_base64(path)


def _build_asset(path: Path, ai_data: dict, is_text: bool, kind: str, preview: str) -> dict:
    """Coerce an AI result into the engine staging-asset schema."""
    safe_name = engine.sanitize_name(ai_data.get("new_filename") or path.stem)
    category, _fallback = engine.validate_category(ai_data.get("suggested_category"))
    staged_name = safe_name
    return {
        "original_path": str(path),
        "original_name": path.name,
        "staged_name": staged_name,
        "category": category,
        "tags": ai_data.get("tags", []),
        "summary": ai_data.get("overall_visual_summary", ""),
        "topic": ai_data.get("topic", ""),
        "description": ai_data.get("description", ""),
        "base64_data": "" if is_text else (preview or ""),
        "audio_transcription": preview if (is_text and kind == "audio") else "",
        "commit_status": "pending",
    }


def run_analysis(
    files: list[str],
    profile: str | None,
    settings: dict,
    send_cb=None,
    cancel_event: threading.Event | None = None,
) -> list[dict]:
    """Run extraction + AI analysis for ``files`` and return staged assets.

    ``send_cb`` (optional) receives each WebSocket event dict as it happens.
    ``cancel_event`` (optional) aborts the run when set.
    """
    if profile:
        engine.set_active_profile(profile)

    template_string = settings.get("template_string")
    case_style = settings.get("case_style", engine.DEFAULT_CASE_STYLE)
    max_chars = int(settings.get("max_chars", engine.DEFAULT_MAX_FILENAME_CHARS) or 0)

    staging: list[dict] = []
    total = len(files)

    def emit(event: dict) -> None:
        if send_cb is not None:
            send_cb(event)

    emit(make_event("extraction_progress", processed=0, total=total))

    for idx, raw in enumerate(files, 1):
        if cancel_event is not None and cancel_event.is_set():
            emit(make_event("cancelled"))
            break

        path = Path(raw)
        if not path.exists():
            emit(make_event("asset_error", name=raw, error="file not found", index=idx, total=total))
            continue

        kind, is_text = _classify(path)
        try:
            preview = _extract(path, kind)
        except Exception as exc:  # extraction can fail (missing ffmpeg etc.)
            emit(make_event("asset_error", name=path.name, error=str(exc), index=idx, total=total))
            continue

        if not preview:
            emit(make_event("asset_error", name=path.name, error="extraction failed", index=idx, total=total))
            continue

        try:
            if is_text:
                ai = engine.analyze_document_with_ai(preview)
            else:
                ai = engine.analyze_asset_with_ai(preview)
        except Exception as exc:
            emit(make_event("asset_error", name=path.name, error=str(exc), index=idx, total=total))
            continue

        if not ai.get("ok"):
            detail = ai.get("detail") or ai.get("error") or "analysis failed"
            emit(make_event("asset_error", name=path.name, error=str(detail), index=idx, total=total))
            continue

        asset = _build_asset(path, ai.get("data", {}), is_text, kind, preview)

        if template_string:
            rendered = engine.apply_naming_template(
                template_string,
                {
                    "category": asset["category"],
                    "topic": asset["topic"],
                    "description": asset["description"],
                    "new_filename": asset["staged_name"],
                },
            )
            rendered = engine.apply_case_style(rendered, case_style)
            rendered = engine.truncate_filename(rendered, max_chars)
            asset["staged_name"] = rendered

        staging.append(asset)
        emit(make_event("asset_analyzed", asset=asset, index=idx, total=total))

    emit(make_event("complete", staged=staging, count=len(staging)))
    deps.set_active_staging(staging)
    return staging


@router.post("/analyze")
def post_analyze(req: AnalyzeRequest) -> dict:
    """Kick off analysis in a background thread and accept the job.

    The WebSocket ``/api/analyze/stream`` is the primary way to observe
    progress; this endpoint exists for fire-and-forget callers.
    """
    if not req.files:
        return {"accepted": False, "detail": "no files provided"}

    cancel_event = deps.reset_cancel_event()

    def _worker() -> None:
        run_analysis(req.files, req.profile, req.settings, send_cb=None, cancel_event=cancel_event)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return {"accepted": True, "files": len(req.files)}


@router.websocket("/analyze/stream")
async def ws_analyze(websocket: WebSocket) -> None:
    """Stream analysis progress. Client sends init/cancel control messages."""
    await manager.connect(websocket)
    cancel_event = deps.reset_cancel_event()
    loop = asyncio.get_running_loop()

    def _send(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(
            manager.send_personal_json(event, websocket), loop
        )

    analysis_thread: threading.Thread | None = None

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("action") == "cancel":
                cancel_event.set()
                continue

            files = data.get("files", [])
            profile = data.get("profile")
            settings = data.get("settings", {})
            if not files:
                await manager.send_personal_json(
                    make_event("error", detail="no files provided"), websocket
                )
                continue

            # Run the (blocking) engine pipeline on a worker thread so this
            # async loop stays free to receive a possible cancel message.
            analysis_thread = threading.Thread(
                target=run_analysis,
                args=(files, profile, settings, _send, cancel_event),
                daemon=True,
            )
            analysis_thread.start()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        cancel_event.set()
    except Exception:
        manager.disconnect(websocket)
