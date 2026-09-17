# ResearchEngine 架构设计

> 文档版本：v1.3
> 状态：services/models 结构修订已实施，528 项全量回归通过；FEAT-030 专项验收未全部关闭
> 最后更新：2026-08-28
> 适用分支：`researchengine`

## 1. 文档定位

本文档描述 SVQuant 当前 ResearchEngine 的运行时架构、模块边界、执行链路、数据与任务生命周期，以及现阶段的工程约束。它是 `ResearchEngine/docs/02-架构文档/` 下的模块级架构基线。

功能细节和验收标准仍以对应 Feature 文档为准；本文档记录跨 Feature 的稳定边界和当前代码
已经实现的行为，仍保留重构前链路作为历史基线。若本文档与代码不一致，应先以
`ResearchEngine/app` 的实际实现为准，再补充本文件。

### 1.1 当前有效决策

本架构基线与下列已接受决策保持一致：

| 决策 | 当前实现约束 |
|------|--------------|
| [ADR-018](../05-技术决策/ADR-018-因子计算区间与收益确认区间分离.md) | `start/end` 定义收益确认区间；因子先使用允许范围内的完整历史计算，再将因子、收益和指标裁剪到确认区间。 |
| [ADR-019](../05-技术决策/ADR-019-为什么由ExperimentManager管理回测并发.md) | 每个进程只有一个应用级 `ExperimentManager`，默认 2 个执行槽和 8 个排队槽。 |
| [ADR-020](../05-技术决策/ADR-020-因子批量指标仓库使用独立SQLite.md) | 批量历史和标量指标由独立 `FactorBacktestStore` SQLite 保存，不替代通用结果存储。 |
| [ADR-021](../05-技术决策/ADR-021-因子回测接口采用异步任务查询.md) | 因子单次与批量提交返回任务标识，查询和取消通过任务接口完成；策略接口当前仍保持同步响应。 |
| [ADR-022](../05-技术决策/ADR-022-回测运行时由ExperimentManager持有共享行情上下文.md) | `ExperimentManager` 持有按 MarketData release 隔离的 `ResearchRuntime`，任务只共享只读行情。 |
| [ADR-023](../05-技术决策/ADR-023-采用单一app命名空间与两槽批量FIFO.md)、[ADR-024](../05-技术决策/ADR-024-ResearchEngine HTTP API 使用 api 前缀.md) | 运行时使用单一 `app.*` 命名空间和 `/api` 根路径；批量协调器不插入通用 FIFO 优先级。 |
| [ADR-025](../05-技术决策/ADR-025-回测采用单一应用执行管线与可插拔后端.md)、[ADR-028](../../../docs/05-技术决策/ADR-028-因子回测由BacktestEngine编排四引擎.md) | 所有因子入口共享同一规格和 `BacktestEngine` 执行边界；旧 Executor/算法不作为当前入口。 |
| [ADR-029](../../../docs/05-技术决策/ADR-029-研究服务采用services与models分层.md) | 业务逻辑位于 `services`，内部结构位于 `models`，数据访问和持久化位于 `database`，不恢复 QuantCore 独立包层。 |

ADR-012、ADR-013、ADR-015、ADR-026 当前仍是提议或后续演进输入，不能反向改变本文件的“当前实现”描述。

## 2. 模块定位与边界

ResearchEngine 是 SVQuant 的投研应用运行时，负责将研究请求编排为可执行的因子或策略实验，并基于只读市场数据产出结构化回测结果。运行时源码位于 `ResearchEngine/app`，公开 Python 命名空间统一为 `app.*`。

### 2.1 负责的能力

- 接收 HTTP、Python API 和 CLI 研究请求。
- 校验请求 DTO、研究资产引用、数据快照和回测参数。
- 统一编排因子计算、策略信号生成、组合回测、指标计算和结果分析。
- 管理实验并发、排队、取消、去重、生命周期和运行时数据上下文。
- 提供因子库、策略库和已发布市场数据的只读查询接口。
- 承载因子批量回测的协调、重试、进度查询和标量结果持久化。
- 提供可追溯的执行版本、指标版本、数据发布版本和源码哈希。

### 2.2 明确不负责的能力

- 不负责用户、租户、权限、计费和前端页面；这些属于平台或 WebApp 边界。
- 不负责交易所接入、订单路由、实盘执行和交易组合管理；TradingEngine 仍处于规划阶段。
- 不把项目级因子/策略目录当作用户资产 CRUD 服务；当前目录是随项目发布的可执行资产。
- 不把 AI 生成、解释接口当作回测算法本身；AI 接口当前只是应用层的草稿生成和结果解释适配。
- 路由负责 HTTP 适配，业务进入 services；内部模型不反向依赖服务、HTTP 或数据访问。

## 3. 总体架构

ResearchEngine 自己拥有研究计算能力，取消 app.quantcore 共享库假设。
WebApp 通过 HTTP 使用研究结果；不为未建立的 TradingEngine 预设代码依赖。

```text
api / CLI / Python → services（实验、回测、目录、批量、AI 适配）
                           ├── models（配置、面板、上下文和结果）
                           └── database（Provider、缓存和持久化）
                                      └── MarketData / 输出 / SQLite
```

选择依据见 [ADR-028](../../../docs/05-技术决策/ADR-028-因子回测由BacktestEngine编排四引擎.md) 和
[ADR-029](../../../docs/05-技术决策/ADR-029-研究服务采用services与models分层.md)；并发、运行时和 API
边界分别见本文件第 1.1 节列出的 ResearchEngine ADR。

## 4. 代码结构

```text
ResearchEngine/app/
├── main.py                         # FastAPI 入口、生命周期和依赖组装
├── api/                            # 路由与控制器
├── models/                         # 面板、配置、结果、上下文和状态
├── schemas/                        # HTTP 请求/响应
├── services/
│   ├── data/                       # DataEngine
│   ├── factor/                     # FactorEngine、加载和预处理
│   ├── portfolio/                  # PortfolioEngine
│   ├── metric/                     # MetricEngine
│   ├── backtest/                   # BacktestEngine
│   ├── experiment/                 # Experiment、Manager、runtime
│   ├── strategy/                   # 既有向量化/事件策略计算
│   ├── catalog/                    # 资产目录业务
│   ├── results/                    # ResultManager
│   └── factor_backtest_batch/      # 批量协调和任务注册表
├── database/                       # Provider、缓存、存储、SQLite 访问
├── utils/                          # 通用工具、异常和路径
├── config.py                       # ConfigManager
├── assets/                         # 策略资产；因子旧源码仅作迁移兼容
└── cli/                            # 现有命令行入口
```

四个计算 Engine 与 BacktestEngine 都是 services，不是模型。models 包含 dataclass、枚举、
面板和结果结构；BaseFactor、FactorLibrary、BaseMetric 等执行契约仍是对应业务服务的组成部分。
仅数据字段访问、纯身份计算和数据不变量留在模型，不把所有类机械地搬入 models。

## 5. 依赖方向与组合根

1. main.py 创建 FastAPI、Manager、任务注册表和依赖；依赖注入仍由 api/dependencies.py 适配。
2. api 路由调用 services；Engine 的输入和输出是 models、DataFrame、Series 或普通映射。
3. services 在读取数据或保存结果时调用 database，database 不反向构造 ResultManager 等服务。
4. models 不在运行时导入 api/schemas/services/database/config；服务类型注解通过 TYPE_CHECKING 隔离。
5. schemas 继续保存 HTTP 请求/响应。现有 service 内 HTTP 投影及 AI 辅助未在本轮全部拆分，
   不据目录迁移宣称所有 HTTP DTO 依赖已消除；新引擎计算不能进一步依赖 HTTP。
6. utils 只存通用路径、日期切片和异常等辅助；计算与编排仍属于 services。

内部旧导入一次切换，运行时源码不保留 app.quantcore/core/repositories 转发包。
Python 调用方应迁移导入；HTTP/OpenAPI 和数据库 schema 不改变。

## 6. 应用生命周期与部署模型

### 6.1 FastAPI 组合

`app.main:create_app()` 当前创建：

- `FastAPI(title="SVQuant Research API", version="2.0.0")`。
- 一个进程级 `ExperimentManager(max_workers=2, max_queue_size=8)`。
- 一个进程级 `FactorBacktestBatchTaskRegistry`。
- `/api` 路由树，包括 health、catalog、factor、strategy、batch 和 AI 适配。
- 应用 lifespan：启动 Manager，关闭时先等待批量任务，再关闭 Manager 和其 `ResearchRuntime`。

当前开发配置允许全来源 CORS。生产部署必须收紧来源、认证和内部接口访问范围。

### 6.2 单进程约束

当前任务状态、队列、去重表、字段缓存和部分目录查询缓存都在进程内。默认启动入口使用：

```text
uvicorn app.main:app --host 0.0.0.0 --port 9527 --workers 1
```

因此现阶段应保持单进程单实例：

- 多 worker 会复制 Manager、并发配额、任务注册表和内存缓存。
- 一个 worker 看不到另一个 worker 的任务状态，轮询和取消会产生不一致。
- 横向扩展前需要将任务队列、状态和锁迁移到外部协调组件，并拆出独立 worker。

### 6.3 配置入口

常用配置通过环境变量注入，实际默认值以 `app.config` 为准：

| 配置 | 作用 |
|---|---|
| `SVQUANT_DATA_DIR` | 当前 `marketdata/` 数据根目录或显式数据根目录；默认值为仓库根目录下的 `marketdata/` |
| `SVQUANT_EXPERIMENT_MAX_WORKERS` | 实验执行并发上限，默认 2 |
| `SVQUANT_EXPERIMENT_MAX_QUEUE_SIZE` | 实验等待队列上限，默认 8 |
| `SVQUANT_FIELD_CACHE_MAX_BYTES` | 进程级字段 LRU 上限，默认约 2 GiB |
| `SVQUANT_BACKTEST_CACHE_ENABLED` | 因子回测文件缓存开关 |
| `SVQUANT_BACKTEST_CACHE_TTL_DAYS` / `SVQUANT_BACKTEST_CACHE_MAX_BYTES` | 文件缓存保留时间和容量上限 |
| `SVQUANT_BACKTEST_CACHE_DIR` | 因子回测可再生缓存目录 |
| `SVQUANT_FACTOR_DB_PATH` / `SVQUANT_FACTOR_DB` | SQLite 因子库路径；默认 `app/assets/factors/factor_library.db` |
| `SVQUANT_FACTOR_TOOL_PATH` / `SVQUANT_FACTOR_TOOL` | 因子公共算子模块路径；默认 `app/assets/factors/tool.py` |
| `SVQUANT_FACTOR_DIR` / `SVQUANT_STRATEGY_DIR` | 迁移期旧因子、策略资产目录覆盖 |
| `SVQUANT_FACTOR_BACKTEST_DB` 或对应 DB path 配置 | 批量回测 SQLite 存储位置 |

## 7. 实验调度与共享运行时

### 7.1 ExperimentManager

`Experiment` 是统一执行协议：

```python
class Experiment(ABC):
    @abstractmethod
    def run(self, context: ExperimentContext): ...
```

`ExperimentContext` 为冻结对象，至少包含当前 `ResearchDataContext`，并通过属性暴露 `DataEngine` 和 provider。当前实现支持两类 lane 元数据：`interactive` 和 `batch`；lane 用于标识来源，调度仍由一个 FIFO Manager 统一处理。

Manager 的职责和状态模型：

```text
submit
  ├─ 容量可用 ──> queued ──> running ──> succeeded / failed
  └─ 队列满 ──> rejected

queued cancel ──────────────> cancelled（释放容量）
running cancel ─────────────> cancel_requested（不强杀用户线程）
```

- 总容量为 `max_workers + max_queue_size`，默认 10 个任务槽位。
- 以 `key` 做 inflight 去重；相同请求可以复用正在运行或排队的 Future。
- 终态快照在内存中保留约 60 秒，供 HTTP 轮询。
- 取消排队任务是实际取消；运行中任务只能设置取消请求，避免强行杀死用户 Python 线程。
- Manager 持有并复用同一进程级 `ResearchRuntime`，实验完成后不关闭共享数据资源。

### 7.2 ResearchRuntime 与 ResearchDataContext

```text
ExperimentManager
        │ owns
        ▼
ResearchRuntime
        │ lazy / release-aware
        ├─ FieldParquetProvider
        └─ DataEngine
                │
                ▼
ResearchDataContext(
    data_dir, release_id, provider, data_engine
)
```

`ResearchRuntime` 在第一次需要数据时懒加载 `FieldParquetProvider` 和 `DataEngine`，并按有效数据目录与 release signature 复用上下文。检测到 MarketData 发布切换时，原子替换上下文；新实验使用新 release，正在运行的实验继续持有自己的上下文。

数据访问约束：

- `FieldParquetProvider` 只读当前发布目录，支持 `current` 入口和显式 release。
- `DataEngine` 是 provider 的透明门面，统一暴露 `get_bars`、`get_universe`、`get_symbols`、`get_panels`、指数和快照查询。
- provider 实现包括 CSV、Parquet、Field Parquet、Wide CSV、AkShare、Wind 和 ClickHouse；业务 service 不应依赖具体 provider。
- 进程级字段 LRU 只缓存原始字段 DataFrame 或切片，不缓存因子值和完整结果。
- 市场数据查询 API 的展示缓存与 Manager 所有的回测 runtime 相互独立，不能据此推断二者共享同一个生命周期。

MarketData 的发布格式和目录约定见项目级 [`database_design.md`](../../../docs/02-架构文档/database_design.md)。

## 8. 因子回测执行架构

因子单次回测、HTTP 异步请求、Python facade 和批量回测最终都汇聚到同一条执行边界：

```text
FactorBacktestRequest
        │ normalize / validate / snapshot
        ▼
FactorBacktestSpec（冻结、可哈希、含 provenance）
        │
        ▼
FactorBacktestExperiment / FactorExperiment
        │
        ▼
BacktestEngine.run（应用层完整编排）
        ├─ DataEngine：行情、股票池、可选筛选掩码和告警
        ├─ FactorEngine：来源加载、因子计算、有效池、预处理
        ├─ PortfolioEngine：分组、权重、持仓、远期收益对齐
        ├─ MetricEngine：收益、净值、IC、分组及 core/full 评价
        └─ FactorBacktestResult / ResultManager
```

`FactorBacktestExperiment` 仅负责因子任务适配，标准因子入口是 `BacktestEngine`；策略回测仍可
使用 `BacktestSignals`、`NativeEngine` 和 `EventBacktestEngine`。

### 8.1 Spec 与可追溯性

`FactorBacktestSpec` 将计算参数、数据快照、资产来源和输出策略显式化。结果至少应带有：

- `execution_version`：当前因子执行协议版本。
- `metric_version`：当前因子评分卡版本。
- `data_release_id`：实际使用的 MarketData 发布版本。
- `spec_hash`：规范化请求的身份哈希。
- `actual_end`：本次任务从当前 release 实际取得的数据终点；原始 Spec 不因此被改写。
- `factor_source_hash`：内置或用户代码因子源码哈希。

这使文件缓存、批量记录和结果解释能够区分“参数相同但数据或源码不同”的运行。
`start/end` 只控制收益确认范围；预热历史属于计算输入，不应被误当作收益样本。

### 8.2 计算阶段

1. 解析 `start/end/as_of`；在 release 和 `as_of` 允许的上界内加载完整历史用于滚动预热，因子值、远期收益、分层分析和指标最终裁剪到收益确认区间。
2. 通过 `DataEngine` 读取收盘价、交易状态、指数、股票池及需要的面板。
3. 通过 `FactorEngine` 加载和计算因子，先应用 DataEngine 有效池，再按配置去极值和标准化。
4. 通过 `PortfolioEngine` 生成共同分组、目标权重、持仓、调仓意图和前瞻收益。
5. 将组合产物交给 `MetricEngine`，统一计算收益、净值、费用、IC、分组和 core/full 评价。
6. 将结果放入 `MetricContext` 并由应用层组装 `FactorBacktestResult` / HTTP 响应。
7. 生成 core 或 full 分析；可选分析失败时按能力降级，不影响核心回测结果返回。
8. 返回 `FactorBacktestResult`，按需由 `ResultManager` 保存 CSV、Parquet 或 SQLite 产物。

### 8.3 FEAT-030 当前实现与剩余验收

[FEAT-030 文档包](../../../docs/03-功能文档/FEAT-030-因子回测流程重构/README.md)
FEAT-030 已由用户批准并完成主链迁移。下图是当前实现；专项跨入口、并发、性能和数值
差异仍按 Feature Verification 收口，不能把阶段性自动化通过写成最终交付。

```text
ExperimentManager
  → FactorExperiment / FactorBacktestExperiment
    → BacktestEngine.run(spec, context)                 # services
      → DataEngine：完整行情、筛选掩码和诊断             # services
      → FactorEngine：计算、有效池、可选去极值/标准化
      → PortfolioEngine：分组、权重、持仓、前瞻数据对齐
      → MetricEngine：收益、净值、基准、IC、core/full 评价
      → FactorBacktestResult / ResultManager
```

- 五个 Engine 均位于 services，内部数据结构位于 models；不再存在 QuantCore 包边界。
- DataEngine 保持共享只读行情，筛选不删历史行；因子与组合状态按任务隔离。
- 因子值、组号、权重分别保留；前瞻收益先在完整索引上计算，只参与评价。
- 停牌/涨停过滤、去极值、标准化默认关闭；新过滤和中性化入口不在首期。
- 缺过滤状态时跳过并告警，保留在当次结果、缓存及日志，不增加批量历史字段。
- 保留现有收益、净值基点、公式和展示时序；批量解除强制过滤，API/CLI 开放四项配置。
- 新因子执行版本为 factor-execution-v5，缓存为 factor-backtest-v11，指标版本为
  factor-scorecard-v3；因子分组使用向量化 rank，核心回测固定计算毛收益。
- 第 9 节策略链路继续使用旧 Native/Event；第 11 节因子批量已调整任务内部委托，
  不改变 Manager、两槽窗口、重试或历史 schema。

相关长期选择见 [ADR-028](../../../docs/05-技术决策/ADR-028-因子回测由BacktestEngine编排四引擎.md)。

## 9. 策略回测执行架构

策略入口同样通过 `StrategyExperiment` 接入 Manager，但策略执行模式由请求的 `engine_mode` 决定。

| 模式 | 用户入口 | 执行内核 | 输出重点 | 当前状态 |
|---|---|---|---|---|
| `vectorized` | `generate_signals` | `BacktestSignals` → `NativeEngine` | 净值、收益、持仓、再平衡 | 当前主路径 |
| `event` | `initialize(context)` | `EventBacktestEngine` | 订单、成交、持仓快照、事件 | 日频 MVP |

共同流程：

```text
StrategyBacktestRequest
        │
        ├─ strategy_code 或 strategy_id（二选一）
        ├─ universe / benchmark 快照或内置资产
        └─ execution mode
        ▼
StrategyCatalog / snapshot resolver
        ▼
源代码校验、编译、入口校验
        ▼
DataEngine 读取研究面板
        ▼
vectorized NativeEngine 或 event EventBacktestEngine
        ▼
MetricEngine + benchmark + StrategyBacktestResponse
```

内置策略通过 `StrategyCatalog` 加载经过索引的源码版本；请求中的 universe 和 benchmark 快照用于固定研究边界，避免执行过程中依赖可变的前端状态。策略源码当前通过受信任环境中的 `exec` 编译执行，生产化沙箱仍是后续工作。

## 10. 研究计算服务与策略适配

### 10.1 Data、Factor、Metric

- `DataEngine`：屏蔽 provider 差异，负责数据接口校验和面板组装。
- `FactorEngine`：维护因子注册表、加载器和计算后端；默认 Python backend。内置因子默认由
  `SQLiteFactorLoader` 从外部 SQLite 加载，用户源码仍走受控临时模块，loader 仍可注入替换。
- `MetricEngine`：维护标准指标注册表，统一执行单个、多个和全部指标；业务层通过 `MetricContext` 提供输入。

这些计算能力和 PortfolioEngine 均属于 services；MetricContext、Panel 等输入由 models 定义。
引擎计算不依赖 HTTP DTO，数据访问由 database Provider 提供。

### 10.2 Backtest adapter

既有策略服务在 `app.services.strategy.vectorized` 保留 adapter；它不是因子 BacktestEngine 的后端层：

```text
BacktestSignals + BacktestConfig
              │
              ▼
IBacktestEngine.run(...)
              │
              ├─ NativeEngine（当前已注册、默认）
              └─ 其他 backend（按需注册）
```

策略侧因子分位、因子分组和因子组合策略仍可把研究信号转换为组合意图；费用、撮合、
持仓和净值由 backtest adapter 处理。因子新主链不调用这些策略包装。事件引擎拥有独立的
`EventBacktestConfig`、`OrderService`、`PortfolioView` 和 `StrategyContext`，当前以日频执行为主。

## 11. 批量因子回测架构

批量回测有自己的业务协调器和 HTTP 任务注册表，但计算不能绕过统一 BacktestEngine：

```text
internal POST /api/internal/factor-backtest-batches
        ▼
FactorBacktestBatchTaskRegistry
        │ one coordinator thread
        ▼
FactorBacktestBatchCoordinator
        │ fixed profile / catalog preflight / window=2
        ▼
FactorBacktestSpec × N
        │ submit lane=batch
        ▼
ExperimentManager（共享 2 个 worker）
        ▼
FactorBacktestExperiment → BacktestEngine
        ├─ 完成一个，再补充下一个 pending
        ├─ 运行时失败最多自动重试一次
        └─ 写入 FactorBacktestStore（SQLite 标量投影）
```

当前批量 profile 固定为 as-of/十年窗口、`CSI_ALL` 与 `CSI300`、long-only、5 组、日频再平衡、core 分析及涨跌停/停牌过滤。`batch_window=2` 是业务窗口，不等同于 Manager 的全部队列容量。

持久化边界：

- `FactorBacktestBatchTaskRegistry` 只保存进程内任务快照，终态约保留 60 秒。
- `FactorBacktestStore` 使用 SQLite 保存 batch、factor run、分位指标和预测指标等标量数据，供历史查询。
- 批量 Store 是批量业务的写入方，不替代通用 `ResultStorage`，也不保存完整净值曲线和全部中间面板。
- 批量请求复用 Manager 的 `ResearchRuntime`，协调器自身不负责关闭 Manager。

## 12. 资产、结果和缓存

### 12.1 因子与策略资产

```text
app/assets/factors/factor_library.db
app/assets/factors/tool.py
        └─ SQLiteFactorRepository / SQLiteFactorLoader

旧 app/assets/factors/index.yaml + libraries/*.py
        └─ 迁移期旧 FactorLoader（非默认来源）

app/assets/strategies/index.yaml
app/assets/strategies/libraries/*
        └─ StrategyCatalog
```

SQLite 因子库集中保存库、分类、稳定 `sv_id`、展示名称、说明和源码；`tool.py` 提供公共算子。
加载器负责只读查询、源码编译和 `BaseFactor` 适配，不负责执行因子计算。旧 YAML/源码路径仅用于
迁移期兼容，不是默认目录、回测或批量来源。

### 12.2 结果存储与缓存分层

| 层 | 实现 | 生命周期 | 目的 |
|---|---|---|---|
| 执行结果对象 | `FactorBacktestResult` / `ResultManager` | 当前任务及调用方持有 | 向 API、Python 和批量协调器传递结构化结果 |
| 结果存储 | CSV / Parquet / SQLite / ClickHouse adapter | 按输出配置 | 保存完整或可查询的研究产物 |
| 因子文件缓存 | `FileBacktestCache` | 可再生、TTL/容量淘汰 | 避免同一规范请求重复计算 |
| 批量业务库 | `FactorBacktestStore` SQLite | 持久化 | 保存批量历史、进度和标量指标 |
| 字段缓存 | 进程级 LRU | 进程生命周期 | 减少相同 MarketData 字段的重复读取 |

文件缓存不是业务历史，不能作为审计记录或唯一结果来源；缓存命中必须仍受请求规范、源码哈希和数据发布指纹约束。

## 13. HTTP 接口地图

根路径当前统一为 `/api`，不存在并行的 `/api/v2` 运行时路由。

| 分组 | 路由 | 语义 |
|---|---|---|
| 健康 | `GET /api/health` | 服务、数据目录和引擎能力检查 |
| 目录 | `GET /api/factor-libraries`、`GET /api/factors/{library_name}` | 因子库和因子只读查询 |
| 目录 | `GET /api/strategies` | 策略只读查询 |
| 市场数据 | `/api/market-data/daily/{symbol}`、`/symbols`、`/indices`、`/indices/{code}/constituents` | 已发布市场数据查询 |
| AI 适配 | `POST /api/ai/factor-generations`、`strategy-generations`、`backtest-interpretations` | 草稿生成和结果解释，不替代实验执行 |
| 因子回测 | `POST /api/backtest/factor`、`GET/DELETE /api/backtest/factor/{run_id}` | 提交、轮询和取消异步因子任务 |
| 策略回测 | `POST /api/backtest/strategy` | 当前 HTTP 同步等待结果，内部仍通过 Manager 执行 |
| 批量查询 | `/api/factor-backtest-batches` 及其 factors/history 子路由 | 查询批量历史、因子指标和进度 |
| 内部批量 | `POST /api/internal/factor-backtest-batches`、`GET /api/factor-backtest-batch-tasks/{task_id}` | 创建和轮询批量任务，需受信任网络控制 |

因子回测 POST 返回 `202 Accepted` 和 `run_id`/轮询地址；策略回测当前对调用方保持同步响应，这是 HTTP 契约差异，不代表两者使用不同的核心执行管线。

## 14. 状态与数据生命周期

```text
只读 MarketData release ────────────────┐
项目资产 index/source ──────────────────┤
请求 DTO / snapshot ────────────────────┤
                                         ▼
                              ExperimentManager
                                         ▼
                              结果对象 / 可选产物
                                ├─ 文件缓存（可再生）
                                └─ 批量 SQLite（历史投影）
```

| 对象 | 来源 | 可变性 | 失效/清理方式 |
|---|---|---|---|
| MarketData release | 外部发布目录 | ResearchEngine 只读 | 发布新 release，runtime 原子切换 |
| 因子/策略资产 | 项目代码和索引 | 随代码版本变化 | Git 版本或资产索引更新 |
| 运行中任务 | Manager 内存 | 可取消/状态变化 | 终态保留约 60 秒 |
| 字段 LRU | 进程内存 | 自动淘汰 | 容量上限或进程退出 |
| 因子回测缓存 | 本地文件 | 可删除、可重建 | TTL、容量淘汰或手动清理 |
| 批量结果 | SQLite | 持久化 | 按数据库生命周期维护 |
| 完整研究产物 | 输出目录或结果存储 | 按配置持久化 | 由调用方/运维策略管理 |

## 15. 安全与运维约束

当前实现允许受信任的因子/策略 Python 源码通过 `exec` 编译执行，因此不能把公开互联网用户输入直接当作同等权限的本地进程代码运行。生产化部署至少需要：

- 独立 worker 或容器沙箱、CPU/内存/时间限制。
- 只读挂载 MarketData 和资产目录，限制输出目录和网络访问。
- API 认证、租户隔离、请求大小限制，以及 `/api/internal/*` 的内网或服务身份控制。
- 收紧 CORS，禁止调试配置直接暴露到公网。
- 监控 Manager 队列深度、拒绝数、运行时失败、缓存命中率、数据 release 和 SQLite 写入延迟。
- 在引入多实例前，先设计共享任务状态、幂等键、取消语义和 worker 恢复策略。

## 16. 当前实现与演进边界

| 能力 | 当前基线 | 后续演进 |
|---|---|---|
| 包和入口 | 单一 `app.*` 命名空间，`app.main` 组合 | 保持上层 API 稳定，继续拆分可部署 worker |
| 实验调度 | 单进程 Manager，2 worker + 8 queued | 外部队列、持久化状态和多实例调度 |
| 数据访问 | `ResearchRuntime` 复用 `FieldParquetProvider` + `DataEngine` | 更多发布治理、质量校验和远程数据服务 |
| 因子资产 | SQLite 因子库 + 项目内 `tool.py`，`SQLiteFactorLoader` 为默认来源；旧 YAML/源码仅迁移兼容 | 版本快照、权限和服务化注册中心 |
| 因子回测 | BacktestEngine 编排四个 services 引擎，core/full 分析；旧 Executor 已移除 | 更多研究规则、性能优化和后续数据来源 |
| 策略回测 | vectorized 主路径，event 日频 MVP | 更完整事件撮合、实时/仿真交易能力 |
| 批量回测 | window=2，进程协调器 + SQLite 标量历史 | 独立批处理 worker、断点恢复和大规模调度 |
| 安全 | 受信任环境执行 Python 源码 | 生产沙箱、权限、租户和审计体系 |
| 交易能力 | TradingEngine 尚未建立 | 订单路由、执行和组合管理独立成同级模块 |

## 17. 关联文档

- [`docs/02-架构文档/system_architecture.md`](../../../docs/02-架构文档/system_architecture.md)：全系统模块和依赖方向。
- [`docs/02-架构文档/database_design.md`](../../../docs/02-架构文档/database_design.md)：MarketData 发布目录、字段格式和数据层设计。
- [`docs/02-架构文档/engine-design.md`](../../../docs/02-架构文档/engine-design.md)：Native/Event 回测引擎设计。
- [`ResearchEngine/docs/03-功能文档/FEAT-002-研究引擎/`](../03-功能文档/FEAT-002-研究引擎/)：ResearchEngine 产品需求和技术设计包。
- [`docs/03-功能文档/FEAT-003-回测适配层/`](../../../docs/03-功能文档/FEAT-003-回测适配层/)：回测适配层设计。
- [`ResearchEngine/docs/03-功能文档/FEAT-027-因子批量回测/`](../03-功能文档/FEAT-027-因子批量回测/)：批量因子回测设计。
- [`ResearchEngine/docs/03-功能文档/FEAT-028-分层应用架构/`](../03-功能文档/FEAT-028-分层应用架构/)：统一 `app.*` 命名空间和分层约束。
- [`ResearchEngine/docs/03-功能文档/FEAT-029-因子注册/`](../03-功能文档/FEAT-029-因子注册/)：因子注册和 loader 演进。
- [`docs/06-技术决策/ADR-019-为什么由ExperimentManager管理回测并发.md`](../05-技术决策/ADR-019-为什么由ExperimentManager管理回测并发.md)：Manager 并发和生命周期。
- [`docs/06-技术决策/ADR-018-因子计算区间与收益确认区间分离.md`](../05-技术决策/ADR-018-因子计算区间与收益确认区间分离.md)：预热历史和收益确认区间。
- [`docs/06-技术决策/ADR-020-因子批量指标仓库使用独立SQLite.md`](../05-技术决策/ADR-020-因子批量指标仓库使用独立SQLite.md)：批量指标存储边界。
- [`docs/06-技术决策/ADR-021-因子回测接口采用异步任务查询.md`](../05-技术决策/ADR-021-因子回测接口采用异步任务查询.md)：异步任务 API。
- [`docs/06-技术决策/ADR-022-回测运行时由ExperimentManager持有共享行情上下文.md`](../05-技术决策/ADR-022-回测运行时由ExperimentManager持有共享行情上下文.md)：共享数据 runtime。
- [`docs/06-技术决策/ADR-023-采用单一app命名空间与两槽批量FIFO.md`](../05-技术决策/ADR-023-采用单一app命名空间与两槽批量FIFO.md)：应用命名空间和分层边界。
- [`docs/06-技术决策/ADR-024-ResearchEngine HTTP API 使用 api 前缀.md`](<../05-技术决策/ADR-024-ResearchEngine HTTP API 使用 api 前缀.md>)：当前 HTTP 前缀。
- [`docs/06-技术决策/ADR-025-回测采用单一应用执行管线与可插拔后端.md`](../05-技术决策/ADR-025-回测采用单一应用执行管线与可插拔后端.md)：因子回测统一执行边界。
- [`docs/06-技术决策/ADR-028-因子回测由BacktestEngine编排四引擎.md`](../../../docs/05-技术决策/ADR-028-因子回测由BacktestEngine编排四引擎.md)：当前因子执行管线和四引擎职责。
- [`docs/06-技术决策/ADR-029-研究服务采用services与models分层.md`](../../../docs/05-技术决策/ADR-029-研究服务采用services与models分层.md)：当前 ResearchEngine 目录和职责边界。
- [`docs/06-技术决策/ADR-027-QuantCore三引擎兼容式重构.md`](../../../docs/05-技术决策/ADR-027-QuantCore三引擎兼容式重构.md)：Data/Factor/Metric 三引擎的兼容式重构。
