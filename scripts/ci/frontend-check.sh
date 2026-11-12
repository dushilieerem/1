#!/usr/bin/env bash
# 前端门禁（P2-09）：类型检查 + 单测 + 构建 + 体积预算。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
ENV_FILE="$ROOT_DIR/backend/.env"
ENV_BACKUP=""
if [[ ! -f "$ENV_FILE" ]] || ! grep -q '^YG_RE_BASE=' "$ENV_FILE" 2>/dev/null; then
  # vite.config.ts 要求 backend/.env 有 YG_RE_BASE；临时补齐，退出时还原
  ENV_BACKUP="$(mktemp)"
  if [[ -f "$ENV_FILE" ]]; then cp "$ENV_FILE" "$ENV_BACKUP"; else : > "$ENV_BACKUP"; fi
  mkdir -p "$ROOT_DIR/backend"
  printf 'YG_RE_BASE=http://127.0.0.1:9527\n' >> "$ENV_FILE"
  trap 'cp "$ENV_BACKUP" "$ENV_FILE"; rm -f "$ENV_BACKUP"' EXIT
fi
cd "$ROOT_DIR/frontend"

if [[ ! -d node_modules ]]; then
  echo "[frontend-check] 安装依赖（npm ci）"
  npm ci
fi

echo "[frontend-check] tsc --noEmit"
./node_modules/.bin/tsc --noEmit

echo "[frontend-check] 单测"
npm test

echo "[frontend-check] 构建"
node node_modules/vite/bin/vite.js build

echo "[frontend-check] 体积预算"
bash "$ROOT_DIR/scripts/ci/frontend-budget.sh"
