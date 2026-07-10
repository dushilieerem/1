"""端到端入口示例。

研究员工作流（对应 ``docs/01-prd.md``）：
在 ``factor/`` 下写入因子代码 -> 修改本文件调用该因子 -> 运行 ``python examples/main.py`` ->
系统读数据、算因子值、算年化收益/最大回撤/calmar/胜率/IC 等指标并保存结果。

本示例另含一段 ``BacktestEngine`` 演示，展示 QuantCore 的交易模拟能力。
"""

from __future__ import annotations

from pathlib import Path

# 研究员入口根目录（用于定位 config.yaml / data / output）
BASE = Path(__file__).resolve().parent.parent

from quantcore import (  # noqa: E402
    BacktestEngine,
    DataEngine,
    FieldParquetProvider,
    Order,
    TransactionCost,
    WideCSVProvider,  # noqa: F401  (宽表 CSV 备用)
)
from researchengine import (  # noqa: E402
    ConfigManager,
    ExperimentManager,
    FactorLoader,
)


def run_factor_experiment() -> None:
    """因子研究主流程：FactorLoader 加载因子 -> ExperimentManager 运行。"""
    print("=" * 60)
    print("① 因子研究流程（ResearchEngine -> QuantCore）")
    print("=" * 60)

    # Step 1: 读取配置
    config = ConfigManager(config_path=str(BASE / "config.yaml"))
    # 数据指向根目录 MarketData（一个字段一个 parquet 的宽表面板）
    config.set("data_dir", str(BASE.parent / "MarketData"))

    # Step 2: 加载因子库，从中取一个因子
    loader = FactorLoader(factor_dir=str(BASE / "factor"))
    loader.load("alpha_library")           # 注册 alpha101, alpha158, ...
    factor = loader.factors["marketcap"]    # 挑一个跑
    print(f"已加载因子: {factor} (来自 AlphaLibrary)")

    # Step 3: 创建并运行实验（start/end 留空 -> 用数据全部区间）
    config.set("output_path", str(BASE / "output" / factor.name))
    mgr = ExperimentManager()
    exp = mgr.create(
        factor=factor,
        universe="CSI500",
        start=None,
        end=None,
        config=config,
    )
    result = mgr.run(exp)

    # Step 4: 打印指标
    print("\n" + result.summary())
    print(f"\n净值区间: {result.equity_curve.index[0].date()} -> "
          f"{result.equity_curve.index[-1].date()}")
    print(f"最终权益: {result.equity_curve.iloc[-1]:.4f}")
    print(f"结果已保存至: {BASE / 'output' / factor.name}")


def run_backtest_demo() -> None:
    """BacktestEngine 演示：等权建仓并持有。"""
    print("\n" + "=" * 60)
    print("② BacktestEngine 演示（交易模拟）")
    print("=" * 60)

    data_engine = DataEngine(FieldParquetProvider(str(BASE.parent / "MarketData")))
    universe = data_engine.get_universe()[:10]  # 取 10 只做演示
    start, end = "2025-09-01", "2026-04-30"

    bt = BacktestEngine(
        data_engine=data_engine,
        cost_model=TransactionCost(
            commission_rate=0.0003, slippage_rate=0.001,
        ),
        start_date=start,
        end_date=end,
        initial_capital=1_000_000.0,
    )

    def strategy(bar, portfolio):
        """首日等权建仓后持有。"""
        orders = []
        prices = bar.dropna()
        if not portfolio.positions and not prices.empty and portfolio.cash > 0:
            per = portfolio.cash * 0.9 / len(prices)
            for sym, price in prices.items():
                qty = int(per / price / 100) * 100  # 100 股/手
                if qty > 0:
                    orders.append(
                        Order(symbol=sym, direction=1, quantity=qty, order_type="market")
                    )
        return orders

    result = bt.run(strategy, universe=universe, start=start, end=end)
    print(f"回测最终权益: {result.equity_curve.iloc[-1]:.2f}")
    print(f"成交笔数: {len(result.fills)}")
    print(f"手续费合计: {sum(f.commission for f in result.fills):.2f}")


if __name__ == "__main__":
    run_factor_experiment()
    run_backtest_demo()
