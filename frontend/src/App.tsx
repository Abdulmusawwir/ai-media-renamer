import { NavLink, Outlet } from "react-router-dom";
import { useEffect } from "react";
import { getEnvironment, getConfig } from "./api/client";
import { useStore } from "./store";

const NAV_ITEMS = [
  { to: "/analysis", label: "Analysis" },
  { to: "/staging", label: "Staging" },
  { to: "/commit", label: "Commit & Export" },
  { to: "/sessions", label: "Sessions" },
  { to: "/settings", label: "Settings" },
  { to: "/models", label: "Models" },
];

export default function App() {
  const { environment, setEnvironment, config, setConfig } = useStore();

  useEffect(() => {
    getEnvironment()
      .then(setEnvironment)
      .catch(() => undefined);
    getConfig()
      .then(setConfig)
      .catch(() => undefined);
  }, [setEnvironment, setConfig]);

  const envOk = environment
    ? environment.ffmpeg && environment.exiftool
    : false;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">AMR</span>
          <span className="brand-title">AI Media Renamer</span>
        </div>
        <nav className="nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                isActive ? "nav-link active" : "nav-link"
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span
            className={envOk ? "env-dot ok" : "env-dot warn"}
            title="ffmpeg / exiftool availability"
          />
          {environment
            ? envOk
              ? "Engine tools ready"
              : "Missing ffmpeg/exiftool"
            : "Backend not reachable"}
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <h1>AI Media Renamer</h1>
          <div className="topbar-status">
            {config && config.version
              ? `v${String(config.version)}`
              : "v2.0.0"}
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
