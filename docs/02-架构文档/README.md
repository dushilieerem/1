# 架构文档

本层回答“系统怎么承载业务”：定义 SVQuant 的产品边界、模块职责、数据所有权、ResearchEngine
HTTP 集成方式、部署依赖和跨仓库发布约束。

## 文档索引

| 文件 | 用途 |
|------|------|
| system_architecture.md | SVQuant 全局边界、模块职责、依赖方向和部署拓扑 |
| engine-design.md | 回测能力的跨仓库调用链、执行模式和网关边界 |
| database_design.md | SVQuant 自有数据、缓存、兼容资产和外部研究数据的所有权 |
| 因子面板-RE接口契约.md | 因子面板迁移到 RE 批量计算的接口提案与职责边界 |
| ResearchEngine 独立仓库 | https://gitee.com/yanggu-yuanqi-intelligence/research-engine：研究服务内部实现、API 契约、契约测试和专属 ADR |

## 当前边界

SVQuant 是产品层，负责用户体验和平台业务；ResearchEngine 是独立的研究计算服务，负责行情、
因子、策略执行、回测和回测结果。两者只通过已版本化的 HTTP API 交互：

~~~text
浏览器 → SVQuant frontend → SVQuant backend → ResearchEngine HTTP API
~~~

- 浏览器不直接访问 ResearchEngine。
- SVQuant 不导入 ResearchEngine 的 Python 包，不读取外部行情目录，不直接打开 ResearchEngine
  管理的回测结果 SQLite。
- ResearchEngine 不负责用户鉴权、用户资产 CRUD、权限、社区和 Web 页面。
- ResearchEngine 的 API 契约与契约测试由独立仓库维护；SVQuant 维护网关适配和集成验证。

## 文档同步关系

根目录只记录 SVQuant 的系统级结论和跨仓库约束。ResearchEngine 的内部架构、实现细节、API
契约和专属 ADR 以其独立仓库为准；当公共接口或所有权发生变化时，两个仓库必须同步更新。

本仓库的 05-技术决策/ 保存 SVQuant 或跨仓库决策。ResearchEngine 专属决策不在本仓库复制，
只链接到独立仓库，避免形成两套会漂移的实现说明。

## 进入功能和实现的最低条件

- 模块边界、职责、数据所有权和依赖方向明确。
- HTTP 接口、版本兼容、错误映射和失败边界明确。
- 配置、部署、监控、回滚和跨仓库锁步发布方式明确。
- 功能包的页面、字段、权限、验收和测试范围可独立执行。

页面、字段、操作、权限和用户提示进入功能文档，交付计划、状态和证据进入项目管理，长期技术
选择进入技术决策。
