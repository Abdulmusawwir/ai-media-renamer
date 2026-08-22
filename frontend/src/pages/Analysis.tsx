import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  browseFolder,
  connectAnalysisWS,
  getStaging,
  type AnalysisWSController,
  type BrowseEntry,
  type BrowseResponse,
} from "../api/client";
import { useStore } from "../store";

const FALLBACK_PROFILES = ["general_broll", "cinematography", "motion_overlays"];

function profileOptions(
  config: Record<string, unknown> | null
): { value: string; label: string }[] {
  const profiles = (config?.prompt_profiles ?? {}) as Record<
    string,
    { label?: string }
  >;
  const keys = Object.keys(profiles);
  if (keys.length === 0) {
    return FALLBACK_PROFILES.map((p) => ({ value: p, label: p }));
  }
  return keys.map((k) => ({ value: k, label: profiles[k]?.label ?? k }));
}

export default function Analysis() {
  const navigate = useNavigate();
  const { config, setStaged, setProgress, progress } = useStore();
  const wsRef = useRef<AnalysisWSController | null>(null);

  const [files, setFiles] = useState<string[]>([]);
  const [profile, setProfile] = useState<string>("");
  const [browsePath, setBrowsePath] = useState<string>("");
  const [browse, setBrowse] = useState<BrowseResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const options = profileOptions(config as Record<string, unknown> | null);
  const activeProfile = profile || options[0]?.value || "";

  // (a) file input -> absolute paths are prefilled by the browser via the
  // `webkitRelativePath` / `name` only; we keep the names for display and rely
  // on the broker's ability to resolve them. On a real backend the user selects
  // files that already exist on the server host.
  const onPickFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const list = Array.from(e.target.files ?? [])
      .map((f) => (f as File & { path?: string }).path || f.name)
      .filter(Boolean);
    setFiles((prev) => Array.from(new Set([...prev, ...list])));
  };

  const doBrowse = useCallback(
    async (path?: string) => {
      try {
        const res = await browseFolder(path);
        setBrowse(res);
        setBrowsePath(res.path);
      } catch (err) {
        setError(String(err));
      }
    },
    []
  );

  const addFromBrowse = (entry: BrowseEntry) => {
    if (!entry.is_media) return;
    setFiles((prev) => Array.from(new Set([...prev, entry.path])));
  };

  const removeFile = (f: string) =>
    setFiles((prev) => prev.filter((x) => x !== f));

  const runAnalysis = () => {
    setError(null);
    if (files.length === 0) {
      setError("Add at least one file or pick media from the folder browser.");
      return;
    }
    setProgress({
      running: true,
      processed: 0,
      total: files.length,
      log: [`Connecting to analysis stream for ${files.length} file(s)...`],
      status: "starting",
    });

    wsRef.current = connectAnalysisWS(
      { files, profile: activeProfile, settings: {} },
      {
        onEvent: (type, data) => {
          if (type === "extraction_progress") {
            setProgress((p) => ({
              ...p,
              total: Number(data.total ?? p.total),
              processed: Number(data.processed ?? 0),
              status: "extracting",
            }));
          } else if (type === "asset_analyzed") {
            const name = (data.asset as { original_name?: string })?.original_name;
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
            setProgress((p) => ({
              ...p,
              running: false,
              status: "complete",
              log: [...p.log, `✓ complete — ${Number(data.count ?? 0)} assets`],
            }));
            getStagingThenNavigate();
          } else if (type === "cancelled") {
            setProgress((p) => ({
              ...p,
              running: false,
              status: "cancelled",
              log: [...p.log, "⛔ analysis cancelled"],
            }));
          } else if (type === "error") {
            setProgress((p) => ({
              ...p,
              running: false,
              status: "error",
              log: [...p.log, `⚠ ${String(data.detail ?? "error")}`],
            }));
          }
        },
        onError: () => {
          setProgress((p) => ({ ...p, running: false, status: "error" }));
          setError("WebSocket error — is the backend running on :8000?");
        },
      }
    );
  };

  const getStagingThenNavigate = async () => {
    try {
      const res = await getStaging();
      setStaged(res.assets);
      navigate("/staging");
    } catch (err) {
      setError(String(err));
    }
  };

  const cancel = () => {
    wsRef.current?.cancel();
  };

  const pct =
    progress.total > 0
      ? Math.round((progress.processed / progress.total) * 100)
      : 0;

  return (
    <div className="page">
      <h2>Analysis</h2>
      <p className="page-sub">
        Choose media to analyze, pick a prompt profile, then run the AI pipeline.
      </p>

      <div className="card">
        <label>Files (absolute paths on the backend host)</label>
        <input type="file" multiple onChange={onPickFiles} />
        {files.length > 0 && (
          <ul className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            {files.map((f) => (
              <li key={f} style={{ display: "flex", gap: 8 }}>
                <span style={{ flex: 1 }}>{f}</span>
                <button
                  className="secondary"
                  style={{ padding: "2px 8px" }}
                  onClick={() => removeFile(f)}
                >
                  remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <label>Browse a folder on the backend</label>
        <div className="row">
          <input
            type="text"
            placeholder="Path (leave empty for backend cwd)"
            value={browsePath}
            onChange={(e) => setBrowsePath(e.target.value)}
          />
          <button className="secondary" onClick={() => doBrowse(browsePath)}>
            Browse
          </button>
        </div>
        {browse && (
          <>
            <div className="breadcrumb">
              <button onClick={() => doBrowse(browse.parent ?? "")}>..</button>
              <span>{browse.path}</span>
            </div>
            <div className="tree">
              {browse.folders.map((f) => (
                <div
                  key={f.path}
                  className="tree-item folder"
                  onClick={() => doBrowse(f.path)}
                >
                  📁 {f.name}
                </div>
              ))}
              {browse.files.map((f) => (
                <div
                  key={f.path}
                  className="tree-item"
                  style={{
                    color: f.is_media ? "var(--text)" : "var(--text-dim)",
                    cursor: f.is_media ? "pointer" : "default",
                  }}
                  onClick={() => addFromBrowse(f)}
                >
                  {f.is_media ? "🎬" : "📄"} {f.name}
                  {f.is_media && (
                    <span className="muted" style={{ marginLeft: "auto" }}>
                      add
                    </span>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="card">
        <div className="grid-2">
          <div>
            <label>Prompt profile</label>
            <select
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
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={runAnalysis} disabled={progress.running}>
            {progress.running ? "Running…" : "Run AI Analysis"}
          </button>
          {progress.running && (
            <button className="danger" onClick={cancel}>
              Cancel
            </button>
          )}
        </div>
        {error && <p className="badge failed">{error}</p>}
      </div>

      {(progress.running || progress.log.length > 0) && (
        <div className="card">
          <label>
            Progress — {progress.processed}/{progress.total} ({progress.status})
          </label>
          <div className="progress">
            <div className="progress-bar" style={{ width: `${pct}%` }} />
          </div>
          <div className="log">{progress.log.join("\n")}</div>
        </div>
      )}
    </div>
  );
}
