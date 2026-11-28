import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  ChevronRight,
  File,
  FileAudio,
  FileImage,
  FileText,
  FileVideo,
  Folder,
  FolderOpen,
  Plus,
  Clock,
} from "lucide-react";
import { authHeaders, browseFolder, type BrowseEntry, type BrowseResponse } from "../api/client";
import { useToast } from "../store";
import { Tooltip } from "./Tooltip";

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
  const [filter, setFilter] = useState("");
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
        setFilter("");
        // Record user-initiated navigations (skip the initial empty load).
        if (target) pushRecent(res.path);
      } catch (err) {
        const msg = String(err);
        // Probe a different endpoint to tell whether the *whole* backend is
        // unreachable (VPN/proxy/antivirus intercepting localhost) vs. a
        // browse-specific issue. Surfaces as part of the toast.
        let diag = "";
        try {
          const probe = await fetch("/api/environment", {
            method: "GET",
            headers: authHeaders(),
          });
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

  const needle = filter.trim().toLowerCase();
  const visibleFolders = needle
    ? (browse?.folders ?? []).filter((f) => f.name.toLowerCase().includes(needle))
    : (browse?.folders ?? []);
  const visibleFiles = needle
    ? (browse?.files ?? []).filter((f) => f.name.toLowerCase().includes(needle))
    : (browse?.files ?? []);

  const breadcrumbs = (() => {
    const raw = (browse?.path ?? "").replace(/\//g, "\\");
    if (!raw) return [] as { label: string; path: string }[];
    const parts: { label: string; path: string }[] = [];
    if (raw.startsWith("\\\\")) {
      const segments = raw.split("\\").filter(Boolean);
      let current = "\\\\";
      for (const segment of segments) {
        current = `${current}\\${segment}`;
        parts.push({ label: segment, path: current });
      }
      return parts;
    }
    const drive = raw.match(/^[A-Za-z]:\\?/)?.[0] ?? "";
    const rest = drive ? raw.slice(drive.length).split("\\").filter(Boolean) : raw.split("\\").filter(Boolean);
    if (drive) parts.push({ label: drive.replace(/\\$/, ""), path: drive });
    let current = drive;
    for (const segment of rest) {
      current = current ? `${current.replace(/\\$/, "")}\\${segment}` : segment;
      parts.push({ label: segment, path: current });
    }
    return parts;
  })();

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
            <Tooltip key={dir} label={dir} side="bottom">
              <button
                type="button"
                onClick={() => doBrowse(dir)}
                className="max-w-[200px] truncate rounded-full border border-border bg-bg px-2.5 py-1 text-xs text-text-dim hover:border-accent hover:text-text"
              >
                {dir.split(/[\\/]/).filter(Boolean).slice(-1)[0] || dir}
              </button>
            </Tooltip>
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
        <span className="flex flex-wrap items-center gap-0.5 break-all">
          {breadcrumbs.length ? (
            breadcrumbs.map((part, index) => (
              <span key={part.path} className="flex items-center gap-0.5">
                {index > 0 && <span className="text-text-dim/50">/</span>}
                <button
                  type="button"
                  className="rounded px-1 py-0.5 text-accent hover:bg-bg-elev-2"
                  onClick={() => doBrowse(part.path)}
                  title={part.path}
                >
                  {part.label}
                </button>
              </span>
            ))
          ) : (
            "—"
          )}
        </span>
      </div>
      {browse?.drives && browse.drives.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-1">
          <span className="mr-1 text-[11px] uppercase tracking-wide text-text-dim">
            Drives
          </span>
          {browse.drives.map((drive) => (
            <Tooltip key={drive} label={`Browse ${drive}`} side="bottom">
              <button
                type="button"
                onClick={() => doBrowse(drive)}
                className={`rounded-full border px-2.5 py-1 text-xs hover:border-accent hover:text-accent ${
                  browse.path.toLowerCase().startsWith(drive.toLowerCase())
                    ? "border-accent text-accent"
                    : "border-border bg-bg text-text-dim"
                }`}
              >
                {drive}
              </button>
            </Tooltip>
          ))}
        </div>
      )}

      <div className="mb-3 flex gap-2">
        <input
          type="text"
          className="flex-1 rounded-md border border-border bg-bg px-2 py-1.5 text-xs"
          placeholder="Filter this folder by name"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      <div className="mb-3 flex gap-2">
        <input
          type="text"
          className="flex-1 rounded-md border border-border bg-bg px-2 py-1.5 text-xs"
          placeholder="Paste a folder path and press Enter"
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              const val = (e.target as HTMLInputElement).value.trim();
              if (val) doBrowse(val);
            }
          }}
        />
      </div>

      <div className="max-h-72 overflow-auto rounded-md border border-border bg-bg p-1">
        {busy && <div className="p-3 text-xs text-text-dim">Loading…</div>}
        {!busy && browse && (
          <ul>
            {visibleFolders.map((f) => (
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
            {visibleFiles.map((f) => (
              <li key={f.path}>
                <div
                  className={`flex items-center gap-2 rounded px-2 py-1.5 text-sm ${
                    f.is_media
                      ? "cursor-pointer hover:bg-bg-elev-2"
                      : "opacity-50"
                  }`}
                  onClick={() => f.is_media && onAddFile(f)}
                >
                  {(() => {
                    const Icon =
                      f.kind === "video"
                        ? FileVideo
                        : f.kind === "image"
                        ? FileImage
                        : f.kind === "audio"
                        ? FileAudio
                        : f.kind === "document"
                        ? FileText
                        : File;
                    return <Icon size={15} className="shrink-0 text-text-dim" />;
                  })()}
                  <span className="flex-1 truncate">{f.name}</span>
                  <span className="text-[10px] uppercase text-text-dim">
                    {f.kind}
                  </span>
                  {f.is_media && (
                    <Tooltip label="Add to analysis">
                      <span className="flex items-center gap-1 rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent">
                        <Plus size={11} /> add
                      </span>
                    </Tooltip>
                  )}
                </div>
              </li>
            ))}
            {visibleFolders.length === 0 && visibleFiles.length === 0 && (
              <li>
                <div className="ui-empty">
                  {needle ? "No matching files here." : "Empty folder."}
                </div>
              </li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
