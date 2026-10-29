# INIT-004：研究第二阶段项目计划

- 状态：重新规划
- 说明：研究计算实现已拆分到 ResearchEngine 独立仓库；本计划只保留 SVQuant 产品层和跨仓库交付事项。

## 1. 目标

围绕因子研究和策略研究完善用户体验，同时保持 SVQuant 与 ResearchEngine 的职责分离：

1. 明确因子/策略页面的产品流程、权限和结果展示；
2. 通过稳定 HTTP 契约完成请求、任务状态和结果展示；
3. 建立 SVQuant 网关集成测试和跨仓库锁步发布流程；
4. 将 AI 生成、回测解读和产品记录留在 SVQuant，将计算执行留在 ResearchEngine。

## 2. 范围

### SVQuant 负责

- 用户输入、鉴权、用户因子/策略配置和资产快照；
- ResearchEngine 网关、请求转换、轮询、超时和错误展示；
- AI 供应商适配、研究结果解读和产品侧历史记录；
- 前端页面、后端 BFF、PostgreSQL 和可再生展示缓存；
- 集成测试、发布说明和人工回滚记录。

### ResearchEngine 负责

- 因子/策略目录、行情读取、计算、回测任务和结果存储；
- API schema、契约测试、计算测试和数据 manifest/质量校验；
- 研究服务自身的配置、部署、健康检查和回测结果 SQLite。

详细实现计划、内部任务和验收矩阵放在[ResearchEngine 独立仓库](https://gitee.com/yanggu-yuanqi-intelligence/research-engine)。

## 3. 交付顺序

~~~text
产品需求与页面流程
        ↓
ResearchEngine API 契约确认
        ↓
SVQuant backend 网关与权限
        ↓
前端请求/状态/结果展示
        ↓
两仓库集成验证
        ↓
锁步发布与人工回滚准备
~~~

## 4. 验收条件

- 未登录或无权限请求不会到达 ResearchEngine。
- 用户资产快照、因子/策略引用和请求参数转换正确。
- 同步与异步任务的提交、轮询、终态、失败、取消和超时均能正确展示。
- SVQuant 不读取 ResearchEngine 本地行情或结果数据库，不执行研究代码。
- 指定版本的 ResearchEngine 契约测试和 SVQuant 集成验证均通过。
- 发布记录包含两个仓库版本、API 契约版本、配置变更和人工回滚步骤。

旧版包含 ResearchEngine 内部文件路径的计划已被本文件替代；历史提交仍保留追溯记录。
