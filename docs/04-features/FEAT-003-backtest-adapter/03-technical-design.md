# Native 向量化回测设计

> 最后更新：2026-07-31
> 状态：已落地（NativeEngine）

## 目标

向量化回测统一使用 `app.quantcore.backtest.adapter.NativeEngine`。`app.services` 与策略代码只通过 `IBacktestEngine.run(signals, config)` 契约调用，无第三方回测后端或可选运行时依赖。

## 输入与输出

`IStrategy.generate_signals()` 产出 `BacktestSignals`：

- `target_weights`：日期 × 标的目标权重；
- `close`：日期 × 标的收盘价。

`NativeEngine` 返回 `BacktestResult`，包含净值曲线、日收益、收盘后持仓与调仓日志；指标层继续复用 `MetricEngine`。

## 收盘成交时序

统一采用前一日信号对应下一交易日收盘收益：首个交易日收盘生成信号，第二个交易日的收益由首日目标权重承担；净值曲线在第二个交易日归一为 1，第三个交易日起展示收盘到收盘复利收益。

```python
held = target.ffill().shift(1).fillna(0.0)       # t 日目标权重承担 t -> t+1 收益
port_ret = (held * close.pct_change()).sum(axis=1).iloc[1:].dropna()
display_ret = port_ret.copy()
display_ret.iloc[0] = 0.0                         # 次日曲线归一
equity = (1.0 + display_ret).cumprod()
```

交易成本按实际持仓权重变化计算，并计入对应持有期。因子分组与指标层可复用该统一时序；市值/因子导入必须保留完整精度，避免 `qcut` 分位边界被显示精度破坏。

## 使用方式

```python
from app.quantcore import BacktestConfig, get_backtest_engine

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
