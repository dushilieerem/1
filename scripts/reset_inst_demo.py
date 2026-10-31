#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""重置机构端演示业务数据（只清 inst_* 业务表，保留机构/成员/公司池）。

  /home/dev01/program/anaconda3/bin/python scripts/reset_inst_demo.py --yes

警告：会删除研究、辩论、议案、审批、授权、订单、持仓、监控与审计记录。
仅用于本地演示/测试。生产环境不要运行。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.core.db import get_conn  # noqa: E402

TABLES = (
    "inst_order",
    "inst_fill",
    "inst_position_snapshot",
    "inst_authorization",
    "inst_approval",
    "inst_proposal_version",
    "inst_proposal",
    "inst_debate_argument",
    "inst_debate_session",
    "inst_evidence",
    "inst_research_version",
    "inst_research_task",
    "inst_research_case",
    "inst_monitor_event",
    "inst_exit_case",
    "inst_audit_event",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="确认删除演示业务数据")
    args = ap.parse_args()
    if not args.yes:
        raise SystemExit("拒绝执行：请加 --yes 确认。")
    with get_conn() as conn:
        conn.execute("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE")
        conn.execute(
            "UPDATE inst_portfolio SET nav=10000000, cash=10000000, updated_at=NOW()"
        )
    print("机构端演示业务数据已重置；公司池、成员、组合保留。")


if __name__ == "__main__":
    main()
