# ResearchEngine 文档中心

ResearchEngine 的模块文档承接项目级主链路（需求 → 业务 → 架构 → 功能 → 实现）：
产品价值、目标用户、路线图和跨模块业务规则仍以根目录 [`docs/README.md`](../../docs/README.md) 为准；本目录只维护研究引擎的模块级设计、功能包、交付状态和专属技术决策。目录编号与根目录同义（02 架构 / 03 功能 / 04 项目管理 / 05 技术决策）；`00-文档治理` 与 `01-需求文档` 为项目级，不在模块重复建立。

## 目录

| 目录 | 内容 | 对应根目录 |
|------|------|------------|
| [`02-架构文档/`](02-架构文档/) | ResearchEngine 运行时架构、模块边界、执行链路和数据/任务生命周期 | `docs/02-架构文档/` |
| [`03-功能文档/`](03-功能文档/) | ResearchEngine 负责的 FEAT 功能包、研究 API、因子/策略、批量回测和 AI 研究能力 | `docs/03-功能文档/` |
| [`04-项目管理/`](04-项目管理/) | 模块级状态快照（模块状态）和阶段汇报 | `docs/04-项目管理/` |
| [`05-技术决策/`](05-技术决策/) | ResearchEngine 专属 ADR | `docs/05-技术决策/` |

模块需求必须链接回根目录对应的需求、业务和 Feature 文档，避免同一事实出现两份版本。

## Feature 索引

当前归入 ResearchEngine 的 Feature：

`FEAT-002`、`FEAT-004`、`FEAT-005`、`FEAT-006`、`FEAT-007`、`FEAT-008`、`FEAT-009`、`FEAT-011`、`FEAT-012`、`FEAT-013`、`FEAT-014`、`FEAT-015`、`FEAT-016`、`FEAT-017`、`FEAT-019`、`FEAT-020`、`FEAT-021`、`FEAT-022`、`FEAT-023`、`FEAT-026`、`FEAT-027`、`FEAT-028`、`FEAT-029`。

对应目录位于 [`03-功能文档/`](03-功能文档/)。数据底座及跨模块 Feature 文档保留在项目级 [`docs/03-功能文档/`](../../docs/03-功能文档/)；QuantCore 的运行时定位已取消，其计算能力全部归 ResearchEngine。

## 当前架构修订

[FEAT-030：因子回测流程重构](../../docs/03-功能文档/FEAT-030-因子回测流程重构/README.md) 统一维护在根目录功能区。用户已授权按
[ADR-029](../../docs/05-技术决策/ADR-029-研究服务采用services与models分层.md) 采用 `services / models / database` 分层；五个 Engine 是服务，内部数据结构是模型。
单次、批量、Python 共用因子流程，策略只迁移目录并保持执行语义；专项验收以功能包和实现验证记录为准。

## 阅读入口

1. 先阅读项目级 [`docs/README.md`](../../docs/README.md) 和 [需求文档](../../docs/01-需求文档/)（业务流程与领域设计同层维护）。
2. 再阅读 [`02-架构文档/researchengine_architecture.md`](02-架构文档/researchengine_architecture.md)。
3. 按需查看对应 [`03-功能文档/`](03-功能文档/) 的 Feature README、技术设计和验证记录。
4. 模块状态与阶段汇报进入 [`04-项目管理/`](04-项目管理/)；长期技术选择进入 [`05-技术决策/`](05-技术决策/)。
5. 涉及跨模块数据或 WebApp HTTP 契约时，回到项目级文档和 [`WebApp/docs/`](../../WebApp/docs/README.md)。

## 共享边界

- 项目级系统总架构、MarketData 数据设计和跨模块契约位于根目录 `docs/02-架构文档/`。
- ResearchEngine 只消费 WebApp 解析后的用户资产快照，不负责用户资产 CRUD、鉴权和权限。
- WebApp 专属文档和待办由 WebApp 团队维护；本仓库不创建 `docs/WebApp` 交接区，也不修改 `WebApp` 中的文件。
