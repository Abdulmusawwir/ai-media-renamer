import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The dev proxy target can be overridden with the VITE_API_PROXY_TARGET env var
// (e.g. VITE_API_PROXY_TARGET=http://192.168.1.50:8000 npm run dev). It defaults
// to the local uvicorn server on port 8000. Both REST (/api/*) and the analysis
// WebSocket (/api/analyze/stream) are proxied so we avoid CORS during dev.
const proxyTarget =
  process.env.VITE_API_PROXY_TARGET || "http://localhost:8000";

export default defineConfig(({ mode }) => {
  loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: proxyTarget,
          changeOrigin: true,
          ws: true,
        },
      },
    },
    preview: {
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
