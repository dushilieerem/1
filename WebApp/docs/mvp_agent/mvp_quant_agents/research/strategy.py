"""组合合成 + 回测 + 绩效分析。

合成：在调仓日对保留因子做截面 z-score，按 IC/IR 权重加权得到 composite 得分。
回测：月频调仓、持有 hold_days；取 composite 前后 top_quantile 做多/空（long_short 模式），
      等权、扣交易成本。绩效：年化收益 / 夏普 / 最大回撤 / Calmar / 日胜率。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_composite(eval_df: pd.DataFrame, factor_rebal: dict, cfg: dict) -> pd.DataFrame:
    rebal = next(iter(factor_rebal.values())).index
    composite = pd.DataFrame(index=rebal, columns=None, dtype=float)
    composite = pd.DataFrame(index=rebal, dtype=float)
    for _, row in eval_df.iterrows():
        f, w, oriented = row["factor"], row["weight"], row["oriented"]
        if w <= 0 or f not in factor_rebal:
            continue
        panel = factor_rebal[f].reindex(rebal)
        z = panel.sub(panel.mean(axis=1), axis=0).div(panel.std(axis=1).replace(0, np.nan), axis=0)
        sign = 1.0 if oriented == "+" else -1.0
        contrib = z * sign * w
        composite = contrib if composite.empty else composite.add(contrib, fill_value=0.0)
    return composite


def backtest(composite: pd.DataFrame, prices: pd.DataFrame, cfg: dict) -> tuple[pd.Series, dict]:
    r = cfg.get("research", {})
    hold = r.get("hold_days", 20)
    top_q = r.get("top_quantile", 0.2)
    long_short = r.get("long_short", True)
    cost_bps = r.get("cost_bps", 10)

    daily_ret = prices.pct_change().fillna(0.0)
    rebal = list(composite.index)
    pos = prices.index
    port = pd.Series(index=prices.index, dtype=float)

    turnover_factor = 2 if long_short else 1
    cost = cost_bps / 1e4 * turnover_factor

    for i, d in enumerate(rebal):
        k = pos.get_loc(d)
        nxt = pos.get_loc(rebal[i + 1]) if i + 1 < len(rebal) else len(pos) - 1
        score = composite.iloc[i].dropna()
        if score.empty:
            continue
        ranked = score.rank(ascending=False)
        n_long = max(1, int(len(score) * top_q))
        longs = ranked[ranked <= n_long].index
        shorts = ranked[ranked > len(score) - n_long].index
        for t in range(k, min(nxt + 1, len(pos))):
            lr = daily_ret.iloc[t].reindex(longs).mean()
            sr = daily_ret.iloc[t].reindex(shorts).mean() if long_short else 0.0
            port.iloc[t] = (lr - sr) - (cost if t == k else 0.0)
    port = port.dropna()
    return port, {"cost_bps": cost_bps, "turnover_factor": turnover_factor,
                  "hold_days": hold, "top_quantile": top_q, "long_short": long_short}


def analyze(port: pd.Series, cfg: dict) -> dict:
    port = port.dropna()
    ann = port.mean() * 252
    vol = port.std() * np.sqrt(252)
    sharpe = ann / vol if vol > 0 else np.nan
    cum = (1.0 + port).cumprod()
    max_dd = float((cum / cum.cummax() - 1.0).min())
    calmar = ann / abs(max_dd) if max_dd != 0 else np.nan
    win_rate = float((port > 0).mean())
    return {
        "ann_return": round(float(ann), 4),
        "ann_vol": round(float(vol), 4),
        "sharpe": round(float(sharpe), 3),
        "max_drawdown": round(max_dd, 4),
        "calmar": round(float(calmar), 3) if np.isfinite(calmar) else None,
        "daily_win_rate": round(win_rate, 3),
        "n_days": int(len(port)),
    }


if __name__ == "__main__":
    from data_source import fetch_data
    from factors import compute_factors
    from evaluation import evaluate_factors
    cfg = {"research": {"hold_days": 20, "ir_keep_threshold": 0.3, "combination": "ic_weighted",
                        "long_short": True, "cost_bps": 10, "top_quantile": 0.2}}
    d = fetch_data({"tushare": {"source": "synthetic"}, "research": {"universe_size": 50}})
    fl = compute_factors(d["prices"], d["fundamentals"])
    ev, fwd, fr = evaluate_factors(fl, d["prices"], cfg)
    comp = build_composite(ev, fr, cfg)
    port, _ = backtest(comp, d["prices"], cfg)
    print(ev[["factor", "ic", "ir", "verdict", "weight"]])
    print("backtest:", analyze(port, cfg))
