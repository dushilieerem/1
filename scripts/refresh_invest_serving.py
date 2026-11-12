#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""重建手机 Invest 的 PG 服务层快照（invest_stocks）。

在 parquet/财务 ETL 之后运行；手机端不再使用 SQLite。
  /home/dev01/program/anaconda3/bin/python scripts/refresh_invest_serving.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.invest.schema import ensure_invest_schema, refresh_invest_stocks  # noqa: E402


def main() -> None:
    ensure_invest_schema()
    n = refresh_invest_stocks()
    print(f"invest_stocks refreshed: {n} rows")


if __name__ == "__main__":
    main()
