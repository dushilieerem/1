# Technical Design：投研因子数据底座

## 模块边界

```text
授权数据供应商 / 用户导入
        ↓ 原始披露记录（不可覆盖）
Data Ingestion + 字段字典 + 质量校验
        ↓ 公告日点时转换
MarketData/（字段 Parquet + 数据清单）
        ↓
FieldParquetProvider / DataEngine → Panel → FactorEngine / ResearchEngine
```

沿用 `FieldParquetProvider` 的“一个字段一个 Parquet”模式。历史数据由 `MarketData/DataIngestion/` 批量采集后发布；`QuantCore` 只读取标准字段并向因子层提供面板；`ResearchEngine` 不管理数据源凭据或数据资产。实时或临时高频查询可使用 `WindProvider`，但不得替代历史回测的可复现数据发布。

## 存储与字段契约

原始财务记录保存为长表，最小列为：`symbol`、`report_period`、`announcement_date`、`field`、`value`、`unit`、`source`、`source_version`、`revision_at`。转换后每个标准字段输出 `日期 × 标的` 宽表，例如：

```text
MarketData/
  DataIngestion/                      # Wind 历史数据采集工具（入库）
  current/                            # API 当前只读数据版本（不入库）
    panels/                           # 字段 Parquet：日期 × 标的
      net_profit_ttm.parquet
      total_assets.parquet
      adj_factor.parquet
      is_suspended.parquet
      listing_status.parquet
      market_return_all_a.parquet
    benchmark/                         # 指数与成分数据
    metadata/                          # stock_info、字段说明等非面板数据
  releases/                           # 后续不可变历史发布版本（不入库）
```

字段字典和数据资产清单的评审基线分别见 `05-field-dictionary.md`、`06-data-catalog.md`。实现时将其机读副本随每个发布版本输出；价格字段必须标注复权口径，财务字段必须标注单季/累计/TTM 与点时规则。

## 已交付的数据访问层

- `DataEngine` 以 `IDataProvider` 作为唯一数据读取入口；因子、研究编排和回测只访问标准字段面板，不直接依赖 Wind、AkShare、iFind 或文件路径。
- `FieldParquetProvider` 支持 `MarketData/current/panels` 的字段宽表、`current/benchmark` 的指数和成分、`current/metadata` 的非面板数据；传入旧版扁平目录时保持兼容。
- Provider 对字段按需懒加载并在实例内缓存；API 服务应按每个进程、每个数据版本复用其实例，而非每次回测重新读取全部文件。多数据源分层和适配要求见 `../../06-decisions/ADR-010-为什么采用统一数据引擎和多数据源适配.md`。
- 历史 Pandas Parquet 的日期索引可能保存于文件元数据；读取器已兼容显式 `datetime` 列与历史隐式索引两种格式，统一输出索引名为 `datetime`。

## 点时转换

对于每只证券、每个交易日，选择公告日不晚于该日的最新有效原始记录。TTM 由当时可见的四个季度构成，缺季度即空值；禁止使用报告期结束日直接对齐。转换任务输出数据版本、源版本、覆盖率和校验报告。

## 接口、兼容与回滚

- 新字段通过现有 `Panel["field"]` 按需加载，不改变已有字段或因子名称。
- 数据清单记录每个文件的哈希、覆盖区间、证券覆盖、来源版本和生成版本；因子/回测缓存键需纳入数据版本。
- 出现源数据问题时，将 `SVQUANT_DATA_DIR` 指向上一个完整版本；原始记录和旧版本 Parquet 保留至验证完成后按数据保留策略清理。

当前 `current/` 是运行时活动版本目录；后续发布流程先在 `releases/<data_version>/` 完成校验，再以原子方式切换 `current/`，避免 API 读到部分更新的数据。

## 测试策略

- 单元测试：字段映射、公告日边界、TTM/同比、修订版本、复权转换与缺字段异常。
- 集成测试：FieldParquetProvider 懒加载、因子计算与 API 回测。
- 数据质量：单位校验、覆盖率、日期连续性、证券代码一致性、异常值和源版本检查。

已完成验证：`FieldParquetProvider` 的 `current/` 目录解析、旧版 Pandas 日期索引读取，以及因子回测 API 从实际 `MarketData` 读取 2023 年 CSI500 数据并返回策略与基准净值曲线。

## 技术风险

最大风险是数据许可和公告日质量；第二风险是不同供应商的科目定义、单位和修订规则不同。MVP 必须先固定一个授权来源和字段字典，不能混用多个来源后再猜测映射。
