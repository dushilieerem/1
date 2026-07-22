"""``Experiment`` - ResearchEngine 的核心对象。

依据 ``docs/04-features/FEAT-002-research-engine/04-class-design.md`` Experiment 节与 ``docs/04-features/FEAT-002-research-engine/05-runtime-flow.md`` 第 2 节：

    属性：
      factor: BaseFactor
      universe: str
      start_date: str
      end_date: str
      config: ConfigManager
      result: ResultManager | None

    方法：
      run() -> ResultManager

内部流程：读取配置 -> 加载因子 -> 调用 QuantCore(Data/Factor/Metric) ->
得到结果 -> 保存结果。Experiment 只组织流程，不计算收益。
"""

from __future__ import annotations

from typing import Callable, Optional
from pathlib import Path
import math
import time

import pandas as pd

from quantcore import (
    BaseFactor,
    BacktestEngine,  # noqa: F401  (可选用)
    CSVDataProvider,
    DataEngine,
    FactorEngine,
    FieldParquetProvider,
    MetricEngine,
    Panel,
    WideCSVProvider,
)
from quantcore.data._util import resolve_universe
from quantcore.metric.context import MetricContext

from researchengine.config import ConfigManager
from researchengine.plotting import (
    plot_equity_drawdown,
    plot_group_ic,
    plot_ic_analysis,
    plot_layered_equity,
    plot_long_short,
    plot_industry_ic_ir,
    plot_ff3_attribution,
)
from researchengine.portfolio import forward_returns
from researchengine.result.manager import ResultManager
from researchengine.result.storage import CSVStorage, ParquetStorage, SQLiteStorage

_STORAGE_MAP = {
    "csv": CSVStorage,
    "parquet": ParquetStorage,
    "sqlite": SQLiteStorage,
}


def _daily_ic_series(factor_values: pd.DataFrame, forward_returns: pd.DataFrame) -> pd.DataFrame:
    """计算日频 Pearson IC 与每个截面的有效样本数。"""
    dates = factor_values.index.intersection(forward_returns.index)
    symbols = factor_values.columns.intersection(forward_returns.columns)
    if dates.empty or symbols.empty:
        return pd.DataFrame(columns=["value", "sample_size"])
    factor = factor_values.loc[dates, symbols]
    returns = forward_returns.loc[dates, symbols]
    valid = factor.notna() & returns.notna()
    result = pd.DataFrame({
        "value": factor.corrwith(returns, axis=1),
        "sample_size": valid.sum(axis=1),
    }).dropna(subset=["value"])
    return result[result["sample_size"] >= 2]


def _industry_equity_analysis(
    factor_values: pd.DataFrame,
    forward_returns: pd.DataFrame,
    industry_map: pd.Series,
    groups: int,
) -> tuple[dict[str, pd.Series], dict[str, pd.DataFrame]]:
    """生成行业等权收益及行业内因子分组的固定本金净值。"""
    dates = factor_values.index.intersection(forward_returns.index)
    symbols = factor_values.columns.intersection(forward_returns.columns)
    industries = industry_map.reindex(symbols).dropna()
    symbols = symbols.intersection(industries.index)
    if dates.empty or symbols.empty:
        return {}, {}

    industry_returns: dict[str, list[tuple[object, float]]] = {}
    industry_group_returns: dict[str, list[tuple[object, dict[str, float]]]] = {}
    for date in dates:
        frame = pd.DataFrame({
            "factor": factor_values.loc[date, symbols],
            "return": forward_returns.loc[date, symbols],
            "industry": industries.reindex(symbols),
        }).dropna()
        for industry, values in frame.groupby("industry", sort=True):
            name = str(industry)
            industry_returns.setdefault(name, []).append((date, float(values["return"].mean())))
            if len(values) < groups:
                continue
            ranks = values["factor"].rank(pct=True, method="average")
            labels = (ranks.mul(groups).apply(math.ceil).clip(upper=groups)).astype(int)
            group_returns = {
                f"G{group}": float(values.loc[labels == group, "return"].mean())
                for group in range(1, groups + 1)
            }
            if all(pd.notna(value) for value in group_returns.values()):
                industry_group_returns.setdefault(name, []).append((date, group_returns))

    equity_curves = {
        industry: 1.0 + pd.Series(dict(rows)).sort_index().cumsum()
        for industry, rows in industry_returns.items()
    }
    group_curves = {
        industry: 1.0 + pd.DataFrame(dict(rows)).T.sort_index().cumsum()
        for industry, rows in industry_group_returns.items()
    }
    return equity_curves, group_curves


class Experiment:
    """一次因子实验。"""

    def __init__(
        self,
        factor: BaseFactor,
        universe: str = "CSI500",
        start_date: str = "2020-01-01",
        end_date: str = "2024-12-31",
        config: Optional[ConfigManager] = None,
        *,
        data_engine: Optional[DataEngine] = None,
        factor_engine: Optional[FactorEngine] = None,
        metric_engine: Optional[MetricEngine] = None,
    ) -> None:
        self.factor: BaseFactor = factor
        self.universe: str = universe
        self.start_date: str = start_date
        self.end_date: str = end_date
        self.config: ConfigManager = config or ConfigManager()
        self.result: Optional[ResultManager] = None

        # QuantCore 引擎（可注入，否则按 config 构造默认）
        self._data_engine = data_engine
        self._factor_engine = factor_engine
        self._metric_engine = metric_engine

    # -- 构建默认 QuantCore 引擎 --
    def _build_engines(self) -> None:
        if self._data_engine is None:
            import os

            data_dir = self.config.get("data_dir", "./data")
            # 文件 -> 宽表 CSV；目录里有 *.parquet -> 字段 parquet；否则逐只 CSV
            if os.path.isfile(data_dir):
                provider = WideCSVProvider(data_dir)
            elif os.path.isdir(data_dir) and any(Path(data_dir).glob("*.parquet")):
                provider = FieldParquetProvider(data_dir)
            else:
                provider = CSVDataProvider(data_dir)
            self._data_engine = DataEngine(provider)

        if self._factor_engine is None:
            backend = self.config.get("compute_backend", "python")
            self._factor_engine = FactorEngine(backend=backend)
        if self.factor.name not in self._factor_engine.factors:
            self._factor_engine.register(self.factor)

        if self._metric_engine is None:
            self._metric_engine = MetricEngine()

    def _build_storage(self):
        kind = self.config.get("storage", "csv")
        if kind not in _STORAGE_MAP:
            raise ValueError(f"未知 storage {kind!r}，可选: {list(_STORAGE_MAP)}")
        return _STORAGE_MAP[kind]()

    @staticmethod
    def _attach_chart(
        result: ResultManager,
        meta_key: str,
        plot_fn: Callable,
        *args,
        **kwargs,
    ) -> None:
        """绘图并挂到 ``result.meta``；绘图失败不阻断主流程（指标已算完并保存）。

        matplotlib 为必装依赖，无需懒加载；两图各自独立守护，互不影响。
        """
        try:
            png = plot_fn(*args, **kwargs)
            if png:
                result.meta[meta_key] = png
        except Exception as exc:  # noqa: BLE001  绘图为副作用，失败不丢指标
            print(f"[warn] {meta_key} 绘图失败: {exc}")

    # -- 因子评估增强（分层 / 多空 / 基准 / 三因子归因 / 分行业 IC）--
    def _run_factor_analysis(self, panel, factor_values, close_panel, fwd) -> dict:
        """分层回测、多空、市值加权基准、三因子归因、分行业 IC/IR。

        数据缺失或失败 graceful skip（与 ``_attach_chart`` 守护一致），不阻断主流程。
        返回 dict，键可能含：``layered_equity`` / ``long_short_returns`` /
        ``long_short_equity`` / ``benchmark_equity`` / ``market_cap_layered`` /
        ``ff3`` / ``ff3_regression`` / ``industry_ic_ir``。
        """
        if not self.config.get("factor_analysis.enabled", True):
            return {}
        from researchengine.layered import (
            layered_equity,
            layered_returns,
            long_short_returns,
        )
        from researchengine.riskmodel import (
            ff3_factors,
            ff3_regression,
            industry_ic_ir,
            market_weighted_returns,
        )

        out: dict = {}
        n_groups = int(
            self.config.get("n_layered_groups", self.config.get("n_groups", 5))
        )
        rebalance = self.config.get("rebalance_days", self.config.get("rebalance", "monthly"))

        ic_series = _daily_ic_series(factor_values, fwd)
        out["ic_series"] = ic_series
        out["cumulative_ic"] = ic_series["value"].cumsum()
        rolling_window = 60
        rolling = ic_series["value"].rolling(rolling_window, min_periods=rolling_window)
        rolling_ir = rolling.mean() / rolling.std(ddof=1)
        out["rolling_ir"] = rolling_ir.dropna()

        # 因子分层 + 多空
        try:
            lr = layered_returns(
                factor_values, close_panel, n_groups=n_groups, rebalance=rebalance
            )
            out["layered_equity"] = layered_equity(lr)
            ls = long_short_returns(lr)
            out["long_short_returns"] = ls
            out["long_short_equity"] = 1.0 + ls.cumsum()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 分层回测失败: {exc}")

        # 基准 / 分市值分层 / FF3（需 total_mv）
        if "total_mv" in panel:
            try:
                total_mv = panel.total_mv
                mkt_ret = market_weighted_returns(
                    close_panel, total_mv, rebalance=rebalance
                )
                out["benchmark_equity"] = 1.0 + mkt_ret.cumsum()
                out["market_cap_layered"] = layered_equity(
                    layered_returns(
                        total_mv, close_panel, n_groups=n_groups, rebalance=rebalance
                    )
                )
                if "pb" in panel:
                    ff3 = ff3_factors(
                        close_panel, total_mv, panel.pb,
                        rebalance=rebalance, n_groups=n_groups,
                    )
                    out["ff3"] = ff3
                    if "long_short_returns" in out:
                        out["ff3_regression"] = ff3_regression(
                            out["long_short_returns"], ff3
                        )
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] 基准/市值分层/FF3 构造失败: {exc}")

        # 分行业 IC/IR（需 stock_info）
        ind_map = self._load_industry_map()
        if ind_map is not None:
            try:
                out["industry_ic_ir"] = industry_ic_ir(factor_values, fwd, ind_map)
                industry_equity, industry_group_equity = _industry_equity_analysis(
                    factor_values, fwd, ind_map, n_groups
                )
                out["industry_equity"] = industry_equity
                out["industry_group_equity"] = industry_group_equity
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] 分行业 IC 失败: {exc}")

        return out

    def _run_core_group_analysis(
        self, factor_values: pd.DataFrame, close_panel: pd.DataFrame,
    ) -> dict:
        """核心回测只计算全市场分组收益，不执行行业与归因诊断。"""
        from researchengine.layered import layered_equity, layered_returns

        groups = int(self.config.get("n_layered_groups", self.config.get("n_groups", 5)))
        rebalance = self.config.get("rebalance_days", self.config.get("rebalance", "monthly"))
        returns = layered_returns(
            factor_values, close_panel, n_groups=groups, rebalance=rebalance,
        )
        return {"layered_equity": layered_equity(returns)}

    def _load_industry_map(self) -> Optional[pd.Series]:
        """读 ``stock_info.parquet`` -> ``{code: industry}``。无文件返回 None。

        ``stock_info`` 是非面板文件（被 :class:`FieldParquetProvider` 跳过），单独读。
        """
        data_dir = self.config.get("data_dir", "./data")
        p = Path(data_dir) / "stock_info.parquet"
        if not p.exists():
            return None
        try:
            df = pd.read_parquet(p)
            if "industry" not in df.columns:
                return None
            for code_column in ("code", "symbol", "ts_code"):
                if code_column in df.columns:
                    return df.set_index(code_column)["industry"]
            return df["industry"]
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 读取 stock_info 失败: {exc}")
        return None

    # -- 执行实验 --
    def run(self) -> ResultManager:
        """执行完整实验流程，返回 :class:`ResultManager`。"""
        timings: dict[str, float] = {}
        # ① 读取配置 / 构建引擎
        started_at = time.perf_counter()
        self._build_engines()
        timings["engine_setup"] = time.perf_counter() - started_at
        print("① 读取配置 / 构建引擎 完毕")

        # ② 取面板一次，因子与组合复用（懒加载：只读因子/组合真正用到的字段）
        started_at = time.perf_counter()
        panels = self._data_engine.get_panels(self.start_date, self.end_date)
        symbols = resolve_universe(self._data_engine, self.universe)
        panel = Panel(
            panels,
            symbols=symbols,
            index_loader=lambda name: self._data_engine.get_index(
                name, self.start_date, self.end_date
            ),
        )
        timings["panel_setup"] = time.perf_counter() - started_at
        print("数据读取完毕")

        # ③a 因子计算（复用已取面板）
        started_at = time.perf_counter()
        factor_values = self._factor_engine.compute_panel(self.factor.name, panel)
        timings["factor_compute"] = time.perf_counter() - started_at
        if factor_values.empty:
            raise RuntimeError("因子计算结果为空，请检查数据源/区间/universe。")
        print("因子值计算完毕")

        # 取收盘价宽表，构造远期收益与组合（触发 close 懒加载）
        if "close" not in panel:
            raise RuntimeError("数据中缺少 close 字段，无法构建组合。")
        started_at = time.perf_counter()
        close_panel = panel.close
        common_symbols = factor_values.columns.intersection(close_panel.columns)
        if len(common_symbols) == 0:
            raise ValueError(
                "因子返回值未包含股票池中的标的。指数序列（如 self.csi300.close）"
                "不能直接作为股票因子返回；请与 self.close 按日期对齐后构造股票宽表。"
            )
        horizon = int(self.config.get("ic_horizon", 1))
        fwd = forward_returns(close_panel, horizon=horizon)

        # ③b 组合净值（适配器：默认 native 与 build_factor_portfolio 逐位等价；
        #    config 设 backtest.engine=vectorbt 走 vectorbt 后端。
        #    成本从 backtest.* 读，默认 0 -> 不改默认结果；与历史 commission/slippage
        #    （旧 BacktestEngine 演示用）解耦。）
        from quantcore.backtest.adapter import (
            BacktestConfig,
            FactorGroupStrategy,
            FactorQuantileStrategy,
            get_backtest_engine,
        )

        groups = self.config.get("groups")
        if groups is None:
            strategy = FactorQuantileStrategy(
                factor_values,
                close_panel,
                rebalance=self.config.get("rebalance", "monthly"),
                stock_num=int(self.config.get("stock_num", 100)),
                long_short=bool(self.config.get("long_short", True)),
            )
        else:
            strategy = FactorGroupStrategy(
                factor_values,
                close_panel,
                groups=int(groups),
                rebalance_days=int(self.config.get("rebalance_days", 20)),
                long_short=bool(self.config.get("long_short", True)),
            )
        bt_config = BacktestConfig(
            engine=self.config.get("backtest.engine", "native"),
            initial_capital=float(self.config.get("backtest.initial_capital", 1_000_000)),
            commission_rate=float(self.config.get("backtest.commission_rate", 0.0)),
            min_commission=float(self.config.get("backtest.min_commission", 0.0)),
            slippage_rate=float(self.config.get("backtest.slippage_rate", 0.0)),
            periods_per_year=int(self.config.get("periods_per_year", 252)),
        )
        bt_result = get_backtest_engine(bt_config.engine).run(
            strategy.generate_signals(), bt_config
        )
        timings["signal_and_backtest"] = time.perf_counter() - started_at
        equity, returns, positions = (
            bt_result.equity_curve,
            bt_result.returns,
            bt_result.positions,
        )

        # ③c 指标计算
        ctx = MetricContext(
            equity_curve=equity,
            returns=returns,
            factor_values=factor_values,
            forward_returns=fwd,
            positions=positions,
            periods_per_year=int(self.config.get("periods_per_year", 252)),
        )
        started_at = time.perf_counter()
        metrics = self._metric_engine.calculate_all(ctx)
        timings["metric_calculation"] = time.perf_counter() - started_at
        print("指标计算完毕")

        # ④ 得到结果
        storage = self._build_storage()
        result = ResultManager(
            metrics=metrics,
            factor_values=factor_values,
            equity_curve=equity,
            positions=positions,
            storage=storage,
            meta={
                "factor": self.factor.name,
                "author": self.factor.author,
                "universe": self.universe,
                "start_date": self.start_date,
                "end_date": self.end_date,
            },
        )
        print("结果保存完毕")

        # ④b 因子评估增强：分层/多空/基准/三因子归因/分行业IC（数据齐才做，失败不阻断）
        started_at = time.perf_counter()
        analysis_level = self.config.get("factor_analysis.level", "full")
        if analysis_level == "full":
            factor_analysis = self._run_factor_analysis(
                panel, factor_values, close_panel, fwd,
            )
        elif analysis_level == "core":
            factor_analysis = self._run_core_group_analysis(factor_values, close_panel)
        else:
            factor_analysis = {}
        timings["factor_analysis"] = time.perf_counter() - started_at
        result.factor_analysis = factor_analysis
        result.meta["timings_seconds"] = {
            name: round(value, 6) for name, value in timings.items()
        }
        _reg = factor_analysis.get("ff3_regression")
        if _reg and _reg.get("n_obs", 0) > 0 and not math.isnan(_reg.get("alpha", float("nan"))):
            result.set_metric("ff3_alpha", _reg["alpha"])
            result.set_metric("ff3_beta_mkt", _reg["beta_mkt"])
            result.set_metric("ff3_beta_smb", _reg["beta_smb"])
            result.set_metric("ff3_beta_hml", _reg["beta_hml"])
            result.set_metric("ff3_r_squared", _reg["r_squared"])

        # ⑤ 保存结果 + 绘图（matplotlib 为必装依赖；绘图失败不阻断主流程，指标已保存）
        out_path = self.config.get("output_path")
        if out_path:
            result.save(out_path)
            out = Path(out_path)
            chart_dir = out if out.is_dir() else out.parent
            bench = factor_analysis.get("benchmark_equity")
            self._attach_chart(
                result, "chart", plot_equity_drawdown,
                equity, chart_dir / "equity_drawdown.png",
                title=f"{self.factor.name} 累计收益 - 回撤",
                benchmark=bench,
            )
            self._attach_chart(
                result, "chart_group_ic", plot_group_ic,
                factor_values, fwd, chart_dir / "group_ic.png",
                n_groups=int(self.config.get("n_groups", 5)),
                title=f"{self.factor.name} 分组 IC",
            )
            self._attach_chart(
                result, "chart_ic_analysis", plot_ic_analysis,
                factor_values, fwd, chart_dir / "ic_analysis.png",
                window=int(self.config.get("ic_ir_window", 60)),
                title=f"{self.factor.name} IC 分析",
            )
            # 因子分层回测（叠基准）
            if factor_analysis.get("layered_equity") is not None:
                self._attach_chart(
                    result, "chart_layered", plot_layered_equity,
                    factor_analysis["layered_equity"], chart_dir / "layered_equity.png",
                    title=f"{self.factor.name} 分层回测", benchmark=bench,
                )
            # 多空收益
            if factor_analysis.get("long_short_equity") is not None:
                self._attach_chart(
                    result, "chart_long_short", plot_long_short,
                    factor_analysis["long_short_equity"], chart_dir / "long_short.png",
                    title=f"{self.factor.name} 多空收益",
                )
            # 分市值分层
            if factor_analysis.get("market_cap_layered") is not None:
                self._attach_chart(
                    result, "chart_market_cap_layered", plot_layered_equity,
                    factor_analysis["market_cap_layered"], chart_dir / "market_cap_layered.png",
                    title=f"{self.factor.name} 分市值分层",
                )
            # 分行业 IC/IR
            _ind = factor_analysis.get("industry_ic_ir")
            if _ind is not None and not getattr(_ind, "empty", True):
                self._attach_chart(
                    result, "chart_industry_ic_ir", plot_industry_ic_ir,
                    _ind, chart_dir / "industry_ic_ir.png",
                    title=f"{self.factor.name} 分行业 IC/IR",
                )
            # 三因子归因
            if factor_analysis.get("ff3_regression") is not None:
                self._attach_chart(
                    result, "chart_ff3_attribution", plot_ff3_attribution,
                    factor_analysis["ff3_regression"], chart_dir / "ff3_attribution.png",
                    title=f"{self.factor.name} 三因子归因",
                )

        self.result = result
        return result

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Experiment factor={self.factor.name!r} universe={self.universe!r} "
            f"{self.start_date}~{self.end_date}>"
        )
