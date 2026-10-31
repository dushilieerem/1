#!/usr/bin/env bash
set -Eeuo pipefail

# One-command local launcher for the SVQuant API, main Vite frontend,
# mobile H5, and cloudflared quick tunnels for external access.
# PostgreSQL and ResearchEngine remain separate services and must be available.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
SCRIPT_PATH="$SCRIPT_DIR/svquant.sh"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
INVEST_H5_DIR="$ROOT_DIR/frontend/invest"
RUNTIME_DIR="$BACKEND_DIR/output/dev-services"
BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
INVEST_H5_PID_FILE="$RUNTIME_DIR/invest-h5.pid"
TUNNEL_FRONTEND_PID_FILE="$RUNTIME_DIR/tunnel-frontend.pid"
TUNNEL_INVEST_PID_FILE="$RUNTIME_DIR/tunnel-invest.pid"
BACKEND_LOG="$RUNTIME_DIR/backend.log"
FRONTEND_LOG="$RUNTIME_DIR/frontend.log"
INVEST_H5_LOG="$RUNTIME_DIR/invest-h5.log"
TUNNEL_FRONTEND_LOG="$RUNTIME_DIR/tunnel-frontend.log"
TUNNEL_INVEST_LOG="$RUNTIME_DIR/tunnel-invest.log"
# 开发端口刻意避开生产（9530 / 8766 / 5432），两套可同时运行
BACKEND_PORT=8768
FRONTEND_PORT=9531
INVEST_H5_PORT=9541
STARTUP_TIMEOUT_SECONDS=60
TUNNEL_TIMEOUT_SECONDS=40
CONDA_ENV_NAME="${SVQUANT_CONDA_ENV:-svquant}"
BASH_BIN="$(command -v bash)"
CLOUDFLARED_INSTALL_PATH="${SVQUANT_CLOUDFLARED_PATH:-$HOME/.local/bin/cloudflared}"
SERVICES=(backend frontend invest-h5)
TUNNELS=(tunnel-frontend tunnel-invest)

# 健康检查/探活必须直连本机：shell 里若有 http_proxy（如 Clash），curl 127.0.0.1
# 会被拐到代理导致服务被误判为未就绪（进而回滚误杀）。子服务一并继承，无副作用。
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost"
export no_proxy="${no_proxy:+$no_proxy,}127.0.0.1,localhost"

usage() {
  cat <<'EOF'
SVQuant 本地开发启动器

用法：
  ./scripts/svquant.sh                    一键启动全部服务 + cloudflared 临时通道
  ./scripts/svquant.sh start              同上
  ./scripts/svquant.sh start --no-tunnel  只启动服务，不建外网通道
  ./scripts/svquant.sh stop               停止全部服务与通道
  ./scripts/svquant.sh restart            重启全部
  ./scripts/svquant.sh status             查看进程状态与外网地址
  ./scripts/svquant.sh logs               跟踪全部日志
  ./scripts/svquant.sh tunnel             仅创建 cloudflared 临时通道
  ./scripts/svquant.sh untunnel           仅停止 cloudflared 临时通道
  ./scripts/svquant.sh install-cloudflared  下载 cloudflared 到 ~/.local/bin

启动成功后：
  主前端     http://127.0.0.1:9530
  API        http://127.0.0.1:8766/docs
  手机 H5    http://127.0.0.1:9540   （演示账号 demo / demo1234）
  Invest API http://127.0.0.1:8767/docs
  外网       *.trycloudflare.com，地址每次启动都会变，用 status 查看

注意：cloudflared 快速通道对公网开放且没有额外鉴权，演示数据也会被访问到，
      仅用于临时演示，用完请 stop 或 untunnel。

cloudflared 未安装时运行 ./scripts/svquant.sh install-cloudflared；
也可用 SVQUANT_CLOUDFLARED_BIN 指定已有二进制。
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

find_cloudflared() {
  local candidate
  if [[ -n "${SVQUANT_CLOUDFLARED_BIN:-}" ]]; then
    if [[ -x "$SVQUANT_CLOUDFLARED_BIN" ]]; then
      printf '%s\n' "$SVQUANT_CLOUDFLARED_BIN"
      return 0
    fi
    return 1
  fi
  if command -v cloudflared >/dev/null 2>&1; then
    command -v cloudflared
    return 0
  fi
  for candidate in "$CLOUDFLARED_INSTALL_PATH" "$ROOT_DIR/.tools/cloudflared"; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

install_cloudflared() {
  local asset="" url="" tmp=""
  command -v curl >/dev/null 2>&1 || die "需要 curl 下载 cloudflared。"
  case "$(uname -m)" in
    x86_64|amd64) asset="cloudflared-linux-amd64" ;;
    aarch64|arm64) asset="cloudflared-linux-arm64" ;;
    armv7l|armv6l) asset="cloudflared-linux-arm" ;;
    *) die "不支持的 CPU 架构：$(uname -m)" ;;
  esac
  url="https://github.com/cloudflare/cloudflared/releases/latest/download/$asset"
  mkdir -p "$(dirname -- "$CLOUDFLARED_INSTALL_PATH")"
  tmp="$(mktemp "$CLOUDFLARED_INSTALL_PATH.XXXXXX")"
  printf '下载 %s ...\n' "$url" >&2
  if ! curl -fL --retry 3 --connect-timeout 15 -o "$tmp" "$url"; then
    rm -f -- "$tmp"
    die "cloudflared 下载失败（网络或代理问题）。"
  fi
  chmod +x "$tmp"
  if ! "$tmp" --version >/dev/null 2>&1; then
    rm -f -- "$tmp"
    die "下载的 cloudflared 无法执行。"
  fi
  mv -f -- "$tmp" "$CLOUDFLARED_INSTALL_PATH"
  printf '已安装 cloudflared：%s\n' "$CLOUDFLARED_INSTALL_PATH"
  "$CLOUDFLARED_INSTALL_PATH" --version
}

pid_file_for() {
  case "$1" in
    backend) printf '%s\n' "$BACKEND_PID_FILE" ;;
    frontend) printf '%s\n' "$FRONTEND_PID_FILE" ;;
    invest-h5) printf '%s\n' "$INVEST_H5_PID_FILE" ;;
    tunnel-frontend) printf '%s\n' "$TUNNEL_FRONTEND_PID_FILE" ;;
    tunnel-invest) printf '%s\n' "$TUNNEL_INVEST_PID_FILE" ;;
    *) return 1 ;;
  esac
}

log_file_for() {
  case "$1" in
    backend) printf '%s\n' "$BACKEND_LOG" ;;
    frontend) printf '%s\n' "$FRONTEND_LOG" ;;
    invest-h5) printf '%s\n' "$INVEST_H5_LOG" ;;
    tunnel-frontend) printf '%s\n' "$TUNNEL_FRONTEND_LOG" ;;
    tunnel-invest) printf '%s\n' "$TUNNEL_INVEST_LOG" ;;
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
      # 主前端与 Invest H5 共用 frontend/node_modules/.bin/vite，必须靠端口区分。
      [[ "$args" == *"$FRONTEND_DIR"* && "$args" == *vite* && "$args" == *"--port $FRONTEND_PORT"* ]]
      ;;
    invest-h5)
      [[ "$args" == *"$SCRIPT_PATH _run_invest_h5"* ||
         ( "$args" == *vite* && "$args" == *"--port $INVEST_H5_PORT"* ) ]]
      ;;
    tunnel-frontend)
      [[ "$args" == *"$SCRIPT_PATH _run_tunnel"* ||
         ( "$args" == *cloudflared* && "$args" == *"127.0.0.1:$FRONTEND_PORT"* ) ]]
      ;;
    tunnel-invest)
      [[ "$args" == *"$SCRIPT_PATH _run_tunnel"* ||
         ( "$args" == *cloudflared* && "$args" == *"127.0.0.1:$INVEST_H5_PORT"* ) ]]
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
    invest-h5) printf 'http://127.0.0.1:%s/\n' "$INVEST_H5_PORT" ;;
    *) return 1 ;;
  esac
}

port_for() {
  case "$1" in
    backend) printf '%s\n' "$BACKEND_PORT" ;;
    frontend) printf '%s\n' "$FRONTEND_PORT" ;;
    invest-h5) printf '%s\n' "$INVEST_H5_PORT" ;;
    *) return 1 ;;
  esac
}

tunnel_url_from_log() {
  local log_file="$1"
  [[ -f "$log_file" ]] || return 1
  grep -oE 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' "$log_file" 2>/dev/null | tail -n 1
}

run_backend() {
  activate_conda_env || die "无法激活 Conda 环境 '$CONDA_ENV_NAME'。"
  cd "$BACKEND_DIR"
  if [[ -n "${SVQUANT_PID_FILE:-}" ]]; then
    printf '%s\n' "$$" > "$SVQUANT_PID_FILE"
  fi
  exec env SVQUANT_BACKEND_PORT="$BACKEND_PORT" python -u api_server.py
}

run_frontend() {
  cd "$FRONTEND_DIR"
  if [[ -n "${SVQUANT_PID_FILE:-}" ]]; then
    printf '%s\n' "$$" > "$SVQUANT_PID_FILE"
  fi
  exec env SVQUANT_BACKEND_PORT="$BACKEND_PORT" SVQUANT_INVEST_H5_PORT="$INVEST_H5_PORT" \
    "$FRONTEND_DIR/node_modules/.bin/vite" --host 0.0.0.0 --port "$FRONTEND_PORT" --strictPort
}

run_invest_h5() {
  cd "$INVEST_H5_DIR"
  if [[ -n "${SVQUANT_PID_FILE:-}" ]]; then
    printf '%s\n' "$$" > "$SVQUANT_PID_FILE"
  fi
  exec env SVQUANT_BACKEND_PORT="$BACKEND_PORT" \
    "$FRONTEND_DIR/node_modules/.bin/vite" --host 0.0.0.0 --port "$INVEST_H5_PORT" --strictPort
}

run_tunnel() {
  local bin="" port="${SVQUANT_TUNNEL_PORT:-}"
  bin="$(find_cloudflared || true)"
  [[ -n "$bin" ]] || die "找不到 cloudflared。"
  [[ -n "$port" ]] || die "缺少 SVQUANT_TUNNEL_PORT。"
  if [[ -n "${SVQUANT_PID_FILE:-}" ]]; then
    printf '%s\n' "$$" > "$SVQUANT_PID_FILE"
  fi
  exec "$bin" tunnel --url "http://127.0.0.1:$port" --no-autoupdate
}

wait_for_services_ready() {
  local -a services=("$@")
  local deadline=$((SECONDS + STARTUP_TIMEOUT_SECONDS))
  local next_notice=$((SECONDS + 5))
  local -a ready=()
  local i service all_ready

  for i in "${!services[@]}"; do
    ready[i]=0
  done

  printf '服务已在独立后台会话启动，等待就绪（最多 %s 秒）...\n' \
    "$STARTUP_TIMEOUT_SECONDS"
  while ((SECONDS <= deadline)); do
    all_ready=1
    for i in "${!services[@]}"; do
      service="${services[i]}"
      if ((ready[i])); then
        continue
      fi
      all_ready=0
      if curl -fsS --max-time 1 "$(health_url_for "$service")" >/dev/null 2>&1; then
        ready[i]=1
        printf '%s 已就绪（PID %s）。\n' "$service" "$(managed_pid "$service" || true)"
      elif ! managed_pid "$service" >/dev/null; then
        printf '%s 进程已退出。\n' "$service" >&2
        return 1
      fi
    done
    if ((all_ready)); then
      return 0
    fi
    if ((SECONDS >= next_notice)); then
      printf '仍在等待服务启动（已等待 %s 秒）。\n' \
        "$((SECONDS - deadline + STARTUP_TIMEOUT_SECONDS))"
      next_notice=$((SECONDS + 5))
    fi
    sleep 0.5
  done

  printf '服务未能在 %s 秒内全部就绪。\n' "$STARTUP_TIMEOUT_SECONDS" >&2
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
  case "$service" in
    backend)
      setsid env \
        SVQUANT_CONDA_ENV="$CONDA_ENV_NAME" \
        SVQUANT_CONDA_HOOK="$SVQUANT_CONDA_HOOK" \
        SVQUANT_PID_FILE="$pid_file" \
        "$BASH_BIN" "$SCRIPT_PATH" _run_backend >> "$log_file" 2>&1 </dev/null &
      ;;
    frontend)
      setsid env SVQUANT_PID_FILE="$pid_file" \
        "$BASH_BIN" "$SCRIPT_PATH" _run_frontend >> "$log_file" 2>&1 </dev/null &
      ;;
    invest-h5)
      setsid env SVQUANT_PID_FILE="$pid_file" \
        "$BASH_BIN" "$SCRIPT_PATH" _run_invest_h5 >> "$log_file" 2>&1 </dev/null &
      ;;
    *)
      printf '错误：未知服务 %s。\n' "$service" >&2
      return 1
      ;;
  esac

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

start_tunnel() {
  local name="$1" port="$2" pid_file log_file pid url attempt existing_pid bin
  pid_file="$(pid_file_for "$name")"
  log_file="$(log_file_for "$name")"

  existing_pid="$(managed_pid "$name" || true)"
  if [[ -n "$existing_pid" ]]; then
    url="$(tunnel_url_from_log "$log_file" || true)"
    printf '%s 已在运行（PID %s）%s\n' "$name" "$existing_pid" "${url:+：$url}"
    return 0
  fi

  bin="$(find_cloudflared || true)"
  if [[ -z "$bin" ]]; then
    printf '未找到 cloudflared，跳过 %s。运行 %s install-cloudflared 安装后重试。\n' \
      "$name" "$SCRIPT_PATH" >&2
    return 1
  fi

  mkdir -p "$RUNTIME_DIR"
  # 每次启动清空日志，确保读到的是本次的新地址。
  : > "$log_file"
  setsid env SVQUANT_PID_FILE="$pid_file" SVQUANT_TUNNEL_PORT="$port" \
    "$BASH_BIN" "$SCRIPT_PATH" _run_tunnel >> "$log_file" 2>&1 </dev/null &

  # 子进程写入 PID 文件有短暂延迟，先等登记完成，避免误判为“进程已退出”。
  pid=""
  for ((attempt = 0; attempt < 100; attempt++)); do
    pid="$(managed_pid "$name" || true)"
    [[ -n "$pid" ]] && break
    sleep 0.05
  done
  if [[ -z "$pid" ]]; then
    printf '错误：%s 后台进程未能登记有效 PID。\n' "$name" >&2
    print_log_tail "$log_file"
    return 1
  fi

  local deadline=$((SECONDS + TUNNEL_TIMEOUT_SECONDS))
  url=""
  while ((SECONDS <= deadline)); do
    if ! managed_pid "$name" >/dev/null; then
      printf '错误：%s 进程已退出。\n' "$name" >&2
      print_log_tail "$log_file"
      return 1
    fi
    url="$(tunnel_url_from_log "$log_file" || true)"
    [[ -n "$url" ]] && break
    sleep 0.5
  done
  if [[ -z "$url" ]]; then
    printf '错误：%s 在 %s 秒内未取得通道地址。\n' "$name" "$TUNNEL_TIMEOUT_SECONDS" >&2
    print_log_tail "$log_file"
    return 1
  fi

  printf '%s 已创建：%s -> http://127.0.0.1:%s\n' "$name" "$url" "$port"
}

start_tunnels() {
  local rc=0
  start_tunnel tunnel-frontend "$FRONTEND_PORT" || rc=1
  start_tunnel tunnel-invest "$INVEST_H5_PORT" || rc=1
  return "$rc"
}

stop_tunnels() {
  local name
  for name in "${TUNNELS[@]}"; do
    stop_service "$name"
  done
}

start_all() {
  local with_tunnel="$1" i j service failed=0
  local -a before=()
  [[ -f "$BACKEND_DIR/.env" ]] || die "缺少 backend/.env；请先复制 backend/.env.example 并填写配置。"
  [[ -x "$FRONTEND_DIR/node_modules/.bin/vite" ]] || die "前端依赖未安装；请先在 frontend 目录运行 npm install。"
  command -v curl >/dev/null 2>&1 || die "需要 curl 执行启动健康检查。"
  command -v setsid >/dev/null 2>&1 || die "需要 setsid 将服务与当前终端会话隔离。"
  SVQUANT_CONDA_HOOK="$(find_conda_hook)" || die "找不到 Conda；请先安装/初始化 Conda，或设置 SVQUANT_CONDA_HOOK。"
  export SVQUANT_CONDA_HOOK CONDA_ENV_NAME
  activate_conda_env || die "无法激活 Conda 环境 '$CONDA_ENV_NAME'。"

  mkdir -p "$RUNTIME_DIR"

  for i in "${!SERVICES[@]}"; do
    service="${SERVICES[i]}"
    before[i]="$(managed_pid "$service" || true)"
    if ! start_service "$service"; then
      failed=1
      break
    fi
  done
  if ((failed)); then
    for ((j = 0; j < i; j++)); do
      if [[ -z "${before[j]}" ]]; then
        stop_service "${SERVICES[j]}" || true
      fi
    done
    return 1
  fi

  if ! wait_for_services_ready "${SERVICES[@]}"; then
    for i in "${!SERVICES[@]}"; do
      print_log_tail "$(log_file_for "${SERVICES[i]}")"
    done
    for i in "${!SERVICES[@]}"; do
      if [[ -z "${before[i]}" ]]; then
        stop_service "${SERVICES[i]}" || true
      fi
    done
    return 1
  fi

  if ((with_tunnel)); then
    if ! start_tunnels; then
      printf '部分外网通道未建立；服务本身仍在运行。可稍后执行 %s tunnel 重试。\n' \
        "$SCRIPT_PATH" >&2
    fi
  fi

  printf '\nSVQuant 已启动：\n'
  printf '  主前端：http://127.0.0.1:%s\n' "$FRONTEND_PORT"
  printf '  API：   http://127.0.0.1:%s/docs\n' "$BACKEND_PORT"
  printf '  手机 H5：http://127.0.0.1:%s  （演示账号 demo/demo1234）\n' "$INVEST_H5_PORT"
  local name url found=0
  if ((with_tunnel)); then
    for name in "${TUNNELS[@]}"; do
      url="$(tunnel_url_from_log "$(log_file_for "$name")" || true)"
      if [[ -n "$url" ]]; then
        printf '  外网 %s：%s\n' "$name" "$url"
        found=1
      fi
    done
  fi
  if ((with_tunnel && found)); then
    printf '  提示：trycloudflare 临时地址公网可访问、每次启动会变，用完记得 stop。\n'
  fi
}

show_status() {
  local service pid url
  for service in "${SERVICES[@]}"; do
    pid="$(managed_pid "$service" || true)"
    if [[ -n "$pid" ]]; then
      if curl -fsS --max-time 2 "$(health_url_for "$service")" >/dev/null 2>&1; then
        printf '%-16s 运行中  PID=%s  %s\n' "$service" "$pid" "$(health_url_for "$service")"
      else
        printf '%-16s 进程存在但未就绪  PID=%s  %s\n' "$service" "$pid" "$(health_url_for "$service")"
      fi
    else
      printf '%-16s 未运行\n' "$service"
    fi
  done
  for service in "${TUNNELS[@]}"; do
    pid="$(managed_pid "$service" || true)"
    url="$(tunnel_url_from_log "$(log_file_for "$service")" || true)"
    if [[ -n "$pid" ]]; then
      printf '%-16s 运行中  PID=%s  %s\n' "$service" "$pid" "${url:-（等待地址）}"
    else
      printf '%-16s 未运行\n' "$service"
    fi
  done
}

MODE="start"
NO_TUNNEL=0
for arg in "$@"; do
  case "$arg" in
    --no-tunnel) NO_TUNNEL=1 ;;
    start|stop|restart|status|logs|tunnel|untunnel|install-cloudflared)
      MODE="$arg"
      ;;
    _run_backend|_run_frontend|_run_invest_h5|_run_tunnel)
      MODE="$arg"
      ;;
    -h|--help|help)
      MODE="help"
      ;;
    *)
      printf '未知参数：%s\n\n' "$arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$MODE" in
  start)
    if ((NO_TUNNEL)); then
      start_all 0
    else
      start_all 1
    fi
    ;;
  stop)
    stop_tunnels
    stop_service invest-h5
    stop_service frontend
    stop_service backend
    ;;
  restart)
    stop_tunnels
    stop_service invest-h5
    stop_service frontend
    stop_service backend
    start_all "$((1 - NO_TUNNEL))"
    ;;
  tunnel)
    start_tunnels
    ;;
  untunnel)
    stop_tunnels
    ;;
  install-cloudflared)
    install_cloudflared
    ;;
  status)
    show_status
    ;;
  logs)
    mkdir -p "$RUNTIME_DIR"
    touch "$BACKEND_LOG" "$FRONTEND_LOG" "$INVEST_H5_LOG" \
      "$TUNNEL_FRONTEND_LOG" "$TUNNEL_INVEST_LOG"
    tail -n 100 -F "$BACKEND_LOG" "$FRONTEND_LOG" "$INVEST_H5_LOG" \
      "$TUNNEL_FRONTEND_LOG" "$TUNNEL_INVEST_LOG"
    ;;
  _run_backend)
    run_backend
    ;;
  _run_frontend)
    run_frontend
    ;;
  _run_invest_h5)
    run_invest_h5
    ;;
  _run_tunnel)
    run_tunnel
    ;;
  help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
