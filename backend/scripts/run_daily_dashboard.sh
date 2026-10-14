#!/usr/bin/env bash
# SVQuant 因子面板日更包装脚本（Linux；对应 Windows 的 run_daily_dashboard.cmd）。
#
# 日常定时已由后端进程内定时器承担（services/factor/dashboard_scheduler.py，默认 00:00），
# 本脚本用于**手动触发**，或给外部调度（cron / systemd timer / 计划任务）当入口。
# 与进程内定时器、API 刷新按钮靠 flock 互斥，可安全并存。
#
# 用法：
#   backend/scripts/run_daily_dashboard.sh
#   backend/scripts/run_daily_dashboard.sh --combo CSI300:3y
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
BACKEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
CONDA_ENV_NAME="${SVQUANT_CONDA_ENV:-svquant}"

# 本机 shell 常带 http_proxy（如 Clash），127.0.0.1 会被拐到代理导致误判/502。
# Python 侧 services/core/lan_http.py 也会自行并入直连白名单，这里兜底 shell 工具。
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost"
export no_proxy="${no_proxy:+$no_proxy,}127.0.0.1,localhost"

find_conda_hook() {
  local candidate=""
  if [[ -n "${CONDA_PREFIX:-}" && -f "$CONDA_PREFIX/etc/profile.d/conda.sh" ]]; then
    printf '%s\n' "$CONDA_PREFIX/etc/profile.d/conda.sh"
    return 0
  fi
  if [[ -n "${CONDA_EXE:-}" ]]; then
    candidate="$(cd -- "$(dirname -- "$(dirname -- "$CONDA_EXE")")" && pwd -P 2>/dev/null || true)"
    if [[ -f "$candidate/etc/profile.d/conda.sh" ]]; then
      printf '%s\n' "$candidate/etc/profile.d/conda.sh"
      return 0
    fi
  fi
  if command -v conda >/dev/null 2>&1; then
    candidate="$(conda info --base 2>/dev/null || true)"
    if [[ -f "$candidate/etc/profile.d/conda.sh" ]]; then
      printf '%s\n' "$candidate/etc/profile.d/conda.sh"
      return 0
    fi
  fi
  # systemd 的 PATH 很干净，conda 可能不在 PATH 上：再兜几个常见安装位置
  for candidate in \
    "${SVQUANT_CONDA_HOOK:-}" \
    "$HOME/anaconda3/etc/profile.d/conda.sh" \
    "$HOME/miniconda3/etc/profile.d/conda.sh" \
    "$HOME/program/anaconda3/etc/profile.d/conda.sh" \
    "/opt/conda/etc/profile.d/conda.sh"; do
    if [[ -n "$candidate" && -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

activate_conda_env() {
  if [[ "${CONDA_DEFAULT_ENV:-}" == "$CONDA_ENV_NAME" ]]; then
    return 0
  fi
  local hook="${SVQUANT_CONDA_HOOK:-}"
  if [[ -z "$hook" || ! -f "$hook" ]]; then
    hook="$(find_conda_hook)" || return 1
  fi
  # shellcheck disable=SC1090
  source "$hook"
  conda activate "$CONDA_ENV_NAME"
}

activate_conda_env || {
  echo "无法激活 Conda 环境 '$CONDA_ENV_NAME'；请设置 SVQUANT_CONDA_HOOK 指向 conda.sh" >&2
  exit 1
}

cd "$BACKEND_DIR"
exec python -u scripts/daily_dashboard_refresh.py "$@"
