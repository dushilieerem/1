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

沿用 `FieldParquetProvider` 的“一个字段一个 Parquet”模式。新增数据转换任务属于数据模块；`QuantCore` 只读取标准字段并向因子层提供面板；`ResearchEngine` 不管理数据源凭据或数据资产。

## 存储与字段契约

原始财务记录保存为长表，最小列为：`symbol`、`report_period`、`announcement_date`、`field`、`value`、`unit`、`source`、`source_version`、`revision_at`。转换后每个标准字段输出 `日期 × 标的` 宽表，例如：

```text
MarketData/
  fundamentals_raw.parquet            # 受控原始披露记录
  net_profit_ttm.parquet              # 公告日点时日频面板
  total_assets.parquet
  total_liabilities.parquet
  operating_revenue_ttm.parquet
  ...
  adj_factor.parquet
  close_unadjusted.parquet
  is_suspended.parquet
  listing_status.parquet
  market_return_all_a.parquet
  data_manifest.yaml
```

字段字典应单独版本化，声明标准名、中文名、单位、频率、源字段、可见性规则、适用行业及废弃状态。价格字段必须标注复权口径；财务字段必须标注单季/累计/TTM与点时规则。

## 点时转换

对于每只证券、每个交易日，选择公告日不晚于该日的最新有效原始记录。TTM 由当时可见的四个季度构成，缺季度即空值；禁止使用报告期结束日直接对齐。转换任务输出数据版本、源版本、覆盖率和校验报告。

## 接口、兼容与回滚

- 新字段通过现有 `Panel["field"]` 按需加载，不改变已有字段或因子名称。
- 数据清单记录每个文件的哈希、覆盖区间和生成版本；因子/回测缓存键需纳入数据版本。
- 出现源数据问题时，将 `SVQUANT_DATA_DIR` 指向上一个完整版本；原始记录和旧版本 Parquet 保留至验证完成后按数据保留策略清理。

## 测试策略

- 单元测试：字段映射、公告日边界、TTM/同比、修订版本、复权转换与缺字段异常。
- 集成测试：FieldParquetProvider 懒加载、因子计算与 API 回测。
- 数据质量：单位校验、覆盖率、日期连续性、证券代码一致性、异常值和源版本检查。

## 技术风险

最大风险是数据许可和公告日质量；第二风险是不同供应商的科目定义、单位和修订规则不同。MVP 必须先固定一个授权来源和字段字典，不能混用多个来源后再猜测映射。
