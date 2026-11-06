#!/usr/bin/env bash
# 每日 PostgreSQL 备份：挂在 poll timer 上，03:10-03:59 之间首次轮询触发一次。
# 失败不写完成标记，下一轮会重试；不阻塞部署轮询。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
STATE_DIR="${POLL_STATE_DIR:-/var/lib/svquant}"
MARKER="$STATE_DIR/db-backup.date"
LOCK="$STATE_DIR/db-backup.lock"
BACKUP_SCRIPT="${DAILY_BACKUP_SCRIPT:-$ROOT_DIR/scripts/ci/backup-db.sh}"

log() { printf '[daily-backup %s] %s\n' "$(date '+%F %T')" "$*" >&2; }

[[ -x "$BACKUP_SCRIPT" ]] || { log "缺少 $BACKUP_SCRIPT"; exit 1; }
mkdir -p "$STATE_DIR"
TODAY="$(date +%F)"
if [[ -f "$MARKER" && "$(cat "$MARKER" 2>/dev/null || true)" == "$TODAY" ]]; then
  exit 0
fi
# 只在这个低峰窗口执行，避免白天与发布/同步抢资源。
hour="$(date +%H)"; minute="$(date +%M)"
if [[ "${DAILY_BACKUP_FORCE:-0}" != "1" ]]; then
  [[ "$hour" == "03" && "$minute" -ge 10 ]] || exit 0
fi

exec 9>"$LOCK"
if ! flock -n 9; then
  log "已有备份在执行，跳过"
  exit 0
fi
log "开始每日备份"
export BACKUP_KEEP="${BACKUP_KEEP:-7}"
if ! bash "$BACKUP_SCRIPT" daily; then
  log "每日备份失败，保留标记为空，下一轮重试"
  exit 1
fi
printf '%s\n' "$TODAY" > "$MARKER"
log "每日备份完成：$TODAY"
