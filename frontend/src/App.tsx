import { NavLink, Outlet } from "react-router-dom";
import { useEffect } from "react";
import { motion } from "framer-motion";
import {
  Film,
  Layers,
  Upload,
  History,
  Settings as SettingsIcon,
  Boxes,
  Cpu,
} from "lucide-react";
import { useEnvironment, useConfig } from "./hooks/api";
import { useStore } from "./store";

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

  useEffect(() => {
    if (envQuery.data) setEnvironment(envQuery.data);
  }, [envQuery.data, setEnvironment]);

  useEffect(() => {
    if (configQuery.data) setConfig(configQuery.data);
  }, [configQuery.data, setConfig]);

  const envOk = environment
    ? environment.ffmpeg && environment.exiftool
    : false;

  return (
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
            className={`h-2 w-2 rounded-full ${
              environment ? (envOk ? "bg-ok" : "bg-warn") : "bg-warn"
            }`}
            title="ffmpeg / exiftool availability"
          />
          {environment
            ? envOk
              ? "Engine tools ready"
              : "Missing ffmpeg/exiftool"
            : "Backend not reachable"}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-border bg-bg-elev px-5">
          <h1 className="text-[15px] font-semibold">AI Media Renamer</h1>
          <div className="flex items-center gap-2 text-xs text-text-dim">
            <Cpu size={14} />
            {config && config.version
              ? `v${String(config.version)}`
              : "v2.0.0"}
          </div>
        </header>
        <main className="flex-1 overflow-auto p-5">
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className="mx-auto max-w-5xl"
          >
            <Outlet />
          </motion.div>
        </main>
      </div>
    </div>
  );
}
