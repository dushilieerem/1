# iFinD HTTP 数据采集

本目录包含 iFinD HTTP 的鉴权、原始响应缓存、交易日历、全 A 证券池和日频行情下载脚本。

## 目录结构

```text
ifind/
├── common/             # HTTP 客户端、原始 JSON 缓存、通用 Parquet 与路径约定
├── calendar/           # 交易日历：pipeline.py → parquet.py
├── universe/           # 证券主表：pipeline.py → parquet.py
├── market_data/        # 日频行情：download.py → csv.py → parquet.py
├── date_sequence/      # 估值、行业与状态：download.py → csv.py → parquet.py
└── index_weights/      # 指数成分权重：download.py → csv.py → parquet.py
```

各业务目录内按处理阶段命名；`common/` 只承载跨管道复用能力，不包含业务采集入口。

## 共同规则

- 凭据只从 `IFIND_REFRESH_TOKEN` 环境变量读取；不得将 refresh token 或 access token 写入代码、配置或 CSV。
- 每个 HTTP 成功响应都先落盘为原始 JSON，再解析为 CSV。重跑同一分区会重放本地 JSON，不重复消耗 iFinD 下载量。
- CSV 是人工检查和问题追溯的原始层；本目录不直接写入 `MarketData/current/` 或 `MarketData/releases/` 的 Parquet。
- 市场行情按复权方式分别汇总为 `MarketData/sources/ifind/market_data_hfq|qfq|none.csv`，再分别转为同名 Parquet。

## 交易日历

全 A 只维护一份统一日历 `calendar/calendar_all_a.csv`。全量回填和日增量都只请求深交所市场代码 `212100`，随后沪深北的全 A 行情下载均使用这份日历；旧的 SH、SZ、BJ CSV 不再更新或读取。

```powershell
cd MarketData/DataIngestion

# 指定历史区间回填
python -m data_ingestion.ifind.calendar.pipeline backfill `
  --start 1990-12-01 --end 2026-08-04

# 每日补充：默认按 iFinD 日数据就绪时间选择截止日
python -m data_ingestion.ifind.calendar.pipeline update

# 一次性按现有深交所 CSV 重建统一日历，不请求 iFinD
python -m data_ingestion.ifind.calendar.pipeline build-from-existing-sz

# 将统一交易日历 CSV 转为 Parquet，不调用 iFinD
python -m data_ingestion.ifind.calendar.parquet
```

CSV 与 Parquet 输出分别为 `MarketData/sources/ifind/calendar/calendar_all_a.csv` 和 `MarketData/sources/ifind/calendar/calendar_all_a.parquet`；原始响应保存在 `calendar/raw/ALL_A/<起始日>_<结束日>.json`。

`update` 未指定 `--as-of` 时使用上海时间判断：17:00 前截止到前一自然日，17:00 起才截止到当天。这里的 17:00 对应 A 股收盘后约两小时，避免 iFinD 尚未完成日数据更新时把当天加入交易日历。周末和节假日没有新交易日时会安全退出。

如已人工确认 iFinD 当天数据已经更新，可显式指定截止日：

```powershell
python -m data_ingestion.ifind.calendar.pipeline update --as-of 2026-08-10
```

## 全 A 证券池

全 A 证券主表使用 iFinD“板块成份”数据池 `p03291` 的三张当日快照合并得到：在市板块为 `001005010`，已摘牌板块为 `001005334011`，退市整理板块为 `001005334025`。每日只下载这三张列表各一次，不按交易日重复下载历史全 A 成份。

```json
{
  "reportname": "p03291",
  "functionpara": {
    "date": "YYYYMMDD",
    "blockname": "001005010、001005334011 或 001005334025",
    "iv_type": "allcontract"
  },
  "outputpara": "p03291_f002,p03291_f003"
}
```

其中超级命令里的“合约类型”对应 HTTP 字段 `iv_type`。鉴权仍只从 `IFIND_REFRESH_TOKEN` 环境变量读取，token 不写入命令文本、代码、原始 JSON 以外的任何产物。

```powershell
# 首次建立或每日更新：目标日只请求在市、已摘牌与退市整理三张快照
python -m data_ingestion.ifind.universe.pipeline update --as-of 2026-08-10

# 从已缓存的三类 raw 重建扁平历史全 A 证券主表，不调用 iFinD
python -m data_ingestion.ifind.universe.pipeline rebuild

# 只合并目标日已有 raw，不调用 iFinD
python -m data_ingestion.ifind.universe.pipeline update-csv --as-of 2026-08-10

# 将全 A 证券主表转为 Parquet，不调用 iFinD
python -m data_ingestion.ifind.universe.parquet
```

输出包括：

- `universe/raw/LISTED/<日期>.json`：当日在市列表原始响应；
- `universe/raw/DELISTED/<日期>.json`：当日已摘牌列表原始响应；
- `universe/raw/DELISTING/<日期>.json`：当日退市整理列表原始响应；
- `universe/a_share.csv`：只保留超级命令实际返回的 `thscode`（`p03291_f002`）和 `name`（`p03291_f003`）两列；
- `universe/a_share.parquet`：同一两列证券主表的 Parquet 版本。

读取时若新文件不存在，会兼容回退到旧版 `a_share_5537.csv`；新生成结果统一写入 `a_share.csv`。

在市与已摘牌快照必须非空；退市整理可能没有证券，iFinD 返回 `-4001 / no data` 时按空快照缓存并继续。三张同日快照的 `thscode` 必须互斥；只要任意两类存在交集就报错并拒绝写入 CSV，不能用状态优先级掩盖数据异常。通过校验后直接联合三张列表，重复运行同一日期会得到相同结果。该表只表达“曾经属于全 A 的证券代码和名称”集合，不包含交易所、上市日期、板块或上市状态等未请求字段；下游按 `thscode` 后缀派生 `SH`、`SZ`、`BJ`。这里假定已摘牌与退市整理板块返回截至目标日的累计列表，因而最新一组三类快照即可覆盖历史证券。

## 全 A 日频行情

日频行情固定分为三个脚本：下载脚本只写原始 JSON；CSV 脚本只读取 JSON 并生成完整 CSV；Parquet 脚本只读取完整 CSV。价格支持 `hfq`（后复权，`CPS: "1"`）、`qfq`（前复权，`CPS: "2"`）和 `none`（不带 CPS）；三种价格 raw 与最终文件分别保存。成交指标使用 `volume,amt,turn` 且不带复权参数，三种价格共用同一份 liquidity raw。下载任务按交易所、证券批次和交易日窗口分区，以便断点续传；默认每个请求为 100 只证券 × 10 个交易日。

```powershell
# 指定历史区间的全量回填；跳过已完成 CSV，重放已有 JSON
python -m data_ingestion.ifind.market_data.download backfill `
  --start 2026-08-05 --end 2026-08-10 --adjustment hfq

# 首次回填或修复：全部 JSON 汇总为完整 CSV，不调用 iFinD
python -m data_ingestion.ifind.market_data.csv rebuild --adjustment hfq

# 收盘后日增量：仅解析当日 JSON，并替换完整 CSV 中同日记录
python -m data_ingestion.ifind.market_data.csv update --as-of 2026-08-05

# 完整 CSV 转 Parquet，不调用 iFinD
python -m data_ingestion.ifind.market_data.parquet --adjustment hfq

# 收盘后执行，仅处理目标日期
python -m data_ingestion.ifind.market_data.download update --as-of 2026-08-05 --adjustment hfq
```

价格原始 JSON 分别保存在 `prices/hfq/raw/`、`prices/qfq/raw/` 与 `prices/none/raw/`；成交指标原始 JSON 保存在共享的 `liquidity/raw/`。最终文件分别为 `market_data_hfq|qfq|none.csv` 与同名 Parquet：一行一个交易日，列为两级索引（第一级为 `thscode`，第二级为 OHLC、`volume`（股）、`amount`（元）、`turnover`（小数））。

## 全 A 日期序列：估值、行业与状态

日期序列同样分为下载 JSON、JSON 汇总 CSV、CSV 转 Parquet 三个脚本。下载流通市值、PE、PB、申万行业名称与代码、涨跌停状态；`Fill` 固定为 `Blank`，即缺失不以前值填充。基础数据周额度为 500 万点，默认每次运行最多计划 450 万估算点；一个请求默认 100 只证券 × 10 个交易日 × 6 字段。

```powershell
python -m data_ingestion.ifind.date_sequence.download backfill `
  --start 2026-01-01 --end 2026-08-04

# 首次回填或修复：全部 JSON 汇总为完整 CSV，不调用 iFinD
python -m data_ingestion.ifind.date_sequence.csv rebuild

# 收盘后日增量：仅解析当日 JSON，并替换完整 CSV 中同日记录
python -m data_ingestion.ifind.date_sequence.csv update --as-of 2026-08-05
python -m data_ingestion.ifind.date_sequence.parquet

python -m data_ingestion.ifind.date_sequence.download update --as-of 2026-08-05
```

原始 JSON 在 `MarketData/sources/ifind/date_sequence/raw/`；完整文件为 `MarketData/sources/ifind/date_sequence.csv` 与 `date_sequence.parquet`：一行一个交易日，列为两级索引（第一级为 `thscode`，第二级为日期序列字段）。涨跌停状态保留 iFinD 原值。

## 指数成分股权重

指数权重使用数据池 `p03563`。超级命令只请求 `p03563_f002`（同花顺证券代码）和 `p03563_f004`（最新权重），业务输入只有 `date` 与 `index_name`。下载时每个“指数代码 × 交易日”保存一份原始 JSON，方便检查某次指数调样或权重异常；CSV 和 Parquet 均为“日期 × 股票”宽表：首列/索引是请求日期，列名是股票代码，单元格保留 iFinD 返回的百分比权重原值。历史四字段原始 JSON 仍可重放转换。

```powershell
# 回填沪深 300（默认指数代码为 000300.SH）
python -m data_ingestion.ifind.index_weights.download backfill `
  --start 2026-01-01 --end 2026-08-07

# 下载其他指数，例如中证 500
python -m data_ingestion.ifind.index_weights.download backfill `
  --index 000905.SH --start 2026-01-01 --end 2026-08-07

# 只下载并写入收盘后的当日原始 JSON
python -m data_ingestion.ifind.index_weights.download update `
  --index 000300.SH --as-of 2026-08-07

# 原始 JSON 汇总为完整宽表 CSV；当日更新只替换该日期行
python -m data_ingestion.ifind.index_weights.csv rebuild --index 000300.SH
python -m data_ingestion.ifind.index_weights.csv update --index 000300.SH --as-of 2026-08-07

# CSV 转 Parquet，不调用 iFinD
python -m data_ingestion.ifind.index_weights.parquet --index 000300.SH
```

原始 JSON 路径为 `index_weights/raw/<指数代码>/<日期>.json`；完整文件为 `index_weights/<指数代码>.csv` 与同名 Parquet。
