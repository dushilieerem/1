# SVQuant 主前端镜像（Vite 构建 → Nginx 静态托管 + /api 反代）
# 构建上下文必须是仓库根目录：docker build -f docker/frontend.Dockerfile .
# 原因：frontend/src/content/help/docs.ts 以 ?raw 方式导入 docs/用户指南/*.md，
# vite.config.ts 还会读 backend/.env 的 YG_RE_BASE，两者都在仓库根目录。

FROM node:22-bookworm-slim AS build

WORKDIR /src

# 仅构建期需要：vite.config.ts 要求 YG_RE_BASE 存在且为完整 URL。
# 生产运行走 Nginx 反代 /api，构建期这个值不会被写进运行时逻辑。
ARG YG_RE_BASE=http://127.0.0.1:9527

COPY frontend/package.json frontend/package-lock.json /src/frontend/
RUN cd /src/frontend && npm ci

COPY frontend /src/frontend
COPY docs/用户指南 /src/docs/用户指南

RUN mkdir -p /src/backend \
    && printf 'YG_RE_BASE=%s\n' "$YG_RE_BASE" > /src/backend/.env \
    && cd /src/frontend && npm run build

FROM nginx:1.27-alpine

RUN apk add --no-cache curl

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/frontend/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=6 \
    CMD curl -fsS http://127.0.0.1/healthz || exit 1

STOPSIGNAL SIGQUIT
CMD ["nginx", "-g", "daemon off;"]
