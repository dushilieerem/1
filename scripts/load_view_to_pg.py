#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""M01：把数据平台视图加载到 PG 服务表。

用法：
  python scripts/load_view_to_pg.py --financials
  python scripts/load_view_to_pg.py --valuation-start 2026-01-01
  python scripts/load_view_to_pg.py --all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.data import view_loader  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--financials", action="store_true", help="加载全市场财务到 financials")
    parser.add_argument("--valuation-start", default=None)
    parser.add_argument("--valuation-end", default=None)
    parser.add_argument("--all", action="store_true", help="财务 + 估值（估值默认全量）")
    args = parser.parse_args()
    if args.all or args.financials:
        counts = view_loader.load_financials()
        print(f"financials rows: {counts}")
    if args.all or args.valuation_start or args.valuation_end:
        n = view_loader.load_valuations(args.valuation_start, args.valuation_end)
        print(f"valuation rows: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
