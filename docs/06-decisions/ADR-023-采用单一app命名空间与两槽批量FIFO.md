## ADR-023: 采用单一 app 命名空间与两槽批量 FIFO

> 状态：部分废止。HTTP 前缀相关决定已由 ADR-024 取代；其余命名空间、Manager 和批量 FIFO 决定继续有效。

### 问题

QuantCore、ResearchEngine、因子资产和策略资产原来分散在多个顶层目录，FastAPI 路由、
实验编排和存储边界容易互相穿透。因子批量回测还需要限制业务并发，同时保证交互式
回测不会被批量任务插队。

### 选择

1. 将运行时统一迁移到 `ResearchEngine/app`，公开 Python 命名空间只保留 `app.*`；
2. `app.main` 是唯一 FastAPI 入口，生产部署固定为单实例、单 Uvicorn Worker；
3. 采用 `api → services → repositories/database → quantcore` 依赖方向。QuantCore 不依赖
   FastAPI、schemas、services 或 repositories；Pydantic 只在 API 边界使用；
4. `Experiment` 改为抽象基类，Manager 只接受具体 Experiment，并向其注入只读行情上下文；
5. Manager 使用一个普通 FIFO 队列。`lane` 只记录元数据，不做优先级排序或插队；
6. 因子批量回测由具体的 `FactorBacktestBatchCoordinator` 实现，不建立通用
   `FactorBatchService`。协调器维护自己的业务队列窗口，最多向 Manager 提交两个未完成因子；
   一个因子进入终态后才提交下一个。协调器按触发请求创建，不作为应用级单例；
7. `FactorBacktestBatchTaskRegistry` 使用独立单线程执行批量编排，避免把父协调任务提交到
   两槽 Manager 后等待子任务导致死锁；应用关闭时先等待注册表，再关闭 Manager；
8. 因子/策略运行时资产放在 `app.assets`，批量状态和标量指标继续通过 SQLite repository
   持久化，行情继续使用 QuantCore Parquet provider；
9. 采用一次性命名切换，删除旧 examples 和旧包兼容转发；批量 HTTP 契约切换到
   `/api/factor-backtest-batches`，
   WebApp 不在本次修改范围内。

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
扩展；WebApp 需要后续适配 `/api/v2`；批量业务在交互任务持续不断时可能延迟，但其已
完成结果和状态会持久化，后续请求可恢复。
