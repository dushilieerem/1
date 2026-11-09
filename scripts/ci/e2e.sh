#!/usr/bin/env bash
# E2E 运行器：按 P0 / 全量跑 Playwright，自动起后端 + 主前端 + H5，结束后清理。
#
# 分层（详见 docs/部署与运维/CI-CD.md）：
#   p0   发 tag 前必跑：登录、H5 个股透视、机构端主链路，约 3 分钟
#   full 每晚或大改动后：全部 spec，约 8 分钟
#
# 用法（仓库根目录）：
#   DATABASE_URL=postgresql://... bash scripts/ci/e2e.sh p0          # 全部 P0
#   bash scripts/ci/e2e.sh p0 h5                                    # 只跑 H5 的 P0
#   bash scripts/ci/e2e.sh full inst                                # 机构端全量
#
# 环境变量：
#   DATABASE_URL   必填，库名需含 _test/_dev/_e2e/_ci（写库用例只在 svquant_test 上启用）
#   PYTHON         默认 <repo>/.ci/venv/bin/python
#   E2E_BACKEND_PORT / E2E_FE_PORT / E2E_H5_PORT   指定端口；默认自动挑空闲端口
#   PYTEST_ARGS 等不使用
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
MODE="${1:-p0}"
SUITE="${2:-all}"
PYTHON="${PYTHON:-$ROOT_DIR/.ci/venv/bin/python}"
E2E_DIR="$ROOT_DIR/tests/e2e"

log() { printf '[e2e] %s\n' "$*" >&2; }

case "$MODE" in p0|full) ;; *) log "用法：e2e.sh [p0|full] [h5|inst|all]"; exit 2 ;; esac
case "$SUITE" in h5|inst|all) ;; *) log "suite 只能是 h5 / inst / all"; exit 2 ;; esac

if [[ -z "${DATABASE_URL:-}" ]]; then
  log "缺少 DATABASE_URL（必须指向 *_test/_dev/_e2e/_ci 库）"
  exit 2
fi
case "$DATABASE_URL" in
  *_test*|*_dev*|*_e2e*|*_ci*) ;;
  *) log "拒绝在非测试库上跑 E2E：$DATABASE_URL"; exit 2 ;;
esac

free_port() {
  "$PYTHON" - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
}
BACKEND_PORT="${E2E_BACKEND_PORT:-$(free_port)}"
FE_PORT="${E2E_FE_PORT:-$(free_port)}"
H5_PORT="${E2E_H5_PORT:-$(free_port)}"

PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT

wait_http() {
  local url="$1" name="$2"
  for _ in $(seq 1 60); do
    if curl -fsS -m 2 -o /dev/null "$url"; then
      log "$name 就绪（$url）"
      return 0
    fi
    sleep 1
  done
  log "$name 60 秒内未就绪（$url）"
  return 1
}

log "启动后端 :$BACKEND_PORT"
(
  cd "$ROOT_DIR/backend"
  DATABASE_URL="$DATABASE_URL" \
  YG_RE_BASE="${YG_RE_BASE:-http://127.0.0.1:9527}" \
  SVQUANT_BACKEND_PORT="$BACKEND_PORT" \
  DEV_SKIP_AUTH=0 \
  INST_E2E_ALLOW_WRITE=1 \
  LLM_API_KEY= LLM_BASE_URL= \
  nohup "$PYTHON" -u api_server.py > "/tmp/svquant-e2e-backend-$BACKEND_PORT.log" 2>&1 &
  echo $! > "/tmp/svquant-e2e-backend-$BACKEND_PORT.pid"
)
PIDS+=("$(cat "/tmp/svquant-e2e-backend-$BACKEND_PORT.pid")")
wait_http "http://127.0.0.1:$BACKEND_PORT/api/health" "后端"

log "启动主前端 :$FE_PORT"
(
  cd "$ROOT_DIR/frontend"
  SVQUANT_BACKEND_PORT="$BACKEND_PORT" \
  nohup node node_modules/vite/bin/vite.js --host 127.0.0.1 --port "$FE_PORT" --strictPort \
    > "/tmp/svquant-e2e-fe-$FE_PORT.log" 2>&1 &
  echo $! > "/tmp/svquant-e2e-fe-$FE_PORT.pid"
)
PIDS+=("$(cat "/tmp/svquant-e2e-fe-$FE_PORT.pid")")

log "启动 H5 :$H5_PORT"
(
  cd "$ROOT_DIR/frontend/invest"
  SVQUANT_BACKEND_PORT="$BACKEND_PORT" \
  nohup node ../node_modules/vite/bin/vite.js --host 127.0.0.1 --port "$H5_PORT" --strictPort \
    > "/tmp/svquant-e2e-h5-$H5_PORT.log" 2>&1 &
  echo $! > "/tmp/svquant-e2e-h5-$H5_PORT.pid"
)
PIDS+=("$(cat "/tmp/svquant-e2e-h5-$H5_PORT.pid")")
wait_http "http://127.0.0.1:$FE_PORT/" "主前端"
wait_http "http://127.0.0.1:$H5_PORT/" "H5"

# P0 只保留业务主链路；布局/溢出/空态类回归放到全量。
P0_FILES=(
  e2e-01-auth.spec.ts
  e2e-08-h5.spec.ts
  e2e-09-inst.spec.ts
  e2e-11-inst-linear-flow.spec.ts
  e2e-13-inst-v3-research-gate.spec.ts
  e2e-14-inst-v3-execute-manage.spec.ts
)
P0_GREP='登录失败提示与成功登录|个股透视 P0|v3 侧栏三组|研究 R3|门禁预览|执行 UI'
H5_FILES=(e2e-08-h5.spec.ts)
INST_FILES=(
  e2e-09-inst.spec.ts e2e-10-inst-audit.spec.ts e2e-11-inst-linear-flow.spec.ts
  e2e-12-inst-approval-roles.spec.ts e2e-13-inst-v3-research-gate.spec.ts
  e2e-14-inst-v3-execute-manage.spec.ts
)

ARGS=()
if [[ "$MODE" == "full" ]]; then
  case "$SUITE" in
    h5) ARGS=("${H5_FILES[@]}") ;;
    inst) ARGS=("${INST_FILES[@]}") ;;
    all) ARGS=() ;;
  esac
else
  case "$SUITE" in
    h5) ARGS=(e2e-08-h5.spec.ts --grep "$P0_GREP") ;;
    inst) ARGS=("${P0_FILES[@]:2}" --grep "$P0_GREP") ;;
    all) ARGS=("${P0_FILES[@]}" --grep "$P0_GREP") ;;
  esac
fi

log "运行 Playwright：$MODE / $SUITE"
cd "$E2E_DIR"
R5_FE_BASE="http://127.0.0.1:$FE_PORT" \
R5_H5_BASE="http://127.0.0.1:$H5_PORT" \
R5_API_BASE="http://127.0.0.1:$BACKEND_PORT" \
INST_E2E_ALLOW_WRITE=1 \
./node_modules/.bin/playwright test "${ARGS[@]}" --reporter=line
