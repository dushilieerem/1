# SVQuant 回测引擎与执行模式设计

> 文档版本：v1.0
> 状态：当前架构基线；因子主链已实施，策略向量化/事件模式按现有行为维护
> 最后更新：2026-08-28
> 适用范围：ResearchEngine 回测计算，不代表 TradingEngine 或实盘交易已实现

## 1. 文档定位

本文档说明项目级回测执行模式和引擎协作边界。ResearchEngine 的完整模块架构以
[`ResearchEngine 模块架构`](../../ResearchEngine/docs/02-架构文档/researchengine_architecture.md) 为准；
本文只保留跨模块需要理解的引擎职责、数据时序和执行差异。

当前架构的决策来源包括：

- [ADR-028：因子回测由 BacktestEngine 编排四引擎](../05-技术决策/ADR-028-因子回测由BacktestEngine编排四引擎.md)
- [ADR-029：研究服务采用 services 与 models 分层](../05-技术决策/ADR-029-研究服务采用services与models分层.md)
- [ResearchEngine ADR-018：因子计算区间与收益确认区间分离](../../ResearchEngine/docs/05-技术决策/ADR-018-因子计算区间与收益确认区间分离.md)
- [ResearchEngine ADR-019：由 ExperimentManager 管理回测并发](../../ResearchEngine/docs/05-技术决策/ADR-019-为什么由ExperimentManager管理回测并发.md)
- [ADR-030：DataEngine 持有应用级市场数据快照](../05-技术决策/ADR-030-DataEngine持有应用级市场数据快照.md)

早期文档中的 `VectorEngine`、`EventEngine`、`ExecutionEngine` 和因子 AST 方案是概念或后续
演进设计，不得当作当前已部署的独立服务、公共类或实盘能力。当前代码中可确认的实现类是
`BacktestEngine`、`NativeEngine` 和 `EventBacktestEngine`。

## 2. 当前引擎责任

| 组件 | 代码位置 | 当前责任 | 当前状态 |
|------|----------|----------|----------|
| `BacktestEngine` | `app/services/backtest/` | 组织完整因子回测，调用四个责任引擎并生成标准结果 | 因子主链当前入口 |
| `DataEngine` | `app/services/data/` | 统一 Provider、行情面板、股票池、基准和筛选掩码 | 当前实现 |
| `FactorEngine` | `app/services/factor/` | 因子来源加载、因子计算、有效池和可选预处理 | 当前实现 |
| `PortfolioEngine` | `app/services/portfolio/` | 分组、权重、持仓、调仓意图和评价数据对齐 | 当前实现 |
| `MetricEngine` | `app/services/metric/` | 收益、费用、净值、IC、分组及扩展评价 | 当前实现 |
| `NativeEngine` | `app/services/strategy/vectorized/` | 向量化策略的策略回测执行适配器 | 当前策略主路径 |
| `EventBacktestEngine` | `app/services/strategy/event/` | 日频事件策略的时序、订单、成交和账本执行 | 日频 MVP |
| `ExperimentManager` | `app/services/experiment/` | 统一任务排队、并发、去重和取消 | 调度边界，不负责数据生命周期或量化计算 |

`DataEngine`、`FactorEngine`、`PortfolioEngine`、`MetricEngine` 和 `BacktestEngine` 都属于
`services`；配置、面板、规格、上下文、订单、成交和结果结构属于 `models`。当前不存在
“因子由 VectorEngine 独立计算、再交给 BacktestEngine”的运行时层级。

## 3. 因子回测执行链路

单次、批量、Python 和 HTTP 入口共享同一规格和执行边界：

```text
FactorBacktestRequest
        ↓ 标准化、校验、数据 release 解析
FactorBacktestSpec（models，不可变、可哈希）
        ↓
ExperimentManager
        ↓
FactorBacktestExperiment
        ↓
BacktestEngine.run(spec, context)
        ├─ DataEngine：行情、股票池、基准和筛选掩码
        ├─ FactorEngine：来源加载、完整历史计算、有效池、预处理
        ├─ PortfolioEngine：分组、权重、持仓和评价数据对齐
        └─ MetricEngine：收益、净值、IC、分组和扩展评价
        ↓
FactorBacktestResult / ResultManager
```

### 3.1 计算时序与数据边界

1. `start/end` 定义本次因子计算和回测数据范围；系统不额外读取区间之前的滚动预热数据。
2. 在 release 和 `as_of` 允许的上界内完成因子计算，随后将因子值、远期收益、分组、净值和指标裁剪到确认区间。
3. DataEngine 负责读取和筛选数据，不通过删除历史行破坏完整时间轴；缺少可选过滤字段时按已确认策略跳过并告警。
4. FactorEngine 负责因子加载/计算和可选去极值、标准化；PortfolioEngine 不使用未来收益参与组合决策。
5. MetricEngine 只负责效果计算和评价，不负责交易撮合；结果身份绑定规格、源码、release、执行版本和指标版本。

当前版本约束：`factor-execution-v4`、`factor-backtest-v10`、`factor-scorecard-v2`。
因子执行期间始终保留调用方提交的原始 `FactorBacktestSpec`；数据实际截止日作为
`actual_end` 单独记录，不生成 `effective_spec`，也不转换为 `ConfigManager`。

### 3.2 因子链路与策略链路的隔离

因子主链不经过 `BacktestSignals`、`NativeEngine` 或 `EventBacktestEngine` 的策略包装；策略链路
可以复用 DataEngine 和部分指标能力，但不因此成为因子回测的第二套实现。因子批量协调器只负责任务
枚举、两槽业务窗口、重试、幂等和 SQLite 标量投影，不能复制四个引擎的计算逻辑。

## 4. 向量化策略执行模式

策略请求通过 `StrategyExperiment` 进入 `services/strategy/vectorized/`：

```text
StrategyBacktestRequest
        ↓
StrategyExperiment
        ↓
BacktestSignals + BacktestConfig
        ↓
IBacktestEngine
        ↓
NativeEngine
        ↓
策略净值、收益、持仓、再平衡和可选执行时间线
```

向量化模式适合按日期×标的面板批量计算。`NativeEngine` 负责策略侧的信号、组合收益和成本
接线；它不是因子 `BacktestEngine` 的后端，也不承担因子分组、因子预处理或因子指标评分。
策略请求当前由 HTTP 同步等待结果，和因子请求的 `202 + run_id` 异步契约不同。

## 5. 事件策略执行模式

当前 `EventBacktestEngine` 是 ResearchEngine 内的日频研究实现，不是交易执行服务：

```text
前一收盘可见的 DataView
        ↓
StrategyContext + schedule
        ↓
策略产生订单意图
        ↓
当日开盘按卖后买执行
        ↓
EventFill + PositionSnapshot + equity
```

当前可验证的研究边界：

- 日频交易日循环；策略在盘前只能读取截至前一收盘的数据。
- 以现金账户为主的研究账本，订单按目标数量或目标金额转换。
- 支持卖后买、手数、现金、T+1、停牌、涨跌停和交易成本等已实现规则。
- 输出订单、成交、持仓快照、权益曲线和事件记录，拒单原因进入订单状态。
- 当前不承诺分钟/Tick、多资产保证金、券商接入、实盘下单或 TradingEngine 复用。

## 6. 调度、数据和部署约束

- 一个 ResearchEngine 进程创建一个 `ExperimentManager(max_workers=2, max_queue_size=8)`。
- Manager 使用一个普通 FIFO；批量 `window=2` 是批量业务窗口，不等于全局队列容量，也不构成优先级插队。
- FastAPI 应用持有一个 `DataEngine`，它加载固定 release、持有 Provider 与原始字段缓存；Manager 仅注入该只读快照。因子、组合、指标中间状态属于任务私有。
- 当前部署保持单实例、单 Uvicorn worker；跨进程任务状态、分布式锁和远程 Worker 属于后续架构决策。
- API 根路径统一为 `/api`；因子单次和批量提交异步，策略回测当前同步。

## 7. 后续演进边界

以下内容不是当前实现的前置假设，必须在新需求和新 ADR 中单独确认：

- 通过 `StrategyRequirements` 与 `EngineProfile` 做事件能力画像匹配（ResearchEngine ADR-013 当前为提议）。
- 分钟/Tick、期货/ETF、多账户和更完整市场规则。
- 独立进程/容器沙箱、外部队列、持久化任务状态和多实例调度。
- `LiveFeed`、`LiveExecutionEngine` 和 TradingEngine 的实盘执行能力。

任何后续变更都要先更新对应 ADR，再同步本文件、ResearchEngine 模块架构和必要的功能/实现文档。
