#!/usr/bin/env bash
# 前端门禁（P2-09）：类型检查 + 单测 + 构建 + 体积预算。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
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
