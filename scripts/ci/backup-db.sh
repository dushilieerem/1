#!/usr/bin/env bash
# PostgreSQL 逻辑备份：deploy/backups/svquant-<tag>-<时间戳>.sql.gz
# 用法：bash scripts/ci/backup-db.sh [标签]
# 保留最近 BACKUP_KEEP（默认 5）份；db 容器没在跑时跳过（首次发布）。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
COMPOSE_FILE="$ROOT_DIR/deploy/compose.yml"
ENV_FILE="$ROOT_DIR/deploy/.env"
BACKUP_DIR="$ROOT_DIR/deploy/backups"
KEEP="${BACKUP_KEEP:-2}"
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

log "导出 $PG_DB → $OUT"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T db \
  pg_dump -U "$PG_USER" -d "$PG_DB" --no-owner --no-privileges | gzip > "$OUT"

SIZE="$(du -h "$OUT" | cut -f1)"
log "完成：$OUT（$SIZE）"

# 只保留最近 KEEP 份，按文件名时间戳排序
ls -1t "$BACKUP_DIR"/svquant-*.sql.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
  log "清理旧备份：$(basename "$old")"
  rm -f -- "$old"
done
