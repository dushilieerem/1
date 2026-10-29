# 向量化策略编写规范

> 适用对象：因子选股、Top-N、固定节奏调仓和参数研究
> 运行方式：在策略项目的「执行模式」中选择“向量化”，然后回测或绑定模拟账户

## 1. 契约

向量化策略只输出“日期 × 标的”的目标权重矩阵。它不直接提交订单，也不维护持仓状态。

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
- 因子方法里可用的字段与[因子编写规范](01-factor-writing.md)第 3 节一致，例如 `current_mv`、`pe_ttm`。

## 3. 自由目标权重策略

策略源码必须且只能包含一个带 `generate_signals()` 的类：

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

构造函数参数名与行情字段同名时，系统会注入对应数据，例如 `close`、`amount`、`current_mv`、`pe_ttm`；带默认值的普通参数会保留默认值。

输出规则：

- 索引为交易日、列为标的代码；建议直接复用 `self.close.index` 和 `self.close.columns`。
- 正数为多头、负数为空头、`0.0` 为清仓。
- `NaN` 表示不更新，沿用上一期目标；`0.0` 表示明确清仓。
- 不要返回价格、订单或交易记录。

## 4. 边界与安全

- 不要使用 `close.shift(-1)` 等未来数据。
- 不要自行读文件、联网、写结果或调用回测引擎。
- 回测页面可以选择是否过滤停牌、ST、涨跌停股票，以及成交时点（`same_close` / `next_close` / `next_open`，默认 `next_close`）。
- 向量化策略按权重调仓，不模拟逐笔成交和 T+1 锁仓；需要这些规则时请使用事件策略。
- `Universe.index(...)` 仅表达选股意图；实际数据范围由页面上选择的股票池决定。
