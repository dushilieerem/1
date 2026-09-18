# -*- coding: utf-8 -*-
"""补算因子面板：跳过已成功结果，只跑剩余；失败只打标不编数。

设计：
  - analysis_level=core（面板所需 IC/分层/年化等标量均在 core，比 full 快）
  - 默认纳入 qlib_alpha（~518）+ 未算过的 jq_compat（~63）
  - skip_ok：已有 ic_mean 且无 error 的行保留
  - unavailable / RE 报错：写 error，数值置空

用法（建议后台）:
  conda activate svquant
  cd backend
  python -u scripts/backfill_panel_remaining.py --matrix-24

  # 先跑默认视图（最快看到面板变多）
  python -u scripts/backfill_panel_remaining.py --combo CSI300:3y

  # 只补聚宽 / 只补 qlib
  python -u scripts/backfill_panel_remaining.py --matrix-24 --libraries jq_compat_emotion,jq_compat_risk,jq_compat_technical
  python -u scripts/backfill_panel_remaining.py --matrix-24 --libraries qlib_alpha

日志: output/factor_dashboard/remaining_backfill.log
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.daily_dashboard_refresh import MATRIX_24, MATRIX_16  # noqa: E402
from services.factor import dashboard_store as ds  # noqa: E402

LOG_DIR = ROOT / "output" / "factor_dashboard"
LOG_PATH = LOG_DIR / "remaining_backfill.log"


def log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def count_todo(
    universe: str,
    period: str,
    filter_limit_up: bool,
    *,
    include_qlib: bool,
    libraries: list[str] | None,
) -> tuple[int, int, int]:
    """返回 (catalog, already_ok, todo)。"""
    factors = ds.load_factor_index(include_qlib=include_qlib)
    if libraries:
        lib_set = set(libraries)
        factors = [f for f in factors if f.get("library") in lib_set]
    conn = ds._connect()
    ok = 0
    todo = 0
    for f in factors:
        if f.get("unavailable"):
            todo += 1  # 仍会写不可用标记（很快）
            continue
        if ds.row_is_ok(
            conn,
            factor_name=f["name"],
            universe=universe,
            period=period,
            filter_limit_up=filter_limit_up,
            filter_suspended=True,
        ):
            ok += 1
        else:
            todo += 1
    conn.close()
    return len(factors), ok, todo


def main() -> None:
    ap = argparse.ArgumentParser(description="补算因子面板剩余因子（跳过已成功）")
    ap.add_argument("--combo", action="append", help="形如 CSI300:3y，可多次")
    ap.add_argument("--matrix-24", action="store_true", help="4池×3周期×过滤开/关")
    ap.add_argument("--matrix-16", action="store_true", help="旧 16 组")
    ap.add_argument("--universe", default=None)
    ap.add_argument("--period", default=None)
    ap.add_argument("--no-filter-up", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--no-skip-ok",
        action="store_true",
        help="强制重算已成功行（默认跳过保留）",
    )
    ap.add_argument(
        "--analysis-level",
        default="core",
        choices=("core", "full"),
        help="默认 core（面板够用且更快）",
    )
    ap.add_argument(
        "--no-qlib",
        action="store_true",
        help="不纳入 qlib_alpha（约 518 个）",
    )
    ap.add_argument(
        "--libraries",
        default=None,
        help="逗号分隔库名过滤，如 qlib_alpha,jq_compat_emotion",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="只统计待算数量，不调 RE",
    )
    args = ap.parse_args()

    jobs: list[tuple[str, str, bool]] = []
    if args.matrix_24:
        # 常用视图优先，面板能尽快看到数量上涨
        priority = [
            ("CSI300", "3y", True),
            ("CSI300", "1y", True),
            ("CSI300", "3m", True),
        ]
        jobs = list(priority)
        for j in MATRIX_24:
            if j not in jobs:
                jobs.append(j)
    elif args.matrix_16:
        jobs = list(MATRIX_16)
    elif args.combo:
        filt = not args.no_filter_up
        for c in args.combo:
            u, p = c.split(":", 1)
            jobs.append((u.strip(), p.strip(), filt))
    elif args.universe and args.period:
        jobs = [(args.universe, args.period, not args.no_filter_up)]
    else:
        # 默认：面板常用视图先补齐
        jobs = [("CSI300", "3y", True)]

    libs = (
        [x.strip() for x in args.libraries.split(",") if x.strip()]
        if args.libraries
        else None
    )
    include_qlib = not args.no_qlib
    skip_ok = not args.no_skip_ok

    log(
        f"remaining backfill start jobs={len(jobs)} skip_ok={skip_ok} "
        f"level={args.analysis_level} include_qlib={include_qlib} libs={libs} "
        f"limit={args.limit} dry_run={args.dry_run}"
    )
    log(f"SQLite → {ds.DB_PATH}")

    catalog = ds.load_factor_index(include_qlib=include_qlib)
    if libs:
        catalog = [f for f in catalog if f.get("library") in set(libs)]
    log(f"catalog={len(catalog)} (含 unavailable)")

    for i, (u, p, f) in enumerate(jobs, 1):
        n, ok, todo = count_todo(
            u, p, f, include_qlib=include_qlib, libraries=libs
        )
        log(f"  [{i}/{len(jobs)}] {u} {p} filter_up={f} catalog={n} ok={ok} todo≈{todo}")

    if args.dry_run:
        log("dry-run 结束")
        return

    failed_combos = 0
    for i, (u, p, filt) in enumerate(jobs, 1):
        log(f"=== [{i}/{len(jobs)}] {u}/{p}/filter_up={filt} ===")
        ds._run_batch(
            universe=u,
            period=p,
            filter_limit_up=filt,
            filter_suspended=True,
            limit=args.limit,
            skip_ok=skip_ok,
            analysis_level=args.analysis_level,
            include_qlib=include_qlib,
            libraries=libs,
        )
        job = ds.read_job()
        log(
            f"=== 结束 status={job.get('status')} done={job.get('done')}/{job.get('total')} "
            f"skipped={job.get('skipped')} failed={job.get('failed')} err={job.get('error')} ==="
        )
        if job.get("status") == "failed":
            failed_combos += 1

    log(f"全部完成 failed_combos={failed_combos}/{len(jobs)}")
    raise SystemExit(1 if failed_combos else 0)


if __name__ == "__main__":
    main()
