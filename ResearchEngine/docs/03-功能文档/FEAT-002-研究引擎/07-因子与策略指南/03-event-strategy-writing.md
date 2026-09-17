# 事件策略编写规范（日频 MVP）

> 适用对象：突破、止损、持仓状态、订单拒绝和 A 股日频交易规则
> 运行入口：`POST /api/backtest/strategy`（`engine_mode: "event"`）或本地 `EventBacktestEngine`

事件策略必须定义 `initialize(context)`。通过 HTTP API 提交时，必须显式传入
`engine_mode: "event"`；引用策略资产时，索引中的 `execution_mode` 也必须为
`event`。响应仍统一使用 HTTP `200`，是否成功以响应 `error` 是否为 `null` 判断。

## 1. 时间口径

每个交易日固定按如下顺序运行：

```text
盘前：策略仅读取截至前一交易日收盘的数据
  → 回调：读取历史、查询持仓、提交目标仓位订单
  → 当日开盘：引擎按“先卖后买”处理订单和市场规则
  → 盘后：记录权益、持仓快照、订单、成交和事件日志
```

例如，策略在 2024-01-03 盘前根据 2024-01-02 收盘价生成突破信号，订单会以 2024-01-03 开盘价尝试成交。回调内不能读取当天或未来的 OHLC 数据。

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
| `context.current_dt` | 当前交易日盘前时间 |
| `context.state` | 策略私有状态，例如最高收盘价、计数器 |
| `context.data.fields` | 已装配的字段集合 |
| `context.data.symbols` | 面板标的代码 |
| `context.data.history(symbols, fields, count)` | 截至前一收盘的字段宽表 |
| `context.portfolio.cash` | 当前可用现金，只读 |
| `context.portfolio.positions` | `{代码: 持仓数量}` 快照，只读 |
| `context.portfolio.quantity(symbol)` | 单标的当前持仓数量 |
| `context.orders` | 提交订单 |

`context.data.symbols` 是本次请求准备好的可用标的集合。请求使用 `universe`
时，ResearchEngine 会按回测数据起点解析股票池；策略不能假设指数成分会在每个
交易日自动动态切换。需要上市天数或 ST 过滤时，必须由回测数据面板和引擎准备
相应的点时数据，策略代码不能用最新静态快照回填历史。

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
| `NO_PRICE` | 缺少当日开盘价 |

## 5. Donchian 风格模板

```python
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

完整策略见 `ResearchEngine/app/assets/strategies/libraries/donchian_a_share_event_v1.py`。
要严谨运行该策略，面板还必须提供 `money`、停牌/涨跌停状态和按历史时点构建
的股票池、上市天数与 ST 过滤结果。

通过 HTTP API 调用事件策略时，最小请求如下：

```json
{
  "engine_mode": "event",
  "strategy_id": "donchian_a_share_event",
  "start": "2026-07-01",
  "end": "2026-08-14",
  "include_execution_timeline": true
}
```

## 6. 当前边界

- 已支持：A 股现金多头、日/周/月调度、开盘成交、整手、T+1、停牌、涨跌停、佣金和卖出印花税。
- 已支持：通过 `POST /api/backtest/strategy` 运行 `initialize(context)` 事件策略，响应可返回订单、成交、持仓快照、事件和 `execution_timeline`。
- 未支持：分钟/Tick、盘中止损、限价单、部分成交、成交量约束、融资融券、期货、ETF T+0。
- 不提供聚宽 `jqdata`、全局 `g`、`run_daily` 或 `order_target` 兼容接口。
- 当前仅限本地可信代码；不支持通过 `strategy_params` 向策略构造函数注入参数，点时基本面是否可用取决于已发布数据面板，生产沙箱仍未交付。

## 7. 策略库登记

源码文件放在 `ResearchEngine/app/assets/strategies/libraries/`，索引文件为
`ResearchEngine/app/assets/strategies/index.yaml`。`file` 只能指向策略库目录
中的 `.py` 文件，`entrypoint` 必须与源码中唯一的策略类名一致。

```yaml
my_event_strategy:
  name: 我的日频事件策略
  strategy_type: trend
  execution_mode: event
  current_version: v1
  tags: [trend, long_only, event]
  versions:
    v1:
      file: my_event_strategy_v1.py
      entrypoint: MyEventStrategy
```
