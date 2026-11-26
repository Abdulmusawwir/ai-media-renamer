import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { X } from "lucide-react";
import {
  Film,
  Layers,
  Upload,
  History,
  Settings as SettingsIcon,
  Boxes,
  Cpu,
} from "lucide-react";
import { useEnvironment, useConfig, useSaveSession } from "./hooks/api";
import { useStore, useToast } from "./store";
import ErrorBoundary from "./components/ErrorBoundary";
import DesktopBridge from "./components/DesktopBridge";
import { getHealth } from "./api/client";
import { isDesktop } from "./desktop";

const NAV_ITEMS = [
  { to: "/analysis", label: "Analysis", icon: Upload },
  { to: "/staging", label: "Staging", icon: Layers },
  { to: "/commit", label: "Commit & Export", icon: Film },
  { to: "/sessions", label: "Sessions", icon: History },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
  { to: "/models", label: "Models", icon: Boxes },
];

export default function App() {
  const setEnvironment = useStore((s) => s.setEnvironment);
  const setConfig = useStore((s) => s.setConfig);
  const environment = useStore((s) => s.environment);
  const config = useStore((s) => s.config);

  const envQuery = useEnvironment();
  const configQuery = useConfig();
  const saveSessionMutation = useSaveSession();
  const toast = useToast();

  const [healthVersion, setHealthVersion] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((h) => {
        if (!cancelled && h?.version) setHealthVersion(String(h.version));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (envQuery.data) setEnvironment(envQuery.data);
  }, [envQuery.data, setEnvironment]);

  useEffect(() => {
    if (configQuery.data) setConfig(configQuery.data);
  }, [configQuery.data, setConfig]);

  const envOk = environment
    ? environment.ffmpeg && environment.exiftool
    : false;

  // The AI server starts behind the scenes, so the first answer can say it is
  // not ready yet. Ask again briefly instead of showing a stale warning.
  const readinessChecks = useRef(0);
  useEffect(() => {
    if (!isDesktop || environment?.llamacpp_running || readinessChecks.current >= 10) {
      return;
    }
    const refetch = envQuery.refetch;
    const timer = window.setInterval(() => {
      readinessChecks.current += 1;
      void refetch();
      if (readinessChecks.current >= 10) window.clearInterval(timer);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [isDesktop, environment?.llamacpp_running, envQuery.refetch]);

  // Keep "backend reachable" separate from "AI ready": /health only proves
  // FastAPI is alive, while /api/environment also knows about llama.cpp.
  const engineStatus = !environment
    ? { ok: false, label: "Backend not reachable", title: "No response from /api/environment" }
    : !envOk
    ? { ok: false, label: "Missing ffmpeg/exiftool", title: "Required media tools are missing" }
    : !environment.llamacpp_running
    ? { ok: false, label: "AI server not ready", title: "llama-server is not answering on the configured port" }
    : !environment.model_available
    ? { ok: false, label: "No AI model", title: "No vision GGUF is configured or available" }
    : { ok: true, label: "Engine + AI ready", title: "Tools, llama.cpp and the model are all available" };

  // Responsive floor: 1024px is the supported minimum width. Below that, show
  // a dismissible banner (the app is not laid out for narrow viewports).
  const [showNarrow, setShowNarrow] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const update = () => setShowNarrow(!mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  const location = useLocation();

  // Global keyboard shortcuts. Modals/dialogs close on Escape; Delete removes
  // staged rows; Ctrl/Cmd+Enter runs analysis; Ctrl/Cmd+S saves; Ctrl/Cmd+Z undo.
  useEffect(() => {
    const isEditable = (el: EventTarget | null) => {
      const node = el as HTMLElement | null;
      if (!node) return false;
      const tag = node.tagName;
      return (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        node.isContentEditable
      );
    };

    const onKey = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      const path = location.pathname;
      const editable = isEditable(e.target);

      if (e.key === "Escape") {
        if (editable) {
          (e.target as HTMLElement).blur();
          return;
        }
        window.dispatchEvent(new CustomEvent("amr:escape"));
        return;
      }

      if (e.key === "Delete") {
        if (editable) return;
        if (path.startsWith("/staging")) {
          e.preventDefault();
          window.dispatchEvent(new CustomEvent("amr:delete-selected"));
          toast.info("Deleted selected rows.");
        }
        return;
      }

      if (meta) {
        if (e.key === "Enter") {
          if (path === "/analysis") {
            e.preventDefault();
            window.dispatchEvent(new CustomEvent("amr:run-analysis"));
            toast.info("Running analysis…");
          }
          return;
        }
        if (e.key.toLowerCase() === "s") {
          e.preventDefault();
          saveSessionMutation
            .mutateAsync({})
            .then(() => toast.success("Session saved."))
            .catch((err) => toast.error(String(err)));
          return;
        }
        if (e.key.toLowerCase() === "z") {
          e.preventDefault();
          toast.info("Undo not available.");
          return;
        }
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [location.pathname, saveSessionMutation, toast]);

  return (
    <>
      <DesktopBridge />
      <div className="flex min-h-screen bg-bg text-text">
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-bg-elev p-3">
        <div className="mb-4 flex items-center gap-2 px-2 py-1">
          <span className="rounded-md bg-accent px-2 py-1 text-xs font-bold text-white">
            AMR
          </span>
          <span className="text-[13px] font-semibold">AI Media Renamer</span>
        </div>
        <nav className="flex flex-col gap-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-accent text-white"
                      : "text-text-dim hover:bg-bg-elev-2 hover:text-text"
                  }`
                }
              >
                <Icon size={16} />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
        <div className="mt-auto flex items-center gap-2 px-2 pt-3 text-[11px] text-text-dim">
          <span
            className={`h-2 w-2 rounded-full ${engineStatus.ok ? "bg-ok" : "bg-warn"}`}
            title={engineStatus.title}
          />
          {engineStatus.label}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {showNarrow && (
          <div className="flex items-center gap-2 border-b border-warn/40 bg-warn/10 px-5 py-2 text-sm text-warn">
            <span className="flex-1">
              Best viewed at 1024px or wider.
            </span>
            <button
              className="ui-btn-icon shrink-0 rounded p-1 hover:bg-warn/20"
              onClick={() => setShowNarrow(false)}
              aria-label="Dismiss"
            >
              <X size={14} />
            </button>
          </div>
        )}
        <header className="flex h-14 items-center justify-between border-b border-border bg-bg-elev px-5">
          <h1 className="text-[15px] font-semibold">AI Media Renamer</h1>
          {Boolean(healthVersion || (config && config.version)) && (
            <div className="flex items-center gap-2 text-xs text-text-dim">
              <Cpu size={14} />
              v{healthVersion ?? String(config?.version)}
            </div>
          )}
        </header>
        <main className="flex-1 overflow-auto p-5">
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className="mx-auto max-w-5xl"
          >
            {/* Per-page boundary: a crash on one route shows a fallback without
                tearing down the app shell (sidebar / header stay alive). The
                key resets the boundary when navigating between pages. */}
            <ErrorBoundary key={location.pathname} label="this page">
              <Outlet />
            </ErrorBoundary>
          </motion.div>
        </main>
      </div>
    </div>
    </>
  );
}
