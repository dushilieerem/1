# -*- coding: utf-8 -*-
"""导入财务三表/指标 CSV（P1-D01）。

CSV 必需列：symbol, report_period, announce_date, statement_type
其余列进入 data JSONB（数值自动转 float）。

用法：
  cd backend
  python scripts/import_financials.py --csv /path/financials.csv --dry-run
  python scripts/import_financials.py --csv /path/financials.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.data.financial_store import (  # noqa: E402
    read_csv_records,
    upsert_records,
    validate_records,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入财务三表/指标")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--source", default="manual-csv")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    records = read_csv_records(args.csv)
    problems = validate_records(records)
    if problems:
        print("[financials] 校验失败：", file=sys.stderr)
        for p in problems[:20]:
            print(f"  - {p}", file=sys.stderr)
        return 2
    print(f"[financials] 校验通过：{len(records)} 条")
    if args.dry_run:
        print("[financials] dry-run，不写库")
        return 0
    n = upsert_records(records, source=args.source)
    print(f"[financials] 已写入 {n} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
