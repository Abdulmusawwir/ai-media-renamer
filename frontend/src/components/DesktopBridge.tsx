import { useEffect } from "react";
import { desktop, isDesktop } from "../desktop";
import { useStore } from "../store";

export default function DesktopBridge() {
  const pushIncomingPaths = useStore((s) => s.pushIncomingPaths);
  const clearIncomingPaths = useStore((s) => s.clearIncomingPaths);
  const setPendingUpdateCheck = useStore((s) => s.setPendingUpdateCheck);

  useEffect(() => {
    if (!isDesktop) return;
    const cleanups: Array<() => void> = [];
    let cancelled = false;

    (async () => {
      try {
        const unlistenDrop = await desktop.installDesktopDropHandler((paths) => {
          pushIncomingPaths(paths);
        });
        if (cancelled) {
          unlistenDrop();
          return;
        }
        cleanups.push(unlistenDrop);

        const pending = await desktop.invoke<string[]>("pending_paths").catch(() => [] as string[]);
        if (!cancelled && Array.isArray(pending) && pending.length) {
          pushIncomingPaths(pending);
        }

        const unlistenOpen = await desktop.listen<string[]>("desktop://open-paths", (paths) => {
          if (Array.isArray(paths)) pushIncomingPaths(paths);
        });
        if (cancelled) {
          unlistenOpen();
          return;
        }
        cleanups.push(unlistenOpen);

        const unlistenCheck = await desktop.listen("desktop://check-updates", () => {
          setPendingUpdateCheck(true);
        });
        if (cancelled) {
          unlistenCheck();
          return;
        }
        cleanups.push(unlistenCheck);

        await desktop.invoke("desktop_ready").catch(() => undefined);
      } catch {
        /* ignore */
      }
    })();

    return () => {
      cancelled = true;
      cleanups.forEach((fn) => {
        try {
          fn();
        } catch {
          /* ignore */
        }
      });
      clearIncomingPaths();
    };
  }, [pushIncomingPaths, clearIncomingPaths, setPendingUpdateCheck]);

  return null;
}
