# DataIngestion

使用 WindPy 将**历史**市场数据批量下载并发布为 SVQuant 标准字段 Parquet。此工具只负责采集、标准化和发布；`ResearchEngine` 仅读取 `MarketData/current/` 中的已发布数据，不在回测请求中调用 Wind。

## 目录约定

```text
MarketData/
├── DataIngestion/            # 本工具（纳入 Git）
├── current/                  # 当前运行时数据版本（不纳入 Git）
│   ├── panels/               # 一个字段一个 日期 × 标的 Parquet
│   ├── benchmark/            # 指数与成分数据
│   └── metadata/             # stock_info 等非面板数据
└── releases/                 # 后续不可变历史发布版本（不纳入 Git）
```

`FieldParquetProvider("MarketData")` 会自动解析 `current/panels` 与 `current/benchmark`，因此 API 的 `SVQUANT_DATA_DIR` 可继续指向 `MarketData`。

## Wind 日频下载

在配置 WindPy 的环境中执行：

```powershell
cd MarketData/DataIngestion
python -m data_ingestion.wind_daily `
  --symbols-file symbols.txt `
  --start 2020-01-01 --end 2024-12-31 `
  --output ../current/panels
```

`symbols.txt` 每行一个 Wind 代码（如 `000001.SZ`）。工具按“单个 Wind 字段 × 一批证券”下载，避免 Wind `wsd` 不支持多证券、多字段组合的问题；已存在输出文件默认拒绝覆盖，只有传入 `--overwrite` 才会替换。

首期支持：OHLC、成交量额、换手率、市值、股本、PE/PB/PS 与复权因子。财务三表、证券状态、公告日点时转换和基准构建仍按 FEAT-010 后续任务实现。
