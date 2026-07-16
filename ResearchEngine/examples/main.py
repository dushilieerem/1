"""端到端回测示例：MA5/Close 因子，市值加权，纯多头，沪深300。

因子逻辑：5日移动均线 / 今日收盘价
  - 比值 > 1 → 股价低于均线（超卖信号）
  - 比值 < 1 → 股价高于均线（超买信号）
持仓加权方式：按市值加权（选中的股票内按总市值比例分配权重）
组合方式：纯多头（long_only）
股票池：沪深300（CSI300）
回测区间：2017-01-01 ~ 2026-01-01
基准：沪深300指数
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# 根目录
BASE = Path(__file__).resolve().parent.parent

from quantcore import (
    DataEngine,
    FieldParquetProvider,
    MetricEngine,
    Panel,
)
from quantcore.backtest.adapter import (
    BacktestConfig,
    FactorQuantileStrategy,
    get_backtest_engine,
)
from quantcore.backtest.result import BacktestResult
from quantcore.metric.context import MetricContext


def compute_factor(close: pd.DataFrame) -> pd.DataFrame:
    """因子：5日移动均线 / 今日收盘价。"""
    ma5 = close.rolling(5).mean()
    return ma5 / close


def load_benchmark() -> pd.Series:
    """加载沪深300指数作为基准。"""
    bench_path = BASE.parent / "MarketData" / "benchmark" / "index_000300.parquet"
    if not bench_path.exists():
        print("⚠ 基准文件不存在，跳过基准对比")
        return None
    idx = pd.read_parquet(bench_path)
    close_col = [c for c in idx.columns if "close" in c.lower()][0]
    series = idx[close_col]
    # 归一化到 1.0
    series = series / series.iloc[0]
    return series


def run_main() -> None:
    print("=" * 60)
    print("SVQuant 因子回测示例")
    print("=" * 60)
    print()

    # ===== 1. 数据准备 =====
    data_dir = str(BASE.parent / "MarketData")
    print(f"数据目录: {data_dir}")
    print()

    # 数据引擎
    provider = FieldParquetProvider(data_dir)
    data_engine = DataEngine(provider=provider)

    # 回测参数
    start_date = "2017-01-01"
    end_date = "2026-01-01"

    # ===== 2. 获取数据 =====
    print(f"获取数据: {start_date} ~ {end_date}")
    raw_panels = data_engine.get_panels(start_date, end_date)
    panel = Panel(raw_panels)
    close = panel.close
    total_mv = panel.total_mv

    # 解析沪深300成分股（从基准成分股文件读取）
    const_path = BASE.parent / "MarketData" / "benchmark" / "CSI300_constituents.parquet"
    if const_path.exists():
        print("加载沪深300成分股列表...")
        cs = pd.read_parquet(const_path)
        # 取最接近开始日期的一个快照
        mask_date = cs.index[cs.index <= start_date]
        if len(mask_date) > 0:
            members = cs.loc[mask_date[-1]]
            csi300_symbols = members[members == 1].index.tolist()
        else:
            csi300_symbols = cs.columns.tolist()
        # 去掉后缀（.SZ/.SH）以匹配市场数据格式
        csi300_symbols_clean = [s.split('.')[0] for s in csi300_symbols]
        print(f"沪深300成分股: {len(csi300_symbols_clean)} 只")
        # 过滤到沪深300成分股
        close = close.reindex(columns=[c for c in close.columns if c in csi300_symbols_clean])
        total_mv = total_mv.reindex(columns=[c for c in total_mv.columns if c in csi300_symbols_clean])
    else:
        print("⚠ 成分股文件不存在，使用全市场数据")

    # ===== 3. 计算因子 =====
    print("计算因子: MA5 / Close ...")
    factor_values = compute_factor(close)
    factor_values = factor_values.dropna(how="all")

    # ===== 4. 构建策略 =====
    print("构建策略: 纯多头 + 市值加权 ...")
    strategy = FactorQuantileStrategy(
        factor_values=factor_values,
        close=close,
        rebalance="monthly",
        stock_num=100,
        long_short=False,             # 纯多头
        weight_by=total_mv,          # 市值加权
    )
    signals = strategy.generate_signals()

    # ===== 5. 跑回测 =====
    print("执行回测（native 引擎）...")
    bt_config = BacktestConfig(
        engine="native",
        initial_capital=1_000_000,
        commission_rate=0.0003,
        slippage_rate=0.001,
    )
    bt_engine = get_backtest_engine("native")
    bt_result: BacktestResult = bt_engine.run(signals, bt_config)

    equity = bt_result.equity_curve
    returns = bt_result.returns

    # ===== 6. 算指标 =====
    print("计算指标...")
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

    # ===== 7. 输出结果 =====
    print()
    print("=" * 60)
    print("回测结果")
    print("=" * 60)
    print(f"因子: MA5 / Close")
    print(f"区间: {start_date} ~ {end_date}")
    print(f"股票池: CSI300")
    print(f"组合: 纯多头 + 市值加权")
    print(f"调仓: 月频")
    print()

    # 核心指标
    def s(v, default="N/A"):
        val = metrics.get(v)
        if val is None:
            return default
        return val

    print(f"夏普比率:       {s('sharpe', 0):.2f}")
    print(f"年化收益:       {s('annual_return', 0):.2%}")
    print(f"最大回撤:       {s('max_drawdown', 0):.2%}")
    print(f"年化波动率:     {s('volatility', 0):.2%}")
    print(f"Calmar比率:     {s('calmar', 0):.2f}")
    print(f"胜率:           {s('win_rate', 0):.2%}")
    print(f"总收益率:       {s('total_return', 0):.2%}")
    print(f"成交次数:       {s('trade_count', 0):.0f}")
    print(f"IC均值:         {s('ic', 0):.4f}")
    print(f"Rank IC:        {s('rank_ic', 0):.4f}")
    print(f"最终净值:       {float(equity.iloc[-1]):.4f}")

    # ===== 8. 基准对比 =====
    bench = load_benchmark()
    if bench is not None:
        # 对齐日期
        common = equity.index.intersection(bench.index)
        if len(common) > 0:
            eq_aligned = equity[common]
            bench_aligned = bench[common]
            # 基准也归一化到1
            bench_aligned = bench_aligned / bench_aligned.iloc[0]
            excess = eq_aligned.iloc[-1] - bench_aligned.iloc[-1]
            print()
            print("--- 基准对比（沪深300）---")
            print(f"策略收益:       {eq_aligned.iloc[-1] - 1:.2%}")
            print(f"基准收益:       {bench_aligned.iloc[-1] - 1:.2%}")
            print(f"超额收益:       {excess:.2%}")

    print()
    print("=" * 60)
    print("回测完成")
    print("=" * 60)


if __name__ == "__main__":
    run_main()
