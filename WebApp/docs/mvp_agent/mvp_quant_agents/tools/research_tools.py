"""真实研究链路的 Agent 阶段函数。

供 DataAgent / FactorAgent / StrategyAgent 在 research.enabled 时调用，
与 mock_tools 接口对齐（返回结构兼容 Boss 报告）。所有计算确定性、不出网（L3 安全）。
"""
from __future__ import annotations

import os
import sys

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from research import (fetch_data, compute_factors, FactorDB, evaluate_factors,
                      build_composite, backtest, analyze)

FACTORS = ["momentum", "pe", "pb", "roe"]


def _db(cfg):
    return FactorDB(cfg.get("research", {}).get("db_path", "research/quant.db"))


def ingest_and_compute(cfg: dict) -> dict:
    db = _db(cfg)
    data = fetch_data(cfg)
    db.save_prices(data["prices"])
    db.save_fundamentals(data["fundamentals"])
    fl = compute_factors(data["prices"], data["fundamentals"])
    db.save_factors(fl)
    return {
        "raw": {"source": data["source"], "symbols": list(data["prices"].columns),
                "rows": len(data["prices"]), "start": str(data["prices"].index[0].date()),
                "end": str(data["prices"].index[-1].date())},
        "libs": {"registered": FACTORS, "count": len(FACTORS), "ready": True},
        "factors": {"computed": FACTORS, "coverage": "100%", "new_factors": []},
    }


def evaluate_factors_stage(cfg: dict) -> dict:
    db = _db(cfg)
    prices = db.load_prices()
    fl = db.load_factors()
    ev, _, _ = evaluate_factors(fl, prices, cfg)
    db.save_eval(ev)
    keep = ev[ev["verdict"] == "keep"]["factor"].tolist()
    top3 = (ev.reindex(ev["ir"].abs().sort_values(ascending=False).index)["factor"].head(3).tolist())
    return {
        "evaluations": ev.to_dict("records"),
        "mined": {"candidates": 0},
        "combination_note": f"IC/IR 加权合成；保留 {keep}；Top3(按|IR|)={top3}",
    }


def build_strategy_stage(cfg: dict) -> dict:
    db = _db(cfg)
    prices = db.load_prices()
    fl = db.load_factors()
    ev, _, fr = evaluate_factors(fl, prices, cfg)
    comp = build_composite(ev, fr, cfg)
    port, bt = backtest(comp, prices, cfg)
    metrics = analyze(port, cfg)
    db.save_strategy({
        "run_time": __import__("pandas").Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "name": "multi_factor_ic_weighted",
        "combination": cfg["research"].get("combination"),
        "long_short": int(bt["long_short"]),
        "ann_return": metrics["ann_return"], "sharpe": metrics["sharpe"],
        "max_drawdown": metrics["max_drawdown"], "calmar": metrics["calmar"],
        "turnover": bt["turnover_factor"],
        "weights": str(dict(zip(ev["factor"], ev["weight"]))),
        "notes": f"保留 {ev[ev['verdict']=='keep']['factor'].tolist()}",
    })
    spec = {
        "name": "multi_factor_ic_weighted", "type": "multi_factor",
        "factors": ev["factor"].tolist(),
        "weights": {f: float(w) for f, w in zip(ev["factor"], ev["weight"])},
        "hold": cfg["research"].get("hold_days", 20),
        "long_short": cfg["research"].get("long_short", True),
    }
    score = round(metrics["sharpe"] * 0.5 + (1 - metrics["max_drawdown"]) * 2, 2)
    return {
        "name": spec["name"], "spec": spec,
        "backtest": {"sharpe": metrics["sharpe"], "max_drawdown": metrics["max_drawdown"],
                     "ann_return": metrics["ann_return"],
                     "cost_model": "include_slippage+commission", "sample": "walk_forward_oos"},
        "evaluation": {"score": score, "verdict": "pass" if metrics["sharpe"] > 1.0 else "revise"},
        "allocation": {"balanced": {"multi_factor": 0.6, "cash": 0.4}},
        "recommend_execute": metrics["sharpe"] > 1.0,
    }
