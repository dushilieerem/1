# DataIngestion

使用 iFinD HTTP 管道及共享发布组件，将市场数据采集、标准化并发布为 SVQuant 标准字段 Parquet。此工具只负责采集、标准化和发布；`ResearchEngine` 仅读取 `MarketData/current/` 中的已发布数据，不在回测请求中调用外部数据源。

## 目录约定

```text
MarketData/
├── DataIngestion/            # 采集工具（纳入 Git）
│   └── data_ingestion/       # 按数据源组织的采集、校验与发布代码
│       ├── ifind/            # iFinD HTTP 数据管道（按公共层和数据域分包）
│       └── shared/           # 跨数据源复用的标准面板质量检查与发布组件
├── current/                  # 当前运行时数据版本（不纳入 Git）
│   ├── panels/               # 一个字段一个 日期 × 标的 Parquet
│   ├── benchmark/            # 指数与成分数据
│   └── metadata/             # stock_info 等非面板数据
├── sources/akshare/          # AkShare / Baostock 原始历史库，待校验数据
└── releases/                 # 后续不可变历史发布版本（不纳入 Git）
```

`FieldParquetProvider("MarketData")` 会自动解析 `current/panels` 与 `current/benchmark`，因此 API 的 `SVQUANT_DATA_DIR` 可继续指向 `MarketData`。

历史版采集入口已移除，不再作为采集或发布入口。免费基本面与证券状态补齐按 [FEAT-025](../../docs/04-features/FEAT-025-free-basic-status-mvp/) 规划实现。

## iFinD HTTP 数据采集

iFinD 的交易日历、全 A 证券池、后复权 OHLC 全量回填和收盘后日增量说明已独立维护在 [data_ingestion/ifind/README.md](data_ingestion/ifind/README.md)。

## 当前标准面板质量检查

共享质量检查只读取候选或当前发布目录，确认字段面板日历一致、证券代码格式正确，并检查发布清单是否存在；不会调用外部数据源，也不会修改 `current/` 之外的既有版本：

```powershell
cd MarketData/DataIngestion
python -m data_ingestion.shared.panel_quality `
  --report ../current/metadata/quality_reports/current_panels.json
```

数据源接入、字段映射和候选发布应按对应 Feature 的数据契约执行。
