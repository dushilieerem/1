# SVQuant 数据存储设计

> 本文定义 SVQuant 产品层的数据所有权和存储边界。
> ResearchEngine 的行情、因子运行时和回测结果存储由独立仓库管理，本文件不复制其内部数据库设计：
> https://gitee.com/yanggu-yuanqi-intelligence/research-engine

## 1. 存储所有权总览

| 数据 | 物理存储/入口 | 所有者 | SVQuant 是否直接访问 |
|------|---------------|--------|---------------------|
| 用户、登录、权限、社区、资讯 | SVQuant PostgreSQL（DATABASE_URL） | SVQuant | 是 |
| KnowledgeHub 元数据 | SVQuant PostgreSQL | SVQuant | 是 |
| KnowledgeHub 附件 | KnowledgeHub/data/ | SVQuant | 是 |
| 用户因子/策略配置 | SVQuant PostgreSQL | SVQuant | 是 |
| 官方因子目录快照 | SVQuant PostgreSQL 的同步表 | SVQuant（缓存） | 通过 ResearchEngine API 更新 |
| 产品展示缓存 | backend/output/ 下的可再生文件/SQLite | SVQuant（缓存） | 是 |
| 内置策略目录快照 | SVQuant PostgreSQL 的 `builtin_strategies` 表 | SVQuant（ResearchEngine 同步缓存） | 展示和请求解析读取 |
| marketdata | SVQuant 外部的 project/marketdata 或 ResearchEngine 配置目录 | ResearchEngine 与数据发布方 | 否 |
| 因子运行时值 | ResearchEngine 进程内 | ResearchEngine | 否 |
| 回测结果 SQLite | ResearchEngine 部署目录 | ResearchEngine | 否 |

根目录 Factor/、根目录 marketdata/ 和 ResearchEngine 的结果目录不属于 SVQuant 当前仓库。
任何需要研究数据或完整回测结果的功能都必须通过 ResearchEngine HTTP API。

## 2. SVQuant PostgreSQL

后端通过 backend/.env 的 DATABASE_URL 连接 PostgreSQL。数据库保存产品事实和用户状态，包括：

- 用户、登录会话所需的账号信息、权限和审计日志；
- 社区帖子、评论、标签、资讯及其产品状态；
- KnowledgeHub 的数据集、文档、分块、对话和模型配置元数据；
- 用户自定义因子、官方因子目录同步快照及因子展示指标；
- 用户策略、策略库、策略广场条目和策略运行的产品记录；
- 证券池、基准等用户资产配置。

ResearchEngine 不连接此 PostgreSQL。它只接收 SVQuant 经过鉴权和解析后的请求快照。

## 3. 文件和可再生缓存

### 3.1 backend/output

backend/output/ 被 .gitignore 忽略，用于本机生成的展示加速缓存，例如因子仪表盘指标。
缓存可以随时删除并通过 ResearchEngine API 重建，不能作为用户资产、回测审计结果或跨服务事实。

### 3.2 KnowledgeHub/data

KnowledgeHub/data/ 保存知识库运行时附件和本地数据。新上传附件默认不提交 Git；部署时由
人工或外部备份流程管理。仓库中已有的示例附件若需要随产品发布，可继续作为受控样例。

### 3.3 builtin_strategies

`builtin_strategies` 是 ResearchEngine 策略目录在 SVQuant PostgreSQL 中的同步快照，保存
内置策略的 ID、名称、类型、执行模式、版本和标签等展示/请求元数据。同步来源是
ResearchEngine API，SVQuant 不在本地保存或执行内置策略源码。

## 4. ResearchEngine 外部数据

ResearchEngine 部署侧负责：

- 读取已发布的 marketdata 目录；
- 校验 data_manifest.yaml 的版本或哈希，并在不匹配时拒绝计算；
- 在自己的进程中加载行情、执行因子/策略回测；
- 保存完整结果、任务状态和回测结果 SQLite。

SVQuant 只把日期、资产快照、因子/策略引用和计算参数提交给 API。它不依赖 Parquet 文件名、
数据目录层级或 ResearchEngine SQLite 表结构。

~~~text
数据发布方
    ↓ 已校验 release
ResearchEngine marketdata
    ↓ HTTP 研究接口
SVQuant backend
    ↓ 用户权限和展示缓存
SVQuant frontend
~~~

这样可以独立扩容或迁移 ResearchEngine，而不把约 9GB 以上的行情/回测生成物重新纳入
SVQuant 版本库。

## 5. 数据生命周期和备份

| 数据层 | 生命周期 | 备份/恢复 |
|--------|----------|-----------|
| PostgreSQL | 长期产品事实 | 按 SVQuant 数据库运维策略备份；恢复后校验迁移版本 |
| KnowledgeHub 附件 | 长期业务文件 | 按附件目录备份；数据库元数据和文件必须成对恢复 |
| backend/output/ | 临时加速缓存 | 不做事实备份，损坏后重建 |
| `builtin_strategies` | ResearchEngine 目录同步快照 | 随 SVQuant PostgreSQL 备份；可从 ResearchEngine 重建 |
| ResearchEngine marketdata | 按数据 release 管理 | 由数据发布方/ResearchEngine 维护版本、manifest 和备份 |
| ResearchEngine 结果 SQLite | 按研究结果保留策略 | 由 ResearchEngine 部署方备份；SVQuant 只依赖 API |

发布、数据 release 和服务升级出现问题时，采用人工回滚。回滚必须同时确认 SVQuant 版本、
ResearchEngine 版本和 API 契约版本相互兼容。

## 6. 禁止的耦合

- 不在 SVQuant 中重新创建 marketdata 镜像或结果 SQLite 副本。
- 不从 SVQuant 代码直接导入 ResearchEngine 的 Python 包。
- 不通过读取 ResearchEngine 的本地文件来判断任务状态或补结果。
- 不把 backend/output/ 缓存当作用户可审计的唯一结果。
- 不将密码、ResearchEngine 地址或数据 manifest 生成物提交到 Git。

## 7. 相关文档

- SVQuant 系统架构：system_architecture.md
- 回测服务集成与执行边界：engine-design.md
- ResearchEngine 独立仓库：https://gitee.com/yanggu-yuanqi-intelligence/research-engine
- 项目级技术决策：../05-技术决策/
