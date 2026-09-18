# -*- coding: utf-8 -*-
"""给 admin 灌 3 条策略广场示例（可重复执行：先清 demo 再插）。"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

from services.strategy.strategy_plaza_store import (
    create_plaza_item,
    ensure_strategy_plaza_schema,
)
from services.core.db import get_conn

DEMO_PREFIX = "plaza-demo-"

SAMPLE_CODE = '''# plaza demo strategy
def initialize(context):
    context.universe = "CSI300"
    context.hold_n = 10

def handle_data(context, data):
    # demo only
    pass
'''


def _trading_days(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _curve(seed: int, n: int, drift: float, vol: float) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    days = _trading_days(date(2023, 7, 3), n)
    eq = 1.0
    bm = 1.0
    peak = 1.0
    equity: list[dict] = []
    bench: list[dict] = []
    for i, day in enumerate(days):
        if i > 0:
            eq *= 1.0 + drift + rng.gauss(0, vol)
            bm *= 1.0 + drift * 0.35 + rng.gauss(0, vol * 0.9)
        peak = max(peak, eq)
        dd = eq / peak - 1.0
        ds = day.isoformat()
        equity.append({"date": ds, "value": round(eq, 6), "drawdown": round(dd, 6)})
        bench.append({"date": ds, "value": round(bm, 6)})
    return equity, bench


def _metrics(equity: list[dict], bench: list[dict]) -> tuple[dict, float]:
    e0 = equity[0]["value"]
    e1 = equity[-1]["value"]
    b0 = bench[0]["value"]
    b1 = bench[-1]["value"]
    years = max(len(equity) / 244.0, 0.2)
    total = e1 / e0 - 1.0
    annual = (e1 / e0) ** (1.0 / years) - 1.0
    mdd = min(p.get("drawdown") or 0.0 for p in equity)
    excess = e1 / e0 - b1 / b0
    rets = []
    for i in range(1, len(equity)):
        rets.append(equity[i]["value"] / equity[i - 1]["value"] - 1.0)
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)
    vol = math.sqrt(var) * math.sqrt(244)
    sharpe = (mean * 244) / vol if vol > 1e-9 else 0.0
    win = sum(1 for r in rets if r > 0) / len(rets)
    return (
        {
            "annual_return": round(annual, 6),
            "total_return": round(total, 6),
            "cumulative_return": round(total, 6),
            "max_drawdown": round(mdd, 6),
            "sharpe": round(sharpe, 4),
            "sortino": round(sharpe * 1.2, 4),
            "calmar": round(annual / abs(mdd), 4) if mdd < 0 else None,
            "win_rate": round(win, 4),
            "volatility": round(vol, 4),
            "turnover": 0.08,
        },
        round(excess, 6),
    )


DEMOS = [
    {
        "title": "综合因子打分选股策略",
        "body": "多因子打分选股，每周调仓，控制持仓数量与行业分散。",
        "universe": "CSI300",
        "universe_label": "沪深300",
        "seed": 11,
        "drift": 0.00055,
        "vol": 0.012,
    },
    {
        "title": "成长因子动态调仓",
        "body": "成长类因子排序持仓，动态控制仓位，适合中证500风格暴露。",
        "universe": "CSI500",
        "universe_label": "中证500",
        "seed": 22,
        "drift": 0.0007,
        "vol": 0.014,
    },
    {
        "title": "短动量反转演示",
        "body": "短周期动量与反转信号结合，演示回测结果展示。",
        "universe": "CSI500",
        "universe_label": "中证500",
        "seed": 33,
        "drift": 0.0004,
        "vol": 0.013,
    },
]


def main() -> None:
    ensure_strategy_plaza_schema()
    with get_conn() as conn:
        admin = conn.execute(
            "SELECT id FROM users WHERE username = %s LIMIT 1",
            ("admin",),
        ).fetchone()
        if not admin:
            raise SystemExit("admin user not found")
        aid = int(admin["id"])
        conn.execute(
            """
            DELETE FROM strategy_plaza_items
            WHERE author_id = %s AND source_run_id LIKE %s
            """,
            (aid, f"{DEMO_PREFIX}%"),
        )

    for d in DEMOS:
        equity, bench = _curve(d["seed"], 520, d["drift"], d["vol"])
        metrics, excess = _metrics(equity, bench)
        create_plaza_item(
            aid,
            title=d["title"],
            body=d["body"],
            source_run_id=f"{DEMO_PREFIX}{d['seed']}",
            snapshot={
                "metrics": metrics,
                "excess_return": excess,
                "equity_curve": equity,
                "benchmark_curve": bench,
                "date_range": {
                    "start": equity[0]["date"],
                    "end": equity[-1]["date"],
                },
                "universe": d["universe"],
                "benchmark": d["universe"],
                "universe_label": d["universe_label"],
                "benchmark_label": d["universe_label"],
                "strategy_code": SAMPLE_CODE,
                "range_label": f"{equity[0]['date']} ~ {equity[-1]['date']}",
            },
        )
        print("seeded", d["title"])


if __name__ == "__main__":
    main()
