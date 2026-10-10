#!/usr/bin/env bash
set -Eeuo pipefail

# One-command local launcher for the SVQuant API and main Vite frontend.
# PostgreSQL and ResearchEngine remain separate services and must be available.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
SCRIPT_PATH="$SCRIPT_DIR/svquant.sh"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
RUNTIME_DIR="$BACKEND_DIR/output/dev-services"
BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
BACKEND_LOG="$RUNTIME_DIR/backend.log"
FRONTEND_LOG="$RUNTIME_DIR/frontend.log"
BACKEND_PORT=8766
FRONTEND_PORT=9530
STARTUP_TIMEOUT_SECONDS=60
CONDA_ENV_NAME="${SVQUANT_CONDA_ENV:-svquant}"
BASH_BIN="$(command -v bash)"

# 健康检查/探活必须直连本机：shell 里若有 http_proxy（如 Clash），curl 127.0.0.1
# 会被拐到代理导致服务被误判为未就绪（进而回滚误杀）。子服务一并继承，无副作用。
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost"
export no_proxy="${no_proxy:+$no_proxy,}127.0.0.1,localhost"

usage() {
  cat <<'EOF'
SVQuant 本地开发启动器

用法：
  ./scripts/svquant.sh                 启动前后端（等同 start）
  ./scripts/svquant.sh start           启动前后端
  ./scripts/svquant.sh stop            停止本脚本启动的前后端
  ./scripts/svquant.sh restart         重启前后端
  ./scripts/svquant.sh status          查看进程状态
  ./scripts/svquant.sh logs            跟踪前后端日志

启动成功后：
  前端  http://127.0.0.1:9530
  API   http://127.0.0.1:8766/docs
  backend/frontend 在独立后台会话运行；启动命令返回或终端断开不会向服务发送 Ctrl+C。

可通过 SVQUANT_CONDA_ENV 指定 Conda 环境，默认 svquant。
EOF
}

die() {
  printf '错误：%s\n' "$*" >&2
  exit 1
}

find_conda_hook() {
  local candidate="" conda_base=""

  if [[ -n "${CONDA_PREFIX:-}" && -f "$CONDA_PREFIX/etc/profile.d/conda.sh" ]]; then
    printf '%s\n' "$CONDA_PREFIX/etc/profile.d/conda.sh"
    return 0
  fi

  if [[ -n "${CONDA_EXE:-}" ]]; then
    conda_base="$(cd -- "$(dirname -- "$(dirname -- "$CONDA_EXE")")" && pwd -P 2>/dev/null || true)"
    candidate="$conda_base/etc/profile.d/conda.sh"
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  if command -v conda >/dev/null 2>&1; then
    conda_base="$(conda info --base 2>/dev/null || true)"
    candidate="$conda_base/etc/profile.d/conda.sh"
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  local base
  for base in \
    "${HOME:-}/miniconda3" \
    "${HOME:-}/anaconda3" \
    "${HOME:-}/mambaforge" \
    "${HOME:-}/miniforge3" \
    "/opt/conda" \
    "/home/dev01/program/anaconda3"; do
    candidate="$base/etc/profile.d/conda.sh"
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

activate_conda_env() {
  local hook="${SVQUANT_CONDA_HOOK:-}"
  if [[ "${CONDA_DEFAULT_ENV:-}" == "$CONDA_ENV_NAME" ]]; then
    return 0
  fi
  if [[ -z "$hook" || ! -f "$hook" ]]; then
    hook="$(find_conda_hook)" || return 1
  fi
  # shellcheck disable=SC1090
  source "$hook"
  conda activate "$CONDA_ENV_NAME"
}

pid_file_for() {
  case "$1" in
    backend) printf '%s\n' "$BACKEND_PID_FILE" ;;
    frontend) printf '%s\n' "$FRONTEND_PID_FILE" ;;
    *) return 1 ;;
  esac
}

log_file_for() {
  case "$1" in
    backend) printf '%s\n' "$BACKEND_LOG" ;;
    frontend) printf '%s\n' "$FRONTEND_LOG" ;;
    *) return 1 ;;
  esac
}

process_matches_service() {
  local service="$1" pid="$2" args=""
  args="$(ps -p "$pid" -o args= 2>/dev/null || ps -p "$pid" -o command= 2>/dev/null || true)"
  case "$service" in
    backend)
      [[ "$args" == *"$SCRIPT_PATH _run_backend"* || "$args" == *"api_server.py"* ]]
      ;;
    frontend)
      [[ "$args" == *"$FRONTEND_DIR"* && "$args" == *vite* ]]
      ;;
    *) return 1 ;;
  esac
}

managed_pid() {
  local service="$1" pid_file pid
  pid_file="$(pid_file_for "$service")"
  [[ -f "$pid_file" ]] || return 1
  IFS= read -r pid < "$pid_file" || true
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  process_matches_service "$service" "$pid" || return 1
  printf '%s\n' "$pid"
}

port_is_listening() {
  local port="$1" listeners=""
  if command -v lsof >/dev/null 2>&1; then
    listeners="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)"
    [[ -n "$listeners" ]]
  elif command -v ss >/dev/null 2>&1; then
    ss -H -ltn "sport = :$port" 2>/dev/null | grep -q .
  else
    (echo >"/dev/tcp/127.0.0.1/$port") >/dev/null 2>&1
  fi
}

health_url_for() {
  case "$1" in
    backend) printf 'http://127.0.0.1:%s/api/health\n' "$BACKEND_PORT" ;;
    frontend) printf 'http://127.0.0.1:%s/\n' "$FRONTEND_PORT" ;;
    *) return 1 ;;
  esac
}

port_for() {
  case "$1" in
    backend) printf '%s\n' "$BACKEND_PORT" ;;
    frontend) printf '%s\n' "$FRONTEND_PORT" ;;
    *) return 1 ;;
  esac
}

run_backend() {
  activate_conda_env || die "无法激活 Conda 环境 '$CONDA_ENV_NAME'。"
  cd "$BACKEND_DIR"
  if [[ -n "${SVQUANT_PID_FILE:-}" ]]; then
    printf '%s\n' "$$" > "$SVQUANT_PID_FILE"
  fi
  exec python -u api_server.py
}

run_frontend() {
  cd "$FRONTEND_DIR"
  if [[ -n "${SVQUANT_PID_FILE:-}" ]]; then
    printf '%s\n' "$$" > "$SVQUANT_PID_FILE"
  fi
  exec "$FRONTEND_DIR/node_modules/.bin/vite" --host 0.0.0.0 --port "$FRONTEND_PORT" --strictPort
}

wait_for_services_ready() {
  local backend_pid="$1" frontend_pid="$2"
  local deadline=$((SECONDS + STARTUP_TIMEOUT_SECONDS))
  local next_notice=$((SECONDS + 5))
  local backend_ready=0 frontend_ready=0

  printf '前后端已在独立后台会话启动，等待就绪（最多 %s 秒）...\n' \
    "$STARTUP_TIMEOUT_SECONDS"
  while ((SECONDS <= deadline)); do
    if ((backend_ready == 0)); then
      if curl -fsS --max-time 1 "$(health_url_for backend)" >/dev/null 2>&1; then
        backend_ready=1
        printf 'backend 已就绪（PID %s）。\n' "$backend_pid"
      elif ! kill -0 "$backend_pid" 2>/dev/null; then
        printf 'backend 进程已退出（PID %s）。\n' "$backend_pid" >&2
        return 1
      fi
    fi

    if ((frontend_ready == 0)); then
      if curl -fsS --max-time 1 "$(health_url_for frontend)" >/dev/null 2>&1; then
        frontend_ready=1
        printf 'frontend 已就绪（PID %s）。\n' "$frontend_pid"
      elif ! kill -0 "$frontend_pid" 2>/dev/null; then
        printf 'frontend 进程已退出（PID %s）。\n' "$frontend_pid" >&2
        return 1
      fi
    fi

    if ((backend_ready && frontend_ready)); then
      return 0
    fi
    if ((SECONDS >= next_notice)); then
      printf '仍在等待服务启动（已等待 %s 秒）。\n' \
        "$((SECONDS - deadline + STARTUP_TIMEOUT_SECONDS))"
      next_notice=$((SECONDS + 5))
    fi
    sleep 0.5
  done

  printf '前后端未能在 %s 秒内全部就绪。\n' "$STARTUP_TIMEOUT_SECONDS" >&2
  return 1
}

print_log_tail() {
  local log_file="$1"
  if [[ -f "$log_file" ]]; then
    printf '\n最近日志（%s）：\n' "$log_file" >&2
    tail -n 40 "$log_file" >&2 || true
  fi
}

start_service() {
  local service="$1" pid_file log_file port pid url existing_pid attempt
  STARTED_PID=""
  pid_file="$(pid_file_for "$service")"
  log_file="$(log_file_for "$service")"
  port="$(port_for "$service")"
  url="$(health_url_for "$service")"

  existing_pid="$(managed_pid "$service" || true)"
  if [[ -n "$existing_pid" ]]; then
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      printf '%s 已运行（PID %s）：%s\n' "$service" "$existing_pid" "$url"
      STARTED_PID="$existing_pid"
      return 0
    fi
    printf '错误：%s 进程（PID %s）存在，但健康检查未通过。\n' "$service" "$existing_pid" >&2
    print_log_tail "$log_file"
    return 1
  fi

  if port_is_listening "$port"; then
    printf '错误：端口 %s 已被其他进程占用；为避免误杀进程，未启动 %s。\n' "$port" "$service" >&2
    return 1
  fi

  : >> "$log_file"
  if [[ "$service" == backend ]]; then
    setsid env \
      SVQUANT_CONDA_ENV="$CONDA_ENV_NAME" \
      SVQUANT_CONDA_HOOK="$SVQUANT_CONDA_HOOK" \
      SVQUANT_PID_FILE="$pid_file" \
      "$BASH_BIN" "$SCRIPT_PATH" _run_backend >> "$log_file" 2>&1 </dev/null &
  else
    setsid env SVQUANT_PID_FILE="$pid_file" \
      "$BASH_BIN" "$SCRIPT_PATH" _run_frontend >> "$log_file" 2>&1 </dev/null &
  fi

  pid=""
  for ((attempt = 0; attempt < 100; attempt++)); do
    pid="$(managed_pid "$service" || true)"
    [[ -n "$pid" ]] && break
    sleep 0.05
  done
  if [[ -z "$pid" ]]; then
    printf '错误：%s 后台进程未能登记有效 PID。\n' "$service" >&2
    print_log_tail "$log_file"
    return 1
  fi

  STARTED_PID="$pid"
  printf '%s 已在独立后台会话启动（PID %s），日志：%s\n' \
    "$service" "$pid" "$log_file"
}

stop_service() {
  local service="$1" pid_file pid attempt
  pid_file="$(pid_file_for "$service")"
  if [[ ! -f "$pid_file" ]]; then
    printf '%s 未由启动脚本运行。\n' "$service"
    return 0
  fi

  IFS= read -r pid < "$pid_file" || true
  if [[ ! "$pid" =~ ^[0-9]+$ ]] || ! kill -0 "$pid" 2>/dev/null; then
    rm -f -- "$pid_file"
    printf '%s 未运行（已清理过期 PID 记录）。\n' "$service"
    return 0
  fi
  if ! process_matches_service "$service" "$pid"; then
    rm -f -- "$pid_file"
    printf '%s PID 记录已不匹配；未向该进程发送信号。\n' "$service"
    return 0
  fi

  kill -TERM "$pid"
  for ((attempt = 0; attempt < 40; attempt++)); do
    if ! kill -0 "$pid" 2>/dev/null || ! process_matches_service "$service" "$pid"; then
      rm -f -- "$pid_file"
      printf '%s 已停止。\n' "$service"
      return 0
    fi
    sleep 0.25
  done

  if kill -0 "$pid" 2>/dev/null && process_matches_service "$service" "$pid"; then
    printf '%s 未在 10 秒内退出，发送 KILL。\n' "$service" >&2
    kill -KILL "$pid" || true
  fi
  rm -f -- "$pid_file"
  printf '%s 已停止。\n' "$service"
}

start_all() {
  local backend_before="" frontend_before="" backend_pid frontend_pid
  [[ -f "$BACKEND_DIR/.env" ]] || die "缺少 backend/.env；请先复制 backend/.env.example 并填写配置。"
  [[ -x "$FRONTEND_DIR/node_modules/.bin/vite" ]] || die "前端依赖未安装；请先在 frontend 目录运行 npm install。"
  command -v curl >/dev/null 2>&1 || die "需要 curl 执行启动健康检查。"
  command -v setsid >/dev/null 2>&1 || die "需要 setsid 将服务与当前终端会话隔离。"
  SVQUANT_CONDA_HOOK="$(find_conda_hook)" || die "找不到 Conda；请先安装/初始化 Conda，或设置 SVQUANT_CONDA_HOOK。"
  export SVQUANT_CONDA_HOOK CONDA_ENV_NAME
  activate_conda_env || die "无法激活 Conda 环境 '$CONDA_ENV_NAME'。"

  mkdir -p "$RUNTIME_DIR"
  backend_before="$(managed_pid backend || true)"
  frontend_before="$(managed_pid frontend || true)"
  start_service backend || return 1
  backend_pid="$STARTED_PID"
  if ! start_service frontend; then
    if [[ -z "$backend_before" ]]; then
      stop_service backend || true
    fi
    return 1
  fi
  frontend_pid="$STARTED_PID"

  if ! wait_for_services_ready "$backend_pid" "$frontend_pid"; then
    print_log_tail "$BACKEND_LOG"
    print_log_tail "$FRONTEND_LOG"
    if [[ -z "$frontend_before" ]]; then
      stop_service frontend || true
    fi
    if [[ -z "$backend_before" ]]; then
      stop_service backend || true
    fi
    return 1
  fi

  printf '\nSVQuant 已启动：\n  前端：http://127.0.0.1:%s\n  API： http://127.0.0.1:%s/docs\n' \
    "$FRONTEND_PORT" "$BACKEND_PORT"
}

show_status() {
  local service pid url
  for service in backend frontend; do
    pid="$(managed_pid "$service" || true)"
    url="$(health_url_for "$service")"
    if [[ -n "$pid" ]]; then
      if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
        printf '%-8s 运行中  PID=%s  %s\n' "$service" "$pid" "$url"
      else
        printf '%-8s 进程存在但未就绪  PID=%s  %s\n' "$service" "$pid" "$url"
      fi
    else
      printf '%-8s 未运行\n' "$service"
    fi
  done
}

case "${1:-start}" in
  start)
    start_all
    ;;
  stop)
    stop_service frontend
    stop_service backend
    ;;
  restart)
    stop_service frontend
    stop_service backend
    start_all
    ;;
  status)
    show_status
    ;;
  logs)
    mkdir -p "$RUNTIME_DIR"
    touch "$BACKEND_LOG" "$FRONTEND_LOG"
    tail -n 100 -F "$BACKEND_LOG" "$FRONTEND_LOG"
    ;;
  _run_backend)
    run_backend
    ;;
  _run_frontend)
    run_frontend
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
