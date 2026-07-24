# -*- coding: utf-8 -*-
"""SVQuant 因子面板日更：调 YGQuant RE，结果写入本地 SQLite。

用法:
  conda activate SVQuant
  cd /d E:\\quant-lab\\SVQuant\\backend
  python scripts/daily_dashboard_refresh.py
  python scripts/daily_dashboard_refresh.py --combo CSI300:3y
  python scripts/daily_dashboard_refresh.py --matrix-24
  python scripts/daily_dashboard_refresh.py --matrix-16
  python scripts/daily_dashboard_refresh.py --limit 3

--matrix-24：4 池 × 近3月/近1年/近3年 × 过滤开/关 = 24 组（区间 end 默认 2026-01-01）。
--matrix-16：旧口径，仅 3m+1y（16 组）。
默认 DEFAULT_COMBOS 为轻量 CSI300×3m/1y。

库：SQLite（backend/output/factor_dashboard/metrics.sqlite），无需安装 Postgres。
每组约 83 因子，单次回测常 30–60s，16 组可能十数小时，建议后台跑。
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services import dashboard_store as ds  # noqa: E402

LOG_DIR = ROOT / "output" / "factor_dashboard"
LOG_PATH = LOG_DIR / "daily_refresh.log"

# 与同事 RE 成分表对齐（无 CSI_ALL）
PANEL_UNIVERSES = ("CSI300", "CSI500", "CSI1000", "SSE50")

# 24 组：4 指数 × 近3月/近1年/近3年 × 过滤涨停开/关（end 见 backtest_range.RE_MARKET_END）
MATRIX_24: list[tuple[str, str, bool]] = [
    (u, p, filt)
    for u in PANEL_UNIVERSES
    for p in ("3m", "1y", "3y")
    for filt in (True, False)
]

# 兼容旧名：原先 16 组不含 3y
MATRIX_16: list[tuple[str, str, bool]] = [
    (u, p, filt)
    for u in PANEL_UNIVERSES
    for p in ("3m", "1y")
    for filt in (True, False)
]

# 日常默认：轻量（约 2 组）；扩量用 --combo / --matrix-16 / --all
DEFAULT_COMBOS = [
    ("CSI300", "3m"),
    ("CSI300", "1y"),
]
ALL_COMBOS = [
    (u, p)
    for u in PANEL_UNIVERSES
    for p in ("3m", "1y", "3y")
]


def log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def wait_job(poll: float = 5.0) -> dict:
    """等后台线程写完；跳过刚启动时的 idle 竞态。"""
    saw_running = False
    idle_ticks = 0
    while True:
        job = ds.read_job()
        st = job.get("status")
        log(
            f"  [{st}] {job.get('done')}/{job.get('total')} "
            f"{job.get('current') or ''} {job.get('error') or ''}"
        )
        if st == "running":
            saw_running = True
            idle_ticks = 0
        elif st == "done":
            return job
        elif st == "failed":
            return job
        elif st == "idle":
            if saw_running:
                return job
            idle_ticks += 1
            if idle_ticks > 6:
                return job
        time.sleep(poll)


def run_one(
    universe: str,
    period: str,
    *,
    filter_limit_up: bool,
    limit: int | None,
    skip_ok: bool = False,
    analysis_level: str = "core",
) -> dict:
    log(f"=== 开始 {universe} / {period} / filter_up={filter_limit_up} limit={limit} skip_ok={skip_ok} level={analysis_level} ===")
    # 同步跑（日更脚本不依赖 api_server 线程，避免服务重启打断）
    ds._run_batch(
        universe=universe,
        period=period,
        filter_limit_up=filter_limit_up,
        filter_suspended=True,
        limit=limit,
        skip_ok=skip_ok,
        analysis_level=analysis_level,
    )
    job = ds.read_job()
    log(f"=== 结束 {universe}/{period}/filter_up={filter_limit_up} status={job.get('status')} error={job.get('error')} ===")
    return job


def main() -> None:
    ap = argparse.ArgumentParser(description="SVQuant 因子面板日更")
    ap.add_argument("--universe", default=None)
    ap.add_argument("--period", default=None)
    ap.add_argument("--combo", action="append", help="形如 CSI300:3y，可多次")
    ap.add_argument(
        "--matrix-24",
        action="store_true",
        help="4池×近3月/近1年/近3年×过滤开/关 = 24 组（end=RE 行情截止日）",
    )
    ap.add_argument(
        "--matrix-16",
        action="store_true",
        help="4池×近3月/近1年×过滤开/关 = 16 组（旧口径）",
    )
    ap.add_argument("--all-default", action="store_true", help="4 池 × 3 周期全量（仅过滤开）")
    ap.add_argument("--no-filter-up", action="store_true", help="单组/多 combo 时关闭涨停过滤")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--skip-ok",
        action="store_true",
        help="跳过已成功行（补算用；全量日更不要加）",
    )
    ap.add_argument(
        "--analysis-level",
        default="core",
        choices=("core", "full"),
        help="默认 core（面板标量足够且更快）",
    )
    args = ap.parse_args()

    # (universe, period, filter_limit_up)
    jobs: list[tuple[str, str, bool]] = []
    if args.matrix_24:
        jobs = list(MATRIX_24)
    elif args.matrix_16:
        jobs = list(MATRIX_16)
    elif args.all_default:
        filt = not args.no_filter_up
        jobs = [(u, p, filt) for u, p in ALL_COMBOS]
    elif args.combo:
        filt = not args.no_filter_up
        for c in args.combo:
            u, p = c.split(":", 1)
            jobs.append((u.strip(), p.strip(), filt))
    elif args.universe and args.period:
        jobs = [(args.universe, args.period, not args.no_filter_up)]
    else:
        filt = not args.no_filter_up
        jobs = [(u, p, filt) for u, p in DEFAULT_COMBOS]

    log(f"日更启动 jobs={len(jobs)} limit={args.limit} skip_ok={args.skip_ok} level={args.analysis_level}")
    for i, (u, p, f) in enumerate(jobs, 1):
        log(f"  [{i}/{len(jobs)}] {u} {p} filter_up={f}")
    log(f"SQLite → {ds.DB_PATH}")

    failed = 0
    for u, p, filt in jobs:
        job = run_one(
            u,
            p,
            filter_limit_up=filt,
            limit=args.limit,
            skip_ok=args.skip_ok,
            analysis_level=args.analysis_level,
        )
        if job.get("status") == "failed":
            failed += 1

    log(f"全部完成 failed_combos={failed}/{len(jobs)}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
