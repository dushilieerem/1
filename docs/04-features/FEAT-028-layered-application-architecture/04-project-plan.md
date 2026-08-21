# Project Plan：ResearchEngine 分层应用架构

## 任务拆解

| 任务 | 复杂度 | 风险 | 依赖 | 状态 |
|---|---:|---|---|---|
| 迁移 QuantCore 到 `app.quantcore` | 4 | 中 | 包发现配置 | 已完成 |
| 建立 api/schemas/services/repositories/database/core 分层 | 4 | 中 | 运行时导入分析 | 已完成 |
| Experiment 抽象、唯一 Manager 和生命周期 | 4 | 中 | QuantCore data/context | 已完成 |
| DailyFactorBacktestCoordinator 两槽 FIFO 窗口 | 4 | 中 | Manager、SQLite | 已完成 |
| 因子/策略资产和索引迁移 | 3 | 中 | catalog loader | 已完成 |
| `/api` 路由、依赖注入和 HTTP CLI | 3 | 低 | services | 已完成 |
| 旧目录删除、文档和 ADR | 2 | 低 | 迁移完成 | 进行中 |
| 全量测试、安装和启动 smoke test | 3 | 中 | 全部模块 | 进行中 |

## 排期与里程碑

- Week 1 / M1：新命名空间可安装，QuantCore 与 API 核心导入通过。
- Week 2 / M2：Factor/Strategy/Batch 三条回测链路和 FIFO 窗口通过专项测试。
- Week 3 / M3：文档、安装、启动 smoke test、全量 pytest 和部署约束完成。

## 风险与缓解

- 上游 `DataEngine`、`FactorEngine`、`FieldParquetProvider` 引用较多：先复制并切换导入，
  再删除旧包，保留量化结果回归测试。
- 单实例 Manager 是当前约束：在文档和启动命令中固定 `--workers 1`，后续再单独设计分布式调度。
- WebApp 仍使用旧契约：本次不改 WebApp，记录 `/api` 联调为后续任务。
- 本机 pytest 临时目录权限受限：验收时使用工作区下的临时目录，不改变业务代码。
