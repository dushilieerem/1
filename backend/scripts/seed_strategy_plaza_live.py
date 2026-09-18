# -*- coding: utf-8 -*-
"""真实跑 3 条内置策略回测，写入策略广场（admin），并清理旧 demo。"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from services.core.db import get_conn
from services.core.re_config import RE_BASE
from services.strategy.builtin_strategies_store import get_builtin_strategy
from services.strategy.strategy_plaza_store import (
    create_plaza_item,
    ensure_strategy_plaza_schema,
)

DEMO_PREFIX = "plaza-live-"

# 较长介绍文案
BODIES = {
    "cross_sectional_momentum": (
        "本策略基于截面动量因子：每日计算股票过去 20 个交易日的收益率，"
        "选取动量最强的前 10 只等权持有，并按交易日频率再平衡。\n\n"
        "设计动机是捕捉中短期相对强弱：在同一股票池内，近期表现更好的标的往往"
        "仍有惯性延续，适合作为偏进攻的选股底仓。回测区间覆盖近三年，股票池为沪深300，"
        "基准同步为沪深300，便于对比超额。\n\n"
        "使用注意：动量策略在急跌反弹或风格剧烈切换时回撤可能放大；实盘需关注"
        "停牌、涨跌停与冲击成本。本页展示为研究回测快照，不构成投资建议。"
    ),
    "low_volatility": (
        "低波动策略选取历史波动率更低的股票构建组合，目标是在控制组合波动的同时"
        "获取更平滑的净值路径。实现上使用平台内置低波动因子，持仓 Top10、等权、"
        "按既定再平衡节奏调仓。\n\n"
        "低波动异常在多市场上被反复验证：波动更低的股票长期风险调整后收益并不差，"
        "适合作为稳健配置或与动量类策略互补。本回测使用中证500股票池、近三年日频数据，"
        "以观察在中小盘环境中的表现。\n\n"
        "局限：极端行情下「低波」也可能同步下跌；因子拥挤时拥挤交易会削弱优势。"
        "请结合自身风险偏好审慎参考。"
    ),
    "short_term_reversal": (
        "短期反转策略选取近若干交易日跌幅较大的标的等权持有，利用短期过度反应后的"
        "均值回归。实现上使用平台内置短期反转逻辑，持仓 Top10、定期再平衡。\n\n"
        "反转与动量在风格上可互补：急跌后的反弹段往往对反转更友好，而趋势延续段"
        "动量更占优。本回测使用中证500、近三年日频，便于与动量/低波动条目对照。\n\n"
        "注意：反转在单边趋势行情中可能持续受损；请结合最大回撤与夏普一起看。"
        "本页为研究分享快照，不构成投资建议。"
    ),
}


def _post_json(url: str, body: dict, timeout: int = 120) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": raw[:500]}


def _get_json(url: str, timeout: int = 60) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def run_strategy_backtest(strategy_code: str, *, universe: str, benchmark: str) -> dict:
    body = {
        "strategy_code": strategy_code,
        "universe": universe,
        "benchmark": benchmark,
        "start": "2023-07-03",
        "end": "2026-07-03",
        "commission_rate": 0.0003,
        "stamp_tax": 0.001,
        "slippage_rate": 0.001,
        "initial_capital": 1_000_000,
        "engine_mode": "vectorized",
        "include_rebalance_logs": False,
    }
    st, data = _post_json(f"{RE_BASE}/api/backtest/strategy", body, timeout=120)
    if st in (200, 202) and data.get("run_id"):
        run_id = data["run_id"]
        deadline = time.time() + 600
        while time.time() < deadline:
            time.sleep(2)
            task = _get_json(f"{RE_BASE}/api/backtest/strategy/{run_id}", timeout=60)
            status = str(task.get("status") or "")
            print("  poll", status)
            if status == "succeeded":
                result = task.get("result") or {}
                if result.get("error"):
                    raise RuntimeError(str(result["error"]))
                return result
            if status in ("failed", "cancelled"):
                raise RuntimeError(str(task.get("error") or status))
        raise RuntimeError("backtest timeout")
    if st == 200 and (data.get("metrics") or data.get("equity_curve")):
        if data.get("error"):
            raise RuntimeError(str(data["error"]))
        return data
    raise RuntimeError(f"submit failed HTTP {st}: {data}")


def _momentum_code() -> str:
    s = get_builtin_strategy("cross_sectional_momentum")
    return str(s.get("strategy_code") or "")


def _low_vol_code() -> str:
    s = get_builtin_strategy("low_volatility")
    return str(s.get("strategy_code") or "")


def _reversal_code() -> str:
    s = get_builtin_strategy("short_term_reversal")
    return str(s.get("strategy_code") or "")


JOBS = [
    {
        "key": "cross_sectional_momentum",
        "title": "截面动量 Top10（近三年）",
        "universe": "CSI300",
        "universe_label": "沪深300",
        "benchmark": "CSI300",
        "benchmark_label": "沪深300",
        "code_fn": _momentum_code,
    },
    {
        "key": "low_volatility",
        "title": "低波动 Top10（中证500）",
        "universe": "CSI500",
        "universe_label": "中证500",
        "benchmark": "CSI500",
        "benchmark_label": "中证500",
        "code_fn": _low_vol_code,
    },
    {
        "key": "short_term_reversal",
        "title": "短期反转 Top10（中证500）",
        "universe": "CSI500",
        "universe_label": "中证500",
        "benchmark": "CSI500",
        "benchmark_label": "中证500",
        "code_fn": _reversal_code,
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
            raise SystemExit("admin not found")
        aid = int(admin["id"])
        # 清旧 demo / 占位
        n = conn.execute(
            """
            UPDATE strategy_plaza_items
            SET status = 'hidden', updated_at = NOW()
            WHERE author_id = %s
              AND status = 'published'
              AND (
                source_run_id LIKE 'plaza-demo-%%'
                OR source_run_id LIKE 'plaza-live-%%'
                OR source_run_id LIKE 'demo-%%'
                OR title IN (
                  '综合因子打分选股策略',
                  '成长因子动态调仓',
                  '短动量反转演示'
                )
              )
            """,
            (aid,),
        ).rowcount
        print("hidden old", n)

    for job in JOBS:
        print("running", job["title"])
        code = job["code_fn"]()
        if not code.strip():
            print("  skip empty code")
            continue
        result = run_strategy_backtest(
            code,
            universe=job["universe"],
            benchmark=job["benchmark"],
        )
        metrics = result.get("metrics") or {}
        print(
            "  annual",
            metrics.get("annual_return"),
            "mdd",
            metrics.get("max_drawdown"),
            "curve",
            len(result.get("equity_curve") or []),
        )
        dr = result.get("date_range") or {}
        start = dr.get("start") or "2023-07-03"
        end = dr.get("end") or "2026-07-03"
        create_plaza_item(
            aid,
            title=job["title"],
            body=BODIES[job["key"]],
            source_run_id=f"{DEMO_PREFIX}{job['key']}",
            snapshot={
                "metrics": metrics,
                "excess_return": result.get("excess_return"),
                "equity_curve": result.get("equity_curve") or [],
                "benchmark_curve": result.get("benchmark_curve") or [],
                "date_range": {"start": start, "end": end},
                "universe": job["universe"],
                "benchmark": job["benchmark"],
                "universe_label": job["universe_label"],
                "benchmark_label": job["benchmark_label"],
                "strategy_code": code,
                "engine_mode": "vectorized",
                "range_label": f"{start} ~ {end}",
            },
        )
        print("  seeded", job["title"])


if __name__ == "__main__":
    main()
