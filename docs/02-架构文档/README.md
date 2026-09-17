# 架构文档

本层回答“系统怎么承载业务”：把已确认的业务流程转换为系统边界、模块职责、数据架构、接口依赖、技术约束和扩展方案。

## 文档索引

| 文件 | 用途 |
|------|------|
| `system_architecture.md` | SVQuant 全局系统边界、ResearchEngine 分层、数据流和接口形态 |
| `engine-design.md` | 向量化与事件驱动引擎的详细设计和协作边界 |
| `database_design.md` | MarketData、因子值、回测结果和发布目录的存储设计 |
| [`ResearchEngine 模块架构`](../../ResearchEngine/docs/02-架构文档/researchengine_architecture.md) | ResearchEngine 运行时架构和模块级调用链 |

## 架构文档同步关系

架构决策、模块架构和项目级架构是上下游关系，不是三份互相独立的说明：

```text
ResearchEngine/docs/05-技术决策/
              ↓ 已接受的模块决策
ResearchEngine/docs/02-架构文档/
              ↓ 影响系统边界、公共契约或数据所有权时同步上收
docs/02-架构文档/
```

- ResearchEngine 的已接受 ADR 必须先反映到 [`ResearchEngine 模块架构`](../../ResearchEngine/docs/02-架构文档/researchengine_architecture.md) 的当前基线、模块边界、执行链路或数据生命周期中。
- 影响跨模块边界、WebApp 契约、MarketData、公共接口或部署方式的结论，还必须同步到 `system_architecture.md`、`database_design.md` 或 `engine-design.md`。
- 只有提议或历史状态的 ADR 不得写入“当前实现”；需要保留时应明确标注为提议、历史或后续演进。
- 细节只保留一个权威版本：根目录记录系统级结论，ResearchEngine 记录模块级落地；另一处用链接引用，不复制出第二套互相漂移的实现说明。

## 进入下一层的最低条件

- 模块边界、职责、数据所有权和依赖方向明确。
- 核心接口、数据契约、兼容策略和失败边界明确。
- 性能、安全、可观测性、迁移和回滚风险有结论。
- 架构能够承载业务层的正常、分支和异常流程。
- 项目级重大长期技术选择已记录到 [`../05-技术决策/`](../05-技术决策/)；ResearchEngine 专属决策已记录到 [`ResearchEngine 技术决策`](../../ResearchEngine/docs/05-技术决策/)。

页面、字段、操作、权限和用户提示进入 [`../03-功能文档/`](../03-功能文档/)，交付计划、状态和发布证据进入 [`../04-项目管理/`](../04-项目管理/)。
