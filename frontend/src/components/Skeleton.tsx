import { Loader2 } from "lucide-react";

/** A small spinning loader built on lucide's Loader2. */
export function Spinner({
  size = 16,
  className = "",
  label,
}: {
  size?: number;
  className?: string;
  label?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-2 text-text-dim ${className}`}>
      <Loader2 size={size} className="animate-spin" />
      {label && <span className="text-sm">{label}</span>}
    </span>
  );
}

/**
 * A shimmering placeholder block used to represent loading content.
 * Pass `className` to control dimensions (e.g. "h-4 w-full").
 */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-md bg-bg-elev-2 ${className}`}
      aria-hidden="true"
    />
  );
}

/** A row of skeleton blocks, handy for table/list loading states. */
export function SkeletonRows({
  rows = 5,
  className = "",
}: {
  rows?: number;
  className?: string;
}) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}
