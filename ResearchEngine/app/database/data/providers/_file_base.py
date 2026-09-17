"""文件型数据源共享逻辑（CSV / Parquet 共用）。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import pandas as pd

from app.utils.data import filter_by_date
from app.database.data.interface import IDataProvider

#: 标准 OHLCV 字段
STANDARD_FIELDS = ("open", "high", "low", "close", "volume")

#: 常见列名到标准字段的映射
_COLUMN_ALIASES = {
    "date": "date",
    "datetime": "date",
    "time": "date",
    "timestamp": "date",
    "symbol": "symbol",
    "code": "symbol",
    "ticker": "symbol",
    "open": "open",
    "o": "open",
    "high": "high",
    "h": "high",
    "low": "low",
    "l": "low",
    "close": "close",
    "c": "close",
    "volume": "volume",
    "vol": "volume",
    "amount": "amount",
    "v": "volume",
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """把常见列名归一到标准 OHLCV 命名。"""
    renamed = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in _COLUMN_ALIASES:
            renamed[col] = _COLUMN_ALIASES[key]
    if renamed:
        df = df.rename(columns=renamed)
    return df


class _FileProvider(IDataProvider):
    """文件型数据源基类。

    约定目录结构：

    ::

        data_dir/
        ├── {symbol}.csv      # 单标的行情文件（CSVProvider）
        ├── {symbol}.parquet  # 或 parquet 文件（ParquetProvider）
        └── universe.csv      # 可选：股票池

    ``universe.csv`` 支持两种形态：

    1. 按日期：列 ``date,symbols``（symbols 以分号分隔），按日期取池；
    2. 按池名：列 ``pool,symbols``，``get_universe("CSI500")`` 取对应池。

    若不存在 ``universe.csv`` 或查询无命中，则返回目录下全部标的。
    """

    #: 子类指定文件扩展名，如 ``".csv"`` / ``".parquet"``
    _ext: str = ""

    def __init__(self, data_dir: str | os.PathLike) -> None:
        self.data_dir = Path(data_dir)
        if not self.data_dir.exists():
            raise FileNotFoundError(f"数据目录不存在: {self.data_dir}")

    # -- 子类实现：读取单个标的原始 DataFrame --
    def _read_file(self, path: Path) -> pd.DataFrame:  # pragma: no cover - 抽象
        raise NotImplementedError

    # -- 公共实现 --
    def _symbol_path(self, symbol: str) -> Path:
        return self.data_dir / f"{symbol}{self._ext}"

    def get_bars(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        path = self._symbol_path(symbol)
        if not path.exists():
            raise FileNotFoundError(f"找不到标的 {symbol} 的数据文件: {path}")

        df = self._read_file(path)
        df = _normalize_columns(df)

        if "date" in df.columns:
            df = df.set_index("date")
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        # 日期过滤（闭区间）
        df = filter_by_date(df, start, end)

        # 字段过滤
        if fields is not None:
            missing = [f for f in fields if f not in df.columns]
            if missing:
                raise KeyError(f"标的 {symbol} 缺少字段: {missing}")
            df = df[list(fields)]

        return df

    def get_symbols(self) -> List[str]:
        return sorted(
            p.stem for p in self.data_dir.glob(f"*{self._ext}")
            if p.is_file() and p.stem.lower() != "universe"
        )

    def get_universe(self, date: Optional[str] = None) -> List[str]:
        univ_path = self.data_dir / "universe.csv"
        if not univ_path.exists():
            return self.get_symbols()

        univ = pd.read_csv(univ_path)
        univ.columns = [c.lower() for c in univ.columns]

        # 形态 2：按池名（pool, symbols）
        if "pool" in univ.columns and date is not None:
            row = univ.loc[univ["pool"].astype(str) == str(date)]
            if not row.empty:
                symbols_cell = row.iloc[0].get("symbols", "")
                return [s for s in str(symbols_cell).split(";") if s]

        # 形态 1：按日期（date, symbols）
        if "date" in univ.columns and date is not None:
            univ["date"] = pd.to_datetime(univ["date"])
            target = pd.to_datetime(date, errors="coerce")
            if not pd.isna(target):
                row = univ.loc[univ["date"] == target]
                if not row.empty:
                    symbols_cell = row.iloc[0].get("symbols", "")
                    return [s for s in str(symbols_cell).split(";") if s]

        # 无日期 / 无命中：取首行 symbols 或回退全部标的
        if "symbols" in univ.columns and not univ.empty:
            symbols_cell = univ.iloc[0]["symbols"]
            return [s for s in str(symbols_cell).split(";") if s]
        return self.get_symbols()
