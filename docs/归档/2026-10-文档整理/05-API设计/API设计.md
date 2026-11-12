# SVQuant API 设计

## 1. API 入口与权威来源

SVQuant 后端使用 FastAPI。服务启动后，运行时 OpenAPI schema 位于 `/openapi.json`，交互式文档位于 `/docs`（本地默认 `http://127.0.0.1:8766/docs`）。代码路由和该 schema 是 SVQuant 已实现接口的事实来源；本文件只提供文档索引和跨服务约束，不复制完整 schema。

ResearchEngine（RE）的 API 契约由 RE 独立仓库维护。SVQuant 只经后端网关调用 RE，浏览器不得直连 RE。

## 2. API 模块索引

| 领域 | 后端路由模块 | 说明 |
|---|---|---|
| 健康检查、认证 | `backend/app/routers/health.py`、`auth.py` | 服务健康状态、登录和会话身份 |
| 因子、检测 | `backend/app/routers/factor.py`、`detect.py` | 因子目录适配、因子面板、检测项目和结果 |
| 策略 | `backend/app/routers/strategy.py` | 策略配置、目录同步和回测 BFF |
| ResearchEngine 网关 | `backend/app/routers/re_gateway.py` | 研究服务相关 HTTP 集成 |
| 社区、资讯 | `community.py`、`news.py` | 帖子、互动、资讯查询 |
| 自选股 | `watchlists.py` | 用户证券列表 |
| AI 与 Agent | `ai.py`、`agent.py` | AI 请求、Agent 和使用信息 |
| 知识库 | `kh.py` | KnowledgeHub API |
| 管理与审计 | `admin_logs.py` | 管理员操作和审计日志 |

目前没有强制统一所有接口使用同一种 JSON 外层信封；请求和响应形状以具体路由及 OpenAPI schema 为准。鉴权接口使用 SVQuant 会话凭据，权限判断在后端执行。

## 3. ResearchEngine 契约

- [因子面板 RE 接口契约](../../../接口设计/RE契约/因子面板-RE接口契约.md)是集成侧提案，文档会注明尚待 RE 确认/实现的字段和行为，不代表当前线上契约。
- ResearchEngine 内部接口的权威 schema、兼容策略和契约测试由 [ResearchEngine 独立仓库](https://gitee.com/yanggu-yuanqi-intelligence/research-engine)维护。
- SVQuant 网关负责鉴权、参数转换、超时和错误映射；不复制 RE 的行情读取、因子/策略执行或回测逻辑。

## 4. 因子接口参考

以下 Markdown 与因子目录适配代码共置。`GET /api/factor/file/{name}` 会从 `backend/factor/` 提供这些文件，因此保留原位置，避免改变现有文件 API 的可见资源。

- [因子回测接口说明](../../../../backend/factor/backtest-factor.md)
- [因子库目录接口说明](../../../../backend/factor/factor-libraries.md)
- [因子列表接口说明](../../../../backend/factor/factor-library-factors.md)
- [因子适配模块说明](../../../../backend/factor/README.md)
