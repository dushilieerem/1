#!/usr/bin/env bash
set -Eeuo pipefail

# PostgreSQL 备份（P1-O04 首版）：custom format + gzip，保留 N 天。
# 依赖 pg_dump；未安装时脚本会明确退出，不静默跳过。
# 用法：
#   ./scripts/backup_pg.sh
#   BACKUP_DIR=/data/backups RETENTION_DAYS=14 ./scripts/backup_pg.sh

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_FILE="${SVQUANT_ENV_FILE:-$ROOT_DIR/backend/.env}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/deploy/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

[[ -f "$ENV_FILE" ]] || { echo "缺少 $ENV_FILE" >&2; exit 1; }
DB_URL="$(sed -n 's/^DATABASE_URL=//p' "$ENV_FILE" | head -n1 | tr -d '\r' | sed 's/^"//;s/"$//')"
[[ -n "$DB_URL" ]] || { echo "$ENV_FILE 缺少 DATABASE_URL" >&2; exit 1; }
command -v pg_dump >/dev/null 2>&1 || {
  echo "未找到 pg_dump；请安装 PostgreSQL 客户端或把 pg_dump 加入 PATH。" >&2
  exit 1
}

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/svquant-$STAMP.dump.gz"
TMP="$BACKUP_DIR/.svquant-$STAMP.dump"

echo "[backup] $DB_URL -> $OUT"
pg_dump --dbname="$DB_URL" --format=custom --no-owner --no-privileges --file="$TMP"
gzip -c "$TMP" > "$OUT"
rm -f "$TMP"
find "$BACKUP_DIR" -name 'svquant-*.dump.gz' -type f -mtime +"$RETENTION_DAYS" -delete
printf '%s\n' "$(date -Iseconds) $OUT $(du -h "$OUT" | cut -f1)" >> "$BACKUP_DIR/backup.log"
echo "[backup] done: $OUT"
echo "[backup] 恢复演练：gunzip -c $OUT | pg_restore --dbname \"\$DATABASE_URL\" --clean --if-exists"
