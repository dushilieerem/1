# iFinD HTTP 数据采集

本目录包含 iFinD HTTP 的鉴权、原始响应缓存、交易日历、全 A 证券池和后复权日频 OHLC 下载脚本。

## 共同规则

- 凭据只从 `IFIND_REFRESH_TOKEN` 环境变量读取；不得将 refresh token 或 access token 写入代码、配置或 CSV。
- 每个 HTTP 成功响应都先落盘为原始 JSON，再解析为 CSV。重跑同一分区会重放本地 JSON，不重复消耗 iFinD 下载量。
- CSV 是人工检查和问题追溯的原始层；本目录不直接写入 `MarketData/current/` 或 `MarketData/releases/` 的 Parquet。

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

## 全 A 后复权 OHLC

后复权协议固定为 `/api/v1/history_data` 且 `functionpara.CPS` 为 `"1"`。任务按交易所日历、证券批次和交易日窗口分区。默认一个请求为 100 只证券 × 10 个交易日 × 4 字段，即约 4,000 个估算点；一次运行最多计划 1.2 亿估算点，到上限安全停止，可断点续传。

```powershell
# 指定历史区间的全量回填；跳过已完成 CSV，重放已有 JSON
python -m data_ingestion.ifind.prices backfill `
  --start 1990-12-01 --end 2026-08-04

# 收盘后执行，仅处理目标日期
python -m data_ingestion.ifind.prices update --as-of 2026-08-05
```

原始响应在 `MarketData/sources/ifind/prices/hfq/raw/`，可检查 CSV 在 `MarketData/sources/ifind/prices/hfq/csv/`。
