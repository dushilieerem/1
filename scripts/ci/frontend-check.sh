#!/usr/bin/env bash
# 前端门禁：npm ci + 生产构建（tsc && vite build）+ 全量单元测试。
#
# 用法（仓库根目录）：
#   bash scripts/ci/frontend-check.sh
# 说明：vite.config.ts 强制要求 backend/.env 里有合法 YG_RE_BASE。
#       CI 里没有该文件时脚本会临时生成，退出时还原，绝不覆盖已有的真实 .env。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
FRONTEND_DIR="$ROOT_DIR/frontend"
ENV_PATH="$ROOT_DIR/backend/.env"
ENV_BACKUP="$ROOT_DIR/backend/.env.ci-backup"
CREATED_ENV=0

log() { printf '[frontend-check] %s\n' "$*" >&2; }

restore_env() {
  if [[ "$CREATED_ENV" == "1" ]]; then
    if [[ -f "$ENV_BACKUP" ]]; then
      mv -f "$ENV_BACKUP" "$ENV_PATH"
    else
      rm -f "$ENV_PATH"
    fi
  fi
}
trap restore_env EXIT

command -v node >/dev/null 2>&1 || { log "缺少 node"; exit 1; }
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if (( NODE_MAJOR < 20 )); then
  log "Vite 8 需要 Node >= 20.19，当前 $(node -v)"
  exit 1
fi

if ! grep -qE '^YG_RE_BASE=.+$' "$ENV_PATH" 2>/dev/null; then
  log "backend/.env 缺 YG_RE_BASE，生成临时构建配置"
  if [[ -f "$ENV_PATH" ]]; then
    cp -p "$ENV_PATH" "$ENV_BACKUP"
  fi
  printf 'YG_RE_BASE=http://127.0.0.1:9527\n' > "$ENV_PATH"
  CREATED_ENV=1
fi

cd "$FRONTEND_DIR"
# Windows（Git Bash/msys）上 npm ci 会因原生模块被占用而 EPERM，退化为 install；
# CI 的 Linux 构建机一律走 npm ci，保证与 lockfile 完全一致。
if [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* ]]; then
  log "Windows 环境：改用 npm install（npm ci 可能因文件占用失败）"
  npm install --no-audit --no-fund
else
  log "安装前端依赖（npm ci）"
  npm ci --no-audit --no-fund
fi

log "类型检查 + 生产构建"
npm run build

log "运行前端单元测试"
npm test
