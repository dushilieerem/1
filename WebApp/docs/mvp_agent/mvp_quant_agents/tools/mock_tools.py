"""MVP 工具桩：数据/因子/回测/风控/交易 的确定性计算实现。

真实环境里这些函数应替换为你们的行情库、因子引擎、回测框架、柜台 API。
此处返回结构化结果，保证 mock 模式也能跑通完整链路并演示 Boss 裁决逻辑。
"""
from __future__ import annotations
import random
from datetime import date, timedelta

random.seed(42)


def fetch_market_data(universe: str = "沪深300") -> dict:
    """数据采集分支：拉取行情（桩）。"""
    symbols = ["600519", "000858", "601318", "300750", "000333", "002594"]
    end = date.today()
    start = end - timedelta(days=120)
    return {
        "universe": universe,
        "symbols": symbols,
        "start": str(start), "end": str(end),
        "rows": len(symbols) * 120,
        "status": "ok",
    }


def build_factor_library(raw: dict) -> dict:
    """因子库管理分支：登记可用因子。"""
    libs = ["momentum_20", "reversal_5", "volatility_60", "pair_spread_z", "size", "value"]
    return {"registered": libs, "count": len(libs), "ready": True}


def compute_factors(raw: dict, libs: list) -> dict:
    """因子计算分支：RAPIDS 上线前的 CPU 桩。"""
    return {"computed": libs, "coverage": "99.2%", "new_factors": ["pair_spread_z"]}


def evaluate_factor(factor_name: str) -> dict:
    """因子评价分支：IC / IR / 衰减。"""
    return {
        "factor": factor_name,
        "ic": round(random.uniform(0.02, 0.08), 3),
        "ir": round(random.uniform(0.4, 1.1), 2),
        "half_life": random.randint(8, 25),
        "verdict": "keep",
    }


def mine_factors(top_n: int = 5) -> dict:
    """因子挖掘分支：遗传规划/搜索（桩）。"""
    mined = [f"gp_factor_{i}" for i in range(1, top_n + 1)]
    return {"mined": mined, "candidates": len(mined), "best_ic": round(random.uniform(0.05, 0.1), 3)}


def generate_strategy(theme: str = "pair_trading") -> dict:
    """策略生成分支：产出策略规格（含西蒙斯式配对交易）。"""
    if theme == "pair_trading":
        spec = {
            "name": "pairs_mean_reversion",
            "type": "statistical_arbitrage",
            "pairs": [["600519", "000858"], ["601318", "600036"]],
            "entry_z": 2.0, "exit_z": 0.5,
            "horizon": "intraday~swing",
        }
    else:
        spec = {"name": "ml_cross_sectional", "type": "ml_alpha", "universe": "沪深300"}
    return {"spec": spec, "theme": theme}


def backtest_strategy(spec: dict) -> dict:
    """回测分支：向量化回测（桩，含真实成本假设）。"""
    sharpe = round(random.uniform(1.4, 2.1), 2)
    max_dd = round(random.uniform(0.05, 0.12), 3)
    ann_ret = round(random.uniform(0.12, 0.28), 3)
    return {
        "sharpe": sharpe, "max_drawdown": max_dd, "ann_return": ann_ret,
        "cost_model": "include_slippage+commission", "sample": "walk_forward_oos",
    }


def evaluate_strategy(backtest: dict) -> dict:
    """策略评价分支：综合打分（样本外稳定性等）。"""
    score = round((backtest["sharpe"] * 0.5 + (1 - backtest["max_drawdown"]) * 2), 2)
    return {"score": score, "oos_stable": backtest["sharpe"] > 1.0,
            "verdict": "pass" if score > 1.0 else "revise"}


def portfolio_switch(style: str = "balanced") -> dict:
    """组合/风格切换分支：风险预算分配。"""
    alloc = {
        "balanced": {"pair_trading": 0.4, "ml_alpha": 0.4, "cash": 0.2},
        "aggressive": {"pair_trading": 0.6, "ml_alpha": 0.35, "cash": 0.05},
        "defensive": {"pair_trading": 0.25, "ml_alpha": 0.25, "cash": 0.5},
    }.get(style, {"pair_trading": 0.4, "ml_alpha": 0.4, "cash": 0.2})
    return {"style": style, "allocation": alloc}


def risk_analysis(proposal: dict, max_position_pct: float = 0.05) -> dict:
    """实盘分析分支：对策略提案做风控研判（一票否决来源）。"""
    bt = proposal.get("backtest", {})
    reasons = []
    if bt.get("sharpe", 0) < 1.0:
        reasons.append("样本外夏普低于 1.0")
    if bt.get("max_drawdown", 0) > 0.15:
        reasons.append("最大回撤超过 15% 阈值")
    # 配对交易单边暴露检查
    spec = proposal.get("spec", {})
    if spec.get("type") == "statistical_arbitrage":
        if spec.get("entry_z", 2.0) < 1.5:
            reasons.append("配对入场阈值过窄，易频繁交易")
    approve = len(reasons) == 0
    return {
        "approve": approve,
        "reasons": reasons or ["指标达标，准予进入执行评审"],
        "limits": {"max_position_pct": max_position_pct, "max_leverage": 1.0},
        "verdict": "approve" if approve else "reject",
    }


def risk_control(limits: dict) -> dict:
    """实盘风控分支：落地硬约束（下单前再校验）。"""
    return {"enforced": True, "limits": limits, "circuit_breaker": "drawdown>8% -> 暂停"}


def simulate_trade(proposal: dict) -> dict:
    """模拟交易分支：回放成交（桩）。"""
    return {"mode": "simulate", "filled": len(proposal.get("spec", {}).get("pairs", [])) * 2,
            "status": "virtual_fill_ok"}


def live_order(proposal: dict, limits: dict) -> dict:
    """实盘下单分支：对接柜台 API（桩，需 Boss 裁决 approve 后才调用）。"""
    return {"mode": "live", "order_id": "ORD" + str(random.randint(100000, 999999)),
            "status": "submitted", "limits_applied": limits}
