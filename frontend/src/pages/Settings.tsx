import { PageHeader } from "../components/PageHeader";
import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Save, RefreshCw, Cpu, Sparkles, FolderOpen, FileText, Download, ExternalLink } from "lucide-react";
import { useConfig, usePutConfig } from "../hooks/api";
import { useStore, useToast } from "../store";
import { Skeleton } from "../components/Skeleton";
import type { Json } from "../api/client";
import { desktop, isDesktop } from "../desktop";
import { formatUpdateError } from "../desktop/updateErrors";

export default function Settings() {
  const toast = useToast();
  const query = useConfig();
  const config = useStore((s) => s.config);
  const setConfig = useStore((s) => s.setConfig);
  const put = usePutConfig();

  const [text, setText] = useState<string>("");
  const [dirty, setDirty] = useState(false);
  const [closeToTray, setCloseToTray] = useState<boolean>(true);
  const pendingUpdateCheck = useStore((s) => s.pendingUpdateCheck);
  const setPendingUpdateCheck = useStore((s) => s.setPendingUpdateCheck);

  const [updateState, setUpdateState] = useState<
    "idle" | "checking" | "up-to-date" | "available" | "downloading" | "installing" | "error"
  >("idle");
  const [updateInfo, setUpdateInfo] = useState<{ version: string; notes?: string; date?: string } | null>(null);
  const [updateProgress, setUpdateProgress] = useState<number>(0);
  const [updateError, setUpdateError] = useState<string>("");
  // Guards against a tray event and the Settings button finishing out of order.
  const checkSeq = useRef(0);

  useEffect(() => {
    if (!isDesktop) return;
    desktop
      .invoke<{ close_to_tray: boolean }>("get_shell_settings")
      .then((s) => setCloseToTray(Boolean(s?.close_to_tray)))
      .catch(() => undefined);
  }, []);

  const runUpdateCheck = async () => {
    if (!isDesktop) return;
    const seq = ++checkSeq.current;
    setUpdateState("checking");
    setUpdateError("");
    try {
      const u = await desktop.checkForUpdate();
      if (seq !== checkSeq.current) return;
      if (!u) {
        setUpdateInfo(null);
        setUpdateState("up-to-date");
      } else {
        setUpdateInfo(u);
        setUpdateState("available");
      }
    } catch (err) {
      if (seq !== checkSeq.current) return;
      setUpdateError(formatUpdateError(err));
      setUpdateState("error");
    }
  };

  useEffect(() => {
    if (!isDesktop) return;
    if (!pendingUpdateCheck) return;
    setPendingUpdateCheck(false);
    runUpdateCheck();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingUpdateCheck]);

  // Tray "Check for Updates" triggers the same flow.
  useEffect(() => {
    if (!isDesktop) return;
    let unlisten: (() => void) | undefined;
    desktop
      .listen("desktop://check-updates", () => {
        runUpdateCheck();
      })
      .then((u) => {
        unlisten = u;
      })
      .catch(() => undefined);
    return () => {
      unlisten?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDesktop]);

  const installUpdate = async () => {
    if (!updateInfo) return;
    if (updateState === "downloading" || updateState === "installing") return;
    // Guard: check backend busy state first.
    try {
      const status = await desktop.invoke<{
        analysis_running: boolean;
        commit_running: boolean;
        model_downloads_running: boolean;
        model_migration_running: boolean;
        setup_running: boolean;
      }>("get_backend_status");
      const busy =
        status.analysis_running ||
        status.commit_running ||
        status.model_downloads_running ||
        status.model_migration_running ||
        status.setup_running;
      if (busy) {
        const ok = window.confirm(
          "An operation is still running. Installing the update may interrupt it. Continue?"
        );
        if (!ok) return;
      }
    } catch {
      /* backend unreachable — treat as not busy */
    }
    setUpdateState("downloading");
    setUpdateProgress(0);
    try {
      await desktop.downloadAndInstall(updateInfo, (e: unknown) => {
        const ev = e as { event?: string; data?: { contentLength?: number; chunkLength?: number } };
        if (ev?.event === "Started") {
          setUpdateProgress(0);
        } else if (ev?.event === "Progress") {
          setUpdateProgress((p) => p + (ev.data?.chunkLength ?? 0));
        }
      });
      setUpdateState("installing");
      await desktop.relaunch();
    } catch (err) {
      setUpdateError(formatUpdateError(err));
      setUpdateState("error");
    }
  };

  // Seed the editor when the query resolves with fresh config.
  const [seededKey, setSeededKey] = useState<string>("");
  const key = String(query.dataUpdatedAt);
  if (key !== seededKey && query.data) {
    setText(JSON.stringify(query.data, null, 2));
    setSeededKey(key);
    setDirty(false);
  }

  const save = async () => {
    try {
      const parsed = JSON.parse(text) as Json;
      const res = await put.mutateAsync(parsed);
      setConfig(res);
      setText(JSON.stringify(res, null, 2));
      setDirty(false);
      toast.success("Config saved.");
    } catch (err) {
      toast.error(`Invalid JSON or save failed: ${String(err)}`);
    }
  };

  const reload = () => {
    query.refetch();
    toast.info("Reloading config…");
  };

  if (query.isLoading) {
    return (
      <div className="space-y-4">
        <PageHeader
          icon={Cpu}
          title="Settings"
          description="View and edit the engine configuration (saved to config.json on the backend)."
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  const provider =
    (config?.model as Json | undefined)?.current_provider ??
    (config?.model as Json | undefined)?.last_provider ??
    "—";
  const profileKeys = config?.prompt_profiles
    ? Object.keys(
        ((config.prompt_profiles as Json).profiles as Json) ?? {}
      )
    : [];

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Settings</h2>
        <p className="text-sm text-text-dim">
          View and edit the engine configuration (saved to config.json on the
          backend).
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="ui-surface">
          <div className="mb-1 flex items-center gap-2 text-xs font-medium text-text-dim">
            <Cpu size={14} /> Provider
          </div>
          <div className="text-sm">{String(provider)}</div>
        </div>
        <div className="ui-surface">
          <div className="mb-1 flex items-center gap-2 text-xs font-medium text-text-dim">
            <Sparkles size={14} /> Prompt profiles
          </div>
          <div className="text-sm">
            {profileKeys.length ? profileKeys.join(", ") : "—"}
          </div>
        </div>
      </div>

      {isDesktop && (
        <div className="ui-surface">
          <div className="mb-3 text-xs font-medium text-text-dim">
            Desktop shell
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={closeToTray}
              onChange={async (e) => {
                const v = e.target.checked;
                setCloseToTray(v);
                try {
                  await desktop.invoke("set_close_to_tray", { value: v });
                  toast.success("Shell preference saved.");
                } catch (err) {
                  toast.error(String(err));
                }
              }}
            />
            Close to tray (hide window instead of quitting)
          </label>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              className="ui-btn ui-btn-secondary"
              onClick={() => desktop.invoke("open_logs").catch((e) => toast.error(String(e)))}
            >
              <FileText size={14} /> Open logs
            </button>
            <button
              type="button"
              className="ui-btn ui-btn-secondary"
              onClick={() => desktop.invoke("open_data_folder").catch((e) => toast.error(String(e)))}
            >
              <FolderOpen size={14} /> Open data folder
            </button>
          </div>
        </div>
      )}

      <div className="ui-surface">
        <div className="mb-3 text-xs font-medium text-text-dim">Updates</div>
        {!isDesktop ? (
          <p className="text-sm text-text-dim">
            Updates are managed by the desktop app.{" "}
            <a
              className="text-accent underline"
              href="https://github.com/Abdulmusawwir/ai-media-renamer/releases/latest"
              target="_blank"
              rel="noreferrer"
            >
              View releases
            </a>
          </p>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="ui-btn ui-btn-secondary"
                onClick={runUpdateCheck}
                disabled={updateState === "checking" || updateState === "downloading" || updateState === "installing"}
              >
                <RefreshCw size={14} /> Check for updates
              </button>
              {updateState === "checking" && <span className="text-xs text-text-dim">Checking…</span>}
              {updateState === "up-to-date" && <span className="text-xs text-ok">You're up to date.</span>}
            </div>
            {updateState === "available" && updateInfo && (
              <div className="rounded-md border border-border bg-bg p-3 text-sm">
                <div className="font-medium">Version {updateInfo.version} available</div>
                {updateInfo.notes && (
                  <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs text-text-dim">
                    {updateInfo.notes}
                  </pre>
                )}
                <button
                  type="button"
                  className="ui-btn ui-btn-primary mt-3"
                  onClick={installUpdate}
                >
                  <Download size={14} /> Install update
                </button>
              </div>
            )}
            {updateState === "downloading" && (
              <div className="text-sm text-text-dim">
                Downloading update… {updateProgress > 0 ? `${updateProgress} bytes` : ""}
              </div>
            )}
            {updateState === "installing" && (
              <div className="text-sm text-text-dim">Installing and relaunching…</div>
            )}
            {updateState === "error" && (
              <div className="space-y-2">
                <div className="ui-inline-error">{updateError || "Update failed."}</div>
                <button
                  type="button"
                  className="rounded-md border border-border bg-bg-elev-2 px-3 py-2 text-xs hover:bg-bg"
                  onClick={runUpdateCheck}
                >
                  Retry
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="ui-surface">
        <label className="mb-2 block text-xs font-medium text-text-dim">
          Raw config (JSON)
        </label>
        <textarea
          className="h-80 w-full rounded-md border border-border bg-bg px-3 py-2 font-mono text-xs"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setDirty(true);
          }}
        />
        <div className="mt-3 flex items-center gap-2">
          <button
            className="ui-btn ui-btn-primary"
            onClick={save}
            disabled={put.isPending || !dirty}
          >
            <Save size={16} /> Save config
          </button>
          <button
            className="ui-btn ui-btn-secondary"
            onClick={reload}
          >
            <RefreshCw size={14} /> Reload
          </button>
          {dirty && (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-xs text-warn"
            >
              Unsaved changes
            </motion.span>
          )}
        </div>
      </div>
    </div>
  );
}
