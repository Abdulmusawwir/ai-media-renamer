// Typed API client for the AI Media Renamer FastAPI backend.
//
// Base URL: import.meta.env.VITE_API_BASE, defaulting to "" which means the
// requests are relative and resolved against the current origin. During `vite
// dev` the /api/* paths are proxied to the backend (see vite.config.ts), so the
// empty default "just works" against `uvicorn server.main:app --port 8000`.

const RAW_BASE = (import.meta.env.VITE_API_BASE ?? "").trim();
export const API_BASE = RAW_BASE === "" ? "" : RAW_BASE.replace(/\/$/, "");

async function request<T = any>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const opts: RequestInit = { method, headers: {} };
  if (body !== undefined) {
    (opts.headers as Record<string, string>)["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const err = await res.json();
      detail = err.detail || err.message || detail;
    } catch {
      /* keep default detail */
    }
    throw new Error(`API ${method} ${path} failed: ${detail}`);
  }
  // Some endpoints (CSV export) return text; callers handle parsing.
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}

// ---------------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------------

export type Json = Record<string, unknown>;

export interface StagedAsset {
  original_path: string;
  original_name: string;
  staged_name: string;
  category: string;
  tags: string[];
  summary?: string;
  topic?: string;
  description?: string;
  base64_data?: string;
  audio_transcription?: string;
  commit_status?: string;
  committed_path?: string;
  commit_error?: string;
  // Client-only UI flag for bulk selection in the staging table.
  selected?: boolean;
}

export interface EnvironmentResponse {
  ffmpeg: boolean;
  exiftool: boolean;
  llamacpp_running: boolean;
  model_available: boolean;
  vision_models: string[];
  text_models: string[];
  errors: string[];
}

export interface ModelsResponse {
  providers: string[];
  current_provider: string;
  models: string[];
  catalog: { provider: string; name: string }[];
}

export interface SessionInfo {
  name?: string;
  path?: string;
  modified?: string;
  size?: number;
  [key: string]: unknown;
}

export interface StagingList {
  assets: StagedAsset[];
  count: number;
}

export interface BrowseEntry {
  name: string;
  path: string;
  kind: string;
  is_media?: boolean;
  size?: number;
}

export interface BrowseResponse {
  path: string;
  parent: string | null;
  folders: BrowseEntry[];
  files: BrowseEntry[];
}

// ---------------------------------------------------------------------------
// REST endpoints
// ---------------------------------------------------------------------------

export function getEnvironment(): Promise<EnvironmentResponse> {
  return request<EnvironmentResponse>("GET", "/api/environment");
}

export function getConfig(): Promise<Json> {
  return request<Json>("GET", "/api/config");
}

// NOTE: the backend route `PUT /api/config` accepts the patch object *directly*
// as the request body (not wrapped in { patch: ... }), so we send it as-is.
export function putConfig(patch: Json): Promise<Json> {
  return request<Json>("PUT", "/api/config", patch);
}

export function browseFolder(path?: string): Promise<BrowseResponse> {
  const qs = path ? `?path=${encodeURIComponent(path)}` : "";
  return request<BrowseResponse>("GET", `/api/browse${qs}`);
}

export function getStaging(): Promise<StagingList> {
  return request<StagingList>("GET", "/api/staging");
}

// PUT /api/staging expects the full list (array) as the body.
export function putStaging(rows: StagedAsset[]): Promise<{ count: number }> {
  return request<{ count: number }>("PUT", "/api/staging", rows);
}

export function bulkUpdateStaging(payload: {
  selected: string[];
  updates: Json;
}): Promise<{ applied: number }> {
  return request<{ applied: number }>("POST", "/api/staging/bulk", payload);
}

export async function exportStagingCsv(): Promise<string> {
  const text = await request<string>("GET", "/api/staging/export");
  return text;
}

export function importStagingCsv(
  csv: string
): Promise<{ imported: number; warnings: string[] }> {
  // Route accepts { csv: "..." } directly as the body.
  return request<{ imported: number; warnings: string[] }>(
    "POST",
    "/api/staging/import",
    { csv }
  );
}

export function commit(payload: {
  assets?: StagedAsset[];
  target_dir?: string;
  sort_folders?: boolean;
  skip_rename?: boolean;
  skip_metadata?: boolean;
}): Promise<{ committed: number; results: string[] }> {
  return request<{ committed: number; results: string[] }>(
    "POST",
    "/api/commit",
    payload
  );
}

export function rollback(): Promise<Json> {
  // Route has no body parameter; send an empty object to be safe.
  return request<Json>("POST", "/api/rollback", {});
}

export function listSessions(): Promise<{ sessions: SessionInfo[] }> {
  return request<{ sessions: SessionInfo[] }>("GET", "/api/sessions");
}

export function saveSession(settings: Json = {}): Promise<{ saved: boolean; path: string }> {
  return request<{ saved: boolean; path: string }>("POST", "/api/sessions", {
    settings,
  });
}

export function loadSession(id: string): Promise<{ loaded: string; asset_count: number }> {
  return request<{ loaded: string; asset_count: number }>(
    "GET",
    `/api/sessions/${encodeURIComponent(id)}`
  );
}

export function deleteSession(id: string): Promise<{ deleted: string }> {
  return request<{ deleted: string }>(
    "DELETE",
    `/api/sessions/${encodeURIComponent(id)}`
  );
}

export function listModels(): Promise<ModelsResponse> {
  return request<ModelsResponse>("GET", "/api/models");
}

export function downloadModel(name: string): Promise<Json> {
  // Route accepts { model: "..." } or { name: "..." }.
  return request<Json>("POST", "/api/models/download", { model: name });
}

// ---------------------------------------------------------------------------
// WebSocket: /api/analyze/stream
// ---------------------------------------------------------------------------

export interface AnalysisParams {
  files: string[];
  profile?: string | null;
  settings?: Json;
}

export interface AnalysisEvent {
  type: string;
  [key: string]: unknown;
}

export interface WSHandlers {
  onEvent?: (type: string, data: AnalysisEvent) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (event: Event) => void;
}

export interface AnalysisWSController {
  cancel: () => void;
  close: () => void;
}

function wsBaseFor(path: string): string {
  if (!API_BASE) {
    // Relative path — browser resolves protocol/host from the page.
    return path;
  }
  const wsBase = API_BASE.replace(/^http/, "ws");
  return `${wsBase}${path}`;
}

export function connectAnalysisWS(
  params: AnalysisParams,
  handlers: WSHandlers
): AnalysisWSController {
  const ws = new WebSocket(wsBaseFor("/api/analyze/stream"));

  ws.onopen = () => {
    ws.send(
      JSON.stringify({
        files: params.files,
        profile: params.profile ?? null,
        settings: params.settings ?? {},
      })
    );
    handlers.onOpen?.();
  };

  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data) as AnalysisEvent;
      handlers.onEvent?.(data.type, data);
    } catch {
      handlers.onEvent?.("error", { type: "error", detail: "failed to parse server message" });
    }
  };

  ws.onerror = (e) => handlers.onError?.(e);
  ws.onclose = () => handlers.onClose?.();

  return {
    cancel: () => {
      try {
        ws.send(JSON.stringify({ action: "cancel" }));
      } catch {
        /* socket may already be closed */
      }
    },
    close: () => ws.close(),
  };
}
