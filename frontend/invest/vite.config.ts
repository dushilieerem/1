import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** 开发启动器会传 SVQUANT_INVEST_API_PORT；独立运行时仍默认生产的 8767。 */
const apiTarget = `http://127.0.0.1:${process.env.SVQUANT_INVEST_API_PORT || 8767}`;

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
        target: apiTarget,
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
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
