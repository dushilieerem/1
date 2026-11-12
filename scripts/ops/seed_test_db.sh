#!/usr/bin/env bash
# 从生产库抽样真实数据灌进测试库，让 E2E 能覆盖「有数据」路径。
#
# 背景：svquant_test 长期只有测试夹具（0 条公告、8 万条 K 线），
# H5/机构端的 E2E 只能验证空态，真实数据下的展示问题跑不出来。
#
# 用法（在数据库容器所在机器执行）：
#   bash scripts/ops/seed_test_db.sh                 # 默认 120 天，源 svquant → 目标 svquant_test
#   bash scripts/ops/seed_test_db.sh --days 60
#   bash scripts/ops/seed_test_db.sh --dry-run       # 只打印将要灌入的行数
#
# 安全：
#   - 目标库名必须含 _test / _e2e / _ci，拒绝写生产；
#   - 只灌行情与内容类表，不动 users / 业务写入表；
#   - 目标表先 TRUNCATE 再灌，重复执行结果一致。
set -Eeuo pipefail

CONTAINER="${DB_CONTAINER:-svquant-db-1}"
DB_USER="${POSTGRES_USER:-svquant}"
SOURCE_DB="${SOURCE_DB:-svquant}"
TARGET_DB="${TARGET_DB:-svquant_test}"
DAYS="${SEED_DAYS:-120}"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --days) DAYS="$2"; shift 2 ;;
    --source) SOURCE_DB="$2"; shift 2 ;;
    --target) TARGET_DB="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

log() { printf '[seed-test-db] %s\n' "$*" >&2; }
psql_src() { docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$SOURCE_DB" -v ON_ERROR_STOP=1 "$@"; }
psql_tgt() { docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$TARGET_DB" -v ON_ERROR_STOP=1 "$@"; }

case "$TARGET_DB" in
  *_test|*_test_*|*_e2e*|*_ci*) ;;
  *) log "拒绝写入非测试库：$TARGET_DB"; exit 2 ;;
esac
[[ "$TARGET_DB" != "$SOURCE_DB" ]] || { log "源库与目标库相同"; exit 2; }

# 表名|过滤条件（不带 WHERE）。空条件表示全量。
TABLES=(
  "public.md_daily_bar|trade_date >= CURRENT_DATE - ${DAYS}"
  "public.md_valuation_daily|trade_date >= CURRENT_DATE - ${DAYS}"
  "public.md_fund_flow_daily|trade_date >= CURRENT_DATE - 30"
  "public.md_index_bar|trade_date >= CURRENT_DATE - 365"
  "public.md_us_stock_snapshot|"
  "public.doc_item|publish_at >= now() - interval '180 days'"
  "public.news_items|created_at >= now() - interval '90 days'"
  "public.fin_dividend|"
  "public.fin_share_capital|"
  "svquant.md_company_profile|"
)

copy_table() {
  local table="$1" where="$2" sql
  if [[ -n "$where" ]]; then
    sql="SELECT * FROM ${table} WHERE ${where}"
  else
    sql="SELECT * FROM ${table}"
  fi
  if ((DRY_RUN)); then
    local n
    n="$(psql_src -t -c "SELECT count(*) FROM (${sql}) t;" | tr -d '[:space:]')"
    log "  ${table}: ${n} 行"
    return 0
  fi
  docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$SOURCE_DB" -c "\copy (${sql}) TO STDOUT" \
    | docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$TARGET_DB" -v ON_ERROR_STOP=1 \
        -c "\copy ${table} FROM STDIN"
}

log "源 ${SOURCE_DB} → 目标 ${TARGET_DB}，行情窗口 ${DAYS} 天$([[ $DRY_RUN == 1 ]] && echo '（dry-run）')"

if ((DRY_RUN == 0)); then
  truncate_list=""
  for entry in "${TABLES[@]}"; do
    truncate_list="${truncate_list:+$truncate_list, }${entry%%|*}"
  done
  log "清空目标表：$truncate_list"
  psql_tgt -c "TRUNCATE TABLE ${truncate_list};" >/dev/null
fi

for entry in "${TABLES[@]}"; do
  table="${entry%%|*}"
  where="${entry#*|}"
  log "灌入 ${table}"
  copy_table "$table" "$where"
done

if ((DRY_RUN == 0)); then
  log "更新统计信息"
  psql_tgt -c "ANALYZE;" >/dev/null
  log "完成。目标库大小：$(psql_tgt -t -c "SELECT pg_size_pretty(pg_database_size(current_database()));" | tr -d '[:space:]')"
fi
