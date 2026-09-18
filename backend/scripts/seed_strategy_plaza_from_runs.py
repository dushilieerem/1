# -*- coding: utf-8 -*-
"""从本机已成功落库的策略回测中挑 3 条优质结果，挂到 admin 策略广场。

说明：当前 RE 不可达时用历史真跑结果；有 RE 时可用 seed_strategy_plaza_live.py。
"""
from __future__ import annotations

import json

from services.core.db import get_conn
from services.strategy.strategy_plaza_store import (
    create_plaza_item,
    ensure_strategy_plaza_schema,
)

DEMO_PREFIX = "plaza-from-run-"

# run_id -> 展示文案（多段）
PICKS = [
    {
        "run_id": "a6b0dce3-1e2b-45b7-9935-8a511646eec2",
        "title": "多因子合成选股（研究回测）",
        "body": (
            "本条来自平台真实回测存档：将多个有效因子合成为综合得分，"
            "按得分排序构建多头组合并定期再平衡，目标是在控制换手的前提下提升风险调整后收益。\n\n"
            "合成因子通常比单一动量/波动更稳健：不同因子在不同市场阶段贡献收益，"
            "组合后回撤与夏普往往更均衡。回测中股票池与基准、费率均按研究页提交参数执行，"
            "净值与指标为 ResearchEngine 返回的原始结果快照。\n\n"
            "阅读建议：优先看年化、最大回撤与夏普的组合，而不只看累计收益；"
            "若要复现，可在「源码」页复制策略后于策略研究中调整区间再跑。"
            "内容仅供研究交流，不构成投资建议。"
        ),
    },
    {
        "run_id": "66fcd01f-762d-43dc-8cbb-0f4c77aeb143",
        "title": "图西阿伦指标 Aroon 趋势选股",
        "body": (
            "Aroon 指标通过刻画「距上次新高/新低的时间」识别趋势启动与衰减，"
            "本策略将其用于 A 股选股：在趋势确认阶段提高相关标的权重，并在趋势走弱时降低敞口。\n\n"
            "相对纯价格动量，Aroon 更强调时间维度上的趋势持续性，有助于过滤短暂脉冲行情。"
            "本页展示为真实回测结果（含完整策略源码与收益曲线），可直接对照基准观察超额来源。\n\n"
            "风险提示：趋势类策略在震荡市容易反复止损；请结合最大回撤与持仓换手理解策略性格。"
            "广场分享用于演示与讨论，请勿当作实盘指令。"
        ),
    },
    {
        "run_id": "37a97816-bd56-4b17-8bfe-5e5b691bb549",
        "title": "20 日动量选股回测",
        "body": (
            "经典截面动量：用过去约 20 个交易日的收益率刻画短期相对强弱，"
            "选取动量靠前的股票等权持有并按既定频率调仓。逻辑直观，便于作为广场对照样例。\n\n"
            "短周期动量对市场情绪与资金流向敏感，牛市中易放大收益，急跌或风格切换时回撤也会更快显现。"
            "本条同样取自平台已完成的回测任务，指标与曲线均为引擎产出，而非手工捏造。\n\n"
            "可在详情页查看源码，或使用「极速运行」在行情服务可用时按默认参数重跑验证。"
            "研究用途，不构成投资建议。"
        ),
    },
]


def _universe_label(code: str | None) -> str:
    m = {
        "CSI300": "沪深300",
        "CSI500": "中证500",
        "CSI1000": "中证1000",
        "CSI800": "中证800",
        "SSE50": "上证50",
        "ALL": "全A",
    }
    return m.get(str(code or "").upper(), str(code or "") or "—")


def main() -> None:
    ensure_strategy_plaza_schema()
    with get_conn() as conn:
        admin = conn.execute(
            "SELECT id FROM users WHERE username = %s LIMIT 1",
            ("admin",),
        ).fetchone()
        if not admin:
            raise SystemExit("admin not found")
        aid = int(admin["id"])

        # 先隐藏 admin 名下旧广场条目，再写入 3 条真跑快照
        conn.execute(
            """
            UPDATE strategy_plaza_items
            SET status = 'hidden', updated_at = NOW()
            WHERE author_id = %s AND status = 'published'
            """,
            (aid,),
        )

        for pick in PICKS:
            row = conn.execute(
                """
                SELECT id, name, request, result
                FROM strategy_runs
                WHERE id = %s
                LIMIT 1
                """,
                (pick["run_id"],),
            ).fetchone()
            if not row:
                print("missing run", pick["run_id"])
                continue
            req = row["request"] or {}
            res = row["result"] or {}
            if isinstance(req, str):
                req = json.loads(req)
            if isinstance(res, str):
                res = json.loads(res)
            uni = req.get("universe")
            bm = req.get("benchmark") or uni
            dr = res.get("date_range") or {}
            start = dr.get("start") or req.get("start") or ""
            end = dr.get("end") or req.get("end") or ""
            metrics = res.get("metrics") or {}
            print(
                "seed",
                pick["title"],
                "ar=",
                metrics.get("annual_return"),
                "curve=",
                len(res.get("equity_curve") or []),
            )
            create_plaza_item(
                aid,
                title=pick["title"],
                body=pick["body"],
                source_run_id=f"{DEMO_PREFIX}{pick['run_id'][:8]}",
                snapshot={
                    "metrics": metrics,
                    "excess_return": res.get("excess_return"),
                    "equity_curve": res.get("equity_curve") or [],
                    "benchmark_curve": res.get("benchmark_curve") or [],
                    "date_range": {"start": start, "end": end},
                    "universe": uni,
                    "benchmark": bm,
                    "universe_label": _universe_label(uni),
                    "benchmark_label": _universe_label(bm),
                    "strategy_code": req.get("strategy_code"),
                    "range_label": f"{start} ~ {end}" if start and end else None,
                },
            )


if __name__ == "__main__":
    main()
