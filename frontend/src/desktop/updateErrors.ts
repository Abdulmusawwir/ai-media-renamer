/** Normalise updater failures into a short, user-facing message. */
export function formatUpdateError(err: unknown): string {
  if (err instanceof Error) {
    return err.message || err.name || "Update failed";
  }
  if (typeof err === "string" && err) {
    return err;
  }
  if (err && typeof err === "object" && "message" in err) {
    const message = (err as { message?: unknown }).message;
    if (typeof message === "string" && message) {
      return message;
    }
  }
  return "Update failed";
}
