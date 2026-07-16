# 事件驱动策略回测引擎：技术设计

## 1. 决策

保留现有向量化 `IBacktestEngine.run(BacktestSignals, BacktestConfig)`，新增独立的事件策略契约与 `EventBacktestEngine`。两者共享数据层、市场规则、成本模型、`BacktestResult` 和指标层，但**不共享策略代码接口**。

```text
快速研究：StrategyCode → target_weights → NativeEngine / VectorBTEngine
复杂研究：EventStrategyCode → StrategyRuntime → EventBacktestEngine
                                              ├─ Scheduler
                                              ├─ DataView（as-of）
                                              ├─ OrderService
                                              ├─ CNMarketRule
                                              ├─ MatchingEngine
                                              └─ Portfolio
```

## 2. 模块边界

| 模块 | 新增/调整职责 | 不承担 |
|---|---|---|
| `quantcore.backtest.event` | 事件循环、时钟、任务调度、策略运行时、订单生命周期 | HTTP、用户资产管理 |
| `quantcore.backtest.market_rules` | A 股 T+1、整手、涨跌停、停牌、交易时段 | 止损等业务策略规则 |
| `quantcore.data` | 提供带 `as_of` 的行情/基本面查询 | 直接执行用户代码 |
| `researchengine.api` | 解析事件回测请求、调用沙箱、序列化结果 | 保存策略和长期任务状态 |
| `TradingEngine` | 未来复用 EventStrategy 与订单端口 | 本 Feature 不实现实盘 |

## 3. 核心接口

```python
class EventStrategy(Protocol):
    def initialize(self, context: StrategyContext) -> None: ...

class StrategyContext:
    current_dt: datetime
    state: StrategyState
    data: DataView
    portfolio: PortfolioView
    orders: OrderService
    schedule: SchedulerRegistrar

class EventBacktestEngine:
    def run(self, strategy: EventStrategy, config: EventBacktestConfig) -> BacktestResult: ...
```

策略源码的适配方式为：源码可定义模块级 `initialize(context)` 和回调函数；受控加载器把它们包装为 `EventStrategy`。`context` 服务由引擎注入，禁止策略直接构造数据提供者、撮合器或组合对象。

## 4. 事件顺序与成交模型

日频 MVP 每个交易日按以下固定顺序执行：

1. 载入当日可见数据，更新前一日收盘估值与持仓可卖数量。
2. 运行盘前任务；执行前一事件提交、等待 next-open 的订单。
3. 运行当天到期的调度任务，提交新订单。
4. 在配置成交时点处理订单、市场规则校验、撮合、成本与组合更新。
5. 运行盘后任务、记录持仓和净值快照。

默认成交模型为 `next_open`；若没有 open，明确降级为下一 bar close 并写入 `execution_assumption`。该规则阻断“当前 close 选股并以当前 close 成交”的未来函数。

## 5. 数据与规则设计

- `DataView.history(symbols, fields, count)` 只能读取当前事件及以前数据。
- `DataView.current(symbols)` 在日频 MVP 返回当前可见日线状态；分钟字段请求返回明确的不支持错误。
- `FundamentalView.query(spec, as_of)` 在数据提供者侧按公告日过滤；若数据源没有公告日，拒绝该查询而非静默使用未来数据。
- `CNMarketRule.validate(order, portfolio, market_state)` 返回可组合的拒单原因码：`INSUFFICIENT_CASH`、`LOT_SIZE`、`T_PLUS_ONE`、`SUSPENDED`、`LIMIT_UP`、`LIMIT_DOWN`、`NO_PRICE`。
- 扩展现有 `Order` / `Fill`：增加提交时间、有效期、拒单原因、成交状态；保留兼容字段，避免影响现有演示 BacktestEngine。

## 6. API 与结果

新增独立端点（名称待 API 评审确认）：`POST /api/backtest/event-strategy`。请求包括策略代码、参数、市场规则配置、数据集引用、回测区间、初始资金和成本配置；不得复用现有向量化 `/api/backtest/strategy` 的 `generate_signals` 契约。

响应在现有指标/净值之外增加：

- `orders[]`：订单、状态与拒单原因；
- `fills[]`：成交价、数量、成本与时间；
- `position_snapshots[]`：现金、可卖数量、持仓市值；
- `events[]`：调度回调、运行日志和规则判定；
- `assumptions`：数据频率、成交时点、规则版本与降级说明。

## 7. 兼容、迁移与回滚

- 现有因子和向量化策略 API 保持不变，默认仍使用 NativeEngine。
- 旧 `BacktestEngine` 的公开行为先保持，逐步由 EventEngine 吸收；不得在首个版本删除。
- 前端用 `engine_mode: vectorized | event` 显式选择，默认 `vectorized`；未满足事件数据前置条件时拒绝运行并提示原因。
- 采用 Feature Flag `event_backtest_enabled`。出现结果偏差或稳定性问题时关闭 Flag，原向量化服务不受影响。

## 8. 测试策略

- 单元：调度、状态隔离、订单校验、T+1、涨跌停、停牌、整手、成本和拒单原因。
- 组件：最小策略的回调顺序、next-open 成交、防未来函数、基本面公告日过滤。
- 回归：现有 QuantCore / ResearchEngine 全量测试与向量化数值基线。
- 金标：为聚宽样例抽取“周调仓 + 个股止损 + 空仓 ETF”简化策略，人工核对订单和持仓时间线。
- 安全：恶意文件/网络访问、死循环、超大内存占用和异常退出均在沙箱内被控制。

## 9. 关键技术风险

| 风险 | 缓解 |
|---|---|
| 时点化基本面数据缺失 | 先只开放带公告日期的数据集；无公告日期即拒绝查询。 |
| 日频数据无法模拟盘中规则 | 在结果中显式标注日频近似；分钟能力单独验收。 |
| 与向量化回测混淆 | API、代码契约与 UI 引擎模式彻底分开。 |
| 用户代码安全 | 开发期可信模式仅供本地；生产前沙箱是上线前置条件。 |
| 规则复杂度失控 | MVP 仅 A 股现金多头与日频，新增市场/融资/限价单另建 Feature。 |
