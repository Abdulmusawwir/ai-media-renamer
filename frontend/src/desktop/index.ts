// Desktop (Tauri) bridge. Dynamically imports Tauri APIs only when running
// inside the desktop shell, so browser builds never require Tauri modules.
export interface DesktopUpdate {
  version: string;
  notes?: string;
  date?: string;
}

export interface Desktop {
  isDesktop: boolean;
  token: string | null;
  port: number | null;
  version: string | null;
  invoke<T = unknown>(cmd: string, args?: Record<string, unknown>): Promise<T>;
  listen<T = unknown>(event: string, cb: (payload: T) => void): Promise<() => void>;
  pickFiles(): Promise<string[]>;
  pickFolder(): Promise<string | null>;
  installDesktopDropHandler(onPaths: (paths: string[]) => void): Promise<() => void>;
  checkForUpdate(): Promise<DesktopUpdate | null>;
  downloadAndInstall(
    update: DesktopUpdate,
    onProgress?: (event: unknown) => void
  ): Promise<void>;
  relaunch(): Promise<void>;
}

const w = window as unknown as {
  __AMR_DESKTOP__?: boolean;
  __AMR_DESKTOP_TOKEN__?: string;
  __AMR_DESKTOP_PORT__?: number;
  __AMR_DESKTOP_VERSION__?: string;
};

export const isDesktop: boolean = Boolean(w.__AMR_DESKTOP__);

let _token: string | null = w.__AMR_DESKTOP_TOKEN__ ?? null;
let _port: number | null = w.__AMR_DESKTOP_PORT__ ?? null;
let _version: string | null = w.__AMR_DESKTOP_VERSION__ ?? null;

export function setDesktopToken(token: string | null): void {
  _token = token;
}

export const desktop: Desktop = {
  isDesktop,
  get token() {
    return _token;
  },
  get port() {
    return _port;
  },
  get version() {
    return _version;
  },
  async invoke<T = unknown>(cmd: string, args?: Record<string, unknown>): Promise<T> {
    if (!isDesktop) throw new Error("not in desktop mode");
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke<T>(cmd, args);
  },
  async listen<T = unknown>(event: string, cb: (payload: T) => void): Promise<() => void> {
    if (!isDesktop) return () => {};
    const { listen } = await import("@tauri-apps/api/event");
    const unlisten = await listen<T>(event, (e) => cb(e.payload));
    return unlisten;
  },
  async pickFiles(): Promise<string[]> {
    if (!isDesktop) return [];
    const { open } = await import("@tauri-apps/plugin-dialog");
    const res = await open({ multiple: true, directory: false });
    if (!res) return [];
    return Array.isArray(res) ? res : [res];
  },
  async pickFolder(): Promise<string | null> {
    if (!isDesktop) return null;
    const { open } = await import("@tauri-apps/plugin-dialog");
    const res = await open({ directory: true, multiple: false });
    if (Array.isArray(res)) return res[0] ?? null;
    return res ?? null;
  },
  async installDesktopDropHandler(onPaths: (paths: string[]) => void): Promise<() => void> {
    if (!isDesktop) return () => {};
    const { getCurrentWebview } = await import("@tauri-apps/api/webview");
    const webview = getCurrentWebview();
    const unlisten = await webview.onDragDropEvent((event) => {
      const payload = event.payload as { type?: string; paths?: string[] };
      if (payload?.type === "drop" && Array.isArray(payload.paths)) {
        onPaths(payload.paths);
      }
    });
    return unlisten;
  },
  async checkForUpdate(): Promise<DesktopUpdate | null> {
    if (!isDesktop) return null;
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const update = await check();
      if (!update) return null;
      return { version: update.version, notes: update.body ?? undefined, date: update.date ?? undefined };
    } catch {
      return null;
    }
  },
  async downloadAndInstall(update: DesktopUpdate, onProgress?: (event: unknown) => void): Promise<void> {
    if (!isDesktop) return;
    const { check } = await import("@tauri-apps/plugin-updater");
    const u = await check();
    if (!u) return;
    await u.downloadAndInstall((e) => onProgress?.(e));
  },
  async relaunch(): Promise<void> {
    if (!isDesktop) return;
    const { relaunch } = await import("@tauri-apps/plugin-process");
    await relaunch();
  },
};