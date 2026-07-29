# -*- coding: utf-8 -*-
"""单票后复权日线拉取（akshare 东财 + 腾讯兜底）。"""
from __future__ import annotations

import time

import akshare as ak
import pandas as pd


def ak_daily_prefix(code: str) -> str:
    code = str(code).split(".")[0].zfill(6)
    if code.startswith("92"):
        return f"bj{code}"
    if code.startswith(("5", "6", "9")):
        return f"sh{code}"
    return f"sz{code}"


def fetch_stock_bar_tx(symbol: str, start: str, end: str) -> pd.DataFrame:
    code = symbol.split(".")[0].zfill(6)
    ak_sym = ak_daily_prefix(code)
    try:
        raw = ak.stock_zh_a_hist_tx(
            symbol=ak_sym,
            start_date=start,
            end_date=end,
            adjust="hfq",
        )
        if raw is None or raw.empty:
            return pd.DataFrame()
        df = raw.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df.insert(0, "symbol", symbol)
        if "amount" not in df.columns:
            df["amount"] = None
        df["change_ratio"] = df["close"].pct_change()
        cols = [
            "symbol",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "change_ratio",
        ]
        return df[[c for c in cols if c in df.columns]]
    except Exception:
        return pd.DataFrame()


def fetch_stock_bar(symbol: str, start: str, end: str, retries: int = 3) -> pd.DataFrame:
    """返回后复权日线；失败返回空表。start/end 为 YYYYMMDD。"""
    code = symbol.split(".")[0]
    ak_sym = ak_daily_prefix(code)
    last_err: Exception | None = None
    for i in range(retries):
        try:
            raw = ak.stock_zh_a_daily(
                symbol=ak_sym,
                start_date=start,
                end_date=end,
                adjust="hfq",
            )
            if raw is None or raw.empty:
                break
            df = raw.copy()
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df.insert(0, "symbol", symbol)
            if "turnover" in df.columns:
                df = df.rename(columns={"turnover": "turn"})
            df["change_ratio"] = df["close"].pct_change()
            cols = [
                "symbol",
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "change_ratio",
                "turn",
            ]
            return df[[c for c in cols if c in df.columns]]
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1.5 * (i + 1))
    tx = fetch_stock_bar_tx(symbol, start, end)
    if not tx.empty:
        return tx
    if last_err is not None:
        raise last_err
    return pd.DataFrame()
