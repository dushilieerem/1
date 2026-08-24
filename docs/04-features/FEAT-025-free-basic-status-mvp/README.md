# FEAT-025：免费数据源补齐日频基本面与证券状态 MVP

- 状态：待批准
- 所属 Initiative：INIT-001 投研核心
- 所属能力：数据 / 研究基础设施
- 优先级：P0
- 关联 Feature：FEAT-010、FEAT-024
- 提案日期：2026-08-14

## 目标

使用可公开获取的免费数据源，补齐以下两个活动数据资产：

- `MarketData/current/panels/daily_basic.parquet`
- `MarketData/current/panels/security_status.parquet`

MVP 的成功标准是：两张表追平 `market_data.parquet` 的最大交易日；沪深股票的核心估值、ST 和停牌字段可用于研究；每个缺口和口径差异均可审计。MVP 不承诺免费数据源与 iFinD 全字段、全市场、全历史等价。

## 文档

- `01-feature-proposal.md`：背景、价值、竞品和 MVP 范围。
- `02-product-requirements.md`：用户故事、业务规则、异常和验收标准。
- `03-technical-design.md`：数据源、转换、发布、质量和回滚设计。
- `04-project-plan.md`：任务拆解、排期、里程碑和风险。
- `05-source-and-field-contract.md`：免费源字段映射、口径和授权边界。

## 核心结论

1. BaoStock 负责沪深历史 `pe_ttm`、`pb`、`ps_ttm`、`is_st` 和交易状态。
2. AKShare/CNINFO 负责股本变动；市值由未复权收盘价乘以对应股本计算。
3. 现有 `pe` 保持 iFinD 语义，MVP 不用免费源的动态 PE 冒充。
4. 申万历史行业和完整历史 `limit_status` 暂不回填，避免引入未来信息或口径伪装。
5. 采用新 release 构建、质量检查、哈希登记和原子切换，禁止直接修改 `current`。
