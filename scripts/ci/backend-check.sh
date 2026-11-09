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
  # 多个 Agent 可能同时跑 CI；默认端口被占用时自动向后找空闲端口。
  # 不用 ss/ss -ltn：CD 的 systemd 服务 PATH 里没有 /usr/sbin，探测会静默失效，
  # 端口被占时 docker run 直接失败。改用解释器自带的 socket bind 探测。
  _port_busy() {
    "$PYTHON_BIN" - "$1" <<'PY' >/dev/null 2>&1
import socket, sys
port = int(sys.argv[1])
s = socket.socket()
try:
    s.bind(("0.0.0.0", port))
except OSError:
    sys.exit(0)  # 被占用
finally:
    s.close()
sys.exit(1)  # 空闲
PY
  }
  if _port_busy "$PG_PORT"; then
    original="$PG_PORT"
    for candidate in $(seq $((PG_PORT + 1)) $((PG_PORT + 30))); do
      if ! _port_busy "$candidate"; then PG_PORT="$candidate"; break; fi
    done
    [[ "$PG_PORT" != "$original" ]] || { log "端口 ${original} 被占用且找不到空闲 CI 端口"; exit 1; }
    log "CI 端口 ${original} 被占用，改用 ${PG_PORT}"
  fi
  log "启动一次性 PostgreSQL（:${PG_PORT}）"
  # 探测与实际启动之间仍可能被别人抢端口，失败就顺延重试，别让整轮 CI 白跑。
  started=0
  for _ in 1 2 3 4 5; do
    if docker run -d --rm --name "$PG_CONTAINER" \
      -e POSTGRES_USER=svquant \
      -e POSTGRES_PASSWORD=svquant \
      -e POSTGRES_DB=svquant_ci \
      -p "127.0.0.1:${PG_PORT}:5432" \
      postgres:16-alpine >/dev/null 2>&1; then
      started=1
      break
    fi
    PG_PORT=$((PG_PORT + 1))
    log "端口启动失败，改试 :${PG_PORT}"
  done
  [[ "$started" == "1" ]] || { log "找不到可用的 CI PostgreSQL 端口"; exit 1; }
  STARTED_PG=1

  for _ in $(seq 1 60); do
    if docker exec "$PG_CONTAINER" pg_isready -U svquant -d svquant_ci >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  docker exec "$PG_CONTAINER" pg_isready -U svquant -d svquant_ci >/dev/null 2>&1 || {
    log "PostgreSQL 未在 60s 内就绪"
    exit 1
  }
  export DATABASE_URL="postgresql://svquant:svquant@127.0.0.1:${PG_PORT}/svquant_ci"
fi

# backend/.env 不存在时，模块导入期会因 YG_RE_BASE 缺失直接抛错。
export YG_RE_BASE="${YG_RE_BASE:-http://127.0.0.1:9527}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-ci-test-secret-0123456789abcdefghijklmnop}"
export DEV_SKIP_AUTH=0

cd "$BACKEND_DIR"
log "迁移门禁：空库 apply 全部迁移"
"$VENV_PY" "$ROOT_DIR/scripts/ci/migration-smoke.py"
log "运行 pytest"
"$VENV_PY" -m pytest tests -q ${PYTEST_ARGS:-}

log "运行 AI 离线评测集（P1-A07）"
"$VENV_PY" -m ai.evals.run
