#!/usr/bin/env bash
# 生产数据 view -> PG 同步。由 scripts/ci/poll.sh 每分钟以后台方式触发；
# 也支持手动执行：./scripts/ops/sync_data_production.sh --dry-run
#
# 只读数据平台 views/current，写本机 PG 服务表；默认要求生产库显式 allow。
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$ROOT_DIR"

if [[ -f deploy/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  . deploy/.env
  set +a
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  : "${POSTGRES_USER:?deploy/.env 缺少 POSTGRES_USER}"
  : "${POSTGRES_PASSWORD:?deploy/.env 缺少 POSTGRES_PASSWORD}"
  : "${POSTGRES_DB:?deploy/.env 缺少 POSTGRES_DB}"
  export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${POSTGRES_DB}"
fi
export SVQUANT_DATA_ROOT="${SVQUANT_DATA_ROOT:-/home/dev01/project/svquant-data}"

PYTHON="${PYTHON:-/home/dev01/program/anaconda3/bin/python}"
exec "$PYTHON" scripts/sync_data_view.py --allow-production --json "$@"
