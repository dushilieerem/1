#!/usr/bin/env bash
# 准备 WAL 归档目录（宿主机侧），给 db 容器的 bind mount 用。
#
# 用法（在部署机执行，普通用户即可）：
#   bash scripts/ops/pg_wal_setup.sh
#
# 做三件事：
#   1. 创建归档目录与基础备份目录；
#   2. 放开写权限（容器内 postgres 以 uid 70 运行，宿主机上没有同名用户）；
#   3. 打印检查项。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
ARCHIVE_DIR="${WAL_ARCHIVE_HOST_DIR:-$ROOT_DIR/deploy/wal-archive}"

log() { printf '[pg-wal-setup] %s\n' "$*" >&2; }

log "归档目录：$ARCHIVE_DIR"
mkdir -p "$ARCHIVE_DIR/base"

# 容器内 postgres 是 uid 70。宿主机上不一定有该用户，直接放开写权限最简单；
# 目录本身只在部署机本地，不含敏感明文。
chmod 0777 "$ARCHIVE_DIR"
chmod 0777 "$ARCHIVE_DIR/base"

cat > "$ARCHIVE_DIR/README.txt" <<'EOF'
PostgreSQL WAL 归档目录（PITR）

- 由 deploy/compose.yml 的 db 服务挂载到容器内 /backup
- WAL 文件：本目录顶层，%f 命名（如 0000000100000000000000A1）
- 基础备份：base/<日期>/，由 scripts/ops/pg_basebackup.sh 生成
- 保留策略：WAL 14 天、基础备份 4 份（由 pg_basebackup.sh 清理）
- 恢复步骤见 docs/运维/数据库恢复与分区方案.md
EOF

log "完成。"
log "启用方式：下一次发布重建 db 容器后自动生效（compose 里已配置 archive_mode=on）。"
log "验证：docker exec svquant-db-1 psql -U svquant -c \"SELECT * FROM pg_stat_archiver;\""
