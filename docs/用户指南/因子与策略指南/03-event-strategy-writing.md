# 事件策略编写规范（日频）

> 适用对象：突破、止损、持仓状态和 A 股日频交易规则
> 运行方式：在策略项目的「执行模式」中选择“事件”，然后回测或绑定模拟账户

## 1. 时间口径

策略回调在每个交易日运行，成交时点由回测页面或模拟账户的执行设置决定：

| 成交时点 | 回调可见数据 | 成交价格 |
|---|---|---|
| `same_close` | 截至当天收盘 | 当天收盘价 |
| `next_close`（默认） | 截至前一交易日收盘 | 当天收盘价 |
| `next_open` | 截至前一交易日收盘 | 当天开盘价 |

例如在 2024-01-03 的回调中，`next_close` / `next_open` 只能看到 2024-01-02 及之前的数据，并分别在 2024-01-03 的收盘价、开盘价成交；`same_close` 则是在 2024-01-03 收盘出信号、同日收盘成交。除 `same_close` 外，回调内不能读取当天或未来的 OHLC 数据。

## 2. 最小策略模板

```python
class MyEventStrategy:
    required_fields = frozenset({"open", "high", "low", "close"})

    def initialize(self, context):
        context.state.entry_count = 0
        context.schedule.daily(self.rebalance)

    def rebalance(self, context):
        close = context.data.history(context.data.symbols, ["close"], 21)["close"]
        if len(close) < 21:
            return
        momentum = close.iloc[-1] / close.iloc[0] - 1
        context.orders.target_value(momentum.idxmax(), context.portfolio.cash * 0.9)
        context.state.entry_count += 1
```

## 3. `context` 接口

| 对象 | 当前可用能力 |
|------|--------------|
| `context.current_dt` | 当前交易日时间 |
| `context.state` | 策略私有状态，例如最高收盘价、计数器 |
| `context.data.fields` | 已装配的字段集合 |
| `context.data.symbols` | 面板标的代码 |
| `context.data.history(symbols, fields, count)` | 截至可见时点的字段宽表 |
| `context.portfolio.cash` | 当前可用现金，只读 |
| `context.portfolio.positions` | `{代码: 持仓数量}` 快照，只读 |
| `context.portfolio.quantity(symbol)` | 单标的当前持仓数量 |
| `context.portfolio.average_cost(symbol)` | 单标的持仓均价，无持仓时为 `None` |
| `context.orders` | 提交订单 |

`context.data.symbols` 不自动等于历史指数成分股。需要沪深300/中证500、上市天数或 ST 过滤时，请在页面选择相应股票池和过滤条件。

## 4. 调度与订单

```python
def initialize(self, context):
    context.schedule.daily(self.daily_task)
    context.schedule.weekly(self.weekly_task, weekday=0)       # 0=周一
    context.schedule.monthly(self.monthly_task, trading_day=1) # 每月首个交易日

def daily_task(self, context):
    context.orders.target_quantity("000001.SZ", 1_000)  # 目标持仓数量，不是增量
    context.orders.target_value("000001.SZ", 100_000)   # 目标持仓市值
    context.orders.close("000001.SZ")                    # 目标持仓为零
```

订单状态为 `filled` 或 `rejected`。主要拒绝原因：

| 原因码 | 含义 |
|--------|------|
| `INSUFFICIENT_CASH` | 现金不足以覆盖成交额和佣金 |
| `LOT_SIZE` | 买入不是 100 股整手 |
| `T_PLUS_ONE` | 当日买入数量不可当日卖出 |
| `SUSPENDED` | 停牌 |
| `LIMIT_UP` / `LIMIT_DOWN` | 涨停买入或跌停卖出 |
| `NO_PRICE` | 缺少当日成交价 |

## 5. Donchian 风格模板

```python
import pandas as pd

class DonchianStyleStrategy:
    def initialize(self, context):
        context.state.peak_close = {}
        context.schedule.daily(self.rebalance)

    def rebalance(self, context):
        data = context.data.history(context.data.symbols, ["close", "high", "low"], 61)
        for symbol in context.portfolio.positions:
            close = data["close"][symbol].dropna()
            high = data["high"][symbol].reindex(close.index)
            low = data["low"][symbol].reindex(close.index)
            atr20 = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1).iloc[-20:].mean()
            peak = max(context.state.peak_close.get(symbol, close.iloc[-1]), close.iloc[-1])
            context.state.peak_close[symbol] = peak
            if close.iloc[-1] < low.iloc[-21:-1].min() or close.iloc[-1] < peak - 3 * atr20:
                context.orders.close(symbol)
```

## 6. 当前边界

- 已支持：A 股现金多头、日/周/月调度、整手、T+1、停牌、涨跌停、佣金和卖出印花税。
- 未支持：分钟/Tick、盘中止损、限价单、部分成交、成交量约束、融资融券、期货、ETF T+0。
- 不提供聚宽 `jqdata`、全局 `g`、`run_daily` 或 `order_target` 兼容接口。
