import React from "react";
import ReactDOM from "react-dom/client";
import "./styles.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { queryClient } from "./lib/query";
import Toaster from "./components/Toaster";
import ErrorBoundary from "./components/ErrorBoundary";
import Analysis from "./pages/Analysis";
import Staging from "./pages/Staging";
import Commit from "./pages/Commit";
import Sessions from "./pages/Sessions";
import Settings from "./pages/Settings";
import Models from "./pages/Models";
import { getAnalysisToken, setAuthReady, setDesktopToken } from "./api/client";
import { isDesktop } from "./desktop";

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
        </BrowserRouter>
        <Toaster />
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>
);
