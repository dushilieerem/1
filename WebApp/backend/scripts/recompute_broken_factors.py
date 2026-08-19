# -*- coding: utf-8 -*-
"""重算面板里失败/有问题的因子（修代码后用）。

默认重算名单：cvar_5 / macd_cross / stoch_rsi / gap / volume_price_corr / max_drawdown_20d
（ep / cp_ttm / dividend_yield 等缺字段的标「数据不可用」，不编造、不重算指标）
以及库中仍有 error、或成功但 q1 为空的行对应因子。

用法:
  conda activate SVQuant
  cd /d E:\\quant-lab\\SVQuant\\backend
  python scripts/recompute_broken_factors.py
  python scripts/recompute_broken_factors.py --names ep,gap
  python scripts/recompute_broken_factors.py --combo CSI300:1y
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.daily_dashboard_refresh import MATRIX_24, log  # noqa: E402
from services.factor import dashboard_store as ds  # noqa: E402

# 已修代码、需强制重算的因子（不含数据不可用项）
FIXED_NAMES = [
    "cvar_5",
    "macd_cross",
    "stoch_rsi",
    "gap",
    "volume_price_corr",
    "max_drawdown_20d",
]


def names_from_db() -> list[str]:
    conn = sqlite3.connect(ds.DB_PATH)
    rows = conn.execute(
        """
        SELECT DISTINCT factor_name
        FROM factor_dashboard_metrics
        WHERE (error IS NOT NULL AND error != '')
           OR ((error IS NULL OR error = '') AND q1_return IS NULL)
        ORDER BY 1
        """
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", type=str, default="", help="逗号分隔因子名；空则 FIXED+库内异常")
    ap.add_argument("--combo", type=str, default="", help="如 CSI300:1y；空则全 MATRIX_24")
    args = ap.parse_args()

    if args.names.strip():
        names = [x.strip() for x in args.names.split(",") if x.strip()]
    else:
        names = sorted(set(FIXED_NAMES) | set(names_from_db()))
        # 跳过自定义样例
        names = [n for n in names if n != "EDIT_BEFORE"]

    if args.combo.strip():
        u, p = args.combo.strip().split(":", 1)
        jobs = [(u, p, True), (u, p, False)]
    else:
        jobs = list(MATRIX_24)

    log(f"recompute names={len(names)} {names}")
    log(f"recompute jobs={len(jobs)}")

    # monkey: run_one → _run_batch with only_names
    failed = 0
    for u, p, f in jobs:
        log(f"=== 开始 {u} / {p} / filter_up={f} only={len(names)} ===")
        ds._run_batch(
            universe=u,
            period=p,
            filter_limit_up=f,
            filter_suspended=True,
            limit=None,
            only_names=names,
        )
        job = ds.read_job()
        log(
            f"=== 结束 {u}/{p}/filter_up={f} status={job.get('status')} "
            f"error={job.get('error')} ==="
        )
        if job.get("status") == "failed":
            failed += 1

    log(f"recompute done failed={failed}/{len(jobs)}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
