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
  const headers: Record<string, string> = {};
  // Attach the LAN auth bearer token (populated by getAnalysisToken) so REST
  // calls respect AMR_AUTH_ENABLED in the same way the WebSocket does.
  if (_cachedToken) headers["Authorization"] = `Bearer ${_cachedToken}`;
  // Explicitly omit credentials (the app authenticates via bearer tokens, not
  // cookies). This keeps every request on the simple (non-credentialed) CORS
  // path, which is required for the permissive `Access-Control-Allow-Origin: *`
  // served by the backend to actually take effect on cross-origin loads.
  const opts: RequestInit = { method, headers, credentials: "omit" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(url, opts);
  } catch (e) {
    // Network-level failure (server down, wrong origin, CORS, mixed content).
    // Surface the URL so the failure is diagnosable from the UI toast.
    throw new Error(
      `API ${method} ${path} request failed (network): ${String(e)} [url=${url}]`
    );
  }
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

// NOTE: the backend route `PUT /api/config` accepts the patch object *wrapped* in
// a `patch` key (`{ patch: { ...partialConfig } }`), so we wrap it before sending.
export function putConfig(patch: Json): Promise<Json> {
  return request<Json>("PUT", "/api/config", { patch });
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

export interface CommitPayload {
  assets?: StagedAsset[];
  target_dir?: string;
  sort_folders?: boolean;
  skip_rename?: boolean;
  skip_metadata?: boolean;
}

export function commit(payload: CommitPayload): Promise<{ committed: number; results: string[] }> {
  return request<{ committed: number; results: string[] }>(
    "POST",
    "/api/commit",
    payload
  );
}

export function rollback(): Promise<Json> {
  // Route accepts an optional empty body; send no body (safest).
  const url = `${API_BASE}/api/rollback`;
  const headers: Record<string, string> = {};
  if (_cachedToken) headers["Authorization"] = `Bearer ${_cachedToken}`;
  return fetch(url, { method: "POST", headers }).then(async (res) => {
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const err = await res.json();
        detail = err.detail || err.message || detail;
      } catch {
        /* keep default detail */
      }
      throw new Error(`API POST /api/rollback failed: ${detail}`);
    }
    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("application/json")) return (await res.json()) as Json;
    return {} as Json;
  });
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

let _cachedToken: string | null = null;
let _tokenFetchedAt = 0;
// JWT lifetime is 12h; refresh a bit earlier to avoid sending an expired token.
const TOKEN_TTL_MS = 11 * 60 * 60 * 1000;

/**
 * Fetch a LAN auth token when the backend has auth enabled. Tokens are cached
 * in memory and reused until near expiry — they are never persisted to disk
 * (keeps the token out of the localStorage/XSS theft surface for a same-origin
 * local app). Returns null when auth is disabled or the endpoint is
 * unreachable, so callers can proceed unauthenticated in the default mode.
 */
export async function getAnalysisToken(): Promise<string | null> {
  const now = Date.now();
  if (_cachedToken && now - _tokenFetchedAt < TOKEN_TTL_MS) {
    return _cachedToken;
  }
  try {
    const res = await request<{ enabled: boolean; token?: string }>(
      "POST",
      "/api/auth/token"
    );
    if (res.enabled && res.token) {
      _cachedToken = res.token;
      _tokenFetchedAt = now;
      return _cachedToken;
    }
    _cachedToken = null;
    return null;
  } catch {
    // Token endpoint unreachable — assume auth disabled / backend down.
    return null;
  }
}

export function connectAnalysisWS(
  params: AnalysisParams,
  handlers: WSHandlers,
  token?: string | null
): AnalysisWSController {
  const suffix = token ? `?token=${encodeURIComponent(token)}` : "";
  const ws = new WebSocket(wsBaseFor(`/api/analyze/stream${suffix}`));

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
