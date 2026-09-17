# FEAT-027：因子批量回测与指标仓库

> [FEAT-030 当前实现](../../../../docs/03-功能文档/FEAT-030-因子回测流程重构/README.md)：每个因子任务改调同一个 BacktestEngine，
> 取消强制过滤，四项可选处理默认关闭，触发 API/CLI 支持显式配置。
> 两槽 FIFO、重试、历史 schema 保持；告警仅留在当次结果/缓存/日志，不持久化进批量历史。
> 以下描述当前批量实现；完整验收仍以 FEAT-030 Verification 为准。

- 状态：开发中（MVP 已实现）
- 所属 Initiative：INIT-001 投研核心
- 所属能力：因子研究 / 研究基础设施
- 优先级：P0

## 目标

按指定 `as_of_date`，对 `ResearchEngine/app/assets/factors/index.yaml` 登记的全部内置因子
按固定研究配置批量回测，把可长期比较的批次状态、分组指标和预测性指标写入独立 SQLite
仓库。CLI 只负责向 FastAPI 发起 HTTP 请求，真正的批量业务由
`FactorBacktestBatchCoordinator` 执行。

每个因子先转换为 `FactorBacktestSpec`，再提交统一的
`FactorBacktestExperiment(spec)`；单因子 API 和 Python `FactorExperiment(...)` 门面使用
同一个 `BacktestEngine`，批量协调器不实现第二套回测算法。`FactorBacktestExperiment`
仅负责 Experiment 任务适配，不再存在独立 Executor。

`ExperimentManager` 只提供一个普通 FIFO 回测队列，不理解优先级。批量业务自行维护
最多两个未完成因子的窗口：只有窗口中的一个因子进入终态，协调器才会向 Manager 提交
下一个因子；若交互式任务已先进入 Manager 队列，它按 FIFO 先于后提交的批量因子执行。

## 功能名称

按指定 `as_of_date` 执行全量内置因子批量回测、指标快照和历史查询。

## 背景

当前单因子 API 适合交互式研究，但无法稳定地按指定日期重跑全量因子，也没有统一的跨日期
指标仓库。研究员需要手工触发、汇总和比较结果，失败因子也容易被遗漏。

## 用户价值

- 研究员每次批量运行得到同一口径的因子评分卡，可按因子、库和日期比较；
- 单个因子异常不会阻断其他因子，失败原因可追溯；
- 通过 FastAPI 内部触发接口启动批次，通过 HTTP 只读接口查看批次进度和因子历史。

## 商业价值

可复现的因子排名和历史曲线是研究服务留存、策略筛选和后续组合构建的基础数据资产，
能够减少人工研究成本，并为未来的因子筛选、报告和付费研究能力提供稳定接口。

## 竞品与差异化

成熟量化平台通常提供因子分析或研究任务，但往往依赖云端任务队列和大数据仓库。SVQuant MVP
优先保证本地/内网可部署、固定配置可复现、失败隔离和低运维成本；后续在实测规模和并发需求
达到阈值后再迁移 PostgreSQL 或 ClickHouse。

## MVP 范围

### 必须做

- 动态枚举 `index.yaml` 内置因子；固定 CSI_ALL、CSI300、纯多头、5 组、每日调仓、core；
- 最近 10 个日历年窗口，保存实际区间、样本天数和 `short_history`；
- 保存 Q1～Q5、benchmark 八项标量指标，以及 IC、RankIC、年化 ICIR；
- SQLite WAL 结果库、单因子隔离、一次重试、断点续跑、幂等和 force-retry；
- 普通 FIFO Manager、批量业务自有的容量为 2 的窗口、交互任务先到先执行；
- 内部 HTTP 异步触发、任务轮询、HTTP 客户端 CLI 和四个只读查询接口。

### 可以以后做

- 增量计算、每日 IC 明细、净值曲线对象存储；
- Web 前端评分卡、告警和邮件通知；
- PostgreSQL/ClickHouse、多进程 Worker 和分布式锁；
- 数据版本指纹和用户自定义因子批处理。

### 明确不做

- Celery/Redis、批次取消/暂停 HTTP 接口；
- 在 MVP 数据库中保存净值曲线或每日 IC 大序列；
- 用户权限、多租户隔离和实盘交易。

## 代码入口

- `ResearchEngine/app/services/factor_backtest_batch/coordinator.py`：具体批量业务、窗口调度、指标摘要和重试
- `ResearchEngine/app/services/factor_backtest_batch/task_registry.py`：单协调线程的异步任务注册表
- `ResearchEngine/app/repositories/factor_backtest.py`：批次结果 repository
- `ResearchEngine/app/database/factor_backtest_store.py`：SQLite 存储实现
- `ResearchEngine/app/services/factor/spec.py`、`experiment.py`：统一规格和因子 Experiment 任务
- `ResearchEngine/app/services/experiment/`：Experiment 抽象、Manager 和单因子/策略实验
- `ResearchEngine/app/api/routes/batch.py`：触发、批次查询、因子明细和历史查询
- `ResearchEngine/app/cli/factor_backtest_batch.py`：轻量 HTTP 客户端 CLI

## 使用方式

启动唯一 FastAPI 实例后，在可信内网调用：

```bash
python -m app.cli.factor_backtest_batch run --as-of YYYY-MM-DD
python -m app.cli.factor_backtest_batch run --as-of YYYY-MM-DD --force-retry
python -m app.cli.factor_backtest_batch run --as-of YYYY-MM-DD --dry-run
python -m app.cli.factor_backtest_batch run --as-of YYYY-MM-DD --wait
```

等价的内部接口为：

```text
POST /api/internal/factor-backtest-batches
{
  "as_of_date": "YYYY-MM-DD",
  "force_retry": false,
  "dry_run": false
}

GET /api/factor-backtest-batch-tasks/{task_id}
GET /api/factor-backtest-batches
GET /api/factor-backtest-batches/{batch_id}
GET /api/factor-backtest-batches/{batch_id}/factors
GET /api/factor-backtest-batches/factors/{library_name}/{factor_name}/history
```

POST 只提交任务并立即返回 `202`。任务状态在进程内保留 60 秒，批次进度和因子结果
长期保存在 SQLite；`--wait` 由 CLI 轮询任务直到成功或失败。`dry_run` 只执行目录和行情
预检，不创建持久化批次。

默认数据库为 `app/assets/factors/factor_backtest.db`，可用
`SVQUANT_FACTOR_BACKTEST_DB` 覆盖。查询接口保留批次列表、批次详情、因子明细和因子
历史四类只读能力。

## 文档索引

- `02-product-requirements.md`：用户故事、流程、异常和验收标准
- `03-technical-design.md`：模块、数据表、接口、幂等和风险
- `05-verification.md`：测试矩阵和上线前检查

## 1. 计划与里程碑

### 任务拆解

| 任务 | 复杂度 | 技术风险 | 依赖 | 状态 |
|---|---:|---|---|---|
| 索引枚举、目录版本和预检 | 2 | 中 | 因子目录、MarketData | 已完成 |
| SQLite 表、事务、WAL 和查询 | 3 | 中 | 无 | 已完成 |
| Experiment core IC 汇总 | 2 | 中 | 现有 Experiment | 已完成 |
| 具体业务协调器、容量为 2 的普通 FIFO 窗口、续跑和重试 | 4 | 中 | Manager、SQLite | 已完成 |
| FastAPI 异步触发、任务轮询、只读查询和 HTTP CLI | 3 | 中 | SQLite、app.main | 已完成 |
| 单元/集成/回归测试 | 3 | 中 | 上述模块 | 进行中 |
| 50 因子耗时基准和任务计划接入 | 2 | 中 | 真实行情数据 | 待执行 |

### 排期

- Week 1：完成 schema、批处理编排和 core 指标摘要。
- Week 2：完成 CLI、只读查询和专项测试。
- Week 3：用真实行情跑 50 个代表因子基准，确认资源配置和任务计划时间窗。

### 里程碑

- M1：小型行情和测试因子完成批次成功/失败/短历史验证。
- M2：本地 SQLite 可重启读取，HTTP 分页和历史查询稳定。
- M3：真实索引全量试跑，确定资源配置和调度窗口；再决定是否增量计算或迁移数据库。

### 资源与风险

MVP 由现有 ResearchEngine 线程池和单机 SQLite 支撑，不新增基础设施。最大不确定性是 1055
因子的实际耗时、字段覆盖和内存峰值；在基准完成前不承诺硬性 SLA，也不盲目增加并发。
