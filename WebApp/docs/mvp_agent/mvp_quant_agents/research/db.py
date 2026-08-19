"""SQLite 落库：行情 / 基本面 / 因子值 / 因子评价 / 策略结果。

MVP 用 SQLite（零依赖、易迁移）。正式环境可把 FactorDB 内部 to_sql 的目标换成
PostgreSQL / DuckDB / 对象存储，接口不变。
"""
from __future__ import annotations

import os
from datetime import datetime

import pandas as pd


class FactorDB:
    def __init__(self, path: str = "research/quant.db"):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        import sqlite3
        with sqlite3.connect(self.path) as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS prices (
                date TEXT, ticker TEXT, close REAL, PRIMARY KEY(date, ticker));
            CREATE TABLE IF NOT EXISTS fundamentals (
                date TEXT, ticker TEXT, metric TEXT, value REAL,
                PRIMARY KEY(date, ticker, metric));
            CREATE TABLE IF NOT EXISTS factors (
                date TEXT, ticker TEXT, factor TEXT, value REAL,
                PRIMARY KEY(date, ticker, factor));
            CREATE TABLE IF NOT EXISTS factor_eval (
                factor TEXT, ic REAL, ir REAL, t_stat REAL, win_rate REAL,
                ic_decay REAL, oriented TEXT, weight REAL, verdict TEXT, eval_date TEXT,
                PRIMARY KEY(factor, eval_date));
            CREATE TABLE IF NOT EXISTS strategy_result (
                id INTEGER PRIMARY KEY AUTOINCREMENT, run_time TEXT, name TEXT,
                combination TEXT, long_short INTEGER, ann_return REAL, sharpe REAL,
                max_drawdown REAL, calmar REAL, turnover REAL, weights TEXT, notes TEXT);
            """)

    # ---------- 写入 ----------
    def save_prices(self, prices: pd.DataFrame):
        df = prices.stack().reset_index()
        df.columns = ["date", "ticker", "close"]
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df.to_sql("prices", self._con(), if_exists="replace", index=False)

    def save_fundamentals(self, fundamentals: dict):
        rows = []
        for metric, panel in fundamentals.items():
            s = panel.stack().reset_index()
            s.columns = ["date", "ticker", "value"]
            s["metric"] = metric
            rows.append(s)
        df = pd.concat(rows, ignore_index=True)
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df.to_sql("fundamentals", self._con(), if_exists="replace", index=False)

    def save_factors(self, factor_long: pd.DataFrame):
        df = factor_long.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df.to_sql("factors", self._con(), if_exists="replace", index=False)

    def save_eval(self, eval_df: pd.DataFrame):
        df = eval_df.copy()
        df["eval_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        df.to_sql("factor_eval", self._con(), if_exists="replace", index=False)

    def save_strategy(self, rec: dict):
        pd.DataFrame([rec]).to_sql("strategy_result", self._con(),
                                  if_exists="append", index=False)

    # ---------- 读取 ----------
    def load_prices(self) -> pd.DataFrame:
        df = pd.read_sql("SELECT * FROM prices", self._con())
        df["date"] = pd.to_datetime(df["date"])
        return df.pivot(index="date", columns="ticker", values="close").sort_index()

    def load_fundamentals(self) -> dict:
        df = pd.read_sql("SELECT * FROM fundamentals", self._con())
        df["date"] = pd.to_datetime(df["date"])
        out = {}
        for metric in df["metric"].unique():
            sub = df[df["metric"] == metric]
            out[metric] = sub.pivot(index="date", columns="ticker",
                                    values="value").sort_index()
        return out

    def load_factors(self) -> pd.DataFrame:
        df = pd.read_sql("SELECT * FROM factors", self._con())
        df["date"] = pd.to_datetime(df["date"])
        return df

    def load_eval(self) -> pd.DataFrame:
        return pd.read_sql("SELECT * FROM factor_eval", self._con())

    def _con(self):
        import sqlite3
        return sqlite3.connect(self.path)
