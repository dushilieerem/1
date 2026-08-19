"""端到端研究链路（可独立运行）。

流程：Tushare/合成取数 -> 四因子 -> 入库 -> IC/IR 评价 -> IC/IR 加权合成
      -> 多空/多头组合回测 -> 绩效分析 -> 落库 -> 打印报告。

运行：
  python research/run_pipeline.py            # 自动按 config.yaml
  python research/run_pipeline.py --source synthetic --size 50
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research import (fetch_data, compute_factors, FactorDB, evaluate_factors,
                      build_composite, backtest, analyze)


def load_cfg() -> dict:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "config.yaml"), "r", encoding="utf-8") as f:
        import yaml
        return yaml.safe_load(f)


def run(cfg: dict) -> dict:
    db = FactorDB(cfg.get("research", {}).get("db_path", "research/quant.db"))
    print("========== 1) 数据接入 ==========")
    data = fetch_data(cfg)
    prices, fund = data["prices"], data["fundamentals"]
    print(f"  来源: {data['source']} | 价格面板: {prices.shape} | "
          f"PE/PB/ROE: {fund['pe'].shape[1]} 只")

    print("========== 2) 四因子计算 + 入库 ==========")
    fl = compute_factors(prices, fund)
    db.save_prices(prices)
    db.save_fundamentals(fund)
    db.save_factors(fl)
    print(f"  因子: {sorted(fl['factor'].unique())} | 因子值行数: {len(fl)}")

    print("========== 3) IC / IR 评价 ==========")
    ev, fwd, fr = evaluate_factors(fl, prices, cfg)
    db.save_eval(ev)
    pd.set_option("display.width", 140)
    print(ev[["factor", "ic", "ir", "t_stat", "win_rate", "ic_decay",
              "oriented", "weight", "verdict"]].to_string(index=False))

    keep = ev[ev["verdict"] == "keep"]
    top3 = keep.reindex(keep["ir"].abs().sort_values(ascending=False).index).head(3)
    print(f"  保留因子: {keep['factor'].tolist()} | Top3(按|IR|): {top3['factor'].tolist()}")

    print("========== 4) 组合合成 + 回测 ==========")
    comp = build_composite(ev, fr, cfg)
    port, bt_info = backtest(comp, prices, cfg)
    print(f"  组合方式: {cfg['research'].get('combination')} | "
          f"long_short={bt_info['long_short']} | 持有={bt_info['hold_days']}天 | "
          f"成本={bt_info['cost_bps']}bp")

    print("========== 5) 绩效分析 ==========")
    metrics = analyze(port, cfg)
    for k, v in metrics.items():
        print(f"  {k}: {v}")

    db.save_strategy({
        "run_time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "name": "multi_factor_ic_weighted",
        "combination": cfg["research"].get("combination"),
        "long_short": int(bt_info["long_short"]),
        "ann_return": metrics["ann_return"], "sharpe": metrics["sharpe"],
        "max_drawdown": metrics["max_drawdown"], "calmar": metrics["calmar"],
        "turnover": bt_info["turnover_factor"],
        "weights": str(dict(zip(ev["factor"], ev["weight"]))),
        "notes": f"保留 {keep['factor'].tolist()}",
    })
    print(f"\n结果已落库: {db.path}")
    return {"eval": ev, "metrics": metrics, "composite": comp, "port": port}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["auto", "synthetic", "tushare"], default=None)
    p.add_argument("--size", type=int, default=None)
    args = p.parse_args()

    cfg = load_cfg()
    if args.source:
        cfg.setdefault("tushare", {})["source"] = args.source
    if args.size:
        cfg.setdefault("research", {})["universe_size"] = args.size
    run(cfg)


if __name__ == "__main__":
    main()
