import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 9540,
    strictPort: true,
    // cloudflared 快速通道（scripts/svquant.sh 创建）经 *.trycloudflare.com 访问，
    // Vite 默认按 Host 头拦截，必须显式放行。
    allowedHosts: [".trycloudflare.com"],
    watch: {
      ignored: ["**/.index.html.*.tmpdir/**", "**/*.tmp"],
    },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8767",
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: "0.0.0.0",
    port: 9541,
    strictPort: true,
    allowedHosts: [".trycloudflare.com"],
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8767",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
