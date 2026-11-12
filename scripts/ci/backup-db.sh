#!/usr/bin/env bash
# PostgreSQL 逻辑备份：deploy/backups/svquant-<tag>-<时间戳>.sql.gz
# 用法：bash scripts/ci/backup-db.sh [标签]
# 保留最近 BACKUP_KEEP（默认 2）份；db 容器没在跑时跳过（首次发布）。
# 可选 BACKUP_REMOTE=user@host:/path：备份校验后 rsync 到异地；失败会终止发布。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
COMPOSE_FILE="$ROOT_DIR/deploy/compose.yml"
ENV_FILE="$ROOT_DIR/deploy/.env"
BACKUP_DIR="$ROOT_DIR/deploy/backups"
KEEP="${BACKUP_KEEP:-2}"
REMOTE="${BACKUP_REMOTE:-}"
LABEL="${1:-manual}"

log() { printf '[backup-db] %s\n' "$*" >&2; }

[[ -f "$ENV_FILE" ]] || { log "缺少 deploy/.env"; exit 1; }

val() { sed -n "s/^$1=//p" "$ENV_FILE" | head -n1; }
PG_USER="$(val POSTGRES_USER)"; PG_USER="${PG_USER:-svquant}"
PG_DB="$(val POSTGRES_DB)"; PG_DB="${PG_DB:-svquant}"

if [[ -z "$(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps -q db 2>/dev/null)" ]]; then
  log "db 容器未运行，跳过备份"
  exit 0
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/svquant-${LABEL}-${STAMP}.sql.gz"
# 中止时删除半截文件，避免把未完成的 gz 留在备份目录里。
trap 'rm -f -- "$OUT"' ERR

log "导出 $PG_DB → $OUT"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T db \
  pg_dump -U "$PG_USER" -d "$PG_DB" --no-owner --no-privileges | gzip > "$OUT"

if ! gzip -t "$OUT"; then
  log "备份校验失败（gzip -t）：$OUT"
  exit 1
fi

SIZE="$(du -h "$OUT" | cut -f1)"
log "完成并校验：$OUT（$SIZE）"

if [[ -n "$REMOTE" ]]; then
  command -v rsync >/dev/null 2>&1 || {
    log "BACKUP_REMOTE 已配置，但找不到 rsync"
    exit 1
  }
  log "复制到异地：$REMOTE"
  rsync -a -- "$OUT" "$REMOTE/" || {
    log "异地备份失败：$REMOTE"
    exit 1
  }
  log "异地备份完成：$REMOTE/$(basename "$OUT")"
fi

# 只保留最近 KEEP 份，按文件名时间戳排序
ls -1t "$BACKUP_DIR"/svquant-*.sql.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
  log "清理旧备份：$(basename "$old")"
  rm -f -- "$old"
done
