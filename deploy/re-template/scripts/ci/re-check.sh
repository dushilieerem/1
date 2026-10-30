#!/usr/bin/env bash
# ResearchEngine 门禁：干净 venv + pytest（复制到 RE 仓库 scripts/ci/ 后使用）。
# 用法：bash scripts/ci/re-check.sh
# 可选：PYTHON_BIN、CI_VENV、PYTEST_ARGS、RE_CI_HAS_MARKETDATA=1（有行情样本时打开依赖行情的用例）
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
VENV_DIR="${CI_VENV:-$ROOT_DIR/.ci/venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

log() { printf '[re-check] %s\n' "$*" >&2; }

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

log "安装依赖"
"$VENV_PY" -m pip install --upgrade pip >/dev/null
"$VENV_PY" -m pip install -r "$ROOT_DIR/requirements.txt"
if [[ -f "$ROOT_DIR/requirements-test.txt" ]]; then
  "$VENV_PY" -m pip install -r "$ROOT_DIR/requirements-test.txt"
else
  "$VENV_PY" -m pip install "pytest>=8"
fi

export RE_CI_HAS_MARKETDATA="${RE_CI_HAS_MARKETDATA:-0}"
cd "$ROOT_DIR"
log "运行 pytest"
"$VENV_PY" -m pytest tests -q ${PYTEST_ARGS:-}
