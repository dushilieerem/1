import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import basicSsl from "@vitejs/plugin-basic-ssl";
import path from "path";
import { fileURLToPath } from "url";
import fs from "node:fs";
import http from "node:http";

/** 默认 HTTP :9530。需要 HTTPS 时用 `npm run dev:https`（会占用同一端口） */
const useHttps = process.env.VITE_DEV_HTTPS === "1";
const devPort = Number(process.env.VITE_DEV_PORT || 9530);

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** 只从 backend/.env 读取 KEY；前端不维护同一配置的第二份副本。 */
function readBackendEnv(key: string): string | undefined {
  const envPath = path.resolve(__dirname, "../backend/.env");
  if (!fs.existsSync(envPath)) return undefined;
  for (const raw of fs.readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const i = line.indexOf("=");
    const k = line.slice(0, i).trim();
    if (k !== key) continue;
    return line
      .slice(i + 1)
      .trim()
      .replace(/^['"]|['"]$/g, "");
  }
  return undefined;
}

/** 只读取 backend/.env 的 YG_RE_BASE，前端不维护第二个地址配置。 */
const ygReBase = (readBackendEnv("YG_RE_BASE") || "").replace(/\/$/, "");
if (!ygReBase) {
  throw new Error("backend/.env 未配置 YG_RE_BASE");
}
const parsedYgReBase = new URL(ygReBase);
if (!["http:", "https:"].includes(parsedYgReBase.protocol) || !parsedYgReBase.hostname) {
  throw new Error("backend/.env 的 YG_RE_BASE 必须是完整的 http(s) URL");
}
const ygReHost = parsedYgReBase.hostname;

/** 本机 Clash 等会设 HTTP_PROXY；192.168 内网必须直连，否则 /yg-api 首包可卡 10s+ */
const noProxyExtra = [ygReHost, "192.168.0.0/16", "10.0.0.0/8", "127.0.0.1", "localhost"];
process.env.NO_PROXY = [...new Set([...(process.env.NO_PROXY || "").split(","), ...noProxyExtra])]
  .map((s) => s.trim())
  .filter(Boolean)
  .join(",");
process.env.no_proxy = process.env.NO_PROXY;

/**
 * agent:false + 显式直连 Agent，避免把 RE 拐进 127.0.0.1:7897。
 */
const ygDirectAgent = new http.Agent({ keepAlive: true, maxSockets: 16 });

const ygApiProxy = {
  target: ygReBase,
  changeOrigin: true,
  rewrite: (p: string) => p.replace(/^\/yg-api/, ""),
  timeout: 1_800_000,
  proxyTimeout: 1_800_000,
  agent: ygDirectAgent,
  configure: (proxy: { on: (ev: string, fn: (...args: unknown[]) => void) => void }) => {
    proxy.on("proxyReq", () => {
      /* keep hook for future debug */
    });
    proxy.on("error", (err: unknown) => {
      console.error("[yg-api proxy]", err);
    });
  },
};

export default defineConfig({
  plugins: [react(), tailwindcss(), ...(useHttps ? [basicSsl()] : [])],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    host: "0.0.0.0",
    port: Number.isFinite(devPort) && devPort > 0 ? devPort : 9530,
    strictPort: true,
    https: useHttps,
    fs: {
      // 帮助页直接引用根目录 docs/08-使用文档/ 下的 Markdown
      allow: [path.resolve(__dirname, "..")],
    },
    // Avoid stale/corrupt Chromium disk-cache after C: filled up (ERR_CACHE_READ_FAILURE).
    headers: {
      "Cache-Control": "no-store",
    },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8766",
        changeOrigin: true,
        // 与 re-backtest BFF 对齐：长回测可 >2min，默认代理超时会变成 Failed to fetch
        timeout: 1_800_000,
        proxyTimeout: 1_800_000,
      },
      "/yg-api": ygApiProxy,
    },
  },
  // 试用版：npm run build && npm run preview:stable → :9532（与开发 :9530 互不干扰）
  preview: {
    host: "0.0.0.0",
    port: 9532,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8766",
        changeOrigin: true,
        timeout: 1_800_000,
        proxyTimeout: 1_800_000,
      },
      "/yg-api": ygApiProxy,
    },
  },
});
