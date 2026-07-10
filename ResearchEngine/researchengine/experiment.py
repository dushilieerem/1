"""``Experiment`` - ResearchEngine 的核心对象。

依据 ``docs/04-类设计.md`` Experiment 节与 ``docs/05-运行流程图.md`` 第 2 节：

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

from typing import Optional
from pathlib import Path

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
from researchengine.portfolio import build_factor_portfolio, forward_returns
from researchengine.result.manager import ResultManager
from researchengine.result.storage import CSVStorage, SQLiteStorage

_STORAGE_MAP = {
    "csv": CSVStorage,
    "sqlite": SQLiteStorage,
}


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

    # -- 执行实验 --
    def run(self) -> ResultManager:
        """执行完整实验流程，返回 :class:`ResultManager`。"""
        # ① 读取配置 / 构建引擎
        self._build_engines()

        # ② 取面板一次，因子与组合复用（懒加载：只读因子/组合真正用到的字段）
        panels = self._data_engine.get_panels(self.start_date, self.end_date)
        symbols = resolve_universe(self._data_engine, self.universe)
        panel = Panel(panels, symbols=symbols)

        # ③a 因子计算（复用已取面板）
        factor_values = self._factor_engine.compute_panel(self.factor.name, panel)
        if factor_values.empty:
            raise RuntimeError("因子计算结果为空，请检查数据源/区间/universe。")

        # 取收盘价宽表，构造远期收益与组合（触发 close 懒加载）
        if "close" not in panel:
            raise RuntimeError("数据中缺少 close 字段，无法构建组合。")
        close_panel = panel.close
        horizon = int(self.config.get("ic_horizon", 1))
        fwd = forward_returns(close_panel, horizon=horizon)

        # ③b 组合净值（向量化分位组合）
        equity, returns, positions = build_factor_portfolio(
            factor_values,
            close_panel,
            rebalance=self.config.get("rebalance", "monthly"),
            n_groups=int(self.config.get("n_groups", 5)),
            long_short=bool(self.config.get("long_short", True)),
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
        metrics = self._metric_engine.calculate_all(ctx)

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

        # ⑤ 保存结果 + 累计收益-回撤图
        out_path = self.config.get("output_path")
        if out_path:
            result.save(out_path)
            # 图表落到输出目录（CSV 存到目录内；SQLite/CH 存到同目录）
            out = Path(out_path)
            chart_dir = out if out.is_dir() else out.parent
            try:
                from researchengine.plotting import plot_equity_drawdown

                png = plot_equity_drawdown(
                    equity, chart_dir / "equity_drawdown.png",
                    title=f"{self.factor.name} 累计收益 - 回撤",
                )
                if png:
                    result.meta["chart"] = png
            except Exception as exc:  # 绘图失败不影响主流程
                print(f"[warn] 绘图失败: {exc}")

            # 分组 IC 图（与收益-回撤图独立，互不影响）
            try:
                from researchengine.plotting import plot_group_ic

                png = plot_group_ic(
                    factor_values, fwd, chart_dir / "group_ic.png",
                    n_groups=int(self.config.get("n_groups", 5)),
                    title=f"{self.factor.name} 分组 IC",
                )
                if png:
                    result.meta["chart_group_ic"] = png
            except Exception as exc:  # 绘图失败不影响主流程
                print(f"[warn] 分组 IC 图绘制失败: {exc}")

        self.result = result
        return result

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Experiment factor={self.factor.name!r} universe={self.universe!r} "
            f"{self.start_date}~{self.end_date}>"
        )
