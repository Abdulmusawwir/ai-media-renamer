import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import { motion } from "framer-motion";
import {
  FolderOpen,
  Play,
  Square,
  UploadCloud,
  X,
  Settings2,
  Sparkles,
} from "lucide-react";
import {
  connectAnalysisWS,
  getStaging,
  type AnalysisWSController,
  type AnalysisParams,
  type BrowseEntry,
} from "../api/client";
import { useStore, useToast, type AnalysisSettings } from "../store";
import DirectoryPicker from "../components/DirectoryPicker";
import { Spinner } from "../components/Skeleton";

const MAX_WS_RETRIES = 3;

const FALLBACK_PROFILES = ["general_broll", "cinematography", "motion_overlays"];

const CASE_STYLES = [
  "snake_case",
  "camelCase",
  "kebab-case",
  "pascal_case",
  "lowercase",
  "title_case",
  "original",
];

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "ar", label: "Arabic" },
  { value: "fr", label: "French" },
  { value: "es", label: "Spanish" },
  { value: "de", label: "German" },
  { value: "ja", label: "Japanese" },
  { value: "zh", label: "Chinese" },
  { value: "auto", label: "Auto-detect" },
];

interface ProgressState {
  running: boolean;
  processed: number;
  total: number;
  log: string[];
  status: string;
}

const INITIAL_PROGRESS: ProgressState = {
  running: false,
  processed: 0,
  total: 0,
  log: [],
  status: "",
};

function profileOptions(config: Record<string, unknown> | null): {
  value: string;
  label: string;
}[] {
  const pp = (config?.prompt_profiles as
    | { profiles?: Record<string, { label?: string }> }
    | undefined)?.profiles;
  const keys = pp ? Object.keys(pp) : [];
  if (keys.length === 0) {
    return FALLBACK_PROFILES.map((p) => ({ value: p, label: p }));
  }
  return keys.map((k) => ({ value: k, label: pp?.[k]?.label ?? k }));
}

export default function Analysis() {
  const navigate = useNavigate();
  const toast = useToast();
  const config = useStore((s) => s.config);
  const setStaged = useStore((s) => s.setStaged);
  const analysisSettings = useStore((s) => s.analysisSettings);
  const setAnalysisSettings = useStore((s) => s.setAnalysisSettings);

  const wsRef = useRef<AnalysisWSController | null>(null);

  const [files, setFiles] = useState<string[]>([]);
  const [profile, setProfile] = useState<string>("");
  const [showSettings, setShowSettings] = useState(false);
  const [progress, setProgress] = useState<ProgressState>(INITIAL_PROGRESS);
  // Non-blocking banner shown while we retry the socket after a drop.
  const [reconnecting, setReconnecting] = useState<{
    active: boolean;
    attempt: number;
  }>({ active: false, attempt: 0 });

  // Whether the run ended with a clean terminal event (complete / cancelled).
  // Used to suppress reconnection once the job is truly finished.
  const cleanEndRef = useRef(false);
  const lastParamsRef = useRef<AnalysisParams | null>(null);

  const options = profileOptions(config as Record<string, unknown> | null);
  const activeProfile = profile || options[0]?.value || "";

  const onDrop = useCallback(
    (accepted: File[]) => {
      const paths = accepted
        .map((f) => (f as File & { path?: string }).path || f.name)
        .filter(Boolean);
      setFiles((prev) => Array.from(new Set([...prev, ...paths])));
    },
    []
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop });

  const addFromBrowse = (entry: BrowseEntry) => {
    if (!entry.is_media) return;
    setFiles((prev) => Array.from(new Set([...prev, entry.path])));
  };

  const removeFile = (f: string) =>
    setFiles((prev) => prev.filter((x) => x !== f));

  const patch = (p: Partial<AnalysisSettings>) => setAnalysisSettings(p);

  // Establish (or re-establish) the analysis WebSocket for the current run.
  // Reconnection with exponential backoff is handled in the onClose handler.
  const startConnection = (attempt: number) => {
    const params = lastParamsRef.current;
    if (!params) return;

    setReconnecting({ active: attempt > 0, attempt });

    wsRef.current = connectAnalysisWS(params, {
      onEvent: (type, data) => {
        if (type === "extraction_progress") {
          setProgress((p) => ({
            ...p,
            total: Number(data.total ?? p.total),
            processed: Number(data.processed ?? 0),
            status: "extracting",
          }));
        } else if (type === "asset_analyzed") {
          const name = (data.asset as { original_name?: string } | undefined)
            ?.original_name;
          setProgress((p) => ({
            ...p,
            processed: Number(data.index ?? p.processed),
            total: Number(data.total ?? p.total),
            status: "analyzing",
            log: [...p.log, `✓ analyzed ${name ?? "asset"}`],
          }));
        } else if (type === "asset_error") {
          setProgress((p) => ({
            ...p,
            log: [
              ...p.log,
              `✗ ${String(data.name ?? "asset")}: ${String(data.error ?? "error")}`,
            ],
          }));
        } else if (type === "complete") {
          // Clean terminal event — stop retrying.
          cleanEndRef.current = true;
          setReconnecting({ active: false, attempt: 0 });
          setProgress((p) => ({
            ...p,
            running: false,
            status: "complete",
            log: [...p.log, `✓ complete — ${Number(data.count ?? 0)} assets`],
          }));
          getStagingThenNavigate();
        } else if (type === "cancelled") {
          cleanEndRef.current = true;
          setReconnecting({ active: false, attempt: 0 });
          setProgress((p) => ({
            ...p,
            running: false,
            status: "cancelled",
            log: [...p.log, "⛔ analysis cancelled"],
          }));
          toast.info("Analysis cancelled.");
        } else if (type === "error") {
          setProgress((p) => ({
            ...p,
            running: false,
            status: "error",
            log: [...p.log, `⚠ ${String(data.detail ?? "error")}`],
          }));
          toast.error(String(data.detail ?? "Analysis error"));
        }
      },
      onOpen: () => {
        // On a reconnect, the single-shot backend may have already finished
        // while we were disconnected. Probe staging once to recover a missed
        // terminal event (see WS-resume limitation note in onClose below).
        if (attempt > 0) {
          getStaging()
            .then((res) => {
              if (res.assets.length > 0) {
                cleanEndRef.current = true;
                setReconnecting({ active: false, attempt: 0 });
                setProgress((p) => ({
                  ...p,
                  running: false,
                  status: "complete",
                  log: [
                    ...p.log,
                    `✓ recovered — ${res.assets.length} assets`,
                  ],
                }));
                setStaged(res.assets);
                navigate("/staging");
              }
            })
            .catch(() => {
              /* ignore — reconnect attempts/errors will surface elsewhere */
            });
        }
      },
      onError: () => {
        // The reconnect decision lives in onClose (which always fires after a
        // socket error) so we don't double-handle here. Just log it.
        setProgress((p) => ({
          ...p,
          log: [...p.log, "⚠ WebSocket error"],
        }));
      },
      onClose: () => {
        // Pragmatic WS resume:
        // The backend runs analysis as a single shot and does NOT support
        // server-side resume. A true mid-run resume (continuing exactly where
        // the stream dropped) is therefore impossible. The best we can do is:
        //   1. PRESERVE UI state — `progress` and `staged` live in component
        //      state / the Zustand store and are never cleared on disconnect,
        //      so already-received assets & progress survive the drop.
        //   2. RETRY the socket with exponential backoff (max 3 attempts).
        //   3. If a terminal event was missed while we were gone, recover via
        //      the staging probe in onOpen.
        // If retries are exhausted without a clean terminal event, the backend
        // job was lost and the user must re-run. This is intentional.
        if (cleanEndRef.current) {
          setReconnecting({ active: false, attempt: 0 });
          return;
        }
        if (attempt >= MAX_WS_RETRIES) {
          setReconnecting({ active: false, attempt: 0 });
          setProgress((p) => ({
            ...p,
            running: false,
            status: "error",
            log: [
              ...p.log,
              "✗ connection lost — analysis could not be resumed. Please re-run.",
            ],
          }));
          toast.error("Connection lost. Please re-run the analysis.");
          return;
        }
        const delay = Math.pow(2, attempt) * 1000; // ~1s, 2s, 4s
        setReconnecting({ active: true, attempt: attempt + 1 });
        setProgress((p) => ({
          ...p,
          log: [
            ...p.log,
            `⚠ connection dropped — reconnecting (attempt ${attempt + 1}/${MAX_WS_RETRIES})…`,
          ],
        }));
        window.setTimeout(() => {
          // If the run was cancelled or already completed meanwhile, don't retry.
          if (!cleanEndRef.current) startConnection(attempt + 1);
        }, delay);
      },
    });
  };

  const runAnalysis = () => {
    if (files.length === 0) {
      toast.error("Add at least one file or pick media from the folder browser.");
      return;
    }
    const settings: Record<string, unknown> = { ...analysisSettings };
    lastParamsRef.current = {
      files,
      profile: activeProfile,
      settings,
    };
    cleanEndRef.current = false;
    setReconnecting({ active: false, attempt: 0 });
    setProgress({
      running: true,
      processed: 0,
      total: files.length,
      log: [`Connecting to analysis stream for ${files.length} file(s)...`],
      status: "starting",
    });
    startConnection(0);
  };

  const getStagingThenNavigate = async () => {
    try {
      const res = await getStaging();
      setStaged(res.assets);
      navigate("/staging");
    } catch (err) {
      toast.error(`Failed to load staging: ${String(err)}`);
    }
  };

  const cancel = () => {
    wsRef.current?.cancel();
  };

  // Allow the global Ctrl/Cmd+Enter shortcut (registered in App) to run the
  // exact same pipeline as the Run button.
  useEffect(() => {
    const handler = () => runAnalysis();
    window.addEventListener("amr:run-analysis", handler);
    return () => window.removeEventListener("amr:run-analysis", handler);
  }, [runAnalysis]);

  const pct =
    progress.total > 0
      ? Math.round((progress.processed / progress.total) * 100)
      : 0;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Analysis Wizard</h2>
        <p className="text-sm text-text-dim">
          Add media, choose an AI profile and settings, then run the pipeline.
        </p>
      </div>

      {/* Step 1: sources */}
      <div className="rounded-lg border border-border bg-bg-elev p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium">
          <UploadCloud size={16} className="text-accent" />
          1 · Add media
        </div>
        <div
          {...getRootProps()}
          className={`cursor-pointer rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
            isDragActive
              ? "border-accent bg-accent/10"
              : "border-border bg-bg hover:border-accent/60"
          }`}
        >
          <input {...getInputProps()} />
          <UploadCloud size={28} className="mx-auto mb-2 text-text-dim" />
          <p className="text-sm text-text-dim">
            {isDragActive
              ? "Drop files here…"
              : "Drag & drop files here, or click to browse"}
          </p>
          <p className="mt-1 text-[11px] text-text-dim">
            For server-host files, use the folder picker below.
          </p>
        </div>

        <div className="mt-4">
          <DirectoryPicker onAddFile={addFromBrowse} />
        </div>

        {files.length > 0 && (
          <div className="mt-3">
            <div className="mb-1 text-xs text-text-dim">
              {files.length} file(s) selected
            </div>
            <ul className="max-h-40 space-y-1 overflow-auto rounded-md border border-border bg-bg p-2">
              {files.map((f) => (
                <li
                  key={f}
                  className="flex items-center gap-2 rounded px-2 py-1 text-xs hover:bg-bg-elev-2"
                >
                  <FolderOpen size={13} className="shrink-0 text-text-dim" />
                  <span className="flex-1 truncate">{f}</span>
                  <button
                    className="shrink-0 text-text-dim hover:text-danger"
                    onClick={() => removeFile(f)}
                    aria-label="Remove"
                  >
                    <X size={13} />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Step 2: profile + settings */}
      <div className="rounded-lg border border-border bg-bg-elev p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium">
          <Sparkles size={16} className="text-accent" />
          2 · Profile & settings
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-text-dim">
              AI profile
            </label>
            <select
              className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm"
              value={activeProfile}
              onChange={(e) => setProfile(e.target.value)}
            >
              {options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-text-dim">
              Language
            </label>
            <select
              className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm"
              value={analysisSettings.language}
              onChange={(e) => patch({ language: e.target.value })}
            >
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button
          className="mt-3 flex items-center gap-1.5 text-xs text-accent hover:underline"
          onClick={() => setShowSettings((v) => !v)}
        >
          <Settings2 size={14} />
          {showSettings ? "Hide advanced settings" : "Show advanced settings"}
        </button>

        {showSettings && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="mt-3 grid grid-cols-1 gap-3 overflow-hidden sm:grid-cols-2"
          >
            <div>
              <label className="mb-1 block text-xs font-medium text-text-dim">
                Case style
              </label>
              <select
                className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm"
                value={analysisSettings.case_style}
                onChange={(e) => patch({ case_style: e.target.value })}
              >
                {CASE_STYLES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-dim">
                Max filename chars (0 = no limit)
              </label>
              <input
                type="number"
                min={0}
                className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm"
                value={analysisSettings.max_chars}
                onChange={(e) =>
                  patch({ max_chars: Math.max(0, Number(e.target.value) || 0) })
                }
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={analysisSettings.sort_folders}
                onChange={(e) => patch({ sort_folders: e.target.checked })}
              />
              Sort into category folders
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={analysisSettings.skip_rename}
                onChange={(e) => patch({ skip_rename: e.target.checked })}
              />
              Skip rename (metadata only)
            </label>
            <label className="flex items-center gap-2 text-sm sm:col-span-2">
              <input
                type="checkbox"
                checked={analysisSettings.skip_metadata}
                onChange={(e) => patch({ skip_metadata: e.target.checked })}
              />
              Skip metadata writing
            </label>
          </motion.div>
        )}
      </div>

      {/* Run */}
      <div className="flex items-center gap-3">
        <button
          className="flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-2 disabled:opacity-50"
          onClick={runAnalysis}
          disabled={progress.running}
        >
          <Play size={16} />
          {progress.running ? "Running…" : "Run AI Analysis"}
        </button>
        {progress.running && (
          <button
            className="flex items-center gap-2 rounded-md bg-danger px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
            onClick={cancel}
          >
            <Square size={16} />
            Cancel
          </button>
        )}
      </div>

      {/* Reconnecting banner (non-blocking) */}
      {reconnecting.active && (
        <div className="flex items-center gap-2 rounded-lg border border-warn/40 bg-warn/10 px-4 py-2.5 text-sm text-warn">
          <Spinner size={15} />
          Reconnecting… (attempt {reconnecting.attempt}/{MAX_WS_RETRIES})
        </div>
      )}

      {/* Progress */}
      {(progress.running || progress.log.length > 0) && (
        <div className="rounded-lg border border-border bg-bg-elev p-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="font-medium">
              Progress — {progress.processed}/{progress.total}
            </span>
            <span className="flex items-center gap-2 rounded-full bg-bg px-2 py-0.5 text-xs text-text-dim">
              {progress.running && progress.processed === 0 && (
                <Spinner size={12} />
              )}
              {progress.status}
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-bg-elev-2">
            <motion.div
              className="h-full bg-accent"
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.2 }}
            />
          </div>
          <div className="mt-3 h-44 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-bg p-2 font-mono text-xs leading-relaxed text-text-dim">
            {progress.log.join("\n")}
          </div>
        </div>
      )}
    </div>
  );
}
