#!/usr/bin/env bash
# 每周基础备份（PITR 的起点）+ 清理过期 WAL/基础备份。
#
# 用法（部署机执行，建议挂在 poll timer 的周日窗口或独立 cron）：
#   bash scripts/ops/pg_basebackup.sh
#
# 保留策略：基础备份 4 份、WAL 14 天（WAL 必须覆盖最老一份基础备份之后的所有变更，
# 14 天 > 4 份周备份中的最近一份 7 天，留有余量）。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
CONTAINER="${DB_CONTAINER:-svquant-db-1}"
DB_USER="${POSTGRES_USER:-svquant}"
ARCHIVE_DIR="${WAL_ARCHIVE_HOST_DIR:-$ROOT_DIR/../svquant-wal-archive}"
KEEP_BASE="${KEEP_BASE:-4}"
KEEP_WAL_DAYS="${KEEP_WAL_DAYS:-14}"

log() { printf '[pg-basebackup] %s\n' "$*" >&2; }

[[ -d "$ARCHIVE_DIR" ]] || { log "归档目录不存在：$ARCHIVE_DIR（先跑 pg_wal_setup.sh）"; exit 1; }

STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="/backup/base/${STAMP}"

log "基础备份 → $ARCHIVE_DIR/base/${STAMP}"
sleep 1
docker exec "$CONTAINER" sh -c "mkdir -p '$TARGET'"
# 走 TCP + 容器内自带的 POSTGRES_USER/POSTGRES_PASSWORD：
# 本地 socket 是 peer 认证，docker exec 的 OS 用户与数据库角色对不上。
if ! docker exec "$CONTAINER" sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_basebackup -h 127.0.0.1 -U "$POSTGRES_USER" -D "'"$TARGET"'" -Ft -z -X stream -c fast'; then
  log "备份失败，清理半成品"
  docker exec "$CONTAINER" rm -rf "$TARGET" 2>/dev/null || true
  exit 1
fi

# 备份文件由容器内用户创建（0600），校验与清理都放回容器里做，宿主机不碰内容
if ! docker exec "$CONTAINER" gzip -t "$TARGET/base.tar.gz" 2>/dev/null; then
  log "base.tar.gz 校验失败"
  exit 1
fi
log "备份完成：$(docker exec "$CONTAINER" du -sh "$TARGET" | cut -f1)"

log "清理：基础备份保留 ${KEEP_BASE} 份"
docker exec "$CONTAINER" sh -c "ls -1dt /backup/base/*/ 2>/dev/null | tail -n +$((KEEP_BASE + 1))" \
  | while read -r old; do
      [[ -n "$old" ]] || continue
      log "  删除 $old"
      docker exec "$CONTAINER" rm -rf "$old"
    done

log "清理：WAL 保留 ${KEEP_WAL_DAYS} 天"
find "$ARCHIVE_DIR" -maxdepth 1 -type f -mtime "+${KEEP_WAL_DAYS}" -delete

log "完成。最新归档："
docker exec "$CONTAINER" sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d postgres -t -c "SELECT last_archived_wal, last_archived_time, failed_count FROM pg_stat_archiver;"' | sed '/^$/d'
