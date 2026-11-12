#!/usr/bin/env bash
# 备份恢复演练：把最新备份恢复进临时库，校验行数后自动清理。
# 支持 CD 的 SQL.gz（pg_dump | gzip）和历史 custom dump.gz（pg_restore）。
# 不改动生产库；临时库名带时间戳，演练结束（成功或失败）都会 DROP。
#
# 用法：
#   bash scripts/ops/backup_restore_drill.sh
#   BACKUP_FILE=/path/to/svquant-*.sql.gz bash scripts/ops/backup_restore_drill.sh
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
ENV_FILE="${SVQUANT_ENV_FILE:-$ROOT_DIR/backend/.env}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/deploy/backups}"
BACKUP_FILE="${BACKUP_FILE:-$(ls -1t "$BACKUP_DIR"/svquant-*.sql.gz "$BACKUP_DIR"/svquant-*.dump.gz 2>/dev/null | head -n1 || true)}"
DRILL_DB="${DRILL_DB:-svquant_restore_drill_$(date +%s)}"

log() { printf '[restore-drill] %s\n' "$*" >&2; }

[[ -f "$ENV_FILE" ]] || { log "缺少 $ENV_FILE"; exit 1; }
[[ -n "${BACKUP_FILE:-}" && -f "$BACKUP_FILE" ]] || { log "找不到备份文件（先跑 scripts/ci/backup-db.sh 或 scripts/backup_pg.sh）"; exit 1; }

case "$BACKUP_FILE" in
  *.sql.gz) MODE=sql; COMPRESSED=1 ;;
  *.sql) MODE=sql; COMPRESSED=0 ;;
  *.dump.gz) MODE=custom; COMPRESSED=1 ;;
  *.dump) MODE=custom; COMPRESSED=0 ;;
  *) log "不支持的备份格式：$BACKUP_FILE（仅支持 .sql/.sql.gz/.dump/.dump.gz）"; exit 1 ;;
esac

for bin in createdb dropdb psql; do
  command -v "$bin" >/dev/null 2>&1 || { log "缺少 $bin"; exit 1; }
done
[[ "$COMPRESSED" == "1" ]] && { command -v gunzip >/dev/null 2>&1 || { log "缺少 gunzip"; exit 1; }; }
[[ "$MODE" == "custom" ]] && { command -v pg_restore >/dev/null 2>&1 || { log "缺少 pg_restore"; exit 1; }; }

DB_URL="$(sed -n 's/^DATABASE_URL=//p' "$ENV_FILE" | head -n1 | tr -d '\r' | sed 's/^"//;s/"$//')"
[[ -n "$DB_URL" ]] || { log "$ENV_FILE 缺少 DATABASE_URL"; exit 1; }

# 从 DATABASE_URL 解析基础连接串（去掉库名，用于 createdb/dropdb）
BASE_URL="${DB_URL%/*}/postgres"

cleanup() {
  dropdb --if-exists --maintenance-db="$BASE_URL" "$DRILL_DB" >/dev/null 2>&1 || true
}
trap cleanup EXIT

createdb --maintenance-db="$BASE_URL" "$DRILL_DB"
DRILL_URL="${BASE_URL%/*}/$DRILL_DB"

if [[ "$MODE" == "custom" ]]; then
  TMP_DUMP="$(mktemp)"
  trap 'rm -f "$TMP_DUMP"; cleanup' EXIT
  if [[ "$COMPRESSED" == "1" ]]; then gunzip -c "$BACKUP_FILE" > "$TMP_DUMP"; else cp "$BACKUP_FILE" "$TMP_DUMP"; fi
  pg_restore --dbname="$DRILL_URL" --no-owner --no-privileges "$TMP_DUMP"
  rm -f "$TMP_DUMP"
  trap cleanup EXIT
else
  # CD 备份是纯 SQL：直接灌入临时库，ON_ERROR_STOP 保证不静默跳过错误。
  if [[ "$COMPRESSED" == "1" ]]; then
    gunzip -c "$BACKUP_FILE" | psql "$DRILL_URL" -v ON_ERROR_STOP=1 -q
  else
    psql "$DRILL_URL" -v ON_ERROR_STOP=1 -q -f "$BACKUP_FILE"
  fi
fi

log "恢复完成，校验关键表行数"
while IFS='|' read -r table count; do
  log "  $table = $count"
  [[ "${count:-0}" -gt 0 ]] || { log "表 $table 为空，恢复不完整"; exit 3; }
done < <(psql "$DRILL_URL" -Atc "SELECT 'users', COUNT(*) FROM users UNION ALL SELECT 'posts', COUNT(*) FROM posts UNION ALL SELECT 'md_daily_bar', COUNT(*) FROM md_daily_bar;")
log "演练通过：$BACKUP_FILE -> $DRILL_DB（已清理）"
