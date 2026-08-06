# iFinD HTTP 数据采集

本目录包含 iFinD HTTP 的鉴权、原始响应缓存、交易日历、全 A 证券池和日频行情下载脚本。

## 共同规则

- 凭据只从 `IFIND_REFRESH_TOKEN` 环境变量读取；不得将 refresh token 或 access token 写入代码、配置或 CSV。
- 每个 HTTP 成功响应都先落盘为原始 JSON，再解析为 CSV。重跑同一分区会重放本地 JSON，不重复消耗 iFinD 下载量。
- CSV 是人工检查和问题追溯的原始层；本目录不直接写入 `MarketData/current/` 或 `MarketData/releases/` 的 Parquet。
- 每次价格或成交指标的全量/日增量任务结束后，都会将所有已完成 CSV 分区汇总为 `MarketData/sources/ifind/daily.csv`。该文件每行是一个 `date + thscode`，列包括后复权 OHLC、成交量、成交额和换手率；任一数据域暂缺时对应字段留空，不丢弃该证券日期记录。

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
```

CSV 输出在 `MarketData/sources/ifind/calendar/`；每个交易所、每个请求区间的原始响应保存在 `calendar/raw/<交易所>/<起始日>_<结束日>.json`。

## 全 A 证券池

从超级命令导出的“股票简称、股票代码、上市交易所、上市日期、上市板块”请求文本中只读取 `formData.codes`，不会读取或保存其中的 access token。当前静态证券池必须校验为 5,537 只：沪 2,310、深 2,894、北 333。

```powershell
python -m data_ingestion.ifind.universe `
  --super-command-file <超级命令文本路径> `
  --as-of 2026-08-04
```

输出为 `MarketData/sources/ifind/universe/a_share_5537.csv`；原始响应为 `universe/raw/all_a_5537_<截面日>.json`。

## 全 A 日频行情

日频行情固定分为三个脚本：下载脚本只写原始 JSON；CSV 脚本只读取 JSON 并生成完整 CSV；Parquet 脚本只读取完整 CSV。后复权 OHLC 使用 `functionpara.CPS: "1"`，成交指标使用 `volume,amt,turn` 且不带复权参数。下载任务按交易所、证券批次和交易日窗口分区，以便断点续传；默认每个请求为 100 只证券 × 10 个交易日。

```powershell
# 指定历史区间的全量回填；跳过已完成 CSV，重放已有 JSON
python -m data_ingestion.ifind.market_data_download backfill `
  --start 1990-12-01 --end 2026-08-04

# JSON 汇总为完整 CSV，不调用 iFinD
python -m data_ingestion.ifind.market_data_csv

# 完整 CSV 转 Parquet，不调用 iFinD
python -m data_ingestion.ifind.market_data_parquet

# 收盘后执行，仅处理目标日期
python -m data_ingestion.ifind.market_data_download update --as-of 2026-08-05
```

原始 JSON 分别保存在 `prices/hfq/raw/` 与 `liquidity/raw/`，用于人工核验和断点续传。完整文件是 `MarketData/sources/ifind/daily.csv` 与 `daily.parquet`，字段为后复权 OHLC、`volume`（股）、`amount`（元）、`turnover`（小数）。

## 全 A 日期序列：估值、行业与状态

日期序列同样分为下载 JSON、JSON 汇总 CSV、CSV 转 Parquet 三个脚本。下载流通市值、PE、PB、申万行业名称与代码、涨跌停状态；`Fill` 固定为 `Blank`，即缺失不以前值填充。基础数据周额度为 500 万点，默认每次运行最多计划 450 万估算点；一个请求默认 100 只证券 × 10 个交易日 × 6 字段。

```powershell
python -m data_ingestion.ifind.date_sequence_download backfill `
  --start 2026-01-01 --end 2026-08-04

python -m data_ingestion.ifind.date_sequence_csv
python -m data_ingestion.ifind.date_sequence_parquet

python -m data_ingestion.ifind.date_sequence_download update --as-of 2026-08-05
```

原始 JSON 在 `MarketData/sources/ifind/date_sequence/raw/`；完整文件为 `MarketData/sources/ifind/date_sequence.csv` 与 `date_sequence.parquet`。涨跌停状态保留 iFinD 原值。
