# 向量化策略编写规范

> 适用对象：因子选股、Top-N、固定节奏调仓和参数研究
> 运行入口：`POST /api/backtest/strategy`

## 1. 契约

向量化策略只输出“日期 × 标的”的目标权重矩阵。它不提交订单，不维护持仓状态，也不模拟 T+1 或涨跌停订单拒绝。

适合复杂度主要来自横截面选股的策略；突破、止损和状态机策略应改用[事件策略](03-event-strategy-writing.md)。

## 2. 推荐：结构化因子组合策略

```python
from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,
)

class SmallCapMomentumStrategy(FactorPortfolioStrategy):
    selector = TopN(30)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(20)

    @factor
    def momentum_20d(self):
        return self.close.pct_change(20)

    @factor
    def value_ep(self):
        return 1.0 / self.pe_ttm

    @signal
    def score(self):
        return 0.6 * self.rank(self.momentum_20d()) + 0.4 * self.rank(self.value_ep())
```

- 必须且只能定义一个 `@signal` 方法。
- `@signal` 返回综合分数宽表，不返回订单或权重。
- `rank`、`zscore`、`winsorize`、`normalize` 都按每日横截面计算。
- `TopN`、`EqualWeight` 和 `EveryNTradingDays` 分别负责选股、权重与调仓节奏。

## 3. 自由目标权重策略

策略源码必须且只能包含一个带 `generate_signals()` 的类。当前 API 使用 `close` 关键字参数构造策略：

```python
import pandas as pd

class PriceMomentumStrategy:
    def __init__(self, close: pd.DataFrame):
        self.close = close

    def generate_signals(self) -> pd.DataFrame:
        momentum = self.close.pct_change(20)
        ranks = momentum.rank(axis=1, ascending=False, method="first")
        weights = pd.DataFrame(0.0, index=self.close.index, columns=self.close.columns)
        weights[ranks <= 30] = 1.0 / 30
        return weights
```

输出规则：

- 索引为交易日、列为标的代码；建议直接复用 `self.close.index` 和 `self.close.columns`。
- 正数为多头、负数为空头、`0.0` 为清仓。
- `NaN` 表示不更新，沿用上一期目标；`0.0` 表示明确清仓。
- 不要返回价格、订单、交易记录或 `BacktestSignals`。

## 4. 边界与安全

- 不要使用 `close.shift(-1)` 等未来数据。
- 不要自行读文件、联网、写结果或调用回测引擎。
- 当前自由策略没有 `factor_values` 或 `strategy_params` 构造参数；多因子策略请使用 `FactorPortfolioStrategy`。
- `Universe.index(...)` 仅表达选股意图；实际数据范围由 API 请求的 `universe` 决定，向量化链路尚未接入 ST、停牌等订单级规则。
