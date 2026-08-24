# iFinD 全 A 股交易日历下载说明

> 状态：已确认协议，待凭据与下载任务接入。
> 关联：FEAT-010、`03-technical-design.md`、`06-data-catalog.md`。

## 目标

为固定全 A 股证券池（上交所、深交所、北交所）建立可追溯的交易日历，用于日线行情下载窗口切分、断点续传、数据质量校验和最终 Parquet 面板日期轴构建。

## 按交易所下载

交易日历必须按交易所独立获取和保存，不假定三地日历恒等。

| 交易所 | 代码后缀 | iFinD `marketcode` | 下载起始日 | 依据 |
|---|---|---:|---|---|
| 深圳证券交易所 | `SZ` | `212100` | `1990-12-01` | 深交所于该日开始营业。 |
| 上海证券交易所 | `SH` | `212001` | `1990-12-19` | 上交所于该日正式开业。 |
| 北京证券交易所 | `BJ` | `212300` | `2021-11-15` | 北交所于该日开市。 |

全 A 股统一日期轴的最早起点为 `1990-12-01`。交易所级任务仍从各自起始日开始；接口返回的首个有效交易日是最终事实来源。

来源： [上海证券交易所介绍](https://www.sse.com.cn/aboutus/overview/)、[深圳证券交易所介绍](https://www.szse.cn/aboutus/sse/introduction/index.html)、[北交所开市公告](https://www.gov.cn/xinwen/2021-11/12/content_5650529.htm)。

## iFinD 请求协议

使用 `POST https://quantapi.51ifind.com/api/v1/get_trade_dates`，请求体结构如下：

```json
{
  "marketcode": "212001",
  "functionpara": {
    "mode": "1",
    "dateType": "0",
    "period": "D",
    "dateFormat": "0"
  },
  "startdate": "1990-12-19",
  "enddate": "YYYY-MM-DD"
}
```

参数含义：

- `mode: "1"`：查询日期区间内的日期序列。
- `dateType: "0"`：仅交易日。
- `period: "D"`：日频。
- `dateFormat: "0"`：返回 `YYYY-MM-DD`。

鉴权使用运行环境中的 `IFIND_REFRESH_TOKEN` 换取 access token；凭据不得写入本文档、命令文件、CSV 或 Git。

## 保存与质量规则

先将接口结果保存为可人工查看的 CSV，再经检查转换为 Parquet：

```text
MarketData/sources/ifind/calendar/
├── SH.csv
├── SZ.csv
└── BJ.csv

MarketData/releases/<data_version>/calendar/
├── SH.parquet
├── SZ.parquet
└── BJ.parquet
```

CSV 最少包含 `date`、`exchange`、`is_trade_day`、`source`、`source_version` 和 `downloaded_at`。每份文件另在采集 checkpoint / manifest 中记录请求区间、请求参数、响应 `dataVol` 与内容哈希。

发布前必须验证：

- 每份日历日期唯一且严格递增；
- 日期均不早于对应交易所起始日；
- 三地日历差异被显式记录，而非静默忽略；
- 日线下载任务按证券代码后缀选择相应日历；
- 全 A 股统一日期轴为三份交易日历的并集，单一证券面板在其所属市场非交易日保留缺失，不填充价格。

