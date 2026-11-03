#!/usr/bin/env bash
# 创建/重建隔离测试库 svquant_test，并灌入当前 view 的最近数据。
# 仅用于开发/测试；生产库 svquant 会被拒绝。
#
# 用法：
#   ./scripts/ops/setup_test_db.sh              # 最近 3 天
#   ./scripts/ops/setup_test_db.sh --full       # 2016 起全量（H5 图表/回测需要）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -f backend/.env ]]; then
  echo "缺少 backend/.env（需要 DATABASE_URL）" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
. backend/.env
set +a

BASE_URL="${DATABASE_URL:?backend/.env 缺少 DATABASE_URL}"
DB_NAME="${BASE_URL##*/}"
case "$DB_NAME" in
  svquant_dev|*_dev|*_test|*_e2e) ;;
  *)
    echo "拒绝：DATABASE_URL 指向 $DB_NAME，只允许 *_dev/*_test/*_e2e" >&2
    exit 1
    ;;
esac

ADMIN_URL="${BASE_URL%/*}/postgres"
TEST_URL="${BASE_URL%/*}/svquant_test"
PYTHON="${PYTHON:-$ROOT/.ci/venv/bin/python}"

echo "[setup_test_db] 创建/确认 svquant_test"
"$PYTHON" - "$ADMIN_URL" <<'PY'
import sys
import psycopg

url = sys.argv[1]
with psycopg.connect(url, autocommit=True) as conn:
    exists = conn.execute("SELECT 1 FROM pg_database WHERE datname='svquant_test'").fetchone()
    if not exists:
        conn.execute("CREATE DATABASE svquant_test OWNER svquant")
        print("created svquant_test")
    else:
        print("svquant_test already exists")
PY

echo "[setup_test_db] 初始化 app schema / demo 账号"
DATABASE_URL="$TEST_URL" PYTHONPATH=backend "$PYTHON" - <<'PY'
from app.bootstrap import bootstrap_schemas
bootstrap_schemas()
PY

echo "[setup_test_db] 同步当前 view"
if [[ "${1:-}" == "--full" ]]; then
  DATABASE_URL="$TEST_URL" "$PYTHON" scripts/sync_data_view.py --full --json
else
  DATABASE_URL="$TEST_URL" "$PYTHON" scripts/sync_data_view.py --from 2026-10-31 --json
fi

echo "[setup_test_db] 完成：DATABASE_URL 指向 svquant_test 后即可跑 e2e"
