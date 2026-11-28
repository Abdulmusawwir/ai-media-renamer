/** Human label for a timestamp in milliseconds; empty when unknown. */
export function relativeTime(at: number): string {
  if (!at) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - at) / 1000));
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

/** Same label from an ISO date string (session files report one). */
export function relativeFromIso(value?: string): string {
  if (!value) return "";
  const parsed = Date.parse(value);
  if (!Number.isNaN(parsed)) return relativeTime(parsed);
  // Session files use `created: YYYY-MM-DD_HHMMSS`.
  const match = /^(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})(\d{2})$/.exec(value);
  if (match) {
    const ms = new Date(
      Number(match[1]),
      Number(match[2]) - 1,
      Number(match[3]),
      Number(match[4]),
      Number(match[5]),
      Number(match[6])
    ).getTime();
    if (!Number.isNaN(ms)) return relativeTime(ms);
  }
  return "";
}
