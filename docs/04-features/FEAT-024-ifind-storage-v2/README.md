# FEAT-024：iFinD 宽表规范与渐进替换

- 状态：已批准
- 所属 Initiative：INIT-001 投研核心
- 所属能力：数据 / 研究基础设施
- 优先级：P0
- 关联 Feature：FEAT-010 投研因子数据底座
- 批准日期：2026-08-11

## 目标

保留现有 AkShare 可用数据，以 iFinD 数据逐步补全和替换 `MarketData/current`。持久化格式采用“一个业务域一个多字段 Parquet 宽表”，数据发布后只读，不在原文件中增量修改。

验证期只规定：每个宽表文件代表什么、包含哪些字段、字段如何排列。字段单位沿用 iFinD 定义，存储层不做换算；缺失值原样保留，交给研究员在使用时处理。

## 文档

- `01-feature-proposal.md`：目标、范围和选择理由。
- `02-product-requirements.md`：业务规则与验收标准。
- `03-technical-design.md`：各多字段 Parquet 宽表的正式规格。
- `04-project-plan.md`：快速验证、切换和服务器运行任务。
- `05-server-memory-runtime.md`：服务器一次加载、共享内存和多用户回测方案。
- `../../06-decisions/ADR-016-Parquet持久化与只读内存快照.md`：持久化与运行时架构决策。
- `../../06-decisions/ADR-017-市场数据按业务域采用多字段宽表.md`：宽表物理组织决策。

## 核心结论

1. `panels/market_data.parquet` 保存后复权价格和流动性七个字段。
2. `panels/daily_basic.parquet` 保存日频市值、股本和估值字段。
3. `panels/security_status.parquet` 保存行业、涨跌停、ST 和是否停牌字段。
4. `display/unadjusted_price.parquet` 单独保存 WebApp 未复权 OHLC。
5. `benchmark/index_weights_<index>.parquet` 同时保存指数权重和历史成分，不再单独保存 constituents 表。
6. `universe/a_share.parquet` 保存静态全 A 股票池列表。
7. 发布文件不可修改；数据更新生成新版本，验证后整体切换 `current`。
8. 服务器启动时将选定版本转换为按字段只读内存数组，正常回测不再读取 Parquet。
