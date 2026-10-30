#!/usr/bin/env bash
# 发布后在宿主机启动 invest-api 与手机 H5，并为生产主前端 / H5 建立 cloudflared 临时通道。
#
# 用法：
#   bash scripts/ci/serve-public.sh start     # 幂等：重启 H5 与 invest-api，复用已有通道
#   bash scripts/ci/serve-public.sh status
#   bash scripts/ci/serve-public.sh stop
#
# 由 deploy.sh 在冒烟通过后调用；PUBLIC_TUNNELS=0 时只启动服务、不建通道。
# 注意：
# - 子进程必须关闭 fd 9（轮询服务的 flock），否则会永久占锁、让后续轮询跳过；
# - 服务需设置 KillMode=process，oneshot 结束时才不会被 systemd 连带杀掉；
# - 手机 H5 目前用 Vite dev server 托管（演示用途），正式上线应改为静态构建 + nginx。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
ENV_FILE="$ROOT_DIR/deploy/.env"
RUNTIME_DIR="${PUBLIC_RUNTIME_DIR:-$ROOT_DIR/deploy/runtime}"
ACTION="${1:-start}"

# 日志走 stderr：start_tunnel 的 stdout 只输出通道地址，供上层捕获
log() { printf '[public %s] %s\n' "$(date '+%F %T')" "$*" >&2; }
die() { log "错误：$*"; exit 1; }

[[ -f "$ENV_FILE" ]] || die "缺少 deploy/.env"
mkdir -p "$RUNTIME_DIR"

env_val() { sed -n "s/^$1=//p" "$ENV_FILE" | head -n1; }

WEB_PORT="${WEB_PORT:-$(env_val WEB_PORT)}"; WEB_PORT="${WEB_PORT:-9530}"
INVEST_API_PORT="${INVEST_API_PORT:-$(env_val INVEST_API_PORT)}"; INVEST_API_PORT="${INVEST_API_PORT:-8767}"
INVEST_H5_PORT="${INVEST_H5_PORT:-$(env_val INVEST_H5_PORT)}"; INVEST_H5_PORT="${INVEST_H5_PORT:-9540}"
INVEST_PYTHON="${INVEST_PYTHON:-$(env_val INVEST_PYTHON)}"; INVEST_PYTHON="${INVEST_PYTHON:-python3}"
INVEST_ENV_NAME="${INVEST_ENV:-$(env_val INVEST_ENV)}"; INVEST_ENV_NAME="${INVEST_ENV_NAME:-production}"
INVEST_JWT="${INVEST_JWT_SECRET:-$(env_val INVEST_JWT_SECRET)}"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-$(env_val CLOUDFLARED_BIN)}"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-$HOME/.local/bin/cloudflared}"
PUBLIC_TUNNELS="${PUBLIC_TUNNELS:-$(env_val PUBLIC_TUNNELS)}"; PUBLIC_TUNNELS="${PUBLIC_TUNNELS:-1}"

API_PID="$RUNTIME_DIR/invest-api.pid"
H5_PID="$RUNTIME_DIR/invest-h5.pid"

pid_alive() { [[ -f "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null; }

stop_pid() { # file name
  local file="$1" name="$2" pid
  [[ -f "$file" ]] || return 0
  pid="$(cat "$file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 1 40); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.25
    done
    kill -KILL "-$pid" 2>/dev/null || true
    log "已停止 $name（PID $pid）"
  fi
  rm -f "$file"
}

wait_http() { # url seconds label
  local url="$1" secs="$2" label="$3"
  for _ in $(seq 1 "$secs"); do
    curl -fsS --max-time 2 "$url" >/dev/null 2>&1 && return 0
    sleep 1
  done
  log "错误：$label 未就绪（$url）"
  return 1
}

ensure_secret() {
  [[ -n "$INVEST_JWT" ]] && return 0
  INVEST_JWT="$(od -An -tx1 -N32 /dev/urandom | tr -d ' \n')"
  printf '\nINVEST_JWT_SECRET=%s\n' "$INVEST_JWT" >> "$ENV_FILE"
  log "已生成 INVEST_JWT_SECRET 并写入 deploy/.env"
}

start_invest_api() {
  ensure_secret
  stop_pid "$API_PID" "invest-api"
  log "启动 invest-api（:${INVEST_API_PORT}）"
  (
    cd "$ROOT_DIR/invest-api"
    # 9>&- 关闭轮询锁，避免子进程长期持有 flock
    exec setsid env INVEST_ENV="$INVEST_ENV_NAME" INVEST_JWT_SECRET="$INVEST_JWT" \
      "$INVEST_PYTHON" -m uvicorn app:app --host 0.0.0.0 --port "$INVEST_API_PORT" \
      > "$RUNTIME_DIR/invest-api.log" 2>&1 < /dev/null 9>&-
  ) &
  echo "$!" > "$API_PID"
  wait_http "http://127.0.0.1:${INVEST_API_PORT}/api/health" 40 "invest-api" || {
    tail -5 "$RUNTIME_DIR/invest-api.log" >&2 || true
    return 1
  }
}

start_h5() {
  local vite="$ROOT_DIR/frontend/node_modules/.bin/vite"
  [[ -x "$vite" ]] || { log "错误：缺少 $vite（先在 frontend 执行 npm ci）"; return 1; }
  stop_pid "$H5_PID" "手机 H5"
  log "启动手机 H5（:${INVEST_H5_PORT}）"
  (
    cd "$ROOT_DIR/frontend/invest"
    exec setsid "$vite" --host 0.0.0.0 --port "$INVEST_H5_PORT" --strictPort \
      > "$RUNTIME_DIR/invest-h5.log" 2>&1 < /dev/null 9>&-
  ) &
  echo "$!" > "$H5_PID"
  wait_http "http://127.0.0.1:${INVEST_H5_PORT}/" 40 "手机 H5" || {
    tail -5 "$RUNTIME_DIR/invest-h5.log" >&2 || true
    return 1
  }
}

tunnel_url() { grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$1" 2>/dev/null | tail -1 || true; }

start_tunnel() { # name port
  local name="$1" port="$2" pid_file="$RUNTIME_DIR/tunnel-$1.pid" log_file="$RUNTIME_DIR/tunnel-$1.log" url=""
  [[ -x "$CLOUDFLARED_BIN" ]] || { log "错误：找不到 cloudflared（$CLOUDFLARED_BIN）"; return 1; }

  if pid_alive "$pid_file"; then
    url="$(tunnel_url "$log_file")"
    if [[ -n "$url" ]]; then
      log "$name 复用通道：$url"
      printf '%s\n' "$url"
      return 0
    fi
  fi

  stop_pid "$pid_file" "$name"
  : > "$log_file"
  (
    exec setsid "$CLOUDFLARED_BIN" tunnel --url "http://127.0.0.1:${port}" --no-autoupdate \
      > "$log_file" 2>&1 < /dev/null 9>&-
  ) &
  echo "$!" > "$pid_file"
  for _ in $(seq 1 45); do
    url="$(tunnel_url "$log_file")"
    [[ -n "$url" ]] && break
    kill -0 "$(cat "$pid_file")" 2>/dev/null || break
    sleep 1
  done
  if [[ -z "$url" ]]; then
    log "错误：$name 未取得通道地址"
    tail -5 "$log_file" >&2 || true
    return 1
  fi
  log "$name 已创建：$url -> http://127.0.0.1:${port}"
  printf '%s\n' "$url"
}

stop_all() {
  stop_pid "$RUNTIME_DIR/tunnel-invest.pid" "H5 通道"
  stop_pid "$RUNTIME_DIR/tunnel-frontend.pid" "主前端通道"
  stop_pid "$H5_PID" "手机 H5"
  stop_pid "$API_PID" "invest-api"
}

status_all() {
  local api="未运行" h5="未运行" fe_url="-" h5_url="-"
  pid_alive "$API_PID" && api="运行中 PID=$(cat "$API_PID")"
  pid_alive "$H5_PID" && h5="运行中 PID=$(cat "$H5_PID")"
  pid_alive "$RUNTIME_DIR/tunnel-frontend.pid" && fe_url="$(tunnel_url "$RUNTIME_DIR/tunnel-frontend.log")"
  pid_alive "$RUNTIME_DIR/tunnel-invest.pid" && h5_url="$(tunnel_url "$RUNTIME_DIR/tunnel-invest.log")"
  printf 'invest-api     %s  http://127.0.0.1:%s\n' "$api" "$INVEST_API_PORT"
  printf '手机 H5        %s  http://127.0.0.1:%s\n' "$h5" "$INVEST_H5_PORT"
  printf '主前端通道     %s\n' "${fe_url:--}"
  printf 'H5 通道        %s\n' "${h5_url:--}"
}

case "$ACTION" in
  start)
    start_invest_api || exit 1
    start_h5 || exit 1
    if [[ "$PUBLIC_TUNNELS" == "1" ]]; then
      fe_url="$(start_tunnel frontend "$WEB_PORT")" || exit 1
      h5_url="$(start_tunnel invest "$INVEST_H5_PORT")" || exit 1
      log "主前端：$fe_url"
      log "手机 H5：$h5_url"
    else
      log "PUBLIC_TUNNELS=0，跳过通道创建"
    fi
    log "手机 H5 与外网通道就绪"
    ;;
  stop)
    stop_all
    ;;
  status)
    status_all
    ;;
  *)
    printf '用法：%s [start|stop|status]\n' "$0" >&2
    exit 2
    ;;
esac
