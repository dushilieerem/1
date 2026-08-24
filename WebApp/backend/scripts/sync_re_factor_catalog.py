# -*- coding: utf-8 -*-
"""同步 ResearchEngine 官方因子目录 → PostgreSQL。

用法（SVQuant 环境）:
  cd E:\\quant-lab\\SV\\SVQuant\\WebApp\\backend
  python scripts/sync_re_factor_catalog.py
  python scripts/sync_re_factor_catalog.py --all
  python scripts/sync_re_factor_catalog.py --status

逻辑：拉 RE → 算 content_hash → 与库中对比；
  - 有变更：写 re_factor_catalog_snapshot
  - 无变更：只记 sync_log，页面继续读旧数据

定时：见 scripts/install_re_catalog_sync_task.ps1（每天 02:00）
手动：你让我跑时执行本脚本即可。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("NO_PROXY", "*")
os.environ.setdefault("no_proxy", "*")

from services.core.db import get_conn  # noqa: E402
from services.factor.re_factor_catalog import (  # noqa: E402
    ensure_re_factor_catalog_schema,
    sync_from_re,
)

LOG_DIR = ROOT / "output"
LOG_PATH = LOG_DIR / "re_factor_catalog_sync.log"


def log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def show_status() -> int:
    ensure_re_factor_catalog_schema()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT scope, content_hash, factor_count, library_count,
                   fetched_at, updated_at
            FROM re_factor_catalog_snapshot
            ORDER BY scope
            """
        ).fetchall()
        logs = conn.execute(
            """
            SELECT scope, changed, factor_count, message, created_at
            FROM re_factor_catalog_sync_log
            ORDER BY id DESC
            LIMIT 5
            """
        ).fetchall()
    if not rows:
        log("status: 库中尚无快照")
    for r in rows:
        log(
            f"status scope={r['scope']} factors={r['factor_count']} "
            f"libs={r['library_count']} hash={str(r['content_hash'])[:12]}… "
            f"fetched={r['fetched_at']} checked={r['updated_at']}"
        )
    for r in logs:
        log(
            f"log [{r['created_at']}] scope={r['scope']} "
            f"changed={r['changed']} {r['message']}"
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="同步 RE 官方因子目录到 PostgreSQL")
    ap.add_argument(
        "--all",
        action="store_true",
        help="同步全部 RE 库（默认仅 primary 十库）",
    )
    ap.add_argument(
        "--status",
        action="store_true",
        help="只看库内快照与最近同步日志，不拉 RE",
    )
    args = ap.parse_args()

    if args.status:
        return show_status()

    include_all = bool(args.all)
    log(f"开始同步 include_all={include_all}")
    try:
        out = sync_from_re(include_all=include_all)
    except Exception as exc:
        log(f"FAIL: {exc}")
        return 1
    log(
        f"OK changed={out.get('changed')} factors={out.get('factor_count')} "
        f"elapsed_ms={out.get('last_check_elapsed_ms') or out.get('elapsed_ms')} "
        f"msg={out.get('message')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
