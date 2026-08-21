"""因子与策略回测共用的数据、资产和基准解析辅助函数。"""

from __future__ import annotations

import inspect
import os
from pathlib import Path
from typing import Any, Optional

import pandas as pd


def _resolve_data_dir(req_data_dir: Optional[str]) -> str:
    """数据目录解析顺序：请求 -> env ``SVQUANT_DATA_DIR`` -> ``<repo>/MarketData``。"""
    if req_data_dir:
        return req_data_dir
    env = os.environ.get("SVQUANT_DATA_DIR")
    if env:
        return env
    import app

    # app/__init__.py -> 上三层 = 仓库根
    repo_root = Path(app.__file__).resolve().parent.parent.parent
    return str(repo_root / "MarketData")


def _resolve_current_data_dir() -> Path:
    """返回当前已发布数据目录，兼容旧版扁平 MarketData。"""
    data_dir = Path(_resolve_data_dir(None))
    current_dir = data_dir / "current"
    return current_dir if current_dir.is_dir() else data_dir


_BENCHMARK_FILES = {
    "CSI300": "index_price_000300.SH.parquet",
    "CSI500": "index_price_000905.SH.parquet",
}


def _load_benchmark_equity(
    benchmark: str,
    dates: pd.DatetimeIndex,
    *,
    data_engine: Any | None = None,
) -> pd.Series:
    """加载指数收盘价并对齐、归一化为净值序列。"""
    if data_engine is not None:
        frame = data_engine.get_index(benchmark)
    else:
        path = _resolve_current_data_dir() / "benchmark" / _BENCHMARK_FILES[benchmark]
        frame = pd.read_parquet(path)
    close_col = "close" if "close" in frame else next(col for col in frame.columns if col.endswith("_close"))
    series = frame[close_col]
    series.index = pd.to_datetime(series.index)
    series = series.reindex(dates).ffill().dropna()
    if series.empty:
        raise ValueError(f"基准 {benchmark} 与回测区间没有重叠数据")
    return series / series.iloc[0]


def _resolve_research_assets(req, *, data_engine: Any | None = None):
    """校验 WebApp 已解析的可选资产快照，不访问用户资产存储。"""
    universe_snapshot = req.universe_snapshot
    benchmark_snapshot = req.benchmark_snapshot
    universe = req.universe
    if universe_snapshot is not None:
        universe = list(universe_snapshot.symbols)
        engine = data_engine
        if engine is None:
            from app.quantcore import DataEngine, FieldParquetProvider

            engine = DataEngine(FieldParquetProvider(_resolve_data_dir(None)))
        available = set(engine.get_panels(req.start, req.end, fields=["close"])["close"].columns)
        missing = [symbol for symbol in universe if symbol not in available]
        if missing:
            raise ValueError(f"证券池包含行情中不存在的证券: {', '.join(missing)}")
    return universe, universe_snapshot, benchmark_snapshot


def _declared_strategy_symbols(strategy) -> tuple[str, ...]:
    """读取策略声明的固定交易标的，兼容旧单标的 ``symbol`` 属性。"""
    symbols: list[str] = []
    for field in ("fixed_symbols", "pair_symbols", "symbols"):
        declared = getattr(strategy, field, ())
        if declared is None:
            continue
        if isinstance(declared, str):
            raise ValueError(f"策略 {field} 必须为证券代码序列，不能是字符串")
        try:
            values = list(declared)
        except TypeError as exc:
            raise ValueError(f"策略 {field} 必须为证券代码序列") from exc
        if any(not isinstance(symbol, str) or not symbol for symbol in values):
            raise ValueError(f"策略 {field} 包含无效证券代码")
        symbols.extend(values)
    if not symbols:
        symbol = getattr(strategy, "symbol", None)
        if isinstance(symbol, str) and symbol:
            symbols.append(symbol)
    if not symbols:
        try:
            parameters = inspect.signature(strategy.__init__).parameters
        except (TypeError, ValueError):
            parameters = {}
        pair = [
            parameters[name].default
            for name in ("stock_a", "stock_b")
            if name in parameters and isinstance(parameters[name].default, str)
        ]
        if len(pair) == 2:
            symbols.extend(pair)
        else:
            symbol = parameters.get("symbol")
            if symbol is not None and isinstance(symbol.default, str) and symbol.default:
                symbols.append(symbol.default)
    return tuple(dict.fromkeys(symbols))


def _resolve_strategy_symbols(
    provider, universe, strategy, *, as_of=None
) -> tuple[list[str], dict[str, str], tuple[str, ...]]:
    """优先解析策略固定标的；否则沿用请求股票池。"""
    from app.quantcore.data._util import resolve_universe
    from app.services.factor.market_data import _market_symbol, _panel_symbol

    declared_symbols = _declared_strategy_symbols(strategy)
    if declared_symbols:
        raw_symbols = [_panel_symbol(symbol) for symbol in declared_symbols]
        available_symbols = set(provider.get_symbols())
        missing_symbols = [symbol for symbol, raw in zip(declared_symbols, raw_symbols) if raw not in available_symbols]
        if missing_symbols:
            raise ValueError(f"策略固定标的行情不可用: {sorted(missing_symbols)}")
        return raw_symbols, dict(zip(raw_symbols, declared_symbols)), declared_symbols

    raw_symbols = resolve_universe(provider, universe, as_of=as_of)
    return raw_symbols, {symbol: _market_symbol(symbol) for symbol in raw_symbols}, ()


class _StrategyPanels:
    """向量化策略的懒加载行情视图，统一输出交易所代码列名。"""

    def __init__(self, panels, raw_symbols: list[str], symbol_mapping: dict[str, str]) -> None:
        self._panels = panels
        self._raw_symbols = raw_symbols
        self._symbol_mapping = symbol_mapping
        self._cache: dict[str, pd.DataFrame] = {}

    def __contains__(self, field: str) -> bool:
        return field in self._panels

    def __iter__(self):
        return iter(self._panels)

    def __getitem__(self, field: str) -> pd.DataFrame:
        if field not in self._cache:
            self._cache[field] = self._panels[field].reindex(
                columns=self._raw_symbols
            ).rename(columns=self._symbol_mapping)
        return self._cache[field]


def _custom_benchmark_equity(
    snapshot,
    dates: pd.DatetimeIndex,
    *,
    data_engine: Any | None = None,
) -> pd.Series:
    """从已发布 close 面板计算静态组合基准，并严格校验价格可得性。"""
    engine = data_engine
    if engine is None:
        from app.quantcore import DataEngine, FieldParquetProvider

        engine = DataEngine(FieldParquetProvider(_resolve_data_dir(None)))
    close = engine.get_panels(None, None, fields=["close"])["close"].reindex(dates)
    weights = pd.Series(snapshot.weights, dtype=float)
    missing = [symbol for symbol in weights.index if symbol not in close.columns]
    if missing:
        raise ValueError(f"组合基准缺少价格的证券: {', '.join(missing)}")
    prices = close.loc[:, weights.index]
    if prices.dropna(how="all").empty:
        raise ValueError("组合基准与回测区间没有重叠数据")
    if prices.iloc[0].isna().any():
        raise ValueError("组合基准首个有效日期存在缺失价格")
    returns = prices.pct_change().iloc[1:]
    if returns.isna().any().any():
        raise ValueError("组合基准价格缺失，无法计算收益")
    return pd.concat([
        pd.Series([1.0], index=prices.index[:1]),
        (1.0 + returns.dot(weights)).cumprod(),
    ])


def _benchmark_equity(
    benchmark: str,
    snapshot,
    dates: pd.DatetimeIndex,
    *,
    data_engine: Any | None = None,
) -> pd.Series:
    return (
        _custom_benchmark_equity(snapshot, dates, data_engine=data_engine)
        if snapshot is not None
        else _load_benchmark_equity(benchmark, dates, data_engine=data_engine)
    )


def _asset_meta(snapshot):
    if snapshot is None:
        return None
    meta = {
        "id": snapshot.asset_id,
        "version": snapshot.version,
        "content_hash": snapshot.content_hash,
    }
    if hasattr(snapshot, "symbols"):
        return {**meta, "constituent_count": len(snapshot.symbols), "membership_mode": snapshot.membership_mode}
    return {**meta, "constituent_count": len(snapshot.weights), "pricing": snapshot.pricing}


def _persisted_asset(snapshot):
    return snapshot.model_dump() if snapshot is not None else None


__all__ = [
    "_BENCHMARK_FILES",
    "_resolve_data_dir",
    "_resolve_current_data_dir",
    "_load_benchmark_equity",
    "_resolve_research_assets",
    "_declared_strategy_symbols",
    "_resolve_strategy_symbols",
    "_StrategyPanels",
    "_custom_benchmark_equity",
    "_benchmark_equity",
    "_asset_meta",
    "_persisted_asset",
]
