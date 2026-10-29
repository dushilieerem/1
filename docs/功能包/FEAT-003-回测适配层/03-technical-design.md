# FEAT-003：回测适配层技术说明

> 本 Feature 的回测执行实现属于 ResearchEngine 独立仓库。本文只保留 SVQuant 产品层的
> HTTP 集成约束，不记录已迁出的 Python 包路径。

## 1. SVQuant 侧适配

策略页面保存用户策略和配置后，由 backend strategy service 调用 ResearchEngine HTTP API。
因子页面由 factor BFF 提交因子引用或用户因子函数体，再按 ResearchEngine 返回的任务状态
读取结果。

SVQuant 侧负责：

- 用户认证、权限和资产快照；
- 请求参数转换、字段白名单和错误映射；
- 异步任务轮询、超时、取消和结果展示；
- 结果摘要与可再生展示缓存。

## 2. ResearchEngine 侧适配

ResearchEngine 负责向量化/事件策略执行、因子计算、行情读取、交易规则、绩效计算和结果存储。
其公开 HTTP API、请求/响应 schema、兼容策略及契约测试以[独立仓库](https://gitee.com/yanggu-yuanqi-intelligence/research-engine)
为准。

SVQuant 不导入 ResearchEngine Python 包，不读取行情 Parquet，不打开结果 SQLite，也不在本地
实现第二套回测逻辑。

## 3. 配置和验收

ResearchEngine 地址只在 SVQuant 的 backend/.env 中配置为 YG_RE_BASE；前端开发代理读取同一
配置。SVQuant 的集成验收至少覆盖：

1. 未授权请求不会转发；
2. 用户资产快照和请求字段正确转换；
3. 同步/异步响应、错误、超时和取消状态正确映射；
4. ResearchEngine 不可用时无本地隐式回退。

历史执行实现和计算测试随仓库拆分迁出，Git 历史保留追溯记录。
