## ADR-024: ResearchEngine HTTP API 使用 `/api` 前缀

### 问题

分层迁移阶段将 ResearchEngine HTTP 路由切换为 `/api/v2`，但现有 WebApp 和历史
ResearchEngine 契约使用 `/api`。继续使用 `/api/v2` 会造成客户端路径不一致，并要求额外的
前端适配。

### 选择

ResearchEngine 当前所有 HTTP 路由统一使用 `/api` 前缀，不提供 `/api/v2` 兼容入口。端点
后缀、请求/响应结构、因子异步任务轮询、策略同步回测和每日批量行为保持不变。

### 备选方案

- **同时保留 `/api` 和 `/api/v2`**：兼容性更好，但会维护两套路由入口并掩盖调用方迁移问题。
- **继续使用 `/api/v2`**：与既有 WebApp 契约不一致，需要额外适配。

### 后果

ResearchEngine 与既有 `/api` 调用方重新对齐，API 文档和测试只有一个当前前缀。仍调用
`/api/v2` 的客户端必须改用 `/api`；本次不修改 WebApp 文件。
