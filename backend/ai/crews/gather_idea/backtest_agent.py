# -*- coding: utf-8 -*-
"""Agent D · 回测雏形：把因子草稿参数发给平台回测接口，收成报告。"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from services.factor.re_backtest_bff import forward_factor_backtest

_TZ = timezone(timedelta(hours=8))


def run_backtest_report(body: dict[str, Any], *, user_id: int) -> dict[str, Any]:
    _ = user_id
    t0 = time.perf_counter()
    hint = body.get("backtest_hint") if isinstance(body.get("backtest_hint"), dict) else {}
    factor = body.get("factor") if isinstance(body.get("factor"), dict) else {}
    name = str(hint.get("factor_name") or factor.get("factor_name") or "").strip()
    code = str(hint.get("factor_code") or factor.get("factor_code") or "").strip()
    if not name or not code:
        raise ValueError("需要因子函数名与代码")
    payload = {
        "factor_name": name,
        "factor_code": code,
        "universe": str(hint.get("universe") or "CSI300"),
        "start": str(hint.get("start") or "2018-01-01")[:10],
        "end": str(hint.get("end") or datetime.now(_TZ).strftime("%Y-%m-%d"))[:10],
        "portfolio_type": str(hint.get("portfolio_type") or "long_only"),
        "rebalance_days": int(hint.get("rebalance_days") or 1),
        "groups": int(hint.get("groups") or 5),
        "benchmark": str(hint.get("benchmark") or "CSI300"),
        "analysis_level": str(hint.get("analysis_level") or "core"),
    }
    raw = forward_factor_backtest(payload)
    elapsed = int((time.perf_counter() - t0) * 1000)
    return {
        "ok": True,
        "report_id": f"fbt_{datetime.now(_TZ).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
        "draft_id": str(body.get("draft_id") or ""),
        "request": payload,
        "metrics": raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {},
        "error": raw.get("error"),
        "date_range": raw.get("date_range"),
        "raw": raw,
        "stats": {"elapsed_ms": elapsed},
        "warnings": [
            "回测区间是收益确认窗，不是因子计算窗；换区间结果可能差很多。",
            "报告可送评价 Agent；不会自动入库。",
        ],
    }
