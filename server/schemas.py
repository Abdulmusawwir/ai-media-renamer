"""Pydantic request/response schemas for the v2 backend API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Payload to start an analysis run (POST or WS init message)."""

    files: list[str] = Field(default_factory=list)
    profile: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class AnalyzeCancel(BaseModel):
    """A control message sent over the WS to cancel the running analysis."""

    action: str = "cancel"


class StagingBulkRequest(BaseModel):
    """Apply a bulk edit to selected staged rows."""

    selected: list[str] = Field(default_factory=list)
    updates: dict[str, Any] = Field(default_factory=dict)


class CommitRequest(BaseModel):
    """Payload to commit staged assets to disk."""

    assets: list[dict[str, Any]] = Field(default_factory=list)
    target_dir: str = "."
    sort_folders: bool = True
    skip_rename: bool = False
    skip_metadata: bool = False


class ConfigPutRequest(BaseModel):
    """Partial config patch merged into the engine config."""

    patch: dict[str, Any] = Field(default_factory=dict)


class StagingImportRequest(BaseModel):
    """Import staging rows from CSV text."""

    csv: str = ""


class ModelsDownloadRequest(BaseModel):
    """Request to download a model by name."""

    model: str = ""


class RollbackRequest(BaseModel):
    """Rollback request — no fields; body is optional."""


class SessionCreateRequest(BaseModel):
    """Create a session from the current staging set."""

    settings: dict[str, Any] = Field(default_factory=dict)


class EnvironmentResponse(BaseModel):
    """Tool/service availability snapshot."""

    ffmpeg: bool = False
    exiftool: bool = False
    llamacpp_running: bool = False
    model_available: bool = False
    vision_models: list[str] = Field(default_factory=list)
    text_models: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ModelsResponse(BaseModel):
    """Available models and providers."""

    providers: list[str] = Field(default_factory=list)
    current_provider: str = ""
    models: list[str] = Field(default_factory=list)
    catalog: list[dict[str, Any]] = Field(default_factory=list)
