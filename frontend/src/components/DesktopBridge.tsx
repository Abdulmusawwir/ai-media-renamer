import { useEffect } from "react";
import { desktop, isDesktop } from "../desktop";
import { useStore } from "../store";

export default function DesktopBridge() {
  const pushIncomingPaths = useStore((s) => s.pushIncomingPaths);
  const clearIncomingPaths = useStore((s) => s.clearIncomingPaths);
  const setPendingUpdateCheck = useStore((s) => s.setPendingUpdateCheck);

  useEffect(() => {
    if (!isDesktop) return;
    let cancelled = false;
    let unlistenDrop: (() => void) | undefined;
    let unlistenOpen: (() => void) | undefined;
    let unlistenCheck: (() => void) | undefined;

    (async () => {
      unlistenDrop = await desktop.installDesktopDropHandler((paths) => {
        pushIncomingPaths(paths);
      });

      // Drain any paths queued by a second instance at startup.
      try {
        const pending = await desktop.invoke<string[]>("pending_paths");
        if (!cancelled && Array.isArray(pending) && pending.length) {
          pushIncomingPaths(pending);
        }
      } catch {
        /* ignore */
      }

      unlistenOpen = await desktop.listen<string[]>("desktop://open-paths", (paths) => {
        if (Array.isArray(paths)) pushIncomingPaths(paths);
      });

      unlistenCheck = await desktop.listen("desktop://check-updates", () => {
        setPendingUpdateCheck(true);
      });

      // Notify the shell that the SPA has mounted.
      try {
        await desktop.invoke("desktop_ready");
      } catch {
        /* ignore */
      }
    })();

    return () => {
      cancelled = true;
      unlistenDrop?.();
      unlistenOpen?.();
      unlistenCheck?.();
      clearIncomingPaths();
    };
  }, [pushIncomingPaths, clearIncomingPaths]);

  return null;
}
