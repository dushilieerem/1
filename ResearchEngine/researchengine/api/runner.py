"""核心：因子代码字符串 -> 回测 -> 序列化结果。

复用 :class:`researchengine.FactorLoader` + :class:`researchengine.ExperimentManager`
+ 回测适配器（默认 native，可 vectorbt），**不新写回测逻辑**，只把 SDK 调用包成可被
HTTP 路由调用的纯函数。

所有异常（语法错 / 导入错 / 运行错 / 因子名不存在）-> ``BacktestResponse.error``（HTTP 200），
不抛 500，便于前端统一处理。
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

import pandas as pd

from researchengine.api.schemas import (
    AnnualReturn,
    DateRange,
    DrawdownInfo,
    EquityPoint,
    FactorAnalysis,
    FactorBacktestMeta,
    FactorBacktestRequest,
    FactorBacktestResponse,
    ICPoint,
    IndustryEquityCurve,
    IndustryGroupEquityCurve,
    IndustryGroupPoint,
    Holding,
    LayeredPoint,
    PositionSnapshot,
    StrategyBacktestMeta,
    StrategyBacktestRequest,
    StrategyBacktestResponse,
    RollingIRPoint,
    ValuePoint,
)
from researchengine.api.serializers import (
    date_range_from,
    equity_to_points,
    metrics_to_dict,
)


def _cache_enabled() -> bool:
    return os.environ.get("SVQUANT_BACKTEST_CACHE_ENABLED", "true").lower() not in {
        "0", "false", "no",
    }


def _cache_int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def run_factor_backtest(req: FactorBacktestRequest, response=None) -> FactorBacktestResponse:
    """因子回测缓存入口；缓存异常时降级为直接回测。"""
    if not _cache_enabled():
        if response is not None:
            response.headers["X-SVQuant-Cache"] = "BYPASS"
        return _run_factor_backtest_uncached(req)

    try:
        from researchengine.assets import backtest_cache_dir
        from researchengine.cache import FileBacktestCache

        cache = FileBacktestCache(
            backtest_cache_dir(),
            ttl_days=_cache_int_env("SVQUANT_BACKTEST_CACHE_TTL_DAYS", 30),
            max_bytes=_cache_int_env("SVQUANT_BACKTEST_CACHE_MAX_BYTES", 10 * 1024**3),
        )
        key = cache.make_key(
            req.model_dump(mode="json"),
            cache.data_fingerprint(Path(_resolve_data_dir(None))),
        )
        cached = cache.get(key)
        if cached is not None:
            if response is not None:
                response.headers["X-SVQuant-Cache"] = "HIT"
            return FactorBacktestResponse.model_validate(cached)

        with cache.lock(key) as acquired:
            cached = cache.get(key)
            if cached is not None:
                if response is not None:
                    response.headers["X-SVQuant-Cache"] = "HIT"
                return FactorBacktestResponse.model_validate(cached)
            result = _run_factor_backtest_uncached(req)
            if acquired and result.error is None:
                try:
                    cache.set(key, result.model_dump(mode="json"))
                except Exception:  # noqa: BLE001 写缓存失败不重复执行回测
                    if response is not None:
                        response.headers["X-SVQuant-Cache"] = "BYPASS"
                    return result
        if response is not None:
            response.headers["X-SVQuant-Cache"] = "MISS"
        return result
    except Exception:  # noqa: BLE001 缓存不可用不得阻断研究回测
        if response is not None:
            response.headers["X-SVQuant-Cache"] = "BYPASS"
        return _run_factor_backtest_uncached(req)


def _resolve_data_dir(req_data_dir: Optional[str]) -> str:
    """数据目录解析顺序：请求 -> env ``SVQUANT_DATA_DIR`` -> ``<repo>/MarketData``。"""
    if req_data_dir:
        return req_data_dir
    env = os.environ.get("SVQUANT_DATA_DIR")
    if env:
        return env
    import researchengine

    # researchengine/__init__.py -> 上三层 = 仓库根
    repo_root = Path(researchengine.__file__).resolve().parent.parent.parent
    return str(repo_root / "MarketData")


def _wrap_factor_code(factor_code: str) -> str:
    """自动补全因子代码：用户只写函数体，系统添加 import 和 class 头。"""
    wrapped = (
        "from quantcore import FactorLibrary\n\n"
        "class UserFactorLibrary(FactorLibrary):\n"
        "    author = \"user\"\n\n"
    )
    for line in factor_code.splitlines():
        if line.strip():
            wrapped += f"    {line}\n"
        else:
            wrapped += "\n"
    return wrapped


def _load_factor_from_code(factor_code: str, factor_name: str):
    """把因子源码写到临时文件，用 :class:`FactorLoader` 加载，取出指定因子。

    因子对象本身是内存中的活实例，临时文件加载完即可清理。
    因子代码自动补全 FactorLibrary 类头，用户只需写函数体。
    """
    from researchengine import FactorLoader

    full_code = _wrap_factor_code(factor_code)

    tmpdir = tempfile.mkdtemp(prefix="svquant_api_")
    mod_name = f"user_factor_{uuid.uuid4().hex[:8]}"
    factor_file = Path(tmpdir) / f"{mod_name}.py"
    factor_file.write_text(full_code, encoding="utf-8")

    try:
        loader = FactorLoader(factor_dir=str(tmpdir))
        loader.load(mod_name)
        if factor_name not in loader.factors:
            raise KeyError(
                f"因子 {factor_name!r} 未找到；可用: {list(loader.factors)}"
            )
        return loader.factors[factor_name]
    finally:
        # 清理：弹 sys.modules 与临时目录（FactorLoader 会把 tmpdir 加进 sys.path）
        sys.modules.pop(mod_name, None)
        try:
            sys.path.remove(str(tmpdir))
        except ValueError:
            pass
        shutil.rmtree(tmpdir, ignore_errors=True)


def _build_config(commission_rate, slippage_rate, stamp_tax=None,
                  rebalance_days=None, groups=None, long_short=None,
                  analysis_level: str = "core"):
    """由参数构建 :class:`ConfigManager`（不设 output_path -> 不落盘）。"""
    from researchengine import ConfigManager

    cfg = ConfigManager()
    cfg.set("data_dir", _resolve_data_dir(None))
    if rebalance_days is not None:
        cfg.set("rebalance_days", rebalance_days)
    if groups is not None:
        cfg.set("groups", groups)
        cfg.set("n_groups", groups)
        cfg.set("n_layered_groups", groups)
    if long_short is not None:
        cfg.set("long_short", long_short)
    if stamp_tax is not None:
        cfg.set("stamp_tax", stamp_tax)
    cfg.set("backtest.engine", "native")
    cfg.set("backtest.initial_capital", 1_000_000.0)
    cfg.set("backtest.commission_rate", commission_rate)
    cfg.set("backtest.slippage_rate", slippage_rate)
    cfg.set("periods_per_year", 252)
    cfg.set("compute_backend", "python")
    cfg.set("factor_analysis.level", analysis_level)
    return cfg


_BENCHMARK_FILES = {
    "CSI300": "index_000300.parquet",
    "CSI500": "index_000905.parquet",
    "CSI1000": "index_000852.parquet",
    "SSE50": "index_000016.parquet",
}


def _load_benchmark_equity(benchmark: str, dates: pd.DatetimeIndex) -> pd.Series:
    """加载指数收盘价并对齐、归一化为净值序列。"""
    path = Path(_resolve_data_dir(None)) / "benchmark" / _BENCHMARK_FILES[benchmark]
    frame = pd.read_parquet(path)
    close_col = next(col for col in frame.columns if col.endswith("_close"))
    series = frame[close_col]
    series.index = pd.to_datetime(series.index)
    series = series.reindex(dates).ffill().dropna()
    if series.empty:
        raise ValueError(f"基准 {benchmark} 与回测区间没有重叠数据")
    return series / series.iloc[0]


def _layered_equity_to_points(equity: pd.DataFrame) -> list[LayeredPoint]:
    """分层净值宽表转为前端消费的逐日对象。"""
    points = []
    for date, row in equity.iterrows():
        values = {"date": pd.Timestamp(date).strftime("%Y-%m-%d")}
        for number, value in enumerate(row, start=1):
            values[f"layer{number}"] = float(value)
        points.append(LayeredPoint(**values))
    return points


def _value_points(series: pd.Series) -> list[ValuePoint]:
    return [
        ValuePoint(date=pd.Timestamp(date).strftime("%Y-%m-%d"), value=float(value))
        for date, value in series.items() if pd.notna(value)
    ]


def _ic_points(frame: pd.DataFrame) -> list[ICPoint]:
    if frame.empty:
        return []
    return [
        ICPoint(
            date=pd.Timestamp(date).strftime("%Y-%m-%d"),
            value=float(row["value"]),
            sample_size=int(row["sample_size"]),
        )
        for date, row in frame.iterrows() if pd.notna(row["value"])
    ]


def _rolling_ir_points(series: pd.Series, window: int = 60) -> list[RollingIRPoint]:
    return [
        RollingIRPoint(
            date=pd.Timestamp(date).strftime("%Y-%m-%d"), value=float(value),
            window=window, sample_size=window,
        )
        for date, value in series.items() if pd.notna(value)
    ]


def _industry_equity_to_response(curves: dict[str, pd.Series]) -> list[IndustryEquityCurve]:
    return [
        IndustryEquityCurve(industry_code=industry, industry_name=industry, points=_value_points(series))
        for industry, series in sorted(curves.items()) if not series.empty
    ]


def _industry_group_equity_to_response(
    curves: dict[str, pd.DataFrame],
) -> list[IndustryGroupEquityCurve]:
    result = []
    for industry, equity in sorted(curves.items()):
        points = [
            IndustryGroupPoint(
                date=pd.Timestamp(date).strftime("%Y-%m-%d"),
                groups={str(group): float(value) for group, value in row.items() if pd.notna(value)},
            )
            for date, row in equity.iterrows()
        ]
        if points:
            result.append(IndustryGroupEquityCurve(
                industry_code=industry, industry_name=industry, points=points,
            ))
    return result


def _compute_drawdowns(equity: pd.Series) -> list[DrawdownInfo]:
    """从净值序列计算回撤区间明细。"""
    if equity is None or len(equity) < 2:
        return []

    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max

    drawdowns_list = []
    in_drawdown = False
    peak_date = None
    peak_value = None
    trough_date = None
    trough_value = None

    for date, (eq_val, dd_val) in enumerate(zip(equity.items(), drawdown.items())):
        idx, eq = eq_val
        _, dd = dd_val

        if dd < 0 and not in_drawdown:
            # 开始回撤
            in_drawdown = True
            peak_date = idx
            peak_value = eq
            trough_date = idx
            trough_value = eq
        elif dd < 0 and in_drawdown:
            # 回撤中，更新最低点
            if eq < trough_value:
                trough_date = idx
                trough_value = eq
        elif dd >= 0 and in_drawdown:
            # 回撤恢复
            in_drawdown = False
            depth = (trough_value - peak_value) / peak_value
            days = (idx - peak_date).days
            drawdowns_list.append(
                DrawdownInfo(
                    start=str(peak_date.date()),
                    end=str(trough_date.date()),
                    peak=float(peak_value),
                    trough=float(trough_value),
                    recovery=str(idx.date()),
                    depth=float(depth),
                    days=days,
                )
            )

    # 如果到末尾还在回撤中
    if in_drawdown and trough_date is not None and peak_date is not None:
        depth = (trough_value - peak_value) / peak_value
        days = (equity.index[-1] - peak_date).days
        drawdowns_list.append(
            DrawdownInfo(
                start=str(peak_date.date()),
                end=str(trough_date.date()),
                peak=float(peak_value),
                trough=float(trough_value),
                recovery=None,
                depth=float(depth),
                days=days,
            )
        )

    # 只返回最大的前 10 个回撤
    drawdowns_list.sort(key=lambda x: x.depth)
    return drawdowns_list[:10]


def _compute_annual_returns(equity: pd.Series) -> list[AnnualReturn]:
    """从净值序列计算分年收益。"""
    if equity is None or len(equity) < 2:
        return []

    # 按年分组算收益
    years = equity.index.year.unique()
    result = []
    for year in sorted(years):
        year_data = equity[equity.index.year == year]
        if len(year_data) < 2:
            continue
        ret = (year_data.iloc[-1] - year_data.iloc[0]) / year_data.iloc[0]
        result.append(AnnualReturn(year=int(year), return_value=float(ret)))
    return result


def _sample_positions(
    positions: pd.DataFrame | None, max_snapshots: int = 60, top_n: int = 20
) -> list[PositionSnapshot] | None:
    """对持仓权重进行采样，减少传输量。"""
    if positions is None or len(positions) == 0:
        return None

    # 每隔 N 个点采样一次
    step = max(1, len(positions) // max_snapshots)
    sampled = []

    for idx in range(0, len(positions), step):
        row = positions.iloc[idx]
        date_str = str(positions.index[idx].date()) if hasattr(positions.index[idx], 'date') else str(positions.index[idx])

        # 只取权重最大的 top_n 只
        sorted_row = row.dropna().sort_values(ascending=False)
        top = sorted_row.head(top_n)

        holdings = [
            Holding(symbol=str(sym), weight=float(w))
            for sym, w in top.items()
        ]
        sampled.append(PositionSnapshot(date=date_str, holdings=holdings))

    return sampled


def _compute_equity_with_drawdown(equity: pd.Series) -> list[EquityPoint]:
    """计算净值点序列，包含回撤值。"""
    points = equity_to_points(equity)
    if not points:
        return []

    values = [p["value"] for p in points]
    if not values or values[0] is None:
        return [EquityPoint(date=p["date"], value=0.0, drawdown=0.0) for p in points]

    cummax_val = values[0]
    result = []
    for p, v in zip(points, values):
        if v is None:
            result.append(EquityPoint(date=p["date"], value=0.0, drawdown=0.0))
            continue
        cummax_val = max(cummax_val, v)
        dd = (v - cummax_val) / cummax_val if cummax_val != 0 else 0.0
        result.append(EquityPoint(date=p["date"], value=v, drawdown=dd))
    return result


def _run_factor_backtest_uncached(req: FactorBacktestRequest) -> FactorBacktestResponse:
    """因子回测：因子代码 + 参数 -> 指标 + 净值 + 因子分析。"""
    started_at = time.perf_counter()
    try:
        from researchengine import ExperimentManager

        factor = _load_factor_from_code(req.factor_code, req.factor_name)

        # 组合方式映射
        long_short = req.portfolio_type == "long_short"

        cfg = _build_config(
            commission_rate=req.commission_rate,
            slippage_rate=req.slippage_rate,
            stamp_tax=req.stamp_tax,
            rebalance_days=req.rebalance_days,
            groups=req.groups,
            long_short=long_short,
            analysis_level=req.analysis_level,
        )
        mgr = ExperimentManager()
        exp = mgr.create(
            factor=factor,
            universe=req.universe,
            start=req.start,
            end=req.end,
            config=cfg,
        )
        result = mgr.run(exp)  # ResultManager
    except Exception as exc:  # noqa: BLE001  任何错都回前端
        return FactorBacktestResponse(
            error=f"{type(exc).__name__}: {exc}",
            meta=None,
        )

    equity = result.equity_curve
    final_equity = (
        float(equity.iloc[-1]) if equity is not None and len(equity) else None
    )

    # 净值曲线（含回撤）
    equity_points = _compute_equity_with_drawdown(equity) if equity is not None else None

    # 回撤区间明细
    drawdowns = _compute_drawdowns(equity) if equity is not None else []

    # 分年收益
    annual_returns = _compute_annual_returns(equity) if equity is not None else []

    # 深度因子分析仅在请求显式要求时计算，避免其拖慢核心回测。
    metrics = metrics_to_dict(result.metrics)
    analysis = getattr(result, "factor_analysis", {})
    factor_analysis = None
    if req.analysis_level in {"core", "full"}:
        layered_equity = analysis.get("layered_equity", pd.DataFrame())
        ic_series = analysis.get("ic_series", pd.DataFrame())
        cumulative_ic = analysis.get("cumulative_ic", pd.Series(dtype=float))
        rolling_ir = analysis.get("rolling_ir", pd.Series(dtype=float))
        has_layered_groups = len(layered_equity.columns) >= req.groups
        layered_returns = {
            "groups": req.groups,
            "long_short_return": metrics.get("total_return"),
        }
        if has_layered_groups:
            layered_returns.update({
                f"layer{number}": float(layered_equity.iloc[-1, number - 1] - 1)
                for number in range(1, req.groups + 1)
            })
            layered_returns["spread"] = float(
                layered_equity.iloc[-1, -1] - layered_equity.iloc[-1, 0]
            )
        else:
            layered_returns["spread"] = None
        factor_analysis = FactorAnalysis(
            ic_mean=metrics.get("ic"),
            ic_std=metrics.get("ic_std"),
            rank_ic_mean=metrics.get("rank_ic"),
            layered_returns=layered_returns,
            cumulative_series=_layered_equity_to_points(layered_equity),
            definition={
                "ic_type": "pearson",
                "forward_return_days": 1,
                "signal_lag_days": 0,
                "rolling_ir_window": 60,
                "groups": req.groups,
                "analysis_level": req.analysis_level,
                **({
                    "industry_return_method": "equal_weight_fixed_capital",
                    "industry_grouping_method": "daily_cross_sectional_equal_weight_fixed_capital",
                } if req.analysis_level == "full" else {}),
            },
            ic_series=_ic_points(ic_series),
            cumulative_ic_series=_value_points(cumulative_ic),
            rolling_ir_series=_rolling_ir_points(rolling_ir),
            industry_equity_curves=_industry_equity_to_response(
                analysis.get("industry_equity", {})
            ),
            industry_group_equity_curves=_industry_group_equity_to_response(
                analysis.get("industry_group_equity", {})
            ),
        )
    benchmark_equity = _load_benchmark_equity(req.benchmark, equity.index)
    benchmark_curve = _compute_equity_with_drawdown(benchmark_equity)
    common_dates = equity.index.intersection(benchmark_equity.index)
    excess_return = None
    if len(common_dates):
        strategy_return = equity.loc[common_dates[-1]] / equity.loc[common_dates[0]] - 1
        benchmark_return = benchmark_equity.loc[common_dates[-1]] / benchmark_equity.loc[common_dates[0]] - 1
        excess_return = float(strategy_return - benchmark_return)

    return FactorBacktestResponse(
        metrics=metrics,
        equity_curve=equity_points,
        drawdowns=drawdowns,
        annual_returns=annual_returns,
        factor_analysis=factor_analysis,
        date_range=DateRange(**date_range_from(equity)),
        final_equity=final_equity,
        benchmark_curve=benchmark_curve,
        excess_return=excess_return,
        meta=FactorBacktestMeta(
            factor=req.factor_name,
            universe=req.universe,
            portfolio_type=req.portfolio_type,
            rebalance_days=req.rebalance_days,
            groups=req.groups,
            benchmark=req.benchmark,
            filter_limit_up=req.filter_limit_up,
            filter_suspended=req.filter_suspended,
            timings_seconds={
                **result.meta.get("timings_seconds", {}),
                "api_total": round(time.perf_counter() - started_at, 6),
            },
        ),
        error=None,
    )


def run_strategy_backtest(req: StrategyBacktestRequest) -> StrategyBacktestResponse:
    """策略回测：自定义策略代码 -> 指标 + 净值。"""
    try:
        from quantcore.backtest.adapter import get_backtest_engine
        from quantcore.backtest.adapter.signals import BacktestConfig, BacktestSignals

        # 编译策略代码
        namespace = {"__name__": "user_strategy"}
        exec(compile(req.strategy_code, '<strategy>', 'exec'), namespace)
        strategy_classes = [
            obj for obj in namespace.values()
            if isinstance(obj, type)
            and obj.__module__ == "user_strategy"
            and hasattr(obj, "generate_signals")
        ]
        if len(strategy_classes) != 1:
            raise ValueError("策略代码必须且只能定义一个包含 generate_signals 方法的类")
        strategy_class = strategy_classes[0]
        from quantcore.backtest.adapter.factor_strategy import FactorPortfolioStrategy

        data_dir = _resolve_data_dir(None)
        from quantcore import DataEngine, FieldParquetProvider
        from quantcore.data._util import resolve_universe
        from quantcore.factor.base import Panel

        provider = FieldParquetProvider(data_dir)
        data_engine = DataEngine(provider=provider)
        panels = Panel(
            data_engine.get_panels(req.start, req.end),
            symbols=resolve_universe(provider, req.universe),
            index_loader=lambda name: data_engine.get_index(name, req.start, req.end),
        )
        close = panels.close
        factor_values = None

        # 结构化策略在策略源码内定义因子；自由策略接收收盘价面板自行生成信号。
        if issubclass(strategy_class, FactorPortfolioStrategy):
            strategy = strategy_class()
            signals = strategy.generate_signals(panels)
        else:
            strategy = strategy_class(close=close)
            signals = strategy.generate_signals()
        if isinstance(signals, BacktestSignals):
            bt_signals = signals
        elif isinstance(signals, pd.DataFrame):
            bt_signals = BacktestSignals(target_weights=signals, close=close)
        else:
            raise TypeError(
                "generate_signals 必须返回 pandas.DataFrame 或 BacktestSignals"
            )

        # 跑回测
        bt_config = BacktestConfig(
            engine="native",
            initial_capital=req.initial_capital,
            commission_rate=req.commission_rate,
            slippage_rate=req.slippage_rate,
        )
        bt_engine = get_backtest_engine("native")
        bt_result = bt_engine.run(bt_signals, bt_config)

        equity = bt_result.equity_curve
        returns = bt_result.returns

        # 算指标
        from quantcore.metric.context import MetricContext
        from quantcore.metric.engine import MetricEngine

        metric_engine = MetricEngine()
        ctx = MetricContext(
            equity_curve=equity,
            returns=returns,
            factor_values=factor_values,
            forward_returns=None,
            positions=bt_result.positions,
            periods_per_year=252,
        )
        metrics = metric_engine.calculate_all(ctx)

    except Exception as exc:  # noqa: BLE001
        return StrategyBacktestResponse(
            error=f"{type(exc).__name__}: {exc}",
            meta=None,
        )

    final_equity = float(equity.iloc[-1]) if equity is not None and len(equity) else None
    metrics = metrics_to_dict(metrics)
    if equity is not None and len(equity):
        metrics["total_return"] = float(equity.iloc[-1] / equity.iloc[0] - 1)

    equity_points = _compute_equity_with_drawdown(equity) if equity is not None else None

    drawdowns = _compute_drawdowns(equity) if equity is not None else []
    annual_returns = _compute_annual_returns(equity) if equity is not None else []

    positions = None
    if req.include_positions and bt_result.positions is not None:
        positions = _sample_positions(bt_result.positions)

    return StrategyBacktestResponse(
        metrics=metrics,
        equity_curve=equity_points,
        drawdowns=drawdowns,
        annual_returns=annual_returns,
        date_range=DateRange(**date_range_from(equity)),
        final_equity=final_equity,
        meta=StrategyBacktestMeta(
            strategy=strategy_class.__name__,
            universe=req.universe,
        ),
        positions=positions,
        error=None,
    )
