# Technical Design：免费数据源补齐日频基本面与证券状态 MVP

## 1. 设计原则

本方案复用 FEAT-024 的多字段宽表、不可变 release 和字段级 manifest，不改变 QuantCore 的数据读取接口。免费源只参与采集和候选发布，不直接进入因子或回测代码。

## 2. 数据源适配

### 2.1 BaoStock

使用历史日频接口采集沪深股票：

- `peTTM` → `pe_ttm`
- `pbMRQ` → `pb`
- `psTTM` → `ps_ttm`
- `isST` → `is_st`
- `tradestatus`（0 为停牌）→ `is_suspended`

采集器按交易日和证券分区落原始 CSV/Parquet，并保存请求参数、返回状态、SDK 版本和采集时间。北京市场不假设与沪深相同，除非单独完成字段验证。

### 2.2 AKShare/CNINFO

使用 CNINFO 股本变动接口采集总股本和流通股本事件。接口返回的万股先转换为股，只有存在明确变动生效日的事件才可展开为日频值。AKShare A 股实时快照用于最新日期的市值、PB 和 ST 交叉校验，不作为历史 TTM 字段的替代。

### 2.3 本地未复权行情

从 `display/unadjusted_price.parquet` 读取 `close`，与股本按日期×证券对齐：

```text
total_mv  = close_unadjusted × total_shares
float_mv  = close_unadjusted × float_shares
```

如果价格、股本任一缺失或非正，则市值保持缺失并记录异常。计算结果不得覆盖既有 release 的历史值。

## 3. 字段映射与来源规则

| 标准字段 | 主来源 | 市场 | 生效规则 | MVP 状态 |
|---|---|---|---|---|
| `total_shares` | AKShare/CNINFO | A 股，按可映射证券 | 股本变动生效日 | 目标补齐 |
| `float_shares` | AKShare/CNINFO | A 股，按可映射证券 | 股本变动生效日 | 目标补齐 |
| `total_mv` | 本地未复权收盘价×总股本 | A 股 | 同日价格和股本 | 目标补齐 |
| `float_mv` | 本地未复权收盘价×流通股本 | A 股 | 同日价格和股本 | 目标补齐 |
| `pe_ttm` | BaoStock | 沪深 | 交易日 | 可用 |
| `pb` | BaoStock | 沪深 | 交易日 | 可用 |
| `ps_ttm` | BaoStock | 沪深 | 交易日 | 可用 |
| `pe` | 既有 iFinD | 既有覆盖范围 | 原值保留 | 不补 |
| `is_st` | BaoStock | 沪深 | 交易日 | 可用 |
| `is_suspended` | BaoStock `tradestatus` | 沪深 | 交易日 | 可用 |
| `industry_sw` | 既有 iFinD | 既有覆盖范围 | 点时有效期 | 新日期暂空 |
| `industry_sw_code` | 既有 iFinD | 既有覆盖范围 | 点时有效期 | 新日期暂空 |
| `limit_status` | 既有 iFinD | 既有覆盖范围 | 原始状态 | 新日期暂空 |

规则是“字段级主来源”，不是逐单元格的 `coalesce`。重叠日期只做 QA，不自动覆盖既有值。

## 4. 历史与点时处理

1. 目标日期范围取 `market_data` 的交易日轴。
2. 候选构建先复制上一 release 的两张目标表。
3. 只对目标增量日期和明确允许补齐的缺失字段写入免费源值。
4. 既有行业仅在其原始有效日期范围内保留；没有历史生效区间的当前行业快照不得向前填充。
5. 股本事件按生效日展开，不能按公告日直接假设当天可见；若只有公告日则标记为 `effective_date_unverified` 并不进入标准面板。

## 5. 发布目录与 manifest

建议目录：

```text
MarketData/releases/free-basic-status-YYYYMMDD-v1/
├── panels/daily_basic.parquet
├── panels/security_status.parquet
├── sources/baostock/...
├── sources/akshare_cninfo/...
├── metadata/free_source_manifest.yaml
├── data_manifest.yaml
└── quality_report.json
```

`data_manifest.yaml` 至少记录：

```yaml
asset: daily_basic
field: pe_ttm
source: baostock
markets: [SH, SZ]
date_range: ["2017-01-03", "2026-08-12"]
transform: "BaoStock peTTM -> pe_ttm; no unit conversion"
status: partial
```

同时记录原始快照哈希、代码版本、SDK 版本、采集时间、缺失数量和质量检查版本。

## 6. 组件边界

建议新增以下采集/发布模块，名称可在实现阶段按现有包结构调整：

- `MarketData/DataIngestion/data_ingestion/baostock/daily.py`
- `MarketData/DataIngestion/data_ingestion/free_data/akshare_cninfo.py`
- `MarketData/DataIngestion/data_ingestion/shared/free_domain_release.py`
- `MarketData/DataIngestion/tests/test_free_basic_status_pipeline.py`

`FieldParquetProvider` 不需要新增字段逻辑；只要候选文件保持现有 schema，读取层即可复用。

运行依赖建议增加独立可选组：

```toml
free-data = ["akshare>=1.18.91", "baostock==0.9.3"]
```

实际版本需在 `svquant` 环境中完成兼容性验证后锁定。

## 7. 质量检查

- schema、日期轴、证券轴、重复列和排序检查。
- 既有非空值保护检查。
- BaoStock 与已有 iFinD 的重叠期差异统计，不以无依据阈值强行覆盖。
- `is_suspended` 与 141 天现有状态的精确率、召回率检查。
- 市值算术一致性和异常价格/股本检查。
- ST 名单与 AKShare 当前 ST 快照抽样比对。
- 运行两次的输出哈希和 manifest 稳定性检查。
- Provider 单字段投影、示例因子和回测回归检查。

## 8. 失败与回滚

任何采集、转换或质量检查失败都只影响候选 release。`current` 仍指向旧版本；切换由 release 指针或目录原子替换完成。需要回滚时恢复上一个已验收 release，不删除原始快照。

## 9. 关键风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 公共接口限流或变更 | 回补中断 | 断点续传、退避、固定 SDK 版本、保存原始响应 |
| BaoStock 与 iFinD 估值口径差异 | 因子结果变化 | manifest 标注来源切换，重叠期只做报告 |
| 股本生效日不清晰 | 市值和因子未来函数 | 无有效日期不进入标准面板 |
| 申万行业无点时历史 | 行业因子污染 | 新日期暂空，后续单独建设行业事件表 |
| 免费源授权不明确 | 对外服务风险 | MVP 仅限内部研究，商业化前做授权审查 |
