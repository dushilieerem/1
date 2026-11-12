import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** 手机 H5 与主后端同源：开发启动器传 SVQUANT_BACKEND_PORT；独立运行默认 8766。 */
const apiTarget = `http://127.0.0.1:${process.env.SVQUANT_BACKEND_PORT || 8766}`;

export default defineConfig({
  plugins: [react()],
  // 相对资源路径：既可独立部署，也可嵌入主站 /mobile/
  base: "./",
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
