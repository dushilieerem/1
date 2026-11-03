#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把数据平台 views/current 同步到 PG 服务层。

默认读取数据平台当前 view，和 `data_sync_state` 比对：
- 同一 view 且无新数据：直接退出；
- 新 view：增量 upsert md_* / ref_*，刷新 invest_stocks / invest_meta；
- 失败回滚并保留旧数据，返回非 0。

用法：
  python scripts/sync_data_view.py --dry-run
  python scripts/sync_data_view.py
  python scripts/sync_data_view.py --full --with-financials
  python scripts/sync_data_view.py --view research-rv-20261103-23 --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.data.view_sync import sync_view  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--view", default="current", help="current 或显式 view id")
    parser.add_argument("--data-root", default=None, help="数据平台根目录，默认 SVQUANT_DATA_ROOT")
    parser.add_argument("--dry-run", action="store_true", help="只计算计划，不写库")
    parser.add_argument("--full", action="store_true", help="从 2016-01-01 全量重载")
    parser.add_argument("--force", action="store_true", help="同一 view 也重跑")
    parser.add_argument("--from", dest="from_date", default=None, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--with-financials", action="store_true", help="同时重载财务四表")
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="允许写生产库 svquant；默认只允许 *_dev/*_test/*_e2e",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    from_date = date.fromisoformat(args.from_date) if args.from_date else None
    try:
        result = sync_view(
            args.view,
            data_root=args.data_root,
            dry_run=args.dry_run,
            full=args.full,
            force=args.force,
            from_date=from_date,
            with_financials=args.with_financials,
            allow_production=args.allow_production,
        )
    except Exception as exc:
        print(f"sync failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, default=str))
    else:
        print(
            f"{result.get('status')}: view={result.get('view_id')} "
            f"data_date={result.get('data_date')} start={result.get('start')} end={result.get('end')}"
        )
        if result.get("rows"):
            print("rows:", json.dumps(result["rows"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
