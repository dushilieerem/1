#!/usr/bin/env bash
set -Eeuo pipefail

# 刷新手机端读取缓存：财务/公告 → SQLite。
# parquet 全量同步很重，默认不跑；release 更新后手动加 --with-parquet。
#
# 用法：
#   ./scripts/refresh_invest_data.sh
#   ./scripts/refresh_invest_data.sh --with-parquet
#   ./scripts/refresh_invest_data.sh --symbols 600519,000858,300750,600036,000333

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
PY_BASE="${SVQUANT_DATA_PYTHON:-/home/dev01/program/anaconda3/bin/python}"
DB="${INVEST_DB:-$ROOT_DIR/invest-api/data/invest.dev.db}"
SYMBOLS="${SVQUANT_FIN_SYMBOLS:-600519,000858,300750,600036,000333,601318,000651,002415}"
LIMIT_SYMBOLS="${SVQUANT_INVEST_LIMIT_SYMBOLS:-500}"
WITH_PARQUET=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-parquet) WITH_PARQUET=1; shift ;;
    --symbols) SYMBOLS="$2"; shift 2 ;;
    --db) DB="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,12p' "$0"
      exit 0
      ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

cd "$ROOT_DIR"

if [[ "$WITH_PARQUET" == "1" ]]; then
  echo "[1/4] parquet → PostgreSQL（全量重载，可能需要数十分钟）"
  "$PY_BASE" scripts/etl_marketdata.py --from 2016-01-01
else
  echo "[1/4] 跳过 parquet（--with-parquet 开启）"
fi

echo "[2/4] 东方财富财务三表 + 公告"
"$PY_BASE" scripts/fetch_financials.py --symbols "$SYMBOLS"

echo "[3/4] 东方财富估值快照（总股本 / 总市值）"
"$PY_BASE" scripts/fetch_valuation_snapshot.py --symbols "$SYMBOLS"

echo "[4/4] PostgreSQL → SQLite（$DB）"
mkdir -p "$(dirname "$DB")"
if [[ ! -f "$DB" ]]; then
  echo "目标 SQLite 不存在；先运行 invest-api/seed.py --force 建库"
  exit 1
fi
"$PY_BASE" scripts/sync_invest_sqlite.py --db "$DB" --limit-symbols "$LIMIT_SYMBOLS"

echo "完成。重启 invest-api 或等待下次请求即可读到新缓存。"
