# FEAT-028：ResearchEngine 分层应用架构

> 2026-08-28 架构修订：用户已确认 ADR-029 的常规 FastAPI 分层。
> 原 QuantCore 运行时边界取消；五个 Engine 的业务逻辑进入 `app.services`，
> Panel、MetricContext、回测规格/结果和实验上下文进入 `app.models`，数据访问进入 `app.database`。
> 配置为 `app.config`，通用工具为 `app.utils`；不增加 domain/application/infrastructure。
> 下文中的旧目录和旧分层仅作历史设计追溯，不再作为新代码约束；既有业务规则和历史验证记录保留。
> 详见根目录 FEAT-030/06-app-layout.md 与 ADR-029。FEAT-029 因子来源加载目标保持不变。

- 状态：开发中
- 所属 Initiative：INIT-001 投研核心
- 优先级：P0

## 文档索引

- `03-technical-design.md`：分层、依赖、运行时和迁移设计

其余原分册（`01-feature-proposal.md`、`02-product-requirements.md`、`04-project-plan.md`、`05-verification.md`）内容已收编至本 README。

## 1. 价值与范围

### 背景

原工程把核心量化引擎、投研编排、FastAPI 路由、因子资产和策略资产分散在多个顶层
包中。随着因子批量回测、策略资产版本化和异步任务加入，旧入口容易被误用，API 也
可能直接触碰行情或 SQLite 细节，增加迁移和回归成本。

### 用户价值

- 研究员使用同一个 `app.*` 命名空间，不需要记忆多个包的安装与导入规则；
- API、业务用例、持久化和 QuantCore 的职责可独立测试；
- 因子、策略资产随应用发布，索引和源码路径稳定；
- 批量因子回测成为清晰的具体业务能力，不与通用任务 Manager 混淆。

### 商业价值

稳定的运行时边界降低新因子、新策略和 Web API 交付成本，为后续研究订阅、评分卡和
策略组合能力提供可演进的基础，而不把当前 MVP 过早绑定到分布式基础设施。

### MVP 范围

#### 必须做

- `ResearchEngine/app` 单一命名空间和 `app.main` 唯一 FastAPI 入口；
- API、schemas、业务能力、repository/database、QuantCore 的固定依赖方向；
- `Experiment` 抽象基类、Factor/Strategy/FactorBacktestBatch 三类具体实验；
- 唯一 Manager、普通 FIFO、有界容量和 FastAPI lifespan 生命周期；
- `FactorBacktestBatchCoordinator` 自有容量为 2 的批量窗口和独立的单线程任务注册表；
- 因子/策略资产迁移、SQLite repository 边界和 `/api` 契约；
- 删除旧运行时包和历史教学入口。

#### 可以以后做

- 多实例调度、分布式锁、外部消息队列；
- WebApp `/api` 适配；
- ORM、PostgreSQL/ClickHouse 结果仓库；
- 用户鉴权、多租户和权限模型。

#### 明确不做

- Manager 内部优先队列或 lane 插队；
- 本次重构修改 WebApp；
- 为兼容旧 Python 导入路径保留转发模块。

## 2. 业务规则与场景

### 用户故事

1. 作为 API 使用者，我希望所有请求经过 `/api` 控制器并得到稳定的请求/响应结构。
2. 作为研究员，我希望因子和策略只依赖 QuantCore 的公开接口，不被 FastAPI 运行时绑架。
3. 作为平台维护者，我希望 FastAPI 进程只创建一个 Manager 和一个行情运行时。
4. 作为批量任务使用者，我希望批量回测最多同时提交两个因子；一个结束后才补充下一个。
5. 作为交互式用户，我希望已经排队的交互回测按普通 FIFO 先于后提交的批量任务执行。

### 业务边界

- API 只负责参数校验、依赖注入、业务调用和 schema 序列化；
- 业务协调器负责用例、幂等、重试、进度和状态转换；
- repository/database 负责 SQLite、资产目录和结果持久化；
- QuantCore 只负责数据、因子、指标和回测基础设施；
- `Experiment` 只接受 Manager 注入的只读 `ExperimentContext`；
- 生产只支持单实例、单 Uvicorn Worker，内部批量接口只部署在可信内网。

### 验收标准

- `from app.main import app` 可导入，lifespan 能启动并关闭 Manager；
- `Experiment` 不能直接实例化，Manager 拒绝普通 callable；
- FactorExperiment、StrategyExperiment 能通过 Manager 执行；
- 任意时刻批量未完成提交数不超过 2，完成一个才提交下一个；
- Manager 的任务执行顺序与提交顺序一致，不根据 lane 插队；
- API 层无直接 QuantCore/SQLite 导入，QuantCore 无 FastAPI/service/schema 导入；
- 旧教学入口、旧包导入和旧式实验构造工作流不再存在；
- editable 安装、启动 smoke test 和全量 pytest 通过。

## 3. 验收与证据

### 自动化验证矩阵

| 验收项 | 验证方式 |
|---|---|
| `app.main` 生命周期 | `tests/api/test_v2_contract.py` |
| Experiment 抽象和 callable 拒绝 | `tests/services/test_experiment_contract.py` |
| Manager 普通 FIFO、容量和取消 | `tests/test_experiment_manager.py` |
| 批量两槽窗口和交互任务先到先执行 | `tests/services/test_factor_backtest_batch_queue.py` |
| SQLite repository 边界 | `tests/repositories/test_factor_backtest_repository.py`、`test_factor_batch.py` |
| 因子/策略资产索引 | `tests/assets/test_asset_namespace.py`、既有库测试 |
| API 响应契约 | `tests/test_api.py`、`test_factor_backtest_async.py` |
| 单因子与批量规格/结果一致、严格截止日和预热 | ADR-025 统一执行器测试、因子回测回归测试 |
| 批量协调器不导入回测算法、基准或指标实现 | 架构约束测试（源码依赖扫描） |
| QuantCore 结果与指标回归 | `tests/quantcore/`、ResearchEngine 因子/策略测试 |

### 交付命令

```bash
pip install -e .
uvicorn app.main:app --workers 1
pytest
```

启动验证必须确认：

1. `app.main:app` 可导入并可打开 `/api/health`；
2. lifespan 结束后 Manager/runtime 已关闭；
3. API 源码不直接导入 QuantCore 或 SQLite；
4. QuantCore 源码不导入 FastAPI、schemas、services 或 repositories；
5. 全量扫描不再发现旧 `researchengine.*`、`quantcore.*`、examples 工作流或
   旧式基于关键字参数的 `Experiment` 构造。

## 4. 计划与里程碑

### 任务拆解

| 任务 | 复杂度 | 风险 | 依赖 | 状态 |
|---|---:|---|---|---|
| 迁移 QuantCore 到 `app.quantcore` | 4 | 中 | 包发现配置 | 已完成 |
| 建立 api/schemas/services/repositories/database/core 分层 | 4 | 中 | 运行时导入分析 | 已完成 |
| Experiment 抽象、唯一 Manager 和生命周期 | 4 | 中 | QuantCore data/context | 已完成 |
| FactorBacktestBatchCoordinator 两槽 FIFO 窗口 | 4 | 中 | Manager、SQLite | 已完成 |
| 独立单线程批量任务注册表与关闭顺序 | 3 | 中 | Manager、FastAPI lifespan | 已完成 |
| 因子/策略资产和索引迁移 | 3 | 中 | catalog loader | 已完成 |
| `/api` 路由、依赖注入和 HTTP CLI | 3 | 低 | services | 已完成 |
| 旧目录删除、文档和 ADR | 2 | 低 | 迁移完成 | 进行中 |
| 全量测试、安装和启动 smoke test | 3 | 中 | 全部模块 | 进行中 |

### 排期与里程碑

- Week 1 / M1：新命名空间可安装，QuantCore 与 API 核心导入通过。
- Week 2 / M2：Factor/Strategy/Batch 三条回测链路和 FIFO 窗口通过专项测试。
- Week 3 / M3：文档、安装、启动 smoke test、全量 pytest 和部署约束完成。

### 风险与缓解

- 上游 `DataEngine`、`FactorEngine`、`FieldParquetProvider` 引用较多：先复制并切换导入，
  再删除旧包，保留量化结果回归测试。
- 单实例 Manager 是当前约束：在文档和启动命令中固定 `--workers 1`，后续再单独设计分布式调度。
- WebApp 仍使用旧契约：本次不改 WebApp，记录 `/api` 联调为后续任务。
- 本机 pytest 临时目录权限受限：验收时使用工作区下的临时目录，不改变业务代码。
