# SVQuant 文档中心

## 主链路：思考顺序，不是目录结构

```text
需求 → 业务 → 架构 → 功能 → 实现
```

这条链路依次回答五个问题：为什么做、业务怎么跑、系统怎么承载、系统具体做什么、如何开发上线可用。它约束的是“结论什么时候必须有”——任何新能力都必须沿链路形成结论，不能从需求直接跳到编码，也不能用代码反向替代业务定义；但它不是文件夹结构，五层结论按下表落位。

### 五层结论的落点

| 链路层 | 回答的问题 | 落点 |
|--------|-----------|------|
| 需求 | 为什么做 | [`01-需求文档/`](01-需求文档/)；FEAT 包 README「价值与范围」 |
| 业务 | 业务怎么跑 | Initiative 的 `domain-design.md`、PRD 业务章节、FEAT 包「业务规则与场景」 |
| 架构 | 系统怎么承载 | [`02-架构文档/`](02-架构文档/)、[`05-技术决策/`](05-技术决策/)（ADR）、FEAT 包内技术设计 |
| 功能 | 系统具体做什么 | FEAT 包 README 与包内 requirements 文件 |
| 实现 | 怎么开发上线 | FEAT 包 README「验收与证据」/ 交付记录；[`04-项目管理/`](04-项目管理/) |

## 目录

| 目录 | 职责 | 变更频率 |
|------|------|----------|
| [`00-文档治理/`](00-文档治理/) | 工作流、分级 DoR/DoD、模板 | 低 |
| [`01-需求文档/`](01-需求文档/) | 为什么做 + 业务怎么跑：产品定位、PRD、用户画像、竞品、路线图、项目组合、Initiative（含业务流程与领域设计） | 低 |
| [`02-架构文档/`](02-架构文档/) | 系统怎么承载：系统架构、引擎设计、数据设计（即概要设计） | 低 |
| [`03-功能文档/`](03-功能文档/) | 每个功能做什么、做到什么程度：FEAT 功能包（唯一交付工作单元）、产品能力说明 | 高 |
| [`04-项目管理/`](04-项目管理/) | 怎么交付：迭代计划、项目计划、风险、技术债、项目状态、会议记录 | 中 |
| [`05-技术决策/`](05-技术决策/) | 长期技术选择：ADR（即技术选型文档） | 只增不改 |
| [`99-历史归档/`](99-历史归档/) | 已被替代的资料（含已废弃的 FEAT-001 QuantCore 包），只读追溯 | 只增不改 |

## FEAT 功能包

`03-功能文档/FEAT-*` 是单个功能从价值到验收的唯一工作单元：

- 默认只有 `README.md` 一个文件，按 [FEAT功能包模板](00-文档治理/文档模板/FEAT功能包模板.md) 分节。
- 内容量大时才拆分 `requirements.md`（业务规则与验收）、`technical-design.md`（技术设计）、`verification.md`（验证记录）或专项参考文档；不写空壳章节文件。
- 状态唯一入口：[项目组合需求池](01-需求文档/项目组合/portfolio-backlog.md) + 包 README。

## 分级投入

文档深度跟随决策权重，不跟随模板层级：

- **平台级 / P0 / 跨模块**：走完整工作流（见 [需求到交付工作流](00-文档治理/需求到交付工作流.md)），必要时先立 Initiative、再拆 Feature，重大选择记 ADR。
- **普通 FEAT**：轻量 DoR 清单（价值、范围冻结、影响面、业务规则、验收、风险），单 README 交付。
- **Bug 修复 / 重构 / 单文件改动**：不要求文档，代码 + 测试即可；改变公共行为时补 README 结论或 ADR。

## 文档边界

- 根目录负责 SVQuant 产品级、项目级、跨模块的需求、业务边界、系统架构、公共契约和交付管理。
- `frontend/`、`backend/`、`KnowledgeHub/` 的工程说明属于 SVQuant；帮助文档统一放在 `docs/help/`。
- ResearchEngine 的内部架构、实现证据和专属 ADR 由[独立仓库](https://gitee.com/yanggu-yuanqi-intelligence/research-engine)维护，本仓库只记录 API 集成和跨仓库边界。
- `marketdata` 和回测结果 SQLite 不属于 SVQuant；ResearchEngine 在自己的部署环境中读取和管理它们。
- ResearchEngine 不负责用户资产 CRUD、鉴权、权限和 Web 页面；SVQuant 不导入 ResearchEngine 的 Python 包。

## 推荐阅读顺序

1. [需求文档](01-需求文档/)：先确认价值、用户、指标和范围；重点阅读 [产品定位](01-需求文档/产品定位.md)、[产品需求文档](01-需求文档/产品需求文档.md) 和 [项目组合需求池](01-需求文档/项目组合/portfolio-backlog.md)。业务结论同层维护：[产品能力地图](01-需求文档/产品能力地图.md)、[领域战略](01-需求文档/domain-strategy.md) 与各 Initiative 的 `domain-design.md`。
2. [架构文档](02-架构文档/)：阅读 [系统架构](02-架构文档/system_architecture.md)、[引擎设计](02-架构文档/engine-design.md) 和 [数据存储设计](02-架构文档/database_design.md)，确认模块边界和数据口径。
3. [功能文档](03-功能文档/)：进入对应 FEAT 功能包，从 README 确认价值、规则、方案、验收口径和当前状态。
4. [项目管理](04-项目管理/)：阅读当前迭代、项目计划、风险和技术债。
5. 按需查看 [技术决策](05-技术决策/)、[项目状态](04-项目管理/项目状态/) 和 [会议记录](04-项目管理/会议记录/)。
6. 按需进入 [ResearchEngine 独立仓库](https://gitee.com/yanggu-yuanqi-intelligence/research-engine)查看研究服务内部文档。

## 当前架构变更

- [ADR-029：研究服务采用 services 与 models 分层](05-技术决策/ADR-029-研究服务采用services与models分层.md)：取消 QuantCore 独立共享库定位，ResearchEngine 采用 `services / models / database` 的常规 FastAPI 分层。
- [FEAT-030：因子回测服务集成](03-功能文档/FEAT-030-因子回测流程重构/README.md)：ResearchEngine 内部实现已迁出，SVQuant 只维护因子回测网关、权限、任务状态和结果展示。
- [ADR-028：BacktestEngine 编排四引擎](05-技术决策/ADR-028-因子回测由BacktestEngine编排四引擎.md)：因子回测由统一应用管线编排。
- [FEAT-031：iFinD 采集项目拆分](03-功能文档/FEAT-031-iFinD采集项目拆分/README.md)：数据生产能力由独立项目维护，ResearchEngine 在部署环境中只读消费已发布的 `marketdata/`。
- [ADR-032：MarketData 扁平只读消费目录](05-技术决策/ADR-032-MarketData扁平只读消费目录.md)：定义外部行情目录与 ResearchEngine 的交接边界；SVQuant 不保存行情文件。

## 文档原则

- 链路顺序约束结论何时必须存在：没有上游结论，不得把实现当作默认答案；实现发现上游失效时回退修订。
- 一个结论只有一个权威版本：SVQuant 系统级结论在根目录，ResearchEngine 模块级结论在独立仓库，决策依据在 ADR；其他位置只链接，不复制。
- 文档深度跟随决策权重（平台级 > 普通 FEAT > 小改动），不追求层级齐全；禁止为凑层产生空壳文件。
- Feature 状态统一维护在 [项目组合需求池](01-需求文档/项目组合/portfolio-backlog.md) 和对应 Feature `README.md`。
- 任何 Feature 通过 [Definition of Ready](00-文档治理/Definition-of-Ready.md) 后才能编码，通过 [Definition of Done](00-文档治理/Definition-of-Done.md) 后才能标记完成。
- 历史文档只读；当前规则、决策和验收事实必须写入当前文档。
