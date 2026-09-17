#!/usr/bin/env bash

set -Eeuo pipefail

# ResearchEngine 的后台进程控制脚本。
# 默认优先使用名为 svquant 的 conda 环境；也可通过 SVQUANT_PYTHON 覆盖。

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RESEARCH_ENGINE_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
RUN_DIR="${SVQUANT_RUN_DIR:-$RESEARCH_ENGINE_ROOT/run}"
LOG_FILE="${SVQUANT_LOG_FILE:-$RESEARCH_ENGINE_ROOT/logs/app.log}"
PID_FILE="${SVQUANT_PID_FILE:-$RUN_DIR/app.pid}"
CONDA_ENV_NAME="${SVQUANT_CONDA_ENV:-svquant}"
PYTHON_BIN="${SVQUANT_PYTHON:-}"
HEALTH_URL="${SVQUANT_HEALTH_URL:-http://127.0.0.1:9527/api/health}"
APP_MODULE="app.main"

select_python() {
    if [[ -n "$PYTHON_BIN" ]]; then
        return
    fi

    if [[ "${CONDA_DEFAULT_ENV:-}" == "$CONDA_ENV_NAME" ]]; then
        PYTHON_BIN="python"
        return
    fi

    if command -v conda >/dev/null 2>&1; then
        local conda_base
        conda_base="$(conda info --base 2>/dev/null || true)"
        if [[ -r "$conda_base/etc/profile.d/conda.sh" ]]; then
            # shellcheck disable=SC1091
            source "$conda_base/etc/profile.d/conda.sh"
            if conda activate "$CONDA_ENV_NAME" >/dev/null 2>&1; then
                PYTHON_BIN="python"
                return
            fi
        fi
    fi

    PYTHON_BIN="python"
}

read_pid() {
    [[ -r "$PID_FILE" ]] || return 1

    local pid
    pid="$(<"$PID_FILE")"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    printf '%s\n' "$pid"
}

is_app_process() {
    local pid="$1"
    local command_line
    command_line="$(ps -p "$pid" -o args= 2>/dev/null || true)"
    [[ "$command_line" == *"$APP_MODULE"* ]]
}

is_running() {
    local pid
    pid="$(read_pid)" || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    is_app_process "$pid"
}

remove_stale_pid() {
    if [[ -e "$PID_FILE" ]] && ! is_running; then
        rm -f -- "$PID_FILE"
    fi
}

start_service() {
    select_python
    mkdir -p -- "$RUN_DIR" "$(dirname -- "$LOG_FILE")"
    remove_stale_pid

    if is_running; then
        printf 'ResearchEngine 已在运行，PID=%s\n' "$(read_pid)"
        printf '日志: %s\n' "$LOG_FILE"
        return 0
    fi

    : >> "$LOG_FILE"
    local python_path
    python_path="$(command -v "$PYTHON_BIN" 2>/dev/null || printf '%s' "$PYTHON_BIN")"
    printf '\n[%s] start: %s -m %s (conda=%s)\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" \
        "$python_path" \
        "$APP_MODULE" \
        "${CONDA_DEFAULT_ENV:-<none>}" >> "$LOG_FILE"

    (
        cd -- "$RESEARCH_ENGINE_ROOT"
        export PYTHONPATH="$RESEARCH_ENGINE_ROOT${PYTHONPATH:+:$PYTHONPATH}"
        exec nohup "$PYTHON_BIN" -m "$APP_MODULE" >> "$LOG_FILE" 2>&1 < /dev/null
    ) &
    local pid=$!
    printf '%s\n' "$pid" > "$PID_FILE"

    # 尽早报告导入失败、数据目录不存在等启动错误。
    sleep 1
    if is_running; then
        printf 'ResearchEngine 已后台启动，PID=%s\n' "$pid"
        printf '日志: %s\n' "$LOG_FILE"
        printf '查看状态: %s status\n' "$SCRIPT_DIR/research-engine.sh"
        printf '查看日志: %s logs\n' "$SCRIPT_DIR/research-engine.sh"
        return 0
    fi

    printf 'ResearchEngine 启动失败，请查看日志: %s\n' "$LOG_FILE" >&2
    tail -n 30 -- "$LOG_FILE" >&2 || true
    rm -f -- "$PID_FILE"
    return 1
}

stop_service() {
    local pid
    pid="$(read_pid 2>/dev/null || true)"
    if [[ -z "$pid" ]] || ! is_running; then
        rm -f -- "$PID_FILE"
        printf 'ResearchEngine 未运行\n'
        return 0
    fi

    kill -TERM "$pid"
    for ((attempt = 0; attempt < 30; attempt++)); do
        if ! is_running; then
            rm -f -- "$PID_FILE"
            printf 'ResearchEngine 已停止\n'
            return 0
        fi
        sleep 1
    done

    printf 'ResearchEngine 未能在 30 秒内停止，PID=%s\n' "$pid" >&2
    return 1
}

status_service() {
    local pid
    pid="$(read_pid 2>/dev/null || true)"
    if [[ -z "$pid" ]] || ! is_running; then
        printf 'ResearchEngine 未运行\n'
        return 1
    fi

    printf 'ResearchEngine 进程运行中，PID=%s\n' "$pid"
    printf '日志: %s\n' "$LOG_FILE"

    if command -v curl >/dev/null 2>&1; then
        local health
        if health="$(curl --noproxy '*' --fail --silent --show-error --max-time 3 "$HEALTH_URL" 2>&1)"; then
            printf 'HTTP 健康检查通过: %s\n' "$health"
            return 0
        fi
        printf 'HTTP 健康检查失败: %s\n' "$health" >&2
        return 2
    fi

    printf '未找到 curl，跳过 HTTP 健康检查\n'
    return 0
}

show_logs() {
    if [[ ! -f "$LOG_FILE" ]]; then
        printf '日志文件尚不存在: %s\n' "$LOG_FILE" >&2
        return 1
    fi

    if [[ "${1:-}" == "--no-follow" ]]; then
        tail -n 100 -- "$LOG_FILE"
    else
        tail -n 100 -F -- "$LOG_FILE"
    fi
}

usage() {
    cat <<'EOF'
用法:
  ResearchEngine/scripts/research-engine.sh start
  ResearchEngine/scripts/research-engine.sh stop
  ResearchEngine/scripts/research-engine.sh restart
  ResearchEngine/scripts/research-engine.sh status
  ResearchEngine/scripts/research-engine.sh logs [--no-follow]

默认文件:
  PID  ResearchEngine/run/app.pid
  日志 ResearchEngine/logs/app.log

可选环境变量:
  SVQUANT_PYTHON      指定 Python 可执行文件，未设置时自动使用 svquant 环境
  SVQUANT_CONDA_ENV   自动激活的 conda 环境，默认 svquant
  SVQUANT_LOG_FILE    日志文件路径
  SVQUANT_PID_FILE    PID 文件路径
  SVQUANT_RUN_DIR     运行时目录
  SVQUANT_HEALTH_URL  健康检查地址
EOF
}

case "${1:-}" in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        stop_service
        start_service
        ;;
    status)
        status_service
        ;;
    logs)
        show_logs "${2:-}"
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
