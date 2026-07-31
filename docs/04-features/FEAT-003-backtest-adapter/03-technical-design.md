# Native 向量化回测设计

> 最后更新：2026-07-31
> 状态：已落地（NativeEngine）

## 目标

向量化回测统一使用 `QuantCore.backtest.adapter.NativeEngine`。ResearchEngine 与策略代码只通过 `IBacktestEngine.run(signals, config)` 契约调用，无第三方回测后端或可选运行时依赖。

## 输入与输出

`IStrategy.generate_signals()` 产出 `BacktestSignals`：

- `target_weights`：日期 × 标的目标权重；
- `close`：日期 × 标的收盘价。

`NativeEngine` 返回 `BacktestResult`，包含净值曲线、日收益、收盘后持仓与调仓日志；指标层继续复用 `MetricEngine`。

## 收盘成交时序

统一采用收盘价成交：首个交易日收盘生成信号，第二个交易日收盘成交并将净值归一为 1，第三个交易日开始计算收盘到收盘收益。

```python
executed = target.ffill().shift(1).fillna(0.0)  # t+1 收盘成交
held = executed.shift(1).fillna(0.0)            # t+2 起承担收益
port_ret = (held * close.pct_change()).sum(axis=1).iloc[1:].dropna()
equity = 1.0 + port_ret.cumsum()
```

交易成本按实际成交权重变化计算，并计入随后的持有期，使建仓日与基准都从 0% 开始展示。

## 使用方式

```python
from quantcore import BacktestConfig, get_backtest_engine

result = get_backtest_engine("native").run(signals, BacktestConfig())
```

`ResearchEngine/config.yaml` 固定使用：

```yaml
backtest:
  engine: native
```

## 边界

- 本模块仅负责批量、日频向量化研究回测。
- A 股逐笔成交、T+1、涨跌停与订单生命周期由事件驱动引擎负责。
- 若未来需要新后端，须重新完成设计评审、契约测试和数据口径验证后再加入注册表。
