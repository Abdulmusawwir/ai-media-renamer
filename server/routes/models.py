"""GET /api/models, POST /api/models/download, GET /api/models/{name}/download-status.

Model catalog + background model downloads. The download runs in a daemon
thread and reports progress through an in-memory state dict keyed by model name.
"""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

import engine
from server import deps
from server.schemas import ModelsDownloadRequest, ModelsResponse

router = APIRouter(prefix="/api", tags=["models"])

# In-memory download progress/state keyed by model name. Good enough for a
# single-user local/LAN tool; a later phase can back this with persistence.
_DOWNLOAD_STATE: dict[str, dict[str, Any]] = {}
_STATE_LOCK = threading.Lock()


def _record_state(name: str, **fields: Any) -> None:
    with _STATE_LOCK:
        state = _DOWNLOAD_STATE.get(name, {})
        state.update(fields)
        _DOWNLOAD_STATE[name] = state


@router.get("/models", response_model=ModelsResponse)
def get_models() -> dict:
    """Return registered providers, the active provider, and available models."""
    providers = engine.list_providers()
    current = engine.CURRENT_PROVIDER

    models: list[str] = []
    try:
        provider = engine.get_provider(current)
        models = provider.available_models()
    except Exception:
        models = []

    # Lightweight catalog built from config-stored provider model lists.
    catalog: list[dict] = []
    model_cfg = engine.config.get("model", {})
    for pname in providers:
        pconf = model_cfg.get("providers", {}).get(pname, {})
        for m in pconf.get("models", []):
            catalog.append({"provider": pname, "name": m})

    return {
        "providers": providers,
        "current_provider": current,
        "models": models,
        "catalog": catalog,
    }


def _run_download(name: str) -> None:
    """Background worker: download ``name`` and record its progress/state."""
    try:
        engine.download_llamacpp_model(name, on_progress=_on_progress)
        _record_state(name, state="done", error=None)
    except Exception as exc:  # surface the failure to the status endpoint
        _record_state(name, state="error", error=str(exc))


def _on_progress(downloaded: int, total: int) -> None:
    _record_state(name=_current_download_name, downloaded=downloaded, total=total)


# ``_on_progress`` needs the in-flight model name; stash it on the worker thread.
_current_download_name = ""


@router.post("/models/download", dependencies=[Depends(deps.require_auth)])
def download_model(req: ModelsDownloadRequest) -> dict:
    """Trigger a background GGUF model download via ``engine.download_llamacpp_model``.

    Accepts ``{model: <name>}`` and starts the download in a daemon thread,
    returning immediately with ``accepted``. Poll ``GET /api/models/{name}/download-status``
    for progress.
    """
    model_name = req.model
    if not model_name:
        raise HTTPException(status_code=400, detail="model name required")
    if not hasattr(engine, "download_llamacpp_model"):
        raise HTTPException(status_code=501, detail="engine model download not available")

    _record_state(model_name, state="downloading", downloaded=0, total=None, error=None)

    def _worker() -> None:
        global _current_download_name
        _current_download_name = model_name
        _run_download(model_name)

    thread = threading.Thread(target=_worker, name=f"model-dl-{model_name}", daemon=True)
    thread.start()
    return {"accepted": True, "model": model_name}


@router.get("/models/{name}/download-status")
def download_status(name: str) -> dict:
    """Return the download progress/state for ``name``.

    ``state`` is one of ``downloading``, ``done``, ``error`` (or ``idle`` when no
    download has been requested for this name in this process).
    """
    with _STATE_LOCK:
        state = dict(_DOWNLOAD_STATE.get(name, {}))
    if not state:
        return {"state": "idle", "downloaded": 0, "total": None, "error": None}
    state.setdefault("state", "downloading")
    state.setdefault("downloaded", 0)
    state.setdefault("total", None)
    state.setdefault("error", None)
    return state
