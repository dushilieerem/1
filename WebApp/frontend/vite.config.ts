import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    host: "0.0.0.0",
    port: 9530,
    strictPort: true,
    // Avoid stale/corrupt Chromium disk-cache after C: filled up (ERR_CACHE_READ_FAILURE).
    headers: {
      "Cache-Control": "no-store",
    },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8766",
        changeOrigin: true,
      },
      "/yg-api": {
        target: "http://192.168.3.64:9527",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/yg-api/, ""),
        timeout: 1_800_000,
        proxyTimeout: 1_800_000,
      },
    },
  },
});
