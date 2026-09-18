# 文档迁移映射

> 2026-07-17 完成文档中心化重构。新引用必须使用右侧路径。

| 原路径 | 新路径 |
|--------|--------|
| `QuantCore/docs/` | `docs/04-features/FEAT-001-quantcore-core/` |
| `ResearchEngine/docs/` | `docs/04-features/FEAT-002-research-engine/` |
| `docs/05-backtest-adapter.md` | `docs/04-features/FEAT-003-backtest-adapter/03-technical-design.md` |
| `docs/01-prd.md` | `docs/02-product/产品需求文档.md` |
| `docs/requirements/factor_engine.md` | `docs/02-product/capabilities/因子研究.md` |
| `docs/requirements/backtest.md` | `docs/02-product/capabilities/策略回测.md` |
| `docs/requirements/phase2-plan.md` | `docs/03-portfolio/initiatives/INIT-004-research-phase2/04-project-plan.md` |
| `docs/02-domain/` | `docs/03-portfolio/` 与 `docs/03-portfolio/initiatives/` |
| `docs/04-engine-design.md` | `docs/05-architecture/engine-design.md` |
| `docs/03-architecture.md` | `docs/10-archive/legacy/system-architecture-v0.1.md` |
| `docs/02-product/产品模块全景图.md` | `docs/10-archive/legacy/产品模块全景图-2026-07-15.md` |

原 `docs/03-architecture.md` 和产品模块全景图包含被新文档替代的重复信息，因此只保留为历史材料。

## 2026-08-28 当前层级调整（已被 2026-09-02 简化取代）

上表记录的是 2026-07-17 的历史迁移。2026-08-28 曾按“需求 → 业务 → 架构 → 功能 → 实现”把目录排为五层，该布局已被下节取代，仅作历史记录：

| 当时职责 | 当时路径 |
|----------|----------|
| 文档治理 | `docs/00-文档治理/` |
| 需求层 | `docs/01-需求文档/` |
| 业务层 | `docs/02-业务文档/` |
| 架构层 | `docs/03-架构文档/` |
| 功能层 | `docs/04-功能文档/` |
| 实现层 | `docs/05-实现文档/` |
| 辅助决策与追踪 | `docs/06-技术决策/`、`docs/07-项目状态/`、`docs/08-会议记录/`、`docs/09-历史归档/` |

## 2026-09-02 文档结构简化（当前生效）

目录从“五层各一目录”收敛为“稳定层 + 功能包”；链路保留为思考顺序，不再是目录结构。本次迁移映射：

| 原路径 | 新路径 |
|--------|--------|
| `docs/02-业务文档/` | 并入 `docs/01-需求文档/`（`domain-strategy.md`、`产品能力地图.md` 移入；INIT `domain-design.md` 移入对应 Initiative 目录；双树合一） |
| `docs/03-架构文档/` | `docs/02-架构文档/` |
| `docs/04-功能文档/` | `docs/03-功能文档/` |
| `docs/04-功能文档/FEAT-001-QuantCore基础能力/` | `docs/99-历史归档/FEAT-001-QuantCore基础能力/`（QuantCore 已由 ADR-029 取消） |
| `docs/05-实现文档/FEAT-031-…-交付记录.md` | `docs/03-功能文档/FEAT-031-iFinD采集项目拆分/交付记录.md` |
| `docs/05-实现文档/`（计划、风险、技术债） | `docs/04-项目管理/` |
| `docs/07-项目状态/`、`docs/08-会议记录/` | `docs/04-项目管理/项目状态/`、`docs/04-项目管理/会议记录/` |
| `docs/06-技术决策/` | `docs/05-技术决策/` |
| `docs/09-历史归档/` | `docs/99-历史归档/` |

同时：FEAT 功能包中的 proposal / project-plan 空壳文件已收编进包 README；新功能包默认单 README（模板见 `docs/00-文档治理/文档模板/FEAT功能包模板.md`）。新引用一律使用新路径。

## 2026-09-02 第二轮：ResearchEngine/docs 同构收敛

模块目录编号与根目录对齐（02 架构 / 03 功能 / 04 项目管理 / 05 技术决策；00-治理与 01-需求为项目级，不在模块重复建立）：

| 原路径 | 新路径 |
|--------|--------|
| `ResearchEngine/docs/03-架构文档/` | `ResearchEngine/docs/02-架构文档/` |
| `ResearchEngine/docs/04-功能文档/` | `ResearchEngine/docs/03-功能文档/` |
| `ResearchEngine/docs/06-技术决策/` | `ResearchEngine/docs/05-技术决策/` |
| `ResearchEngine/docs/05-实现文档/` | 并入 `ResearchEngine/docs/04-项目管理/`（README 空壳删除） |
| `ResearchEngine/docs/07-模块状态/` | `ResearchEngine/docs/04-项目管理/模块状态/` |
| `ResearchEngine/docs/08-阶段汇报/` | `ResearchEngine/docs/04-项目管理/阶段汇报/` |

同时：模块内 20 个 FEAT 功能包按同一规则收编空壳文件（小包合并为单 README，大包保留 requirements / technical-design / verification）；FEAT-002、FEAT-007、FEAT-022 保持原文件结构仅修链接。新引用一律使用新路径。

SVQuant 文档仍由 `SVQuant/docs/` 维护，仓库不创建 `docs/SVQuant` 交接区。
