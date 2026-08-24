# Technical Design：`current` 多字段 Parquet 宽表规格

## 1. 统一物理结构

股票日频宽表使用 Pandas/PyArrow 两级列：第一级为证券代码，第二级为逻辑字段。

```text
symbol        000001.SZ                         000002.SZ
field         open  high  close  volume         open  high  close  volume
datetime
2026-08-07    ...   ...   ...    ...            ...   ...   ...    ...
2026-08-08    ...   ...   ...    ...            ...   ...   ...    ...
```

| 项目 | 规范 |
|---|---|
| 行 | 交易日 |
| 日期索引 | `datetime`，唯一、升序 |
| 第一级列 | iFinD 完整证券代码，如 `000001.SZ` |
| 第二级列 | 本业务宽表允许的逻辑字段 |
| 缺失 | 原样保存，不在存储阶段处理 |
| 格式 | PyArrow Parquet + ZSTD |
| 修改方式 | 发布后只读；更新生成新文件和新 release |

`DataEngine` 对外仍返回 `{field: DataFrame[日期 × 证券]}`。物理文件的多字段组织不泄漏到因子和回测代码。

## 2. 目录与文件职责

```text
MarketData/<release>/
├── panels/
│   ├── market_data.parquet
│   ├── daily_basic.parquet
│   └── security_status.parquet
├── display/
│   └── unadjusted_price.parquet
├── benchmark/
│   ├── index_price_000300.SH.parquet
│   └── index_weights_000300.SH.parquet
├── universe/
│   └── a_share.parquet
├── calendar/
│   └── trading_calendar.parquet
├── metadata/
│   └── security_master.parquet
├── data_manifest.yaml
└── quality_report.json
```

`MarketData/current` 是活动 release 的只读视图。任何采集、合并和转换任务都必须在候选版本中完成，禁止直接修改活动文件。

## 3. `panels/market_data.parquet`

代表股票日频后复权行情和流动性。允许字段固定为：

| 逻辑字段 | 代表什么 | iFinD 原字段 |
|---|---|---|
| `open` | 当日后复权开盘价 | `open` |
| `high` | 当日后复权最高价 | `high` |
| `low` | 当日后复权最低价 | `low` |
| `close` | 当日后复权收盘价 | `close` |
| `volume` | 当日成交量 | `volume` |
| `amount` | 当日成交额 | `amt` |
| `turnover` | 当日换手率 | `turn` |

验证期保存 iFinD 返回值，不在存储阶段对 `turn` 等字段做单位换算。

## 4. `panels/daily_basic.parquet`

代表股票日频市值、股本和估值。允许字段为：

| 逻辑字段 | 代表什么 | 当前来源 |
|---|---|---|
| `total_mv` | 当日总市值 | AkShare，后续 iFinD 替换 |
| `float_mv` | 当日流通市值 | AkShare + iFinD `ths_current_mv_stock` |
| `total_shares` | 当日总股本 | AkShare，后续 iFinD 替换 |
| `float_shares` | 当日流通股本 | AkShare，后续 iFinD 替换 |
| `pe` | 当日 iFinD PE 字段 | iFinD `ths_pe_stock` |
| `pe_ttm` | 现有 PE TTM 字段 | AkShare，确认后再决定是否替换 |
| `pb` | 当日 PB 字段 | AkShare + iFinD `ths_pb_stock` |
| `ps_ttm` | 现有 PS TTM 字段 | AkShare，后续 iFinD 替换 |

`pe` 与 `pe_ttm` 是两个独立逻辑字段，不因存放在同一文件而视为同一口径。

## 5. `panels/security_status.parquet`

代表会影响证券池、交易可行性和研究分组的日频状态。允许字段为：

| 逻辑字段 | 代表什么 | 来源/生成方式 |
|---|---|---|
| `industry_sw` | 当日申万行业名称 | iFinD `ths_the_sw_industry_stock` |
| `industry_sw_code` | 当日申万行业代码 | iFinD `ths_the_sw_industry_code_stock` |
| `limit_status` | iFinD 返回的涨停、跌停、停牌等原始状态 | iFinD `ths_up_and_down_status_stock` |
| `is_st` | 当日是否处于 ST 或 *ST 状态 | 现有数据，后续 iFinD 替换 |
| `is_suspended` | 当日是否停牌 | 优先使用 iFinD 独立停牌字段；当前可由 `limit_status` 中的停牌状态生成 |

`is_suspended` 必须作为独立布尔逻辑字段暴露，回测不需要解析 `limit_status` 文本。原始 `limit_status` 仍保留，供研究员直接使用或复核。

## 6. `display/unadjusted_price.parquet`

代表 WebApp K 线使用的股票未复权价格，与研究用后复权行情隔离。

| 逻辑字段 | 代表什么 | iFinD 原字段 |
|---|---|---|
| `open` | 未复权开盘价 | `open` |
| `high` | 未复权最高价 | `high` |
| `low` | 未复权最低价 | `low` |
| `close` | 未复权收盘价 | `close` |

## 7. 指数、日历和证券主表

### `benchmark/index_price_<index>.parquet`

单指数普通表，列为 `datetime/open/high/low/close`。

### `benchmark/index_weights_<index>.parquet`

日期 × 证券宽表。第一列为 `datetime`，其余列为证券代码，单元格为当日 iFinD 权重；权重非空且大于零即表示当日属于该指数。因此该文件同时承担指数权重和历史成分职责，不再生成独立 constituents 表。

回测解析规则如下：

1. 先从已按起止区间过滤的股票行情中确定首个实际交易日 `T0`。
2. 在权重表中取 `datetime <= T0` 的最近一期快照，禁止向后读取未来快照。
3. 将该行中权重非空且大于零的证券解析为列表。
4. 整个回测区间固定使用该列表；权重表在 `T0` 之后的调入调出不改变本次股票池。

市场数据浏览接口仍可读取最新一期权重，用于展示“当前成分”；这与回测的点时固定股票池是两个独立语义。

### `universe/a_share.parquet`

静态全 A 股票池列表，至少包含 `thscode/name`。它只表达当前可选证券集合，不代表价格或权重，不放入 `benchmark` 或日频面板。

### `calendar/trading_calendar.parquet`

列为 `datetime/SH/SZ/BJ`，三个交易所列表示当日是否交易。

### `metadata/security_master.parquet`

至少包含 `code/thscode/name/source`。上市日期、退市日期、板块等证券级属性以后直接追加到此表，不放入日频宽表。

## 8. 渐进替换与不可变发布

每次更新生成一个新的完整 release：

```text
读取上一 release
→ 对选定逻辑字段应用 iFinD 候选数据
→ 生成新的业务域宽表
→ 校验 schema、日期、证券和抽样值
→ 写 manifest 和文件哈希
→ 加载为新只读内存快照
→ 验证后切换 current/服务流量
```

不得修改上一 release 的 Parquet，也不得在运行中的内存快照上追加数据。

## 9. Manifest 最小契约

manifest 以文件为资产、以字段记录来源：

```yaml
- asset: market_data
  path: panels/market_data.parquet
  fields:
    close:
      sources: [akshare, ifind]
      ifind_field: close
      merge_rule: ifind_non_null_overrides_akshare
    turnover:
      sources: [ifind]
      ifind_field: turn
  date_range: ["1990-12-19", "2026-08-11"]
  symbol_count: 5912
  sha256: "..."
```

## 10. 读取层和内存快照

- 持久化读取器扫描 `market_data`、`daily_basic` 和 `security_status` 的两级列，建立 `field → 文件及物理列` 映射。
- 请求单字段时，PyArrow 只读取对应证券 × 字段列，不加载同文件其他字段的数值数据。
- 服务器启动加载全部研究字段后，拆成 `field → ndarray[date, symbol]` 的只读内存结构。
- 磁盘按业务域分组，内存按字段分组；两者服务不同目标，不要求物理结构相同。

### 10.1 当前验证版的实际加载时点

- 因子回测和策略回测在每次任务开始时创建 Provider、扫描当前数据规格，字段在本次任务第一次访问时按需读取并缓存；新任务会重新解析 `current`。
- `/api/market-data/` 在进程内首次访问时创建并缓存读取器。日线与股票列表读取 `display/unadjusted_price.parquet`；指数行情和成分读取 `benchmark/` 与 `universe/`。
- 替换已被 `/api/market-data/` 读取过的 Parquet 后，当前进程不会主动失效缓存，必须重启 API 服务。正式只读内存快照上线后，所有 release 切换也统一通过加载新实例并切流完成。
- 当前内置指数标识仅包含 `CSI300` 和 `CSI500`。仅放入中证 800 文件不会自动注册 `CSI800`；还需增加指数代码/名称映射及 API 请求契约，之后才可使用。
