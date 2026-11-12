#!/usr/bin/env bash
# PR 门禁：在待合并分支的 head 上跑 P0 E2E，不碰生产、不动主检出。
#
# 用途：合并前对 PR 分支做一次真实链路验证，替代「各自本机跑一遍再说」。
# 现在不自动发 Gitee 评论（需要额外授权），结果打在 stdout / 调用方日志里。
#
# 用法（仓库根目录）：
#   bash scripts/ci/pr-gate.sh dev-zmy              # 分支
#   bash scripts/ci/pr-gate.sh origin/dev-zmy       # 远端分支
#   bash scripts/ci/pr-gate.sh <sha> h5             # 指定 sha，只跑 H5
#   PR_GATE_DB=postgresql://... bash scripts/ci/pr-gate.sh dev-zmy
#
# 说明：
#   - 在临时 worktree（默认 /tmp/svquant-pr-gate）里检出目标 ref，跑完删除；
#   - 复用主检出的 .ci venv / frontend node_modules / backend/.env；
#   - 同一时间只允许一个 PR 门禁（flock），避免抢端口和测试库；
#   - 默认跑 p0，约 1 分钟；`all|h5|inst` 与 e2e.sh 一致。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
REF="${1:?用法: pr-gate.sh <branch|sha> [all|h5|inst]}"
SUITE="${2:-all}"
WORKTREE="${PR_GATE_WORKTREE:-/tmp/svquant-pr-gate}"
LOCK="${PR_GATE_LOCK:-/tmp/svquant-pr-gate.lock}"
# 不内置任何连接串：由调用方通过 PR_GATE_DB 或 DATABASE_URL 提供（必须指向 *_test/_dev/_e2e 库）
DB_URL="${PR_GATE_DB:-${DATABASE_URL:-}}"

log() { printf '[pr-gate] %s\n' "$*" >&2; }

if [[ -z "$DB_URL" ]]; then
  log "缺少 PR_GATE_DB 或 DATABASE_URL（指向 *_test/_dev/_e2e 库）"
  exit 2
fi
case "$DB_URL" in
  *_test*|*_dev*|*_e2e*|*_ci*) ;;
  *) log "拒绝在非测试库上跑门禁"; exit 2 ;;
esac

exec 9>"$LOCK"
if ! flock -n 9; then
  log "已有 PR 门禁在执行，本次跳过"
  exit 3
fi

cd "$ROOT_DIR"
log "拉取远端"
git fetch --prune --tags origin >/dev/null 2>&1 || true

# 解析 ref：分支名优先取 origin/<ref>，其次当 sha 用
TARGET="$REF"
if git rev-parse --verify --quiet "origin/${REF}^{commit}" >/dev/null; then
  TARGET="origin/${REF}"
fi
git rev-parse --verify --quiet "${TARGET}^{commit}" >/dev/null || { log "找不到 ref：$REF"; exit 2; }
SHA="$(git rev-parse --short "${TARGET}^{commit}")"
log "目标 ${TARGET} @ ${SHA}"

cleanup() {
  git -C "$ROOT_DIR" worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
  rm -rf "$WORKTREE" 2>/dev/null || true
}
trap cleanup EXIT

git worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
rm -rf "$WORKTREE"
git worktree add --force --detach "$WORKTREE" "${TARGET}^{commit}" >/dev/null
log "已检出到 $WORKTREE"

# 复用依赖，避免每次 npm ci / pip 重装
ln -sfn "$ROOT_DIR/.ci" "$WORKTREE/.ci"
[ -d "$ROOT_DIR/frontend/node_modules" ] && ln -sfn "$ROOT_DIR/frontend/node_modules" "$WORKTREE/frontend/node_modules"
[ -f "$ROOT_DIR/backend/.env" ] && ln -sfn "$ROOT_DIR/backend/.env" "$WORKTREE/backend/.env"
[ -d "$ROOT_DIR/tests/e2e/node_modules" ] && ln -sfn "$ROOT_DIR/tests/e2e/node_modules" "$WORKTREE/tests/e2e/node_modules"

log "跑 P0 E2E（suite=${SUITE}）"
set +e
DATABASE_URL="$DB_URL" \
YG_RE_BASE="${YG_RE_BASE:-http://127.0.0.1:9527}" \
PYTHON="${PYTHON:-$ROOT_DIR/.ci/venv/bin/python}" \
  bash "$WORKTREE/scripts/ci/e2e.sh" p0 "$SUITE"
rc=$?
set -e

if (( rc == 0 )); then
  log "通过：${REF} @ ${SHA}"
else
  log "失败：${REF} @ ${SHA}（rc=${rc}）"
fi
exit "$rc"
