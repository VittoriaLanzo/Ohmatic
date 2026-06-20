import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import process from "node:process";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // OHMATIC_GATEWAY_URL lets the launcher point the dev proxy at a dynamically chosen
  // gateway port while the browser keeps making same-origin /v1 and /health calls.
  const gateway =
    env.OHMATIC_GATEWAY_URL || env.VITE_OHMATIC_API_BASE_URL || "http://localhost:8080";
  // The exporter binds loopback-only (:8004) and is NOT proxied through the gateway,
  // so the dev server forwards /v1/export straight to it while the browser stays
  // same-origin. Fixed port (not gateway-dynamic); override with OHMATIC_EXPORTER_URL.
  const exporter = env.OHMATIC_EXPORTER_URL || "http://127.0.0.1:8004";

  return {
    plugins: [react()],
    server: {
      headers: {
        "Cache-Control": "no-store"
      },
      // BACKEND ENTRY: local dev keeps browser requests same-origin while forwarding to gateway :8080.
      // Production can serve the gateway on the same /v1 and /health paths or set VITE_OHMATIC_API_BASE_URL.
      // Order matters: the more specific /v1/export must precede /v1 so it wins the match.
      proxy: {
        "/v1/export": {
          target: exporter,
          changeOrigin: true
        },
        "/v1": {
          target: gateway,
          changeOrigin: true
        },
        "/health": {
          target: gateway,
          changeOrigin: true
        }
      }
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/test/setup.ts"
    }
  };
});
