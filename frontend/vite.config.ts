import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The dev proxy target can be overridden with the VITE_API_PROXY_TARGET env var
// (e.g. VITE_API_PROXY_TARGET=http://192.168.1.50:8000 npm run dev). It defaults
// to the local uvicorn server on 127.0.0.1:8000. Both REST (/api/*) and the
// analysis WebSocket (/api/analyze/stream) are proxied so we avoid CORS during
// dev. The Tauri dev shell loads the Vite server from 127.0.0.1:5173, so the
// host must match that loopback origin.
const proxyTarget =
  process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";

export default defineConfig(({ mode }) => {
  loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: {
        "/api": {
          target: proxyTarget,
          changeOrigin: true,
          ws: true,
        },
        // The app's health probe lives at /health (root), not /api/health.
        // Without this entry the dev server answers it with index.html and the
        // version chip silently falls back to its hardcoded default.
        "/health": {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: "127.0.0.1",
      port: 4173,
      proxy: {
        "/api": {
          target: proxyTarget,
          changeOrigin: true,
          ws: true,
        },
      },
    },
  };
});
