# FEAT-010 数据清单（v1.0）

> 状态：待数据授权、样本和数据负责人确认。本文定义数据资产而非供应商合同；`授权状态` 未确认前不得下载、落盘或用于产品交付。

## 1. 清单与发布规则

- 每次完整数据发布在 `MarketData/releases/<data_version>/` 下生成；`MarketData/current/` 是 API 的活动版本目录，`SVQUANT_DATA_DIR` 可指向 `MarketData/` 根目录，由读取层自动解析 `current/`。
- 每个发布必须包含 `data_manifest.yaml`、字段字典副本、质量报告和所有已声明字段文件。清单记录文件 SHA-256、行列规模、日期区间、证券覆盖、来源版本和生成时间。
- 标准面板文件为 `<field>.parquet`，首列/索引为 `datetime`，其余列为规范化证券代码；原始受控数据不进入 Git，也不与运行时面板混放。
- `已存在（待盘点）` 仅表示项目声明已有相应文件；在质量盘点完成前，不能作为字段覆盖或授权已确认的证据。

## 2. MVP 数据资产

| ID | 数据资产 / 建议路径 | 内容与关键字段 | 粒度 / 格式 | 来源与授权状态 | 发布验收 |
|---|---|---|---|---|---|
| DATA-001 | `current/panels/{field}.parquet` | 既有 OHLC、成交量额、换手率、市值股本、PE/PB/PS、ST、涨停 | 日 × 证券，字段宽表 | 已迁移，口径/许可待盘点 | 对每个文件核对复权口径、日期区间、证券代码和缺失率 |
| DATA-002 | `raw/fundamentals.parquet` | 原始三表记录及第 5 节必填元数据 | 披露记录长表 | 待授权 | 抽样核对报告期、公告日、单位、修订链和供应商版本 |
| DATA-003 | `panels/{financial_field}.parquet` | 第 05 文档第 3 节所有财务标准字段 | 日 × 证券，字段宽表 | 由 DATA-002 转换 | 公告日前不可见；修订后切换；TTM 缺季为空 |
| DATA-004 | `current/panels/adj_factor.parquet` 与前复权价格面板 | 累计复权因子与前复权开高低收价格 | 日 × 证券，字段宽表 | 待授权 / 待确认现有数据 | 抽样复算复权公式；明确基日、企业行为处理和价格单位 |
| DATA-005 | `panels/listing_status.parquet`、`is_suspended.parquet`、`is_tradable.parquet` | 上市、停牌与交易可行状态 | 日 × 证券，字段宽表 | 待授权 | 抽样覆盖 IPO、停牌、复牌、退市与涨跌停边界 |
| DATA-006 | `panels/market_return_all_a.parquet` | 全 A 市场收益单列面板或日期序列 | 日，Parquet | 由 DATA-001/004/005 派生 | 用 t-1 流通市值复算抽样日期；记录成分和剔除规则 |
| DATA-007 | `metadata/security_master.parquet` | `symbol`、证券名称、上市/退市日期、代码变更关系 | 证券 / 生效区间，长表 | 待授权 / 待确认 | 证券代码可与所有面板列一一对应，历史代码变更可追溯 |
| DATA-008 | `releases/<version>/data_manifest.yaml` | 发布、来源、字段、文件、质量和授权摘要 | YAML | 本 Feature 生成 | 哈希齐全、字典版本匹配、所有必需资产状态为 `ready` |
| DATA-009 | `releases/<version>/quality_report.json` | 覆盖率、连续性、异常、映射和审计样本结果 | JSON | 本 Feature 生成 | 未解决的阻断错误为零；警告有责任人与处置说明 |

## 3. 后续数据资产（不属于 MVP 准入）

| ID | 数据资产 | 目的 | 前置条件 |
|---|---|---|---|
| DATA-101 | 历史行业分类面板 | 行业中性化、行业因子和归因 | 分类体系授权及生效区间样本 |
| DATA-102 | 分析师一致预期与修订 | 预期差、预期动量因子 | 明确再分发与缓存许可 |
| DATA-103 | 分红、资本结构和无风险利率 | 资本结构、收益调整、风险模型 | 公司行为事件日期与利率期限口径 |

## 4. `data_manifest.yaml` 最小契约

```yaml
schema_version: 1
data_version: 2026.07.0
field_dictionary_version: 1.0
generated_at: "2026-07-24T00:00:00+08:00"
assets:
  - id: DATA-003
    field: total_assets
    path: panels/total_assets.parquet
    sha256: "<64 位十六进制摘要>"
    date_range: ["2015-01-01", "2026-07-23"]
    symbol_count: 0
    source: "<授权供应商或用户导入>"
    source_version: "<供应商版本>"
    availability_rule: "announcement_date <= trade_date"
    status: ready
quality_report: quality_report.json
```

`status` 仅允许为 `ready`、`blocked`、`deprecated`。因子或回测依赖的字段不是 `ready` 时，加载层必须报告缺少字段及其数据资产 ID，不能降级为零值或替代口径。

## 5. 责任与待确认项

| 项目 | 建议责任角色 | 当前状态 | 进入开发前的完成标准 |
|---|---|---|---|
| 数据供应商许可 | 数据负责人 / 商务 | 阻塞 | 明确研究、缓存、展示、团队使用和再分发边界 |
| 源字段映射 | 数据负责人 + 量化研究员 | 阻塞 | 为 DATA-002 的每个源字段给出标准字段、单位和口径映射，并通过样本复核 |
| 数据质量基线 | 数据工程师 | 待开始 | 选定覆盖年份、证券范围、允许缺失与异常阈值 |
| 发布与回滚 | 数据工程师 | 待开始 | 成功生成 DATA-008/009，并能切换至上一个 `ready` 版本 |

结论：字段和资产边界现已定义，但 DATA-002、004、005、007 的授权与样本仍是本 Feature 的阻塞性未决问题；在它们关闭前 Feature 保持“待批准”。
