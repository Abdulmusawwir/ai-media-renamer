import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import App from "./App";
import { StoreProvider } from "./store";
import "./styles.css";
import Analysis from "./pages/Analysis";
import Staging from "./pages/Staging";
import Commit from "./pages/Commit";
import Sessions from "./pages/Sessions";
import Settings from "./pages/Settings";
import Models from "./pages/Models";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <StoreProvider>
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
      </StoreProvider>
    </BrowserRouter>
  </React.StrictMode>
);
