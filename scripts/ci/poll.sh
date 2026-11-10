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

# 数据 view 同步挂在已有的 poll timer 上：不新增 systemd unit、不需要 root。
# 后台执行，避免阻塞代码部署；flock 防止长同步与下一轮重叠。
SYNC_SCRIPT="$ROOT_DIR/scripts/ops/sync_data_production.sh"
SYNC_LOCK="$STATE_DIR/data-sync.lock"
sync_data_bg() {
  if [[ "$DRY_RUN" == "1" ]]; then
    return 0
  fi
  [[ -x "$SYNC_SCRIPT" ]] || return 0
  (
    exec 9>&-
    if command -v flock >/dev/null 2>&1; then
      flock -n "$SYNC_LOCK" "$SYNC_SCRIPT"
    else
      "$SYNC_SCRIPT"
    fi
  ) >>"$STATE_DIR/data-sync.log" 2>&1 &
}
BACKUP_SCRIPT="$ROOT_DIR/scripts/ci/daily-backup.sh"
daily_backup_bg() {
  if [[ "$DRY_RUN" == "1" ]]; then
    return 0
  fi
  [[ -x "$BACKUP_SCRIPT" ]] || return 0
  (
    exec 9>&-
    "$BACKUP_SCRIPT"
  ) >>"$STATE_DIR/db-backup.log" 2>&1 &
}
# 每周基础备份（PITR 起点）：周日 04:00-04:59 首次轮询触发，一周只跑一次。
BASEBACKUP_SCRIPT="$ROOT_DIR/scripts/ops/pg_basebackup.sh"
weekly_backup_bg() {
  if [[ "$DRY_RUN" == "1" ]]; then
    return 0
  fi
  [[ -x "$BASEBACKUP_SCRIPT" ]] || return 0
  local week marker
  week="$(date +%G-W%V)"
  marker="$STATE_DIR/basebackup.week"
  if [[ "${WEEKLY_BASEBACKUP_FORCE:-0}" != "1" ]]; then
    [[ "$(date +%u)" == "7" && "$(date +%H)" == "04" ]] || return 0
  fi
  [[ -f "$marker" && "$(cat "$marker" 2>/dev/null || true)" == "$week" ]] && return 0
  (
    exec 9>&-
    exec 8>"$STATE_DIR/basebackup.lock"
    if ! flock -n 8; then
      log "已有基础备份在执行，跳过"
      exit 0
    fi
    if "$BASEBACKUP_SCRIPT"; then
      printf '%s\n' "$week" > "$marker"
    fi
  ) >>"$STATE_DIR/basebackup.log" 2>&1 &
}
trap 'sync_data_bg; daily_backup_bg; weekly_backup_bg' EXIT

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

# CI/CD 的完整输出落到 State 目录：systemd 的 journal 普通用户读不到，
# 失败时没有现场只能靠猜。部署与 CI 都追加写，按 8MB 简单截断。
JOB_LOG="$STATE_DIR/jobs.log"
run_job() {
  local action="$1" ref="$2" label="$3"
  log "触发 $label：webhook-job.sh $action $ref（日志：$JOB_LOG）"
  if [[ -f "$JOB_LOG" ]] && (( $(stat -c %s "$JOB_LOG" 2>/dev/null || echo 0) > 8*1024*1024 )); then
    tail -c 2M "$JOB_LOG" > "$JOB_LOG.tmp" && mv -f "$JOB_LOG.tmp" "$JOB_LOG"
  fi
  printf '\n===== %s %s %s =====\n' "$(date '+%F %T')" "$action" "$ref" >> "$JOB_LOG"
  bash "$JOB_SCRIPT" "$action" "$ref" 2>&1 | tee -a "$JOB_LOG"
  return "${PIPESTATUS[0]}"
}

# CI 与部署解耦：CI 在独立 worktree 里跑、用独立锁，并放到后台。
# 否则轮询单元要等 CI 跑完（约 4 分钟）才退出，这期间推的 tag 只能排队。
CI_LOCK="$STATE_DIR/ci.lock"
run_ci_bg() {
  local sha="$1" label="$2"
  exec 8>"$CI_LOCK"
  if ! flock -n 8; then
    exec 8>&-
    log "上一轮 CI 仍在执行，本轮不重复触发（下一轮重试）"
    return 1
  fi
  log "触发 $label（后台执行，日志：$JOB_LOG）"
  (
    exec 9>&-   # 不继承 poll 锁：CI 跑着的时候部署照样可以进行
    printf '\n===== %s ci %s =====\n' "$(date '+%F %T')" "$sha" >> "$JOB_LOG"
    if bash "$JOB_SCRIPT" ci "$BRANCH" "$sha" >> "$JOB_LOG" 2>&1; then
      printf '[poll %s] CI 通过：%s\n' "$(date '+%F %T')" "${sha:0:8}" >> "$JOB_LOG"
    else
      printf '[poll %s] CI 失败：%s（见上方输出；下轮不重试）\n' "$(date '+%F %T')" "${sha:0:8}" >> "$JOB_LOG"
    fi
  ) >/dev/null 2>&1 &
  # fd 8 由后台子进程继承并持有，父进程关掉自己的副本即可释放本次占用
  exec 8>&-
  return 0
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
  if run_ci_bg "$MASTER_SHA" "CI ${MASTER_SHA:0:8}"; then
    LAST_MASTER="$MASTER_SHA"
    RESULT="ci-queued:${MASTER_SHA:0:8}"
    log "CI 已排队：${MASTER_SHA:0:8}（不阻塞本机部署）"
  else
    # 不推进 LAST_MASTER，下一轮重试，避免这次提交的 CI 被吞掉
    RESULT="ci-busy:${MASTER_SHA:0:8}"
  fi
fi

if (( CHANGED == 0 )); then
  log "无变化（master ${MASTER_SHA:0:8}，tag ${LATEST_TAG:-none}）"
  exit 0
fi

save_state "$LAST_MASTER" "$LAST_TAG" "$RESULT"
[[ "$LAST_RESULT" == "$RESULT" ]] || log "本轮结果：$RESULT"
