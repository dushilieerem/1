# SVQuant 文档中心

本文档中心按“宏观规划 → 微观交付 → 宏观反馈”组织，是项目产品、架构、研发和交付信息的统一入口。

## 一句话流程

产品战略和能力地图产生 Initiative，Initiative 拆分为可验收的 Feature 完成设计与开发，交付结果再反馈到 Backlog、路线图和能力地图，形成闭环。

## 目录职责

| 目录 | 职责 | 主要读者 |
|------|------|----------|
| `01-workflow/` | 需求到交付流程、准入标准和模板 | 全团队 |
| `02-product/` | 产品定位、用户、市场、能力地图和路线图 | 老板、产品、研发 |
| `03-portfolio/` | Initiative、优先级和 Portfolio Backlog | 老板、产品、项目管理 |
| `04-features/` | 单个 Feature 的需求、设计、计划和验收材料 | 产品、研发、测试 |
| `05-architecture/` | 当前系统架构、数据设计和跨 Feature 技术约束 | 研发 |
| `06-decisions/` | 具有长期影响的架构决策记录（ADR） | 研发 |
| `07-delivery/` | Sprint、版本、风险和技术债 | 项目管理、研发 |
| `08-status/` | 已交付能力和当前实现状态 | 全团队 |
| `09-meeting/` | 会议纪要和阶段汇报 | 全团队 |
| `10-archive/` | 已被替代但需要保留的历史文档 | 按需 |

## 阅读顺序

1. `02-product/产品定位.md`
2. `02-product/产品能力地图.md`
3. `02-product/产品路线图.md`
4. `03-portfolio/portfolio-backlog.md`
5. 当前 Initiative 的 `README.md`
6. 当前 Feature 的 `README.md` 及其需求、设计和计划
7. `05-architecture/` 与相关 `06-decisions/`

## 文档原则

- 产品能力地图只在能力边界变化时更新，不承载日常开发状态。
- Feature 状态统一维护在 Portfolio Backlog 和 Feature `README.md`。
- 任何 Feature 通过 Definition of Ready 后才能编码，通过 Definition of Done 后才能标记完成。
- 历史文档只读；当前决策不得只记录在 `10-archive/` 或会议纪要中。

