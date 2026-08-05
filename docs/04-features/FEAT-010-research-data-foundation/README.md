# FEAT-010：投研因子数据底座

- 状态：待批准
- 所属 Initiative：INIT-001 投研核心
- 所属能力：数据 / 因子研究
- 优先级：P0
- 宏观影响：L1（补齐既有数据与因子研究能力，不改变产品定位或模块边界）

## 目标

补齐聚宽兼容因子和投研基础能力所缺的点时财务、历史分类、复权、交易状态、市场基准与预期数据，并以统一的字段字典、授权记录和 Parquet 数据契约对外提供。

## 文档索引

- `01-feature-proposal.md`：商业背景、MVP 范围和优先级。
- `02-product-requirements.md`：数据范围、业务规则、边界及验收标准。
- `03-technical-design.md`：数据模型、存储、接口、回滚和测试设计。
- `04-project-plan.md`：任务拆解、排期、风险、里程碑与 DoR。
- `05-field-dictionary.md`：标准字段、单位、口径、点时可见性与变更控制。
- `06-data-catalog.md`：数据资产、发布清单、质量验收与授权待确认项。
- `07-ifind-trading-calendar.md`：iFinD 全 A 股交易日历的交易所映射、下载起始日与质量规则。

## 当前结论

现有 `MarketData/` 已迁移为 `current/panels`、`current/benchmark` 与 `current/metadata` 三类运行时数据目录。`FieldParquetProvider("MarketData")` 可自动解析该目录，并兼容旧版扁平 Parquet；`DataEngine` 继续通过 `IDataProvider` 向因子和回测屏蔽存储及供应商差异。真实因子回测 API 已验证可从当前目录读取行情与基准。

数据访问基础已经交付，但本 Feature 仍保持“待批准”：DATA-001 的口径/许可盘点，以及公告日财务、复权、交易状态、市场基准和完整发布清单尚未完成。历史数据采集工具位于 `MarketData/DataIngestion/`；点时财务数据的授权和样本确认仍是进入后续开发的阻塞项。
