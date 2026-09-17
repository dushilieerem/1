## ADR-023: 采用单一 app 命名空间与两槽批量 FIFO

> 2026-08-28 架构修订：用户已确认 ADR-029 的常规 FastAPI 分层。
> 原 QuantCore 运行时边界取消；五个 Engine 的业务逻辑进入 `app.services`，
> Panel、MetricContext、回测规格/结果和实验上下文进入 `app.models`，数据访问进入 `app.database`。
> 配置为 `app.config`，通用工具为 `app.utils`；不增加 domain/application/infrastructure。
> 下文中的旧目录和旧分层仅作历史设计追溯，不再作为新代码约束；既有业务规则和历史验证记录保留。
> 详见根目录 FEAT-030/06-app-layout.md 与 ADR-029。FEAT-029 因子来源加载目标保持不变。


> 状态：部分废止。HTTP 前缀相关决定已由 ADR-024 取代；批量独立 Experiment 相关决定已由 ADR-025 取代；其余命名空间、Manager 和批量 FIFO 决定继续有效。

### 问题

QuantCore、ResearchEngine、因子资产和策略资产原来分散在多个顶层目录，FastAPI 路由、
实验编排和存储边界容易互相穿透。因子批量回测还需要限制业务并发，同时保证交互式
回测不会被批量任务插队。

### 选择

1. 将运行时统一迁移到 `ResearchEngine/app`，公开 Python 命名空间只保留 `app.*`；
2. `app.main` 是唯一 FastAPI 入口，生产部署固定为单实例、单 Uvicorn Worker；
3. 采用 `api → services → models/database` 依赖方向。`models` 不依赖 API、服务或数据访问；
   `database` 不构造业务服务；Pydantic 只在 HTTP schema 边界使用。取消 QuantCore 运行时依赖；
4. `Experiment` 改为抽象基类，Manager 只接受具体 Experiment，并向其注入只读行情上下文；
5. Manager 使用一个普通 FIFO 队列。`lane` 只记录元数据，不做优先级排序或插队；
6. 因子批量回测由具体的 `FactorBacktestBatchCoordinator` 实现，不建立通用
   `FactorBatchService`。协调器只维护业务队列窗口、重试和持久化，统一向 Manager 提交
   `FactorBacktestExperiment(spec)`；不再建立 `FactorBacktestBatchExperiment` 独立执行封装。
   协调器最多提交两个未完成因子，一个因子进入终态后才提交下一个；协调器按触发请求创建，
   不作为应用级单例；
7. `FactorBacktestBatchTaskRegistry` 使用独立单线程执行批量编排，避免把父协调任务提交到
   两槽 Manager 后等待子任务导致死锁；应用关闭时先等待注册表，再关闭 Manager；
8. 因子/策略运行时资产放在 `app.assets`，批量状态和标量指标继续通过 `app.database` 的 SQLite
   repository 持久化，行情通过 `app.database.data` 的 Provider 读取；
9. 采用一次性命名切换，删除旧 examples 和旧包兼容转发；批量 HTTP 契约切换到
   `/api/factor-backtest-batches`；ResearchEngine 当前统一使用 `/api` 根路径，WebApp 不在本次修改范围内。

### 备选方案

- **Manager 优先队列**：可以让交互任务抢占批量任务，但会把业务策略错误地下沉到通用
  执行器，且改变所有任务的可预测 FIFO 语义，因此不采用。
- **为批量建立通用 FactorBatchService**：名称和抽象粒度掩盖了这是一个具体产品业务；
  采用具体协调器，让幂等、断点、重试和两槽窗口保持在业务边界内。
- **保留 `quantcore.*`/`researchengine.*` 转发**：降低短期迁移成本，但会长期保留两套
  入口并掩盖依赖错误；本次选择一次性切换。
- **Celery/Redis 或多进程 Worker**：当前数据访问和 SQLite 规模尚不需要，且会引入部署
  运维成本；留待独立的分布式调度决策。

### 后果

正面影响：模块职责、依赖和启动边界清晰；实验可测试；批量业务的“最多两个、完成一个
补一个、交互 FIFO”可直接验证；资产和 API 路径稳定。

负面影响：这是破坏性包迁移，外部 Python 调用方必须改用 `app.*`；单实例约束限制横向
扩展；仍使用 `/api/v2` 的客户端需要按 ADR-024 调整为 `/api`；批量业务在交互任务持续不断时可能延迟，但其已
完成结果和状态会持久化，后续请求可恢复。
