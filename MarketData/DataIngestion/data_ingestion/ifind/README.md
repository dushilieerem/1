# iFinD HTTP 数据采集

本目录包含 iFinD HTTP 的鉴权、原始响应缓存、交易日历、全 A 证券池和日频行情下载脚本。

## 共同规则

- 凭据只从 `IFIND_REFRESH_TOKEN` 环境变量读取；不得将 refresh token 或 access token 写入代码、配置或 CSV。
- 每个 HTTP 成功响应都先落盘为原始 JSON，再解析为 CSV。重跑同一分区会重放本地 JSON，不重复消耗 iFinD 下载量。
- CSV 是人工检查和问题追溯的原始层；本目录不直接写入 `MarketData/current/` 或 `MarketData/releases/` 的 Parquet。
- 市场行情按复权方式分别汇总为 `MarketData/sources/ifind/market_data_hfq|qfq|none.csv`，再分别转为同名 Parquet。

## 交易日历

全 A 只维护一份统一日历 `calendar/ALL_A.csv`。全量回填和日增量都只请求深交所市场代码 `212100`，随后沪深北的全 A 行情下载均使用这份日历；旧的 SH、SZ、BJ CSV 不再更新或读取。

```powershell
cd MarketData/DataIngestion

# 指定历史区间回填
python -m data_ingestion.ifind.calendar backfill `
  --start 1990-12-01 --end 2026-08-04

# 每日收盘后补充
python -m data_ingestion.ifind.calendar update

# 一次性按现有深交所 CSV 重建统一日历，不请求 iFinD
python -m data_ingestion.ifind.calendar build-from-existing-sz

# 将统一交易日历 CSV 转为 Parquet，不调用 iFinD
python -m data_ingestion.ifind.calendar_parquet
```

CSV 与 Parquet 输出在 `MarketData/sources/ifind/calendar/`；原始响应保存在 `calendar/raw/ALL_A/<起始日>_<结束日>.json`。

## 全 A 证券池

从超级命令导出的“股票简称、股票代码、上市交易所、上市日期、上市板块”请求文本中只读取 `formData.codes`，不会读取或保存其中的 access token。当前静态证券池必须校验为 5,537 只：沪 2,310、深 2,894、北 333。

```powershell
python -m data_ingestion.ifind.universe `
  --super-command-file <超级命令文本路径> `
  --as-of 2026-08-04

# 将证券池 CSV 转为 Parquet，不调用 iFinD
python -m data_ingestion.ifind.universe_parquet
```

输出为 `MarketData/sources/ifind/universe/a_share_5537.csv` 与 `a_share_5537.parquet`；原始响应为 `universe/raw/all_a_5537_<截面日>.json`。

## 全 A 日频行情

日频行情固定分为三个脚本：下载脚本只写原始 JSON；CSV 脚本只读取 JSON 并生成完整 CSV；Parquet 脚本只读取完整 CSV。价格支持 `hfq`（后复权，`CPS: "1"`）、`qfq`（前复权，`CPS: "2"`）和 `none`（不带 CPS）；三种价格 raw 与最终文件分别保存。成交指标使用 `volume,amt,turn` 且不带复权参数，三种价格共用同一份 liquidity raw。下载任务按交易所、证券批次和交易日窗口分区，以便断点续传；默认每个请求为 100 只证券 × 10 个交易日。

```powershell
# 指定历史区间的全量回填；跳过已完成 CSV，重放已有 JSON
python -m data_ingestion.ifind.market_data_download backfill `
  --start 1990-12-01 --end 2026-08-04 --adjustment hfq

# 首次回填或修复：全部 JSON 汇总为完整 CSV，不调用 iFinD
python -m data_ingestion.ifind.market_data_csv rebuild --adjustment hfq

# 收盘后日增量：仅解析当日 JSON，并替换完整 CSV 中同日记录
python -m data_ingestion.ifind.market_data_csv update --as-of 2026-08-05

# 完整 CSV 转 Parquet，不调用 iFinD
python -m data_ingestion.ifind.market_data_parquet --adjustment hfq

# 收盘后执行，仅处理目标日期
python -m data_ingestion.ifind.market_data_download update --as-of 2026-08-05 --adjustment hfq
```

价格原始 JSON 分别保存在 `prices/hfq/raw/`、`prices/qfq/raw/` 与 `prices/none/raw/`；成交指标原始 JSON 保存在共享的 `liquidity/raw/`。最终文件分别为 `market_data_hfq|qfq|none.csv` 与同名 Parquet：一行一个交易日，列为两级索引（第一级为 `thscode`，第二级为 OHLC、`volume`（股）、`amount`（元）、`turnover`（小数））。

## 全 A 日期序列：估值、行业与状态

日期序列同样分为下载 JSON、JSON 汇总 CSV、CSV 转 Parquet 三个脚本。下载流通市值、PE、PB、申万行业名称与代码、涨跌停状态；`Fill` 固定为 `Blank`，即缺失不以前值填充。基础数据周额度为 500 万点，默认每次运行最多计划 450 万估算点；一个请求默认 100 只证券 × 10 个交易日 × 6 字段。

```powershell
python -m data_ingestion.ifind.date_sequence_download backfill `
  --start 2026-01-01 --end 2026-08-04

# 首次回填或修复：全部 JSON 汇总为完整 CSV，不调用 iFinD
python -m data_ingestion.ifind.date_sequence_csv rebuild

# 收盘后日增量：仅解析当日 JSON，并替换完整 CSV 中同日记录
python -m data_ingestion.ifind.date_sequence_csv update --as-of 2026-08-05
python -m data_ingestion.ifind.date_sequence_parquet

python -m data_ingestion.ifind.date_sequence_download update --as-of 2026-08-05
```

原始 JSON 在 `MarketData/sources/ifind/date_sequence/raw/`；完整文件为 `MarketData/sources/ifind/date_sequence.csv` 与 `date_sequence.parquet`：一行一个交易日，列为两级索引（第一级为 `thscode`，第二级为日期序列字段）。涨跌停状态保留 iFinD 原值。

## 指数成分股权重

指数权重使用数据池 `p03563`。下载时每个“指数代码 × 交易日”保存一份原始 JSON，方便检查某次指数调样或权重异常；CSV 和 Parquet 为长表，一行代表该指数在该日的一只成分股。当前先保留接口原始字段名 `p03563_f001` 至 `p03563_f004`，避免在未核对实际响应前误写字段含义；下载一个样本后可据原始 JSON 固化为股票代码、名称、权重等业务字段。

```powershell
# 回填沪深 300（默认指数代码为 000300.SH）
python -m data_ingestion.ifind.index_weights_download backfill `
  --start 2026-01-01 --end 2026-08-07

# 下载其他指数，例如中证 500
python -m data_ingestion.ifind.index_weights_download backfill `
  --index 000905.SH --start 2026-01-01 --end 2026-08-07

# 只下载并写入收盘后的当日原始 JSON
python -m data_ingestion.ifind.index_weights_download update `
  --index 000300.SH --as-of 2026-08-07

# 原始 JSON 汇总为完整 CSV；当日更新只替换该日行
python -m data_ingestion.ifind.index_weights_csv rebuild --index 000300.SH
python -m data_ingestion.ifind.index_weights_csv update --index 000300.SH --as-of 2026-08-07

# CSV 转 Parquet，不调用 iFinD
python -m data_ingestion.ifind.index_weights_parquet --index 000300.SH
```

原始 JSON 路径为 `index_weights/raw/<指数代码>/<日期>.json`；完整文件为 `index_weights/<指数代码>.csv` 与同名 Parquet。
