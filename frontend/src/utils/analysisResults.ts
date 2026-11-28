export type FileStatus = "queued" | "done" | "failed";

export interface LiveResult {
  originalName: string;
  stagedName: string;
  category: string;
  tags: string[];
  summary: string;
}

export interface AnalyzedAsset {
  original_path?: string;
  original_name?: string;
  staged_name?: string;
  category?: string;
  tags?: string[];
  summary?: string;
}

/** Last path segment, used to match error events (which carry a basename). */
export function basename(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

export function initialFileStatus(files: string[]): Record<string, FileStatus> {
  return Object.fromEntries(files.map((file) => [file, "queued" as const]));
}

/**
 * Keyed by original path so a duplicate or repeated event updates the same
 * card instead of adding another one. Returns the input when the event has no
 * usable path.
 */
export function mergeLiveResult(
  prev: Record<string, LiveResult>,
  asset: AnalyzedAsset | undefined
): Record<string, LiveResult> {
  const path = asset?.original_path;
  if (!asset || !path) return prev;
  return {
    ...prev,
    [path]: {
      originalName: asset.original_name ?? path,
      stagedName: asset.staged_name ?? "",
      category: asset.category ?? "uncategorized",
      tags: Array.isArray(asset.tags) ? asset.tags : [],
      summary: asset.summary ?? "",
    },
  };
}

export function markFileStatus(
  prev: Record<string, FileStatus>,
  name: string,
  status: FileStatus
): Record<string, FileStatus> {
  return { ...prev, [name]: status };
}

export function forgetFileStatus(
  prev: Record<string, FileStatus>,
  name: string
): Record<string, FileStatus> {
  if (!(name in prev)) return prev;
  const next = { ...prev };
  delete next[name];
  return next;
}

/** A session's identifier is its name, or the filename from its stored path. */
export function sessionKey(session: { name?: string; path?: string }): string {
  const name = session.name ? String(session.name) : "";
  if (name) return name;
  const path = session.path ? String(session.path) : "";
  return path ? basename(path) : "";
}
