# 个股日线行情 API：Technical Design

## 模块边界

- `QuantCore.data`：继续拥有统一数据读取契约；通过 `DataEngine(FieldParquetProvider(...))` 读取标准字段，不新增供应商逻辑。
- `ResearchEngine.api`：作为当前 Web 的 HTTP 适配层，负责参数校验、HTTP 状态码及 JSON 序列化；不计算指标、不持久化行情。
- Web：调用接口并渲染图表；不参与数据口径与缓存。

## 实现设计

新增 `researchengine.api.market_data`：进程内按当前数据目录复用 `DataEngine`。股票列表调用 `get_symbols()`，它从已发布面板 schema 获取可查询代码、从 `stock_info.parquet` 获取名称后去重排序；日线查询读取同一证券主数据的名称与 `open`、`high`、`low`、`close`，再以请求代码切出单标的序列，内连接、日期过滤、丢弃缺失值并序列化。路由和 Pydantic 响应模型保持薄层。

```text
Web → GET /api/market-data/symbols
    → ResearchEngine.api 路由/契约
    → DataEngine → FieldParquetProvider
    → 已发布 Parquet 面板 schema
    → JSON symbols

Web → GET /api/market-data/daily/{symbol}
    → ResearchEngine.api 路由/契约
    → DataEngine → FieldParquetProvider
    → 已发布 Parquet 面板（open/high/low/close）
    → JSON bars
```

## 兼容、回滚与安全

新增 GET 端点，不修改既有回测请求或响应，向后兼容。若运行异常，可从部署路由中移除该端点，既有回测 API 不受影响。生产环境的鉴权、CORS 白名单、调用额度由未来 SaaS 应用层统一处理；本 Feature 不绕过该长期边界。

## 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 数据字段缺失或版本不完整 | 无法画出可信日线 | 503 明确失败，禁止 close 填充 |
| 大范围请求响应过大 | Web 加载变慢 | MVP 保持契约简洁；后续增加最大范围与分页 |
| 证券代码口径不同 | 查不到数据 | 保持精确匹配；代码标准化作为独立数据主数据能力 |

## 测试策略

使用最小 Field Parquet 测试目录验证成功路径、日期过滤、无标的、倒置日期和字段缺失；运行完整 pytest 回归。
