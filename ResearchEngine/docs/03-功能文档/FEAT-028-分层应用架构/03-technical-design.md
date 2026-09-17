# Technical Design：ResearchEngine 分层应用架构

> 2026-08-28 架构修订：用户已确认 ADR-029 的常规 FastAPI 分层。
> 原 QuantCore 运行时边界取消；五个 Engine 的业务逻辑进入 `app.services`，
> Panel、MetricContext、回测规格/结果和实验上下文进入 `app.models`，数据访问进入 `app.database`。
> 配置为 `app.config`，通用工具为 `app.utils`；不增加 domain/application/infrastructure。
> 下文中的旧目录和旧分层仅作历史设计追溯，不再作为新代码约束；既有业务规则和历史验证记录保留。
> 详见根目录 FEAT-030/06-app-layout.md 与 ADR-029。FEAT-029 因子来源加载目标保持不变。


## 目标结构

```text
ResearchEngine/app/
├── main.py
├── api/routes/          # health/catalog/factor/strategy/batch
├── schemas/             # Pydantic DTO，仅 HTTP 边界
├── services/            # experiment/factor/strategy/catalog/factor_backtest_batch
├── repositories/        # catalogs/results/factor_backtest
├── database/            # SQLite store 与行情访问边界
├── core/                # config/runtime/exceptions
├── quantcore/           # data/factor/metric/backtest
└── assets/              # factors/strategies 源码与 index.yaml
```

依赖方向为：

```text
api → services → repositories/database → quantcore
assets → quantcore 公开接口
quantcore → 不依赖 FastAPI、services、repositories、schemas
```

## Experiment 与 Manager

```python
class Experiment(ABC, Generic[TResult]):
    def run(self, context: ExperimentContext) -> TResult: ...
```

Manager 使用普通 `queue.Queue` 和有界 semaphore。`lane` 只是元数据，不参与排序。
Manager 的 worker 从唯一 FIFO 队列取任务；单实例配置为 `max_workers=2`，队列容量由
`SVQUANT_EXPERIMENT_MAX_QUEUE_SIZE` 控制，默认 8。

具体实验为：

- `FactorBacktestExperiment(spec)`：单因子 API 与因子批量共同使用的唯一因子回测任务；
- `FactorExperiment(...)`：保留旧 Python 调用方式的兼容门面，内部只转换规格并委托统一执行器；
- `StrategyExperiment`：现阶段策略回测适配器，后续迁入 ADR-025 的统一应用管线。

因子任务固定经过 `FactorBacktestSpec → FactorBacktestExperiment → BacktestEngine → FactorBacktestResult`。
实验不创建 `DataEngine` 或 Manager，Manager 创建只读 `ExperimentContext` 并注入。

## 因子批量回测业务

`FactorBacktestBatchCoordinator` 是具体业务能力，不抽象成通用 `FactorBatchService`。
它负责目录扫描、批次幂等、断点续跑、重试、SQLite 进度和窗口调度。自身在协调器线程
中等待 Manager future，不占用 Manager worker。

协调器不是应用级单例。每个触发请求通过 `get_experiment_manager()` 获取共享
`ExperimentManager` 后创建一个无跨请求状态的协调器；`FactorBacktestBatchTaskRegistry`
只负责异步任务快照和单协调线程，批次状态仍由 SQLite 持久化。

伪代码：

```text
while 还有未完成因子:
    while pending < 2:
        submit(FactorBacktestExperiment(spec))  # 普通 FIFO
    等待一个 future 进入终态
    持久化结果并移除 pending
```

如果 Manager 的有界容量暂时被交互任务占满，协调器等待可提交；它不插队、不扩容。
因此交互任务只要先进入 Manager 队列，就会先于之后的批量提交执行。

## HTTP 与生命周期

- `app.main` 创建 FastAPI 应用并注册 `/api` 路由；
- lifespan 启动唯一 Manager；关闭时先停止并等待批量任务注册表，再关闭 Manager；
- API 通过 `app.api.dependencies` 注入 Manager，并为当前触发请求创建协调器；
- 内部触发为 `POST /api/internal/factor-backtest-batches`，立即返回 `202` 任务；
- 任务查询为 `GET /api/factor-backtest-batch-tasks/{task_id}`；
- 批次查询使用 `/api/factor-backtest-batches` 及其详情、因子和历史子路径；
- CLI 仅用 stdlib HTTP 客户端调用该接口，不本地执行回测；
- 不支持多 Worker、多实例；内部触发接口当前不鉴权，只允许可信内网访问。

## 数据与迁移

因子/策略源码迁移到 `app/assets`；行情仍由 QuantCore Parquet provider 读取；批量结果
继续使用 SQLite，但 API/业务只通过 `FactorBacktestRepository` 访问。因子批量 SQLite
使用 schema v2，并保存 execution/data release/spec 溯源字段；旧 schema 不混写，按 ADR-025
在上线时清理重建。旧目录和旧命名空间一次性删除，不提供兼容转发。
