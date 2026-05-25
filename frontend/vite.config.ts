import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import process from "node:process";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const gateway = env.VITE_OHMATIC_API_BASE_URL || "http://localhost:8080";

  return {
    plugins: [react()],
    server: {
      // BACKEND ENTRY: local dev keeps browser requests same-origin while forwarding to gateway :8080.
      // Production can serve the gateway on the same /v1 and /health paths or set VITE_OHMATIC_API_BASE_URL.
      proxy: {
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
