import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ChevronRight, File, Folder, FolderOpen, Plus, Clock } from "lucide-react";
import { browseFolder, type BrowseEntry, type BrowseResponse } from "../api/client";
import { useToast } from "../store";

const RECENTS_KEY = "amr:recent-dirs";
const MAX_RECENTS = 8;

function loadRecents(): string[] {
  try {
    const raw = localStorage.getItem(RECENTS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((d) => typeof d === "string") : [];
  } catch {
    return [];
  }
}

interface DirectoryPickerProps {
  onAddFile: (entry: BrowseEntry) => void;
}

export default function DirectoryPicker({ onAddFile }: DirectoryPickerProps) {
  const [browse, setBrowse] = useState<BrowseResponse | null>(null);
  const [path, setPath] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [recents, setRecents] = useState<string[]>(() => loadRecents());
  const toast = useToast();

  const pushRecent = useCallback((dir: string) => {
    if (!dir) return;
    setRecents((prev) => {
      const next = [dir, ...prev.filter((d) => d !== dir)].slice(0, MAX_RECENTS);
      try {
        localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
      } catch {
        /* ignore persistence failures */
      }
      return next;
    });
  }, []);

  const doBrowse = useCallback(
    async (target?: string) => {
      setBusy(true);
      try {
        const res = await browseFolder(target);
        setBrowse(res);
        setPath(res.path);
        // Record user-initiated navigations (skip the initial empty load).
        if (target) pushRecent(res.path);
      } catch (err) {
        const msg = String(err);
        // Probe a different endpoint to tell whether the *whole* backend is
        // unreachable (VPN/proxy/antivirus intercepting localhost) vs. a
        // browse-specific issue. Surfaces as part of the toast.
        let diag = "";
        try {
          const probe = await fetch("/api/environment", { method: "GET" });
          diag = probe.ok
            ? " (but /api/environment IS reachable)"
            : ` (and /api/environment -> ${probe.status})`;
        } catch {
          diag = " (and /api/environment is ALSO unreachable)";
        }
        const origin = window.location.origin;
        const network = /network|Failed to fetch|ERR_/i.test(msg);
        if (network) {
          toast.error(
            `Can't reach backend at ${origin}${diag}. If you use a VPN, proxy, ` +
              `or antivirus with web shielding, it is likely intercepting localhost — ` +
              `add 127.0.0.1 to its bypass list. [${msg}]`
          );
        } else {
          toast.error(`Browse failed: ${msg}${diag}`);
        }
      } finally {
        setBusy(false);
      }
    },
    [toast, pushRecent]
  );

  // Run the initial listing exactly once on mount. Guarding with a ref (rather
  // than depending on `doBrowse`) prevents an infinite re-render loop: the toast
  // store updates on every toast, which can change `doBrowse`'s identity and
  // otherwise re-trigger the effect forever, spamming the UI.
  const didInit = useRef(false);
  useEffect(() => {
    if (didInit.current) return;
    didInit.current = true;
    doBrowse("");
  }, [didInit]);

  return (
    <div className="rounded-lg border border-border bg-bg-elev p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-text-dim">
        <FolderOpen size={16} />
        Folder picker (backend host)
      </div>

      {recents.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          <span className="flex items-center gap-1 text-[11px] uppercase tracking-wide text-text-dim">
            <Clock size={12} /> Recent
          </span>
          {recents.map((dir) => (
            <button
              key={dir}
              type="button"
              title={dir}
              onClick={() => doBrowse(dir)}
              className="max-w-[200px] truncate rounded-full border border-border bg-bg px-2.5 py-1 text-xs text-text-dim hover:border-accent hover:text-text"
            >
              {dir.split(/[\\/]/).filter(Boolean).slice(-1)[0] || dir}
            </button>
          ))}
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-1 rounded-md border border-border bg-bg px-2 py-1.5 text-xs text-text-dim">
        <button
          className="rounded px-1.5 py-0.5 text-accent hover:bg-bg-elev-2"
          onClick={() => doBrowse(browse?.parent ?? "")}
          disabled={!browse?.parent}
        >
          .. (up)
        </button>
        <span className="break-all">{browse?.path ?? "—"}</span>
      </div>

      <div className="max-h-72 overflow-auto rounded-md border border-border bg-bg p-1">
        {busy && <div className="p-3 text-xs text-text-dim">Loading…</div>}
        {!busy && browse && (
          <ul>
            {browse.folders.map((f) => (
              <li key={f.path}>
                <button
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-accent hover:bg-bg-elev-2"
                  onClick={() => doBrowse(f.path)}
                >
                  <Folder size={15} />
                  <span className="flex-1 truncate">{f.name}</span>
                  <ChevronRight size={14} className="opacity-60" />
                </button>
              </li>
            ))}
            {browse.files.map((f) => (
              <li key={f.path}>
                <div
                  className={`flex items-center gap-2 rounded px-2 py-1.5 text-sm ${
                    f.is_media
                      ? "cursor-pointer hover:bg-bg-elev-2"
                      : "opacity-50"
                  }`}
                  onClick={() => f.is_media && onAddFile(f)}
                >
                  <File size={15} />
                  <span className="flex-1 truncate">{f.name}</span>
                  <span className="text-[10px] uppercase text-text-dim">
                    {f.kind}
                  </span>
                  {f.is_media && (
                    <span
                      className="flex items-center gap-1 rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent"
                      title="Add to analysis"
                    >
                      <Plus size={11} /> add
                    </span>
                  )}
                </div>
              </li>
            ))}
            {browse.folders.length === 0 && browse.files.length === 0 && (
              <li className="p-3 text-xs text-text-dim">Empty folder.</li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
