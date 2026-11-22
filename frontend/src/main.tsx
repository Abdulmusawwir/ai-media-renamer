import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import "./styles.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { queryClient } from "./lib/query";
import Toaster from "./components/Toaster";
import ErrorBoundary from "./components/ErrorBoundary";
import Analysis from "./pages/Analysis";
import { getAnalysisToken, setAuthReady, setDesktopToken } from "./api/client";
import { isDesktop } from "./desktop";

// Analysis is the landing page, so it stays in the initial bundle. The heavier
// table/settings pages (and their chart dependencies) load on demand.
const Staging = lazy(() => import("./pages/Staging"));
const Commit = lazy(() => import("./pages/Commit"));
const Sessions = lazy(() => import("./pages/Sessions"));
const Settings = lazy(() => import("./pages/Settings"));
const Models = lazy(() => import("./pages/Models"));

const RouteFallback = () => (
  <div className="flex h-full items-center justify-center text-sm text-text-dim">
    Loading…
  </div>
);

// Best-effort: fetch a LAN auth token up front so REST calls (staging, commit,
// rollback) carry the bearer header when the backend has auth enabled. Failures
// are non-fatal (default mode is auth-disabled).
if (isDesktop) {
  const w = window as unknown as { __AMR_DESKTOP_TOKEN__?: string };
  setDesktopToken(w.__AMR_DESKTOP_TOKEN__ ?? null);
} else {
  setAuthReady(getAnalysisToken());
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ErrorBoundary label="the app">
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/" element={<App />}>
                <Route index element={<Navigate to="/analysis" replace />} />
                <Route path="analysis" element={<Analysis />} />
                <Route path="staging" element={<Staging />} />
                <Route path="commit" element={<Commit />} />
                <Route path="sessions" element={<Sessions />} />
                <Route path="settings" element={<Settings />} />
                <Route path="models" element={<Models />} />
                <Route path="*" element={<Navigate to="/analysis" replace />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
        <Toaster />
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>
);
