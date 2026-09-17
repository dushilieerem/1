# ResearchEngine 架构文档

本目录承接根目录业务层，回答 ResearchEngine 如何承载研究计算业务。架构基线是 [`researchengine_architecture.md`](researchengine_architecture.md)。

## 覆盖范围

- `app.services/` 下的数据、因子、组合、指标和回测服务。
- `app.models/` 下的内部数据结构，以及服务与模型之间的边界。
- `app.database/` 下的数据 Provider、字段缓存和结果存储。
- FastAPI 适配层、实验编排、任务生命周期和公开 API。
- 与 MarketData、WebApp 解析后的用户资产快照之间的接口边界。

ResearchEngine 不创建独立 QuantCore 共享库，也不承担用户资产管理、鉴权、权限和 Web 页面职责；长期技术选择记录在 [`../05-技术决策/`](../05-技术决策/)。

## 当前架构基线

本目录必须反映已接受的模块级技术决策，而不是只记录最初的设计草案。当前基线包括：

| 决策 | 对本目录的约束 |
|------|----------------|
| ADR-018 | 因子计算需要使用收益确认区间之前的历史预热数据，结果和指标再裁剪到确认区间。 |
| ADR-019、ADR-022 | 一个进程由 `ExperimentManager` 统一管理回测资源，并复用按 release 隔离的 `ResearchRuntime`。 |
| ADR-020、ADR-021 | 批量指标使用独立 SQLite；因子单次和批量提交采用异步任务查询。 |
| ADR-023、ADR-024、ADR-025 | 使用单一 `app.*` 命名空间、`/api` 前缀、统一任务调度和批量业务协调边界。 |
| ADR-028、ADR-029 | 因子回测由 `BacktestEngine` 编排四个 services 引擎；ResearchEngine 采用 `api / schemas / services / models / database` 常规分层。 |

根目录 [`docs/02-架构文档/`](../../../docs/02-架构文档/) 负责系统级边界、跨模块依赖和公共数据契约；本目录负责上述结论在 ResearchEngine 内部的具体落地。两处不得各自维护相互冲突的当前实现描述。提议状态的 ADR-012、ADR-013、ADR-015、ADR-026 只作为后续演进输入，不改变当前运行时基线。
