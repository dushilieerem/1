#!/usr/bin/env bash
set -Eeuo pipefail

# 构建主前端 + 手机 H5，并把 H5 产物放到主前端 dist/mobile。
# 主站 /m 路由用同域 iframe 加载 /mobile/；生产 Nginx 直接托管 dist/mobile。
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR/frontend"

node node_modules/vite/bin/vite.js build
cd "$ROOT_DIR/frontend/invest"
node ../node_modules/vite/bin/vite.js build

rm -rf "$ROOT_DIR/frontend/dist/mobile"
mkdir -p "$ROOT_DIR/frontend/dist/mobile"
cp -a "$ROOT_DIR/frontend/invest/dist/." "$ROOT_DIR/frontend/dist/mobile/"

printf '已生成 %s/dist/mobile（手机 H5 嵌入主站 /mobile/）\n' "$ROOT_DIR/frontend"
