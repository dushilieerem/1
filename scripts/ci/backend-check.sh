#!/usr/bin/env bash
# 后端门禁：干净 venv 安装依赖 + 全量 pytest。
# 不依赖部署用 backend/.env：所有外部依赖用临时值注入（测试内部对 HTTP 全 mock）。
#
# 用法（仓库根目录）：
#   bash scripts/ci/backend-check.sh
# 可选环境变量：
#   PYTHON_BIN        解释器，默认 python3（要求 >= 3.11）
#   DATABASE_URL      已有的 PostgreSQL；不填则用 docker 起一次性实例
#   CI_PG_PORT        一次性实例端口，默认 55432
#   PYTEST_ARGS       追加给 pytest 的参数
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="${CI_VENV:-$ROOT_DIR/.ci/venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PG_PORT="${CI_PG_PORT:-55432}"
PG_CONTAINER="svquant-ci-pg-$$"
STARTED_PG=0

log() { printf '[backend-check] %s\n' "$*" >&2; }

cleanup() {
  if [[ "$STARTED_PG" == "1" ]]; then
    docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit(f"需要 Python >= 3.11，当前 {sys.version.split()[0]}")
PY

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  log "创建 venv：$VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
VENV_PY="$VENV_DIR/bin/python"

log "安装后端依赖"
"$VENV_PY" -m pip install --upgrade pip >/dev/null
"$VENV_PY" -m pip install -r "$BACKEND_DIR/requirements-test.txt"

if [[ -z "${DATABASE_URL:-}" ]]; then
  command -v docker >/dev/null 2>&1 || {
    log "没有 docker 也没有 DATABASE_URL；刷新锁相关用例需要真实 PostgreSQL，请二选一提供"
    exit 1
  }
  log "启动一次性 PostgreSQL（:${PG_PORT}）"
  docker run -d --rm --name "$PG_CONTAINER" \
    -e POSTGRES_USER=svquant \
    -e POSTGRES_PASSWORD=svquant \
    -e POSTGRES_DB=svquant \
    -p "127.0.0.1:${PG_PORT}:5432" \
    postgres:16-alpine >/dev/null
  STARTED_PG=1

  for _ in $(seq 1 60); do
    if docker exec "$PG_CONTAINER" pg_isready -U svquant -d svquant >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  docker exec "$PG_CONTAINER" pg_isready -U svquant -d svquant >/dev/null 2>&1 || {
    log "PostgreSQL 未在 60s 内就绪"
    exit 1
  }
  export DATABASE_URL="postgresql://svquant:svquant@127.0.0.1:${PG_PORT}/svquant"
fi

# backend/.env 不存在时，模块导入期会因 YG_RE_BASE 缺失直接抛错。
export YG_RE_BASE="${YG_RE_BASE:-http://127.0.0.1:9527}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-ci-test-secret-0123456789abcdefghijklmnop}"
export DEV_SKIP_AUTH=0

cd "$BACKEND_DIR"
log "运行 pytest"
"$VENV_PY" -m pytest tests -q ${PYTEST_ARGS:-}

log "运行 AI 离线评测集（P1-A07）"
"$VENV_PY" -m ai.evals.run
