#!/usr/bin/env bash
# 本地快检：只跑和本次改动相关的测试，目标 30 秒内给出反馈。
#
# 用途是「改了代码、还没提 PR」时的第一道门槛，不是发布门禁：
#   - 后端：按改动文件匹配 tests/test_*.py；跨切面改动（core / migrations）退回全量
#   - 前端：tsc --noEmit；命中同名/同域的测试文件才跑
#   - H5：build（<2s）
#   - 脚本：bash -n
# 全量门禁仍然是 scripts/ci/backend-check.sh + frontend-check.sh（PR 前、合并后各一次）。
#
# 用法（仓库根目录）：
#   bash scripts/ci/quick-check.sh                 # 对比 origin/master + 未提交改动
#   bash scripts/ci/quick-check.sh HEAD~3          # 对比指定基线
#   BASE=origin/master bash scripts/ci/quick-check.sh
#
# 可选环境变量：
#   PYTHON   解释器，默认 <repo>/.ci/venv/bin/python
#   PYTEST_ARGS  追加参数
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
BASE="${1:-${BASE:-origin/master}}"
PYTHON="${PYTHON:-$ROOT_DIR/.ci/venv/bin/python}"

# backend/.env 里可能有真实 LLM 配置，个别用例会走网络并挂起十几分钟。
# 与 CI 口径一致默认置空；要联调真实模型时显式传 LLM_API_KEY / LLM_BASE_URL。
export LLM_API_KEY="${LLM_API_KEY-}"
export LLM_BASE_URL="${LLM_BASE_URL-}"

log() { printf '[quick-check] %s\n' "$*" >&2; }

cd "$ROOT_DIR"

if ! git rev-parse --verify --quiet "$BASE" >/dev/null; then
  log "基线 $BASE 不存在；先 git fetch origin"
  exit 2
fi

MERGE_BASE="$(git merge-base HEAD "$BASE" 2>/dev/null || echo "$BASE")"
CHANGED="$(
  {
    git diff --name-only "$MERGE_BASE" HEAD
    git status --porcelain --untracked-files=all | sed 's/^...//'
  } | sed '/^$/d' | sort -u
)"

if [[ -z "$CHANGED" ]]; then
  log "相对 ${MERGE_BASE:0:8} 没有改动"
  exit 0
fi

log "相对 $(git rev-parse --short "$MERGE_BASE") 的改动：$(echo "$CHANGED" | wc -l) 个文件"

BACKEND_TESTS=()
BACKEND_FULL=0
RUN_FRONTEND_TSC=0
FRONTEND_TESTS=()
RUN_H5_BUILD=0
SHELL_FILES=()

while IFS= read -r f; do
  case "$f" in
    backend/migrations/*|backend/services/core/*)
      BACKEND_FULL=1
      ;;
    backend/tests/*.py)
      [[ -f "$f" ]] && BACKEND_TESTS+=("${f#backend/}")
      ;;
    backend/*.py)
      stem="$(basename "$f" .py)"
      area="$(echo "$f" | cut -d/ -f3)"
      matched=""
      if [[ -n "$stem" ]]; then
        matched="$(grep -lE "$stem" backend/tests/*.py 2>/dev/null || true)"
      fi
      if [[ -z "$matched" ]]; then
        case "$area" in
          institution) matched="$(ls backend/tests/test_inst_*.py 2>/dev/null || true)" ;;
          quant_factor) matched="$(ls backend/tests/test_quant*.py backend/tests/test_factor*.py 2>/dev/null || true)" ;;
          invest) matched="$(ls backend/tests/test_invest*.py 2>/dev/null || true)" ;;
          marketdata) matched="$(ls backend/tests/test_md*.py backend/tests/test_market*.py 2>/dev/null || true)" ;;
          ai) matched="$(ls backend/tests/test_ai*.py 2>/dev/null || true)" ;;
        esac
      fi
      while IFS= read -r t; do
        [[ -n "$t" ]] && BACKEND_TESTS+=("${t#backend/}")
      done <<< "$matched"
      ;;
    frontend/src/*)
      RUN_FRONTEND_TSC=1
      stem="$(basename "$f" | sed -E 's/\.(tsx?|css)$//')"
      if [[ -n "$stem" ]]; then
        while IFS= read -r t; do
          [[ -n "$t" ]] && FRONTEND_TESTS+=("${t#frontend/}")
        done <<< "$(grep -liE "$stem" frontend/tests/* 2>/dev/null || true)"
      fi
      ;;
    frontend/invest/*)
      RUN_H5_BUILD=1
      ;;
    scripts/*.sh)
      SHELL_FILES+=("$f")
      ;;
  esac
done <<< "$CHANGED"

STATUS=0

run() {
  local label="$1"; shift
  log "== $label =="
  if ! "$@"; then
    STATUS=1
    log "失败：$label"
  fi
}

if ((${#SHELL_FILES[@]})); then
  run "bash -n（${#SHELL_FILES[@]} 个脚本）" bash -n "${SHELL_FILES[@]}"
fi

if ((RUN_H5_BUILD)); then
  run "H5 build" bash -c "cd '$ROOT_DIR/frontend/invest' && npm run build --silent >/dev/null"
fi

if ((RUN_FRONTEND_TSC)); then
  run "前端 tsc" bash -c "cd '$ROOT_DIR/frontend' && ./node_modules/.bin/tsc --noEmit"
fi

if ((${#FRONTEND_TESTS[@]})); then
  mapfile -t FRONTEND_TESTS < <(printf '%s\n' "${FRONTEND_TESTS[@]}" | sort -u)
  run "前端单测（${#FRONTEND_TESTS[@]} 个文件）" bash -c \
    "cd '$ROOT_DIR/frontend' && node --import tsx --test --test-concurrency=1 ${FRONTEND_TESTS[*]}"
elif ((RUN_FRONTEND_TSC)); then
  log "未匹配到前端测试文件；tsc 已通过，PR 前仍需跑 frontend-check.sh 全量"
fi

if ((BACKEND_FULL)); then
  log "改动涉及 core/migrations，后端跑全量"
  run "后端 pytest（全量）" bash -c "cd '$ROOT_DIR/backend' && '$PYTHON' -m pytest tests -q ${PYTEST_ARGS:-}"
elif ((${#BACKEND_TESTS[@]})); then
  mapfile -t BACKEND_TESTS < <(printf '%s\n' "${BACKEND_TESTS[@]}" | sort -u)
  run "后端 pytest（${#BACKEND_TESTS[@]} 个文件）" bash -c \
    "cd '$ROOT_DIR/backend' && '$PYTHON' -m pytest ${BACKEND_TESTS[*]} -q ${PYTEST_ARGS:-}"
else
  log "未匹配到后端测试；PR 前仍需跑 backend-check.sh 全量"
fi

if ((STATUS == 0)); then
  log "快检通过"
else
  log "快检失败，先修再提 PR"
fi
exit "$STATUS"
