"""真实数据接入层。

对外统一返回：
  {
    "source": "tushare" | "synthetic" | "synthetic(fallback)",
    "prices": DataFrame(index=datetime, columns=ticker, value=复权收盘价),
    "fundamentals": {"pe": df, "pb": df, "roe": df}   # 每个都是 index=datetime, columns=ticker
  }

真实路径用 Tushare 取 daily（价格）+ daily_basic（pe_ttm/pb）+ fina_indicator（roe）。
无 token / 网络失败时使用带因子结构的合成数据，保证链路可端到端验证。
"""
from __future__ import annotations
import os
from datetime import datetime

import numpy as np
import pandas as pd


def _synthetic(n: int, start: str, end: str, seed: int = 42):
    """生成带真实因子结构的合成面板，使四因子具备可观测的 IC。

    潜变量：
      q  质量因子（驱动 roe 与未来收益，+）
      v  价值因子（驱动 pe/pb 反向，与未来收益 +）
      m  动量状态 AR(1)（驱动过去/未来收益，+但衰减）
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, end)
    tickers = [f"{i:06d}" for i in range(1, n + 1)]

    q = rng.normal(0, 1, n)          # 质量
    v = rng.normal(0, 1, n)          # 价值
    # 动量状态：AR(1) 持久度 0.95
    m = np.zeros((len(dates), n))
    m[0] = rng.normal(0, 1, n)
    for t in range(1, len(dates)):
        m[t] = 0.95 * m[t - 1] + rng.normal(0, np.sqrt(1 - 0.95 ** 2), n)

    # 日收益：漂移 + 质量/价值/动量暴露 + 噪声
    # 因子暴露调小、噪声调大，使合成 IC/IR 落在接近真实多因子选股的可信区间
    mu = 0.0003
    daily = (mu
             + 0.0009 * q[None, :]
             + 0.0009 * v[None, :]
             + 0.0007 * m
             + rng.normal(0, 0.018, (len(dates), n)))
    close = 10.0 * np.cumprod(1.0 + daily, axis=0)
    prices = pd.DataFrame(close, index=dates, columns=tickers)

    # 基本面：pe/pb 与价值因子反向；roe 与质量因子同向
    pe = 20.0 * np.exp(-0.5 * v[None, :] + rng.normal(0, 0.05, (len(dates), n)))
    pb = 3.0 * np.exp(-0.5 * v[None, :] + rng.normal(0, 0.05, (len(dates), n)))
    roe = (0.10 + 0.04 * q[None, :] + rng.normal(0, 0.005, (len(dates), n))).clip(0.0, 0.4)

    fundamentals = {
        "pe": pd.DataFrame(pe, index=dates, columns=tickers),
        "pb": pd.DataFrame(pb, index=dates, columns=tickers),
        "roe": pd.DataFrame(roe, index=dates, columns=tickers),
    }
    return prices, fundamentals


def _fetch_tushare(cfg: dict, token: str):
    """真实 Tushare 取数。返回与 _synthetic 相同的结构。"""
    import tushare as ts
    ts.set_token(token)
    pro = ts.pro_api()

    start = cfg.get("start_date", "2019-01-01").replace("-", "")
    end = cfg.get("end_date", "2023-12-31").replace("-", "")
    index = cfg.get("index", "000300.SH")

    # 指数成分股
    cons = pro.index_weight(index_code=index, start_date=start, end_date=end)
    tickers = sorted(cons["con_code"].unique().tolist())[: cfg.get("universe_size", 50)]
    # 利润表/财务指标 -> roe（取最新报告期，前向填充）
    # 日线价格 + 估值
    frames = {}
    pe_frames, pb_frames, roe_frames = {}, {}, {}
    for code in tickers:
        df = pro.daily(ts_code=code, start_date=start, end_date=end)[["trade_date", "close"]]
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        frames[code] = df.set_index("trade_date")["close"]
        db = pro.daily_basic(ts_code=code, start_date=start, end_date=end,
                             fields="trade_date,pe_ttm,pb")[["trade_date", "pe_ttm", "pb"]]
        db["trade_date"] = pd.to_datetime(db["trade_date"])
        db = db.set_index("trade_date")
        pe_frames[code] = db["pe_ttm"]
        pb_frames[code] = db["pb"]
        fin = pro.fina_indicator(ts_code=code, fields="end_date,roe") \
            .sort_values("end_date")
        roe_frames[code] = fin.set_index("end_date")["roe"]
    prices = pd.DataFrame(frames).sort_index()
    fundamentals = {
        "pe": pd.DataFrame(pe_frames).sort_index().ffill(),
        "pb": pd.DataFrame(pb_frames).sort_index().ffill(),
        "roe": pd.DataFrame(roe_frames).sort_index().ffill().resample("B").ffill(),
    }
    return prices, fundamentals


def fetch_data(cfg: dict) -> dict:
    ts_cfg = cfg.get("tushare", {})
    token = ts_cfg.get("token") or os.environ.get("TUSHARE_TOKEN")
    source_mode = ts_cfg.get("source", "auto")
    start = ts_cfg.get("start_date", "2019-01-01")
    end = ts_cfg.get("end_date", "2023-12-31")
    n = cfg.get("research", {}).get("universe_size", 50)

    if source_mode == "synthetic" or not token:
        if source_mode != "synthetic":
            print(f"[data] 未检测到 TUSHARE_TOKEN，使用合成数据演示（{n} 只，{start}~{end}）。"
                  "接入真实数据请配置 tushare.token 或环境变量 TUSHARE_TOKEN。")
        prices, fundamentals = _synthetic(n, start, end)
        return {"source": "synthetic", "prices": prices, "fundamentals": fundamentals}

    try:
        prices, fundamentals = _fetch_tushare(ts_cfg, token)
        return {"source": "tushare", "prices": prices, "fundamentals": fundamentals}
    except Exception as e:  # noqa: BLE001
        print(f"[data] Tushare 调用失败({e})，回退合成数据。")
        prices, fundamentals = _synthetic(n, start, end)
        return {"source": "synthetic(fallback)", "prices": prices, "fundamentals": fundamentals}


if __name__ == "__main__":
    d = fetch_data({"tushare": {"source": "synthetic"}, "research": {"universe_size": 10}})
    print("source:", d["source"], "| prices:", d["prices"].shape,
          "| pe:", d["fundamentals"]["pe"].shape)
