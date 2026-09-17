# Technical Design：因子批量回测与指标仓库

> 2026-08-28 架构修订：用户已确认 ADR-029 的常规 FastAPI 分层。
> 原 QuantCore 运行时边界取消；五个 Engine 的业务逻辑进入 `app.services`，
> Panel、MetricContext、回测规格/结果和实验上下文进入 `app.models`，数据访问进入 `app.database`。
> 配置为 `app.config`，通用工具为 `app.utils`；不增加 domain/application/infrastructure。
> 下文中的旧目录和旧分层仅作历史设计追溯，不再作为新代码约束；既有业务规则和历史验证记录保留。
> 详见根目录 FEAT-030/06-app-layout.md 与 ADR-029。FEAT-029 因子来源加载目标保持不变。


> FEAT-030 当前实现：协调器保持目录、窗口、重试与投影职责，因子 Experiment 改调 BacktestEngine。
> Profile 解除强制过滤；API/CLI 透传四项可选处理；批次身份加入新执行版本。
> 当次任务摘要、缓存及日志保留过滤诊断，SQLite schema 不变且不清理历史。
> [完整设计](../../../../docs/03-功能文档/FEAT-030-因子回测流程重构/README.md) 已实施；下面的兼容 Executor 只表示旧导入，
> 标准任务执行边界是 BacktestEngine。

## 模块边界

### `FactorBacktestBatchCoordinator`

这是因子批量回测这一具体业务能力的编排对象，负责目录枚举、预检、固定配置、批次键、
批量窗口、因子重试、结果分类和断点续跑。它把每个因子转换为不可变
`FactorBacktestSpec`，通过唯一 `FactorBacktestExperiment(spec)` 和
`ExperimentManager` 提交，不创建 Manager 或行情引擎，也不实现基准、分组指标或因子计算。
单因子 API、Python 门面和批量因子都进入同一个 `BacktestEngine`；
`FactorBacktestExperiment` 仅实现 Experiment 任务适配。

协调器由每次触发请求按需创建，不保存跨请求批次状态；幂等、进度和结果由 SQLite repository
负责。FastAPI 应用只持有 `ExperimentManager` 和异步任务注册表，不持有批量协调器实例。

协调器自己的业务窗口固定为 2。它只维护最多两个尚未进入终态的 future；消费一个 future
并持久化结果后，才从目录取下一个因子提交。Manager 不实现 lane 优先级，只有普通 FIFO；
`lane="batch"` 仅用于任务元数据和观测。

### `FactorBacktestRepository` / `factor_backtest_store.py`

repository 隔离 SQLite 存储实现；store 负责建表、WAL/busy timeout、批次和因子状态、
标量指标写入及分页读取。批处理协调器是唯一写入者，Worker 只返回内存结果。

### `ExperimentManager` 与 `ResearchRuntime`

`ExperimentManager` 是回测任务的统一运行时边界。它持有一个进程内
`ResearchRuntime`，由 runtime 按当前 `MarketData` release 懒加载并复用同一个
`FieldParquetProvider`、`DataEngine` 和字段级 LRU 缓存。CLI 批处理、因子回测 API
和策略回测 API 都通过 Manager 注入这份上下文，不在每个因子/请求中重新构建行情引擎。

缓存按 `release_id + field + 日期/证券切片` 分层，默认上限 2 GiB（可由
`SVQUANT_FIELD_CACHE_MAX_BYTES` 覆盖）；行情发布切换后自动创建新 release 上下文，旧
上下文由 Manager 关闭。缓存返回的行情 DataFrame 约定为只读，因子计算产生的中间结果
仍属于单任务内存，不进入 SQLite。

这是 Windows MVP 的进程内复用方案；跨进程物理内存共享、完整只读快照和 fork worker
仍按 FEAT-024 的 P1 规划推进。

### `Experiment` core 增量

core 分组分析在已有分组收益计算旁计算 Pearson IC、Spearman RankIC 和 ICIR 汇总；
日频序列只在内存中存在，汇总完成后随任务释放。
交互和批量 profile 都把 `is_suspended` 与 `limit_up/limit_status` 过滤作为规格参数；
字段存在时使用完全相同的过滤逻辑，字段未发布时两个入口都跳过该可选过滤器。所有入口
计算面板的结束日都锁定为规格的 `end/as_of_date`，避免历史回测读取其后的行情。

## 数据模型

`batch_runs` 保存批次键、窗口、固定 profile、目录/指标版本、进度计数和基础设施错误。
`factor_runs` 保存因子源哈希、状态、重试次数、实际区间、样本质量和耗时。
`factor_quantile_metrics` 使用 `(factor_run_id, quantile)` 主键保存六行分组指标。
`factor_predictive_metrics` 使用因子运行 ID 主键保存 IC、RankIC、ICIR。

索引：批次按 `as_of_date DESC`，因子按批次/状态及库名、因子名、创建时间建立索引。

## 幂等与恢复

```text
batch_key = hash(as_of_date, profile_hash, catalog_version, data_release_id, execution_version, metric_version)
```

完成批次直接返回；`pending/running` 批次复用并续跑终态以外的因子；`force-retry` 使用带时间后缀
的新键并写入 `supersedes_batch_id`。SQLite 事务在写单个因子时同时替换其两类指标，避免半行结果。

## 指标口径

分组指标复用 `QuantileMetric` 和 `_compute_quantile_metrics`，Q1 是因子值最高组，Q5 是最低组。
年化收益为几何 CAGR，波动率为日收益样本标准差乘 `sqrt(252)`，最大回撤为负值；相对基准
指标保持现有实现语义。IC/RankIC 是每日截面 Pearson/Spearman 均值，ICIR 为
`IC均值 / IC标准差 × sqrt(252)`。当前指标版本为 `factor-scorecard-v3`，文件缓存版本为
`factor-backtest-v11`。批次行保存 `execution_version`、`data_release_id`、`spec_hash`，
因子行保存对应的规格身份。

## 异步任务、CLI 与 HTTP

CLI 必须显式提供 `--as-of`，支持 `--force-retry`、`--dry-run`，只调用
`POST /api/internal/factor-backtest-batches`。提交接口由
`FactorBacktestBatchTaskRegistry` 接收，注册表使用固定一个协调线程；协调线程执行批量
编排，两个因子实验仍提交给共享 `ExperimentManager` 的两个 worker。批量协调器不能提交
进 Manager，否则父任务等待子任务时会形成死锁。

任务状态为 `queued/running/succeeded/failed`，内存快照保留 60 秒；相同非
`force_retry` 请求在进程内复用 task ID，`force_retry` 创建新任务。成功后任务快照映射
`batch_id`、`batch_url` 和批次结果；`dry_run` 成功时不创建 SQLite 批次。HTTP 还提供：

- `GET /api/factor-backtest-batch-tasks/{task_id}`
- `GET /api/factor-backtest-batches`
- `GET /api/factor-backtest-batches/{batch_id}`
- `GET /api/factor-backtest-batches/{batch_id}/factors`
- `GET /api/factor-backtest-batches/factors/{library_name}/{factor_name}/history`

## 兼容与回滚

现有单因子 API 和 `SQLiteStorage` 不改职责。批量 SQLite schema 固定为 v2；上线时停止服务，
确认解析后的数据库路径后直接删除数据库及 WAL/SHM sidecar，由应用重新初始化。发现旧或未知
schema 时失败并提示清理，不混写历史。Python SDK 仍通过 `FactorExperiment(...)` 兼容门面
保持原有本地保存行为。

## 风险与缓解

- 1055 个因子的运行时长未知：先记录耗时，保持默认 2 Worker，依据 50 个代表因子基准再调优。
- SQLite 单写者吞吐有限：协调器串行写入；超过本地研究服务规模后按 ADR-020 迁移。
- 数据字段缺失：预检基础字段，因子级缺字段标记 skipped，保留错误信息。
- 现有 core 方法变更风险较高：新增字段不改变原有 layered_returns/layered_equity，回归测试覆盖既有 API。
