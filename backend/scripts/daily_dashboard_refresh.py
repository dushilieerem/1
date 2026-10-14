# -*- coding: utf-8 -*-
"""SVQuant 因子面板日更：调 YGQuant RE，结果写入 PostgreSQL。

用法:
  conda activate svquant
  cd backend
  python scripts/daily_dashboard_refresh.py                 # 默认=全量组合（见下）
  python scripts/daily_dashboard_refresh.py --matrix        # 同默认
  python scripts/daily_dashboard_refresh.py --combo CSI300:3y
  python scripts/daily_dashboard_refresh.py --limit 3

默认（DEFAULT_COMBOS）= 面板全量组合 = 2 池 × 近3月/1年/3年 × 过滤涨停开/关 = 12 组。
股票池只含 RE 实际支持的 CSI300 / CSI500：RE 对其它池直接 422
（报「可用: ['ALL_A','A_SHARE','CSI300','CSI500','CSI_ALL']」），全市场池不纳入日更。

指标缓存写入 SVQuant PostgreSQL 的 factor_dashboard_metrics 表。
单因子实测约 6s(3m)/9s(1y)/10s(3y)，331 个因子单组约 0.5–1 小时，
12 组预计 10–12 小时（CSI500 成分更多、更慢），必须后台/定时跑。
整批持有跨进程刷新锁：上一轮未结束则本轮跳过并告警，不会两批并发。
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.factor import dashboard_store as ds  # noqa: E402
from services.factor.dashboard_store import (  # noqa: E402
    PANEL_COMBOS,
    PANEL_PERIODS,
    PANEL_UNIVERSES,
)

LOG_DIR = ROOT / "output" / "factor_dashboard"
LOG_PATH = LOG_DIR / "daily_refresh.log"

# 组合定义在服务层（进程内定时器与脚本共用同一份）
MATRIX_FULL: list[tuple[str, str, bool]] = list(PANEL_COMBOS)

# 兼容旧名：池数收敛后 24/16 已不是真实组数，统一指向当前全量矩阵。
# 保留是为了不让既有运维脚本静默失效（调用处会打弃用日志）。
MATRIX_24: list[tuple[str, str, bool]] = list(MATRIX_FULL)
MATRIX_16: list[tuple[str, str, bool]] = list(MATRIX_FULL)

# 日更默认 = 全量组合：面板所有股票池 × 周期 × 过滤口径都有数
DEFAULT_COMBOS: list[tuple[str, str, bool]] = list(MATRIX_FULL)
# 仅「过滤涨停开」（临时缩量/排查用）
ALL_COMBOS = [
    (u, p)
    for u in PANEL_UNIVERSES
    for p in PANEL_PERIODS
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
        "--matrix",
        action="store_true",
        help="面板全量组合：2 池 × 3 周期 × 过滤开/关 = 12 组（等同默认）",
    )
    ap.add_argument(
        "--matrix-24",
        action="store_true",
        help="[已弃用] 旧口径，现等同 --matrix",
    )
    ap.add_argument(
        "--matrix-16",
        action="store_true",
        help="[已弃用] 旧口径，现等同 --matrix",
    )
    ap.add_argument(
        "--all-default",
        action="store_true",
        help="2 池 × 3 周期（仅过滤涨停开）",
    )
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
    if args.matrix or args.matrix_24 or args.matrix_16:
        if args.matrix_24 or args.matrix_16:
            log("注意：--matrix-24/--matrix-16 已弃用（RE 只支持 CSI300/CSI500），按全量矩阵执行")
        jobs = list(MATRIX_FULL)
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
        # 默认：面板全量组合（--no-filter-up 只影响 --combo / --universe 模式）
        jobs = list(DEFAULT_COMBOS)

    log(f"日更启动 jobs={len(jobs)} limit={args.limit} skip_ok={args.skip_ok} level={args.analysis_level}")
    for i, (u, p, f) in enumerate(jobs, 1):
        log(f"  [{i}/{len(jobs)}] {u} {p} filter_up={f}")
    log("指标缓存 → PostgreSQL.factor_dashboard_metrics")

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
            if "刷新锁" in str(job.get("error") or ""):
                log(
                    "中止：另一轮面板回测正在运行（未抢到刷新锁）。本批不再继续，"
                    "避免两批并发压 RE 并交叉写同表；请确认上一轮是否卡住。"
                )
                break

    log(f"全部完成 failed_combos={failed}/{len(jobs)}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
