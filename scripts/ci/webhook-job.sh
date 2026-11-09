#!/usr/bin/env bash
# WebHook 任务执行器：由 deploy/webhook/server.py 在持有 flock 的情况下调用。
# 用法：bash scripts/ci/webhook-job.sh <ci|deploy> <ref> [sha]
#   ci      拉取 master 最新提交，跑后端 + 前端门禁
#   deploy  切到指定 tag，走 deploy.sh（备份 → 构建 → 部署 → 冒烟 → 回滚）
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
ACTION="${1:?用法: webhook-job.sh <ci|deploy> <ref> [sha]}"
REF="${2:?缺少 ref}"
SHA="${3:-}"
BRANCH="${WEBHOOK_BRANCH:-master}"

log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*"; }

cd "$ROOT_DIR"

# 服务器上的检出目录必须是干净可拉取的；残留改动直接报错而不是静默覆盖
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  log "错误：工作区有未提交改动，拒绝自动更新"
  git status --short
  exit 2
fi

log "拉取远端 refs"
git fetch --prune --tags origin

case "$ACTION" in
  ci)
    # CI 在独立 worktree 里跑：主检出留给部署，两者互不抢工作区。
    CI_WORKTREE="${CI_WORKTREE:-$ROOT_DIR/../svquant-ci-wt}"
    log "CI：独立检出 $CI_WORKTREE @ origin/$BRANCH ${SHA:+(${SHA:0:8})}"
    git worktree prune
    if [[ -d "$CI_WORKTREE" ]]; then
      if ! git -C "$CI_WORKTREE" checkout -f --detach "origin/$BRANCH"; then
        log "工作区异常，重建 worktree"
        rm -rf "$CI_WORKTREE"
        git worktree prune
        git worktree add --force --detach "$CI_WORKTREE" "origin/$BRANCH"
      fi
    else
      git worktree add --force --detach "$CI_WORKTREE" "origin/$BRANCH"
    fi
    # 复用主检出的依赖，避免每轮 npm ci / pip 重装
    mkdir -p "$CI_WORKTREE/frontend"
    ln -sfn "$ROOT_DIR/frontend/node_modules" "$CI_WORKTREE/frontend/node_modules"
    ln -sfn "$ROOT_DIR/.ci" "$CI_WORKTREE/.ci"
    bash "$CI_WORKTREE/scripts/ci/backend-check.sh"
    bash "$CI_WORKTREE/scripts/ci/frontend-check.sh"
    log "CI 通过"
    ;;
  deploy)
    TAG="${REF#refs/tags/}"
    [[ "$TAG" != "$REF" ]] || { log "错误：deploy 只接受 tag，收到 $REF"; exit 2; }
    log "部署：检出 tag $TAG"
    git checkout -f "refs/tags/$TAG"
    bash "$ROOT_DIR/scripts/ci/deploy.sh" "$TAG"
    log "部署完成：$TAG"
    ;;
  *)
    log "错误：未知动作 $ACTION"
    exit 2
    ;;
esac
