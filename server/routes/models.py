"""GET /api/models and POST /api/models/download — model catalog + download."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

import engine
from server.schemas import ModelsDownloadRequest, ModelsResponse

router = APIRouter(prefix="/api", tags=["models"])


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


@router.post("/models/download")
def download_model(req: ModelsDownloadRequest) -> dict:
    """Trigger a model download if the engine exposes a helper.

    The engine currently has no server-callback download helper, so this
    endpoint is intentionally minimal: it returns ``accepted`` and notes that
    downloads are handled by the setup wizard / llama.cpp tooling. Wire a real
    engine helper here once one exists.
    """
    model_name = req.model
    if not model_name:
        raise HTTPException(status_code=400, detail="model name required")
    # No engine download helper exists yet; surface a clear, non-failing status.
    return {
        "accepted": True,
        "model": model_name,
        "detail": "model download is handled by the setup wizard; no engine helper available yet",
    }
