# 事件驱动策略回测引擎：技术设计

## 1. 决策

保留现有向量化 `IBacktestEngine.run(BacktestSignals, BacktestConfig)`，新增独立的、策略无关的事件策略契约与 `EventBacktestEngine`。两者共享数据层、市场规则、成本模型、`BacktestResult` 和指标层，但**不共享策略代码接口**。事件内核根据能力画像组合时钟、数据、账户、规则和执行模型，不含任何策略名称、因子公式或品种白名单。

```text
快速研究：StrategyCode → target_weights → NativeEngine
复杂研究：EventStrategyCode + StrategyRequirements
                    ↓ capability validation
             EngineProfile → EventBacktestEngine
                               ├─ EventClock / Scheduler
                               ├─ DataView（as-of，日频/分钟）
                               ├─ InstrumentRegistry / MarketRule
                               ├─ PortfolioLedger（现金/保证金/子账户）
                               ├─ OrderService / ExecutionModel
                               └─ ResultLedger
```

## 2. 模块边界

| 模块 | 新增/调整职责 | 不承担 |
|---|---|---|
| `quantcore.backtest.event` | 事件循环、时钟、任务调度、策略运行时、订单生命周期、能力校验 | HTTP、用户资产管理、策略公式 |
| `quantcore.backtest.market_rules` | 按市场/品种注入 T+N、整手、涨跌停、保证金、合约乘数、费用、交易时段 | 止损、Alpha、选股等业务策略规则 |
| `quantcore.data` | 提供带 `as_of` 的日频/分钟行情、基本面、证券和合约参考数据查询 | 直接执行用户代码、推断缺失数据 |
| `quantcore.backtest.portfolio` | 现金与保证金子账户、可用资金、持仓、逐日/逐 bar 估值 | 期货或 ETF 的策略选择逻辑 |
| `researchengine.api` | 解析事件回测请求、调用沙箱、序列化结果 | 保存策略和长期任务状态 |
| `TradingEngine` | 未来复用 EventStrategy 与订单端口 | 本 Feature 不实现实盘 |

## 3. 核心接口

```python
class EventStrategy(Protocol):
    def initialize(self, context: StrategyContext) -> None: ...

    def requirements(self) -> StrategyRequirements: ...

class StrategyContext:
    current_dt: datetime
    state: StrategyState
    data: DataView
    portfolio: PortfolioView
    orders: OrderService
    schedule: SchedulerRegistrar

class EventBacktestEngine:
    def run(self, strategy: EventStrategy, config: EventBacktestConfig,
            profile: EngineProfile) -> BacktestResult: ...
```

### 3.1 交易标的范围契约

策略可在类级声明 `fixed_symbols`（单标的或固定篮子）、`pair_symbols`（配对策略）或 `symbols`（固定篮子）。API 在读取行情前优先使用这些标的，不受请求 `universe` 的限制，并校验每个标的在当前数据快照中可用；请求股票池仍作为性能展示或比较口径保留，但不限制固定标的下单。为兼容已有单标的事件策略，未声明上述字段但实例提供非空 `symbol` 字符串时，API 将该值视为单个固定标的；对向量化策略，构造函数中 `stock_a`、`stock_b` 或 `symbol` 的字符串默认值也会被识别为固定标的。`benchmark_symbol` 不属于交易标的，不参与该解析。新策略仍应优先显式使用 `fixed_symbols` 或 `pair_symbols`。

未声明上述字段的策略继续以请求 `universe` 解析可交易范围。策略代码对外统一使用交易所代码（如 `600519.SH`）；API 在数据边界将底层六位代码标准化后再交给策略。响应 `meta.trading_symbols` 仅在策略声明固定标的时返回，用于前端明确展示实际交易范围。

策略源码的适配方式为：源码可定义模块级 `initialize(context)`、`requirements()` 和回调函数；受控加载器把它们包装为 `EventStrategy`。`context` 服务由引擎注入，禁止策略直接构造数据提供者、撮合器或组合对象。

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
- 策略启动前的能力校验返回结构化失败码：`DATA_NOT_READY`（缺少已发布的点时数据）、`UNSUPPORTED_FREQUENCY`（日频策略请求分钟语义）、`UNSUPPORTED_STRATEGY_CAPABILITY`（未实现的订单或数据能力）；不得进入事件循环。
- 扩展现有 `Order` / `Fill`：增加提交时间、有效期、拒单原因、成交状态；保留兼容字段，避免影响现有演示 BacktestEngine。

## 6. API 与结果

复用 `POST /api/backtest/strategy`，以请求中的 `engine_mode: "vectorized" | "event"` 显式分流。两种模式共用策略资产引用、回测区间、初始资金和成本字段，但不共用策略代码契约：`vectorized` 需要 `generate_signals()`，`event` 需要 `initialize(context)`。目录策略的 `execution_mode` 必须与请求一致；不一致时返回业务错误。

响应在现有指标/净值之外增加：

- `orders[]`：订单、状态与拒单原因；
- `fills[]`：成交价、数量、成本与时间；
- `position_snapshots[]`：现金、可卖数量、持仓市值；
- `events[]`：调度回调、运行日志和规则判定；
- `assumptions`：数据频率、成交时点、规则版本与降级说明。

## 7. 兼容、迁移与回滚

- 现有因子和向量化策略 API 保持不变，默认仍使用 NativeEngine。
- 已删除旧 `BacktestEngine` 演示实现及其公开入口；新事件策略一律使用 `EventBacktestEngine`。向量化 API 与其 `IBacktestEngine` 契约保持不变。
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

## 10. 能力画像、市场规则与执行模型

### 10.1 能力匹配

```python
@dataclass(frozen=True)
class StrategyRequirements:
    frequency: Literal["1d", "1m"]
    instruments: frozenset[str]       # cn_equity / cn_etf_t0 / cn_index_future
    data_capabilities: frozenset[str] # bars / fundamentals_pit / industry_history / futures_chain
    trading_capabilities: frozenset[str]  # long_only / short / margin / t0 / multi_account
    schedule_capabilities: frozenset[str] # daily / monthly / every_n_minutes / intraday_flatten

@dataclass(frozen=True)
class EngineProfile:
    name: str
    provided_capabilities: frozenset[str]
    clock: EventClock
    rules: Mapping[str, MarketRule]
    execution_models: Mapping[str, ExecutionModel]
```

启动顺序固定为：解析策略声明 → 加载数据/规则/执行画像 → 比对能力集合 → 仅在完全满足时创建 `StrategyContext` → 进入事件循环。`StrategyRequirements` 是通用声明，GARP 与统计套利只是两份不同参数，不得定义 `GARPDataSpec` 等策略专用内核类型。

### 10.2 通用事件与订单模型

内核事件统一包含 `SESSION_OPEN`、`SCHEDULED_CALLBACK`、`BAR`、`ORDER_SUBMITTED`、`ORDER_REJECTED`、`FILL`、`SESSION_CLOSE` 和 `CONTRACT_ROLL`。日频和分钟频仅改变 `BAR` 的频率及可用执行模型。

订单必须携带 `account_id`、`instrument_id`、`side`、`position_effect`（open/close/close_today）、`quantity` 或 `target_value`、`submitted_at`、`time_in_force`。`MarketRule` 将标的映射至现金、T+0、保证金或期货规则；`ExecutionModel` 负责按 bar/tick 模拟成交；策略不判断手续费、保证金或平今费用。

### 10.3 分阶段启用画像

| 画像 | 事件时钟 | 账户/规则 | 依赖数据 | 状态 |
|---|---|---|---|---|
| `cn_equity_daily_v1` | 交易日阶段 | 现金、T+1、整手、涨跌停 | 日线、公告日财务、历史证券/行业状态 | 首个实现目标 |
| `cn_etf_t0_minute_v1` | 1 分钟 bar + 定时回调 | 现金、T+0、ETF 成本 | ETF 分钟线、T+0 资格历史、交易日历 | 后续画像 |
| `cn_index_future_minute_v1` | 1 分钟 bar + 换月事件 | 保证金、双向、乘数、平今费率 | 期货分钟线、合约链、主力映射、现货指数 | 后续画像 |
| `cn_multi_asset_intraday_v1` | 统一分钟时钟 | 多子账户、组合级风险/净值 | 上述 ETF + 期货全部数据 | 后续集成画像 |

画像按契约演进而非硬编码。新增市场、资产类别或频率通过新 `MarketRule`、`ExecutionModel`、数据适配器和 `EngineProfile` 扩展；若触及策略接口语义，则单独建 Feature/ADR。

## 11. GARP 金标策略的迁移设计

### 10.1 不直接执行聚宽源码

GARP 原始策略依赖 `jqdata`、全局 `g`、`run_daily`、`run_monthly`、`get_fundamentals` 和 `order_target`。受控加载器不提供这些兼容函数。迁移后的策略使用 SVQuant `context`：

```python
def initialize(context):
    context.schedule.monthly(prepare_review, trading_day=1, phase="before_open")
    context.schedule.daily(apply_pending_orders, phase="before_open")

def prepare_review(context):
    # 仅查询 context.current_dt 前一交易日可见的公告日财务与证券状态
    # 1/7 月重建目标组合；4/10 月复核持仓；生成目标市值订单
    ...
```

策略的“评分、候选过滤、持有判定”属于策略代码；引擎只提供时点数据、调度、订单和状态。GARP 以 `StrategyRequirements` 声明数据依赖，缺字段时引擎以 `DATA_NOT_READY` 失败，避免运行一半后静默降级。

### 10.2 日频事件阶段

为避免把日频 OHLC 误称为分钟成交，事件时钟增加固定阶段：

```text
前一交易日收盘的数据快照
  → before_open：策略读取 as-of 快照、提交订单
  → open_execution：按当日 open 撮合上一阶段订单（先卖后买）
  → after_close：估值、持仓快照、日志
```

同一 `open_execution` 批次按卖单、买单、提交顺序稳定排序；每笔买单在已结算卖出所得现金基础上校验。`9:35`、`9:40`、`10:30` 仅在分钟数据模式下可作为真实时钟；日频模式将它们映射为上述阶段并在 `assumptions` 返回 `daily_open_proxy`。

### 10.3 时点财务与横截面查询

`FundamentalView.query(spec, as_of)` 扩展为三个只读操作：

```python
fundamentals.latest(fields, symbols, as_of)
fundamentals.quarters(fields, symbols, count, as_of)
reference.industry(symbols, scheme="sw_l1", as_of=as_of)
```

底层只能消费 FEAT-010 发布为 `ready` 的公告日点时面板与历史分类表。GARP 的三年 EPS CAGR 通过同季度、相隔十二个季度的已公告 EPS 计算；近八季增长比例、ROE/现金流中位数及行业中位数均限制在 `as_of` 可见样本。原始报表或行业数据缺少公告日/生效日时，查询必须失败。

### 11.4 GARP 运行金标

金标夹具包含：一只在公告日前不可见、公告后进入候选的成长股；一只 ST 触发退出的持仓；一只停牌或涨跌停导致拒单的标的；以及候选不足 15 只时保留现金的组合。验收关注订单、持仓、现金和可见性，不以历史收益率作为正确性标准。

## 12. 分钟多资产统计套利金标

西蒙斯风格策略使用 `cn_multi_asset_intraday_v1`：一分钟 bar 触发、每五分钟计算信号、14:45 禁止新开仓、14:50 全平。其 ETF 子账户仅请求 `long_only + t0`；期货子账户请求 `short + margin + futures_chain`。金标验证当前 bar 之后的数据不可见、风险乘数为零时退出、主力合约切换先平后开、平今费用和保证金独立核算，以及 ETF/期货资金隔离。
