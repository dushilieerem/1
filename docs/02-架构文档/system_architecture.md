# SVQuant 系统架构设计

> 本文档定义 SVQuant 的系统架构，面向技术团队与老板汇报。
> 关联：`../99-历史归档/历史资料/system-architecture-v0.1.md`（历史原稿）、`../01-需求文档/产品定位.md`、`../05-技术决策/`（项目级 ADR）、`../../ResearchEngine/docs/05-技术决策/`（模块级 ADR）

> 当前实现说明：ResearchEngine 的运行时统一位于 `ResearchEngine/app`，公开 Python
> 命名空间为 `app.*`，FastAPI 唯一入口为 `app.main`。QuantCore 的独立包边界已取消；
> 代码分层以 ADR-029 为准，五个 Engine 全部属于 ResearchEngine 的 services。
> ResearchEngine 模块级架构见 `../../ResearchEngine/docs/02-架构文档/researchengine_architecture.md`。

---

## 0. 当前架构修订（FEAT-030 / ADR-028 / ADR-029）

用户确认采用常规 FastAPI 结构，取消 QuantCore 的共享库定位，见
[ADR-029](../05-技术决策/ADR-029-研究服务采用services与models分层.md)。
[FEAT-030](../03-功能文档/FEAT-030-因子回测流程重构/README.md) 的四引擎流程保持；
本轮只整理服务、模型和数据访问归属，自动化回归与专项验收分别记录。

当前项目级架构需同时承接 ResearchEngine 的已接受模块决策：因子计算与收益确认区间分离（ADR-018）、
Manager/Runtime 的进程级资源边界（ADR-019、ADR-022）、异步因子任务与 `/api` 前缀（ADR-021、ADR-024）、
独立批量指标 SQLite（ADR-020）、统一 BacktestEngine 执行边界（ADR-028）和 `services / models / database`
分层（ADR-029）。模块级细节以 [`ResearchEngine 模块架构`](../../ResearchEngine/docs/02-架构文档/researchengine_architecture.md)
为准；本文件只保留系统边界、跨模块依赖和公共数据契约。

| 服务 | 职责 |
|---|---|
| BacktestEngine | 组织完整因子回测 |
| DataEngine | 研究数据访问与可选筛选 |
| FactorEngine | 因子加载、计算和可选预处理 |
| PortfolioEngine | 分组、权重、持仓和评价标签对齐 |
| MetricEngine | 收益、净值、IC、分层和绩效评价 |

五者均位于 `app/services/`。Panel、MetricContext、回测规格/结果及实验上下文位于 `app/models/`。
所有过滤/预处理仍按已确认配置执行；当前因子执行版本为 `factor-execution-v4`，文件缓存为
`factor-backtest-v10`，指标版本为 `factor-scorecard-v2`。本轮不修改跨模块数据 schema，批量历史
由独立 SQLite 保存，具体字段和生命周期见模块架构与对应 ADR。

## 1. 系统边界

```text
SVQuant
├── WebApp                 # 前端与上层业务，通过 HTTP 调用研究服务
├── ResearchEngine         # 独立的投研计算应用；拥有自己的 services/models/database
├── marketdata             # iFinD 活动数据目录；研究服务只读读取
└── TradingEngine          # 规划中的交易应用；本期不规定其内部结构或依赖

外部同级项目
└── IFind                  # 外部数据采集、日更、源数据、候选、备份与发布工具
```

用户、数据、新闻、社区、研究、实盘/模拟盘仍是产品能力分类，不等于六个已部署服务。
ResearchEngine 当前负责因子/策略回测、调度、数据和资产只读查询、结果及批量历史。
WebApp 消费 HTTP API，不直接导入 Python 引擎。TradingEngine 没有已确认的共享代码需求，
不预建共享 QuantCore，不承诺研究事件引擎可以直接用于实盘。

`IFind` 与 SVQuant 不互相导入 Python 源码。`IFind` 独立持有供应商鉴权、HTTP 请求、raw/CSV/Parquet 生成、候选版本、备份和发布 CLI；SVQuant 只持有数据契约及 `marketdata/` 根目录中的活动数据。旧 `MarketData/` 目录已废弃。发布通过显式目标目录和清单/质量报告交接，见 ADR-031、ADR-032。

## 2. ResearchEngine 分层

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
├── logging.py                      # 标准 logging 配置；服务记录运行诊断与告警
├── assets/                         # 现有因子/策略源码和索引
└── cli/                            # 现有命令行入口
```

api 调用 services；services 使用 models，并按需调用 database。
models 不在运行时导入服务、HTTP、配置或存储；database 不构造业务服务。
ResultStorage 返回 ResultData，ResultManager.load 在服务层恢复管理对象。
utils 不承担选股、分组或绩效公式；分组和指标计算仍在对应 service。
`logging.py` 统一配置 Python 标准 `logging` 的 `app.*` 命名空间；各 service 记录运行状态、
可选数据缺失和过滤告警，结果/缓存仍保留需要对外展示的诊断副本。
`ConfigManager` 继续服务策略和应用配置，但因子回测主链只使用原始 `FactorBacktestSpec`，
不再把规格复制成第二份运行配置。

这是一套普通分层应用，不额外建立 domain/application/infrastructure 目录。

## 3. 研究执行模式

因子流程由一个具体 `BacktestEngine` 组织 `DataEngine`、`FactorEngine`、`PortfolioEngine` 和
`MetricEngine` 四个 services 引擎，不设因子专用 Executor、Native 实现层、Simulator 或通用工作流框架。
既有策略流程继续使用 `services/strategy/vectorized` 的 `NativeEngine` 和
`services/strategy/event` 的 `EventBacktestEngine`；本轮只迁移代码位置，不统一两类策略流程或改变撮合。

策略 Config、Signals、订单、成交及结果数据放在 models；策略执行方法留在 services。
因子主链不通过策略信号包装进行计算。两条路径共用研究数据和指标服务，不代表交易应用复用。

当前责任划分如下：

| 研究路径 | 当前入口 | 当前执行边界 | 对外行为 |
|---|---|---|---|
| 因子回测 | 单次、批量、Python | `FactorBacktestSpec → BacktestEngine.run()` | 单因子提交异步，批量提交异步 |
| 向量化策略 | `engine_mode=vectorized` | `StrategyExperiment → NativeEngine` | HTTP 当前同步等待 |
| 事件策略 | `engine_mode=event` | `StrategyExperiment → EventBacktestEngine` | 日频 MVP，保留既有事件语义 |

## 4. 数据与任务流程

```text
HTTP / Python / CLI
    → services 的实验入口
    → ExperimentManager（FIFO）
    → FactorBacktestExperiment
    → BacktestEngine
        → DataEngine → database Provider → 只读 MarketData release
        → FactorEngine → 因子面板
        → PortfolioEngine → 组合与对齐后的评价数据
        → MetricEngine → 效果计算
    → 结果组织、缓存/持久化、HTTP 响应或 Python 结果
```

数据发布链路独立于研究执行链路：

```text
iFinD HTTP → IFind 回填/日更 → IFind data/ifind 候选数据
    → 在 IFind 内校验、备份、显式发布 → SVQuant marketdata
    → FieldParquetProvider → DataEngine
```

database 在读取和保存时调用，不是 MetricEngine 之后才执行的计算步骤。
运行时维持一个 Uvicorn worker、一个应用级全局 DataEngine 和一个进程级 Manager。FastAPI lifespan
先由 DataEngine 加载固定 release，再启动 Manager；Manager 不向任务注入数据对象。
任务有独立因子注册、筛选结果、组合和评价数据；不为每个实验复制完整行情，不共享任务可变配置。

HTTP 与任务边界：

- `POST /api/backtest/factor` 只负责校验、生成任务并返回 `202`；调用方通过
  `GET/DELETE /api/backtest/factor/{run_id}` 查询或取消。
- `POST /api/internal/factor-backtest-batches` 返回批量 `task_id`；批量协调器以固定业务窗口
  向同一个 `ExperimentManager` 提交 `FactorBacktestExperiment`，历史标量写入独立
  `FactorBacktestStore` SQLite。
- 策略回测当前仍同步返回；异步因子任务、同步策略任务和批量业务协调不能混写成同一种 HTTP 契约。

## 5. 数据存储方案

| 数据类型 | 当前存储 | 所有权与说明 |
|---------|----------|--------------|
| MarketData release | Parquet | 以不可变 release 发布；物理上可按业务域宽表或字段文件组织，由 `FieldParquetProvider` 统一暴露逻辑字段面板。 |
| 研究运行时行情 | DataEngine 持有当前 release 的数据来源与字段缓存 | FastAPI lifespan 不预热字段；因子任务按 spec 的日期范围读取自己的字段切片，FieldFrameCache 只复用已经实际读取的完整字段。 |
| 因子值、组合和指标中间结果 | 任务内存 | 每个实验独立持有，不写入共享行情上下文；由 `BacktestEngine` 和四个 services 引擎协作产生。 |
| 完整回测结果 | CSV/Parquet/SQLite/ClickHouse | 由 `ResultManager` 和结果存储适配器按输出配置持久化到 `ResearchEngine/output/` 或指定后端。 |
| 因子批量历史和标量指标 | SQLite | 独立 `FactorBacktestStore`，默认路径为 `Factor/database/factor_backtest.db`；不替代完整结果存储。 |
| 用户资产与权限数据 | WebApp/平台侧 | ResearchEngine 只接收已解析的用户资产快照，不拥有用户资产 CRUD、鉴权和权限数据。 |

因子回测的 `start/end` 同时定义本次因子计算与回测数据范围；滚动窗口不足导致的缺失由因子设计
自行表达，系统不额外读取区间之前的预热历史。版本、源码哈希和 release 标识共同
参与结果身份，避免把不同数据版本或执行协议的结果混为一谈。

---

## 6. 后续扩展边界

多市场、分布式 worker 和 TradingEngine 属于后续需求，不以这次目录整理提前创建代码。
将来确有第二个应用的复用需求时，再基于实际契约评估提取公共库。
当前事件策略只保留既有日频研究能力和测试覆盖，不据此宣称实盘与全部市场规则已实现。

## 7. 接口形态

| 接口形式 | 当前职责 | 当前契约 |
|---------|----------|----------|
| Python API | 研究员和内部任务调用 | 单次、批量和策略入口复用 services；因子回测进入统一 `BacktestEngine`。 |
| CLI | 批量触发、运维和辅助研究 | 批量触发返回任务标识，查询仍走 ResearchEngine 任务/历史接口。 |
| HTTP (FastAPI) | WebApp 或其他受信任客户端远程调用 | 根路径统一为 `/api`；因子和批量提交异步返回 `202`，策略回测当前同步返回。 |

ResearchEngine 不提供 `/api/v2` 并行入口；公开 API 的完整路由和响应字段以模块功能文档为准，
跨模块调用必须同时遵循 ADR-021 与 ADR-024。

---

## 8. 架构决策索引

| 决策 | 当前选择 | 来源 |
|------|----------|------|
| ResearchEngine 分层 | `api / schemas / services / models / database / utils / config.py`，不恢复 QuantCore 独立包层 | [ADR-029](../05-技术决策/ADR-029-研究服务采用services与models分层.md) |
| 因子回测编排 | `BacktestEngine` 编排 Data、Factor、Portfolio、Metric 四个 services 引擎 | [ADR-028](../05-技术决策/ADR-028-因子回测由BacktestEngine编排四引擎.md) |
| 数据与调度边界 | 每进程一个应用级 `DataEngine` 持有固定 release；`ExperimentManager` 只调度 | [ADR-030](../05-技术决策/ADR-030-DataEngine持有应用级市场数据快照.md) |
| 数据生产边界 | 回填、日更、凭据、源数据、候选、备份和发布 CLI 位于独立 `IFind` 项目；SVQuant 只读消费 `marketdata/` 目录镜像 | [ADR-031](../05-技术决策/ADR-031-iFinD采集迁移为独立项目.md)、[ADR-032](../05-技术决策/ADR-032-MarketData扁平只读消费目录.md) |
| 因子任务接口 | 单次和批量提交异步返回任务标识；策略回测当前同步 | [ResearchEngine ADR-021](../../ResearchEngine/docs/05-技术决策/ADR-021-因子回测接口采用异步任务查询.md) |
| HTTP 根路径 | 统一使用 `/api`，不提供 `/api/v2` 并行入口 | [ResearchEngine ADR-024](../../ResearchEngine/docs/05-技术决策/ADR-024-ResearchEngine HTTP API 使用 api 前缀.md) |
| 批量指标存储 | 独立 `FactorBacktestStore` SQLite，完整结果仍走通用结果存储 | [ResearchEngine ADR-020](../../ResearchEngine/docs/05-技术决策/ADR-020-因子批量指标仓库使用独立SQLite.md) |
| 因子区间语义 | `start/end` 就是因子计算、组合和评价的数据范围；系统不额外补读区间前历史 | [ADR-028](../05-技术决策/ADR-028-因子回测由BacktestEngine编排四引擎.md) |
| 计算技术基座 | NumPy/Pandas 面板计算；策略保留向量化和事件两种执行模式 | ADR-001、ADR-002、[引擎详细设计](engine-design.md) |
| 历史行情存储 | 不可变 release + Parquet；Provider 向上提供统一字段面板 | ADR-003、ADR-016、ADR-017、[数据存储设计](database_design.md) |
| 包管理 | setuptools + pyproject.toml | 项目构建约束 |
| HTTP 框架 | FastAPI | 运行时实现与 OpenAPI 契约 |
| 业务模块边界 | 用户 / 数据 / 新闻 / 社区 / 研究 / 实盘模拟盘 | 产品能力边界；不等同于已部署服务数量 |
| 文档 | Markdown + AGENTS.md | 轻量，版本可控 |
| 代码托管与协作 | Gitee 为主仓 | 当前国内团队协作更稳定；需要国际生态时再评估 GitHub 镜像或双平台流程 |
