#!/usr/bin/env bash
# 内网轮询触发：从 Gitee 拉取 master 与 tag，发现新提交就按 webhook-job.sh 的口径执行。
#
# 为什么用轮询：公司内网没有公网入口，Gitee 的 WebHook 打不进来；服务器能出网拉 Gitee，
# 就反向由服务器定时检查，等价于"推送即触发"，只是最多延迟一个间隔（默认 60 秒）。
#
# 用法：
#   bash scripts/ci/poll.sh                 # 正常检查一次（systemd timer 调它）
#   POLL_DRY_RUN=1 bash scripts/ci/poll.sh  # 只打印将要做什么
#   POLL_TAG_PREFIX=v bash scripts/ci/poll.sh
#
# 状态文件记录「上次见到的 master / tag」，首次运行只建立基线、不触发，
# 避免装上定时器就把历史版本重新部署一遍。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
STATE_DIR="${POLL_STATE_DIR:-/var/lib/svquant}"
STATE_FILE="$STATE_DIR/poll-state.env"
LOCK_FILE="${POLL_LOCK_FILE:-$STATE_DIR/poll.lock}"
BRANCH="${POLL_BRANCH:-master}"
TAG_PREFIX="${POLL_TAG_PREFIX:-v}"
DRY_RUN="${POLL_DRY_RUN:-0}"
JOB_SCRIPT="$ROOT_DIR/scripts/ci/webhook-job.sh"

log() { printf '[poll %s] %s\n' "$(date '+%F %T')" "$*"; }

[[ -f "$JOB_SCRIPT" ]] || { log "缺少 $JOB_SCRIPT"; exit 1; }
mkdir -p "$STATE_DIR"

# 用 fd 9 持锁防止两轮重叠（systemd timer 正常不会重叠，手动执行可能）
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "上一轮仍在执行，本轮跳过"
  exit 0
fi

cd "$ROOT_DIR"
if ! git fetch --prune --tags origin >/dev/null 2>&1; then
  log "git fetch 失败，检查远端凭据与网络"
  exit 1
fi

MASTER_SHA="$(git rev-parse "origin/$BRANCH")"
LATEST_TAG="$(git tag -l "${TAG_PREFIX}*" --sort=-v:refname | head -n1)"

declare -A STATE=()
if [[ -f "$STATE_FILE" ]]; then
  while IFS='=' read -r key value; do
    [[ -n "$key" ]] && STATE["$key"]="$value"
  done < "$STATE_FILE"
fi
LAST_MASTER="${STATE[master]:-}"
LAST_TAG="${STATE[tag]:-}"
LAST_RESULT="${STATE[result]:-}"

save_state() {
  local tmp="$STATE_FILE.tmp"
  {
    printf 'master=%s\n' "$1"
    printf 'tag=%s\n' "$2"
    printf 'result=%s\n' "$3"
    printf 'updated=%s\n' "$(date '+%F %T')"
  } > "$tmp"
  mv -f "$tmp" "$STATE_FILE"
}

# 首次运行只记录基线
if [[ -z "$LAST_MASTER" ]]; then
  save_state "$MASTER_SHA" "$LATEST_TAG" "baseline"
  log "首次运行，建立基线 master=${MASTER_SHA:0:8} tag=${LATEST_TAG:-none}（不触发）"
  exit 0
fi

run_job() {
  local action="$1" ref="$2" label="$3"
  log "触发 $label：webhook-job.sh $action $ref"
  bash "$JOB_SCRIPT" "$action" "$ref"
}

# dry-run 只报告差异，不改状态
if [[ "$DRY_RUN" == "1" ]]; then
  [[ -n "$LATEST_TAG" && "$LATEST_TAG" != "$LAST_TAG" ]] && log "[dry-run] 将部署 $LATEST_TAG"
  [[ "$MASTER_SHA" != "$LAST_MASTER" ]] && log "[dry-run] 将跑 CI ${MASTER_SHA:0:8}"
  log "[dry-run] 当前基线 master=${LAST_MASTER:0:8} tag=${LAST_TAG:-none}"
  exit 0
fi

RESULT="ok"
CHANGED=0

# 先发 tag（发布优先），再跑 master 的 CI
if [[ -n "$LATEST_TAG" && "$LATEST_TAG" != "$LAST_TAG" ]]; then
  CHANGED=1
  if run_job deploy "refs/tags/$LATEST_TAG" "部署 $LATEST_TAG"; then
    LAST_TAG="$LATEST_TAG"
    log "部署完成：$LATEST_TAG"
  else
    RESULT="deploy-failed:$LATEST_TAG"
    LAST_TAG="$LATEST_TAG"
    log "部署失败：$LATEST_TAG（下轮不重试，修好后手动执行）"
  fi
fi

if [[ "$MASTER_SHA" != "$LAST_MASTER" ]]; then
  CHANGED=1
  if run_job ci "$BRANCH" "CI ${MASTER_SHA:0:8}"; then
    LAST_MASTER="$MASTER_SHA"
    log "CI 通过：${MASTER_SHA:0:8}"
  else
    RESULT="ci-failed:${MASTER_SHA:0:8}"
    LAST_MASTER="$MASTER_SHA"
    log "CI 失败：${MASTER_SHA:0:8}（下轮不重试，看日志修完再手动跑）"
  fi
fi

if (( CHANGED == 0 )); then
  log "无变化（master ${MASTER_SHA:0:8}，tag ${LATEST_TAG:-none}）"
  exit 0
fi

save_state "$LAST_MASTER" "$LAST_TAG" "$RESULT"
[[ "$LAST_RESULT" == "$RESULT" ]] || log "本轮结果：$RESULT"
