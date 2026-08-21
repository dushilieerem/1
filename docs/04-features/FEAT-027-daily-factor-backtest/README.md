# FEAT-027：每日全量因子回测与指标仓库

- 状态：开发中（MVP 已实现）
- 所属 Initiative：INIT-001 投研核心
- 所属能力：因子研究 / 研究基础设施
- 优先级：P0

## 目标

在每个行情发布日，对 `ResearchEngine/app/assets/factors/index.yaml` 登记的全部内置因子按
固定研究配置回测，把可长期比较的批次状态、分组指标和预测性指标写入独立 SQLite 仓库。
CLI 只负责向 FastAPI 发起 HTTP 请求，真正的批量业务由
`DailyFactorBacktestCoordinator` 执行。

`ExperimentManager` 只提供一个普通 FIFO 回测队列，不理解优先级。每日批量业务自行维护
最多两个未完成因子的窗口：只有窗口中的一个因子进入终态，协调器才会向 Manager 提交
下一个因子；若交互式任务已先进入 Manager 队列，它按 FIFO 先于后提交的批量因子执行。

## 文档索引

- `01-feature-proposal.md`：背景、价值、竞品和 MVP 边界
- `02-product-requirements.md`：用户故事、流程、异常和验收标准
- `03-technical-design.md`：模块、数据表、接口、幂等和风险
- `04-project-plan.md`：交付任务、工作量和里程碑
- `05-verification.md`：测试矩阵和上线前检查

## 代码入口

- `ResearchEngine/app/services/daily_factor_backtest/coordinator.py`：具体批量业务、窗口调度、指标摘要和重试
- `ResearchEngine/app/repositories/factor_backtest.py`：批次结果 repository
- `ResearchEngine/app/database/factor_backtest_store.py`：SQLite 存储实现
- `ResearchEngine/app/services/experiment/`：Experiment 抽象、Manager 和单因子/策略实验
- `ResearchEngine/app/api/routes/batch.py`：触发、批次查询、因子明细和历史查询
- `ResearchEngine/app/cli/factor_batch.py`：轻量 HTTP 客户端 CLI

## 使用方式

启动唯一 FastAPI 实例后，在可信内网调用：

```bash
python -m app.cli.factor_batch run --as-of YYYY-MM-DD
python -m app.cli.factor_batch run --as-of YYYY-MM-DD --force-retry
python -m app.cli.factor_batch run --as-of YYYY-MM-DD --dry-run
```

等价的内部接口为：

```text
POST /api/internal/factor-backtests/batches
{
  "as_of_date": "YYYY-MM-DD",
  "force_retry": false,
  "dry_run": false
}
```

默认数据库为 `Factor/database/factor_backtest.db`，可用
`SVQUANT_FACTOR_BACKTEST_DB` 覆盖。查询接口保留批次列表、批次详情、因子明细和因子
历史四类只读能力。
