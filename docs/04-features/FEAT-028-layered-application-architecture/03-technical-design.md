# Technical Design：ResearchEngine 分层应用架构

## 目标结构

```text
ResearchEngine/app/
├── main.py
├── api/routes/          # health/catalog/factor/strategy/batch
├── schemas/             # Pydantic DTO，仅 HTTP 边界
├── services/            # experiment/factor/strategy/catalog/daily_factor_backtest
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

- `FactorExperiment`：单因子回测；
- `StrategyExperiment`：策略回测；
- `DailyFactorExperiment`：每日批量中单个因子的适配器。

实验不创建 `DataEngine` 或 Manager，Manager 创建只读 `ExperimentContext` 并注入。

## 每日因子业务

`DailyFactorBacktestCoordinator` 是具体业务能力，不抽象成通用 `FactorBatchService`。
它负责目录扫描、批次幂等、断点续跑、重试、SQLite 进度和窗口调度。自身在协调器线程
中等待 Manager future，不占用 Manager worker。

伪代码：

```text
while 还有未完成因子:
    while pending < 2:
        submit(DailyFactorExperiment)  # 普通 FIFO
    等待一个 future 进入终态
    持久化结果并移除 pending
```

如果 Manager 的有界容量暂时被交互任务占满，协调器等待可提交；它不插队、不扩容。
因此交互任务只要先进入 Manager 队列，就会先于之后的批量提交执行。

## HTTP 与生命周期

- `app.main` 创建 FastAPI 应用并注册 `/api` 路由；
- lifespan 启动/关闭唯一 Manager；协调器只引用该 Manager；
- API 通过 `app.api.dependencies` 注入 Manager/协调器；
- 内部触发为 `POST /api/internal/factor-backtests/batches`；
- CLI 仅用 stdlib HTTP 客户端调用该接口，不本地执行回测；
- 不支持多 Worker、多实例；内部触发接口当前不鉴权，只允许可信内网访问。

## 数据与迁移

因子/策略源码迁移到 `app/assets`；行情仍由 QuantCore Parquet provider 读取；批量结果
继续使用 SQLite，但 API/业务只通过 `FactorBacktestRepository` 访问。旧目录和旧命名空间
一次性删除，不提供兼容转发。
