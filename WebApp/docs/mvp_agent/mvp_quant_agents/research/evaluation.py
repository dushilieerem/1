"""因子评价：rank IC / IR / t 值 / 胜率 / IC 衰减 / 取向 / 合成权重。

评价逻辑：
- 在每个月末调仓日 t，取因子截面原始值 与 未来 hold_days 收益率 做截面 Spearman 秩相关 = 单期 rank IC。
- 多期 IC 序列 -> IC_mean, IC_std, IR = IC_mean/IC_std, t_stat, win_rate(IC>0 占比)。
- 取向：sign(IC_mean) 决定因子方向（保证“因子越大 -> 未来收益越高”）。
- 合成权重：ic_weighted 模式按 |IR| 归一化；top3 模式取 |IR| 最大的 3 个。
- 废弃阈值：|IR| < ir_keep_threshold 判为 keep=False。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def _month_end_rebalance(prices: pd.DataFrame, hold_days: int):
    """返回可用于回测的月末调仓日（其位置 k 满足 k+hold_days 仍在样本内）。"""
    idx = prices.index
    month_ends = idx.to_series().groupby(idx.to_period("M")).tail(1)
    valid = [d for d in month_ends if idx.get_loc(d) + hold_days < len(idx)]
    return valid


def evaluate_factors(factor_long: pd.DataFrame, prices: pd.DataFrame,
                     cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    from .factors import factor_wide

    hold = cfg.get("research", {}).get("hold_days", 20)
    ir_thr = cfg.get("research", {}).get("ir_keep_threshold", 0.30)

    fw = factor_wide(factor_long)
    rebal = _month_end_rebalance(prices, hold)

    # 未来 hold_days 收益率（调仓日 -> 下个持有期末）
    fwd = pd.DataFrame(index=rebal, columns=prices.columns, dtype=float)
    pos = prices.index
    for d in rebal:
        k = pos.get_loc(d)
        fwd.loc[d] = prices.iloc[k + hold].values / prices.iloc[k].values - 1.0

    # 各因子单期 rank IC 序列
    ic_series = {f: [] for f in fw}
    ic_dates = {f: [] for f in fw}
    for d in rebal:
        fwd_row = fwd.loc[d].dropna()
        for f, panel in fw.items():
            if d not in panel.index:
                continue
            fac_row = panel.loc[d].reindex(fwd_row.index).dropna()
            common = fac_row.index.intersection(fwd_row.index)
            if len(common) < 10:
                continue
            ic, _ = spearmanr(fac_row[common].values, fwd_row[common].values)
            if np.isfinite(ic):
                ic_series[f].append(ic)
                ic_dates[f].append(d)

    rows = []
    for f in fw:
        s = np.array(ic_series[f])
        if len(s) < 3:
            rows.append(dict(factor=f, ic=np.nan, ir=np.nan, t_stat=np.nan,
                             win_rate=np.nan, ic_decay=np.nan, oriented="+",
                             verdict="drop"))
            continue
        ic_mean, ic_std = s.mean(), s.std(ddof=1)
        ir = ic_mean / ic_std if ic_std > 0 else np.nan
        t_stat = ic_mean / (ic_std / np.sqrt(len(s))) if ic_std > 0 else np.nan
        win_rate = float((s > 0).mean())
        # IC 衰减：单期 IC 序列的一阶自相关（持续性）
        ic_decay = float(np.corrcoef(s[:-1], s[1:])[0, 1]) if len(s) > 3 else np.nan
        oriented = "+" if ic_mean >= 0 else "-"
        keep = (abs(ir) >= ir_thr) and (abs(t_stat) > 2.0)
        rows.append(dict(factor=f, ic=round(ic_mean, 4), ir=round(ir, 3),
                         t_stat=round(t_stat, 2), win_rate=round(win_rate, 3),
                         ic_decay=round(ic_decay, 3), oriented=oriented,
                         verdict="keep" if keep else "drop"))

    eval_df = pd.DataFrame(rows)

    # 合成权重
    method = cfg.get("research", {}).get("combination", "ic_weighted")
    if method == "top3":
        cand = eval_df[eval_df["verdict"] == "keep"].copy()
        cand = cand.reindex(cand["ir"].abs().sort_values(ascending=False).index).head(3)
        w = cand["ir"].abs()
    else:
        cand = eval_df[eval_df["verdict"] == "keep"].copy()
        w = cand["ir"].abs()
    if w.sum() > 0:
        cand["weight"] = (w / w.sum()).round(4)
    else:
        cand["weight"] = 0.0
    eval_df = eval_df.merge(cand[["factor", "weight"]], on="factor", how="left")
    eval_df["weight"] = eval_df["weight"].fillna(0.0)

    # 仅保留调仓日的因子原始值，便于策略层合成
    factor_rebal = {f: panel.reindex(rebal) for f, panel in fw.items() if f in eval_df["factor"].values}

    return eval_df, fwd, factor_rebal


if __name__ == "__main__":
    from data_source import fetch_data
    from factors import compute_factors
    cfg = {"research": {"hold_days": 20, "ir_keep_threshold": 0.3, "combination": "ic_weighted"}}
    d = fetch_data({"tushare": {"source": "synthetic"}, "research": {"universe_size": 50}})
    fl = compute_factors(d["prices"], d["fundamentals"])
    ev, fwd, fr = evaluate_factors(fl, d["prices"], cfg)
    pd.set_option("display.width", 120)
    print(ev)
