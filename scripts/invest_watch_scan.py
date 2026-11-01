#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""F9/F23 值守 Agent 的日频扫描（收盘后运行）。

用法：
  python scripts/invest_watch_scan.py --all
  python scripts/invest_watch_scan.py --user-id 1

只写 invest_event_log，不推送、不发通知；实时行情到位后再接调度层。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.core.db import get_conn  # noqa: E402
from services.invest import agent_tools  # noqa: E402
from services.invest.db import PGConn  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=int)
    parser.add_argument("--all", action="store_true", help="扫描所有有自选/持仓的用户")
    args = parser.parse_args()
    if not args.user_id and not args.all:
        parser.error("需要 --user-id 或 --all")
    with get_conn() as raw:
        conn = PGConn(raw)
        if args.user_id:
            user_ids = [args.user_id]
        else:
            rows = conn.execute(
                "SELECT DISTINCT user_id FROM ("
                "  SELECT user_id FROM invest_watchlist UNION"
                "  SELECT user_id FROM invest_portfolio"
                ") t ORDER BY user_id"
            ).fetchall()
            user_ids = [int(r["user_id"]) for r in rows]
        total = 0
        for uid in user_ids:
            out = agent_tools.watch_scan(conn, uid)
            total += int(out.get("inserted") or 0)
            print(f"user={uid} alerts={len(out.get('alerts') or [])} inserted={out.get('inserted')}")
    print(f"done users={len(user_ids)} inserted={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
