# FEAT-015：个股日线行情 API

- 状态：开发中
- 所属 Initiative：INIT-001 投研核心
- 所属能力：数据、研究 API

## 文档索引

- `02-product-requirements.md`：业务规则与验收

其余原分册（`01-feature-proposal.md`、`03-technical-design.md`、`04-project-plan.md`、`05-verification.md`）内容已收编至本 README。

## 1. 价值与范围

### 功能名称

个股日线行情 API。

### 背景

Web 应用需要以指定股票代码渲染日线图，但当前 HTTP 服务仅提供回测与因子相关结果，前端没有可复用的标准日线数据入口。

### 用户价值

研究者可在 Web 工作台快速查看任一已发布标的的开、高、低、收价格，辅助理解因子、策略和回测结果。

### 商业价值

日线图是研究工作台的基础交互组件。先建立稳定的只读行情接口，可降低 Web 端接入成本，并为后续股票详情、指标叠加和研究结果联动提供统一契约。

### 竞品分析

主流量化平台均在股票详情或研究界面提供历史 K 线。MVP 只提供已发布数据版本的原始日线，不引入实时行情、复权切换或技术指标计算，确保价格口径可追溯。

### MVP 范围

- **必须做**：按股票代码和可选日期区间返回日频 `open`、`high`、`low`、`close`；返回实际数据区间；明确区分无标的、无数据和数据不可用。
- **可以以后做**：成交量/成交额、复权模式、分页或条数限制、指数日线、技术指标、实时或盘中行情、数据版本查询。
- **明确不做**：在线数据源调用、用户鉴权与额度、行情数据持久化、前端图表实现、投资建议。

### 优先级与宏观影响

评分：商业价值 3、用户价值 4、战略价值 3、技术成本 2，优先级为 P1。属于既有数据与研究 API 能力的 L1 增量，更新 Backlog 和 Feature 文档，不改变产品能力边界或新建 Initiative。

## 2. 方案设计

### 模块边界

- `QuantCore.data`：继续拥有统一数据读取契约；通过 `DataEngine(FieldParquetProvider(...))` 读取标准字段，不新增供应商逻辑。
- `ResearchEngine.api`：作为当前 Web 的 HTTP 适配层，负责参数校验、HTTP 状态码及 JSON 序列化；不计算指标、不持久化行情。
- Web：调用接口并渲染图表；不参与数据口径与缓存。

### 实现设计

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

### 兼容、回滚与安全

新增 GET 端点，不修改既有回测请求或响应，向后兼容。若运行异常，可从部署路由中移除该端点，既有回测 API 不受影响。生产环境的鉴权、CORS 白名单、调用额度由未来 SaaS 应用层统一处理；本 Feature 不绕过该长期边界。

### 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 数据字段缺失或版本不完整 | 无法画出可信日线 | 503 明确失败，禁止 close 填充 |
| 大范围请求响应过大 | Web 加载变慢 | MVP 保持契约简洁；后续增加最大范围与分页 |
| 证券代码口径不同 | 查不到数据 | 保持精确匹配；代码标准化作为独立数据主数据能力 |

### 测试策略

使用最小 Field Parquet 测试目录验证成功路径、日期过滤、无标的、倒置日期和字段缺失；运行完整 pytest 回归。

## 3. 验收与证据

### 自动化验证

- 2026-07-28：`ResearchEngine/tests/test_api.py` 通过，37 passed。
- 覆盖：股票代码列表的排序返回、OHLC 返回与日期筛选、未知代码、倒置日期、字段缺失，以及现有因子/策略 API 回归。

### 验收结论

`GET /api/market-data/symbols` 与 `GET /api/market-data/daily/{symbol}` 已实现，满足 MVP 的股票选择器数据、结构化 OHLC、明确错误语义和已发布 Parquet 数据边界。

### 已知验证限制

历史验证曾因第三方回测依赖初始化报错而中断；该依赖已从项目移除，后续全量回归不再受其影响。

## 4. 计划与里程碑

| 任务 | 复杂度 | 风险 | 依赖 |
|---|---:|---|---|
| 定义日线请求/响应模型与错误语义 | 1 | 低 | Product Requirements |
| 定义股票代码列表响应模型与错误语义 | 1 | 低 | Product Requirements |
| 实现基于 DataEngine 的日线读取与序列化 | 2 | 低 | FieldParquetProvider |
| 实现基于 DataEngine 的股票代码列表读取与序列化 | 1 | 低 | FieldParquetProvider |
| 接入 FastAPI 路由和 OpenAPI 文档 | 1 | 低 | API 模型 |
| 增加 API 与回归测试、更新 API 文档 | 2 | 低 | 前三项 |

预计投入：1 人天。

里程碑：M1 读取标准 OHLC；M2 Web 可调用端点；M3 自动化测试与文档验收通过。

### Definition of Ready

- [x] 所属 Initiative 和产品能力明确。
- [x] Feature Proposal 已由本次需求确认。
- [x] MVP 范围和明确不做项已冻结。
- [x] 用户流程、业务规则和边界条件明确。
- [x] 验收标准可测试。
- [x] 架构边界、接口和数据影响已评估。
- [x] 关键技术风险已有明确失败语义与缓解方案。
- [x] 任务、依赖、复杂度和里程碑已拆分。
- [x] 测试策略和回滚方式已定义。
- [x] 没有阻塞性未决问题。
