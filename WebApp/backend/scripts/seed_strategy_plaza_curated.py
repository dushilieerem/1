# -*- coding: utf-8 -*-
"""将筛出的优质 3 年回测写入策略广场，并下架表现差的 plaza-live 演示。"""
from __future__ import annotations

import json
from pathlib import Path

from services.core.db import get_conn
from services.strategy.strategy_plaza_store import (
    create_plaza_item,
    ensure_strategy_plaza_schema,
)

PREFIX = "plaza-curated-"
TOP_PATH = Path(__file__).with_name("_plaza_screen_top.json")

META = {
    "mom12_1_csi500": {
        "title": "12-1 动量选股（中证500 · 近三年）",
        "universe_label": "中证500",
        "benchmark_label": "中证500",
        "body": (
            "经典 Jegadeesh–Titman「12-1」动量思路：用近一年收益刻画中期相对强弱，"
            "并剔除最近一个月的短期噪声，等权持有得分靠前的约 20 只股票，按月再平衡。\n\n"
            "相对日频换仓的短动量，本策略换手更低，近三年回测年化与夏普表现更均衡。"
            "指标与净值曲线均由 ResearchEngine 实盘口径回测产出。\n\n"
            "研究分享，不构成投资建议；风格切换阶段动量可能阶段性失效。"
        ),
    },
    "mom60_w_csi500": {
        "title": "60 日动量周调 Top20（中证500）",
        "universe_label": "中证500",
        "benchmark_label": "中证500",
        "body": (
            "以过去约 60 个交易日收益率做截面动量排序，每周再平衡，等权持有 Top20。"
            "相比日频短动量，周调可以降低交易成本对净值的侵蚀。\n\n"
            "本条为近三年真实回测快照，便于与 12-1、低波动等风格对照阅读。"
            "内容仅供研究交流。"
        ),
    },
    "quality_mom_csi300": {
        "title": "中期动量 + 波动稳定（沪深300）",
        "universe_label": "沪深300",
        "benchmark_label": "沪深300",
        "body": (
            "在沪深300成分内，将 120 日中期动量与 60 日低波动做截面排名后加权合成，"
            "持仓 Top15、约双周再平衡，兼顾趋势与路径平滑。\n\n"
            "适合作为大盘蓝筹池内的进攻–防守折中样例。回测结果来自引擎实跑。"
        ),
    },
    "lowvol60_m_csi500": {
        "title": "60 日低波动月调（中证500）",
        "universe_label": "中证500",
        "benchmark_label": "中证500",
        "body": (
            "选取过去 60 日收益波动更低的股票构建等权组合，按月再平衡、持仓 Top30。"
            "目标是控制回撤、获得更平滑的净值路径，适合作为稳健对照条目。\n\n"
            "近三年回测中最大回撤相对可控；极端行情下低波也可能同步下跌，请综合夏普与回撤阅读。"
        ),
    },
}


def main() -> None:
    ensure_strategy_plaza_schema()
    picks = json.loads(TOP_PATH.read_text(encoding="utf-8"))
    # only curated keys we care about, preserve sharpe order
    want = ["mom12_1_csi500", "mom60_w_csi500", "quality_mom_csi300", "lowvol60_m_csi500"]
    by_key = {p["key"]: p for p in picks}
    ordered = [by_key[k] for k in want if k in by_key]

    with get_conn() as conn:
        admin = conn.execute(
            "SELECT id FROM users WHERE username = %s LIMIT 1",
            ("admin",),
        ).fetchone()
        if not admin:
            raise SystemExit("admin not found")
        aid = int(admin["id"])
        n = conn.execute(
            """
            UPDATE strategy_plaza_items
            SET status = 'hidden', updated_at = NOW()
            WHERE author_id = %s
              AND status = 'published'
              AND (
                source_run_id LIKE 'plaza-live-%%'
                OR source_run_id LIKE 'plaza-curated-%%'
                OR source_run_id LIKE 'plaza-demo-%%'
              )
            """,
            (aid,),
        ).rowcount
        print("hidden old curated/live/demo", n)

    for p in ordered:
        key = p["key"]
        meta = META[key]
        res = p["result"]
        metrics = res.get("metrics") or {}
        dr = res.get("date_range") or {}
        start = dr.get("start") or "2023-07-03"
        end = dr.get("end") or "2026-07-03"
        print(
            "seed",
            meta["title"],
            "ar=",
            metrics.get("annual_return"),
            "sharpe=",
            metrics.get("sharpe"),
        )
        create_plaza_item(
            aid,
            title=meta["title"],
            body=meta["body"],
            source_run_id=f"{PREFIX}{key}",
            snapshot={
                "metrics": metrics,
                "excess_return": res.get("excess_return"),
                "equity_curve": res.get("equity_curve") or [],
                "benchmark_curve": res.get("benchmark_curve") or [],
                "date_range": {"start": start, "end": end},
                "universe": p["universe"],
                "benchmark": p.get("benchmark") or p["universe"],
                "universe_label": meta["universe_label"],
                "benchmark_label": meta["benchmark_label"],
                "strategy_code": p["code"],
                "engine_mode": "vectorized",
                "range_label": f"{start} ~ {end}",
            },
        )
    print("done", len(ordered))


if __name__ == "__main__":
    main()
