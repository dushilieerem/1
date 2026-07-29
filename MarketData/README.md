# MarketData 数据目录

`MarketData/` 存放运行期数据和数据采集工具，行情文件不提交到仓库；只有本说明与 `DataIngestion/` 下的采集代码纳入版本管理。

```text
MarketData/
├── current/                         # 当前已发布的标准数据版本，供 API / 回测只读
│   ├── panels/                       # 标准字段宽表 Parquet（日期 × 证券）
│   ├── benchmark/                    # 指数与成分数据
│   └── metadata/                     # 证券信息和数据说明
├── sources/                          # 未发布的来源原始数据；不得被读取层直接使用
│   └── akshare/                      # AkShare / Baostock 历史原始库
└── DataIngestion/                    # 数据采集与发布工具（纳入 Git）
    ├── akshare_bars/                 # AkShare 日线增量采集脚本及其本地 data/、logs/
    └── data_ingestion/               # Wind 历史数据下载和标准化发布代码
```

当前发布版本为 `akshare-full-hfq-v1`，覆盖至 `2026-07-23`；此前第三方版本保留在 `releases/third-party-current-legacy-2026-07-24/`，不再由默认读取入口加载。

## 使用边界

- `current/` 是唯一的默认读取入口。`FieldParquetProvider("MarketData")` 会自动解析它。
- `sources/` 仅保存原始或待校验数据。数据必须通过字段映射、质量校验和版本清单后，才能发布到 `current/` 或未来的 `releases/<data_version>/`。
- `DataIngestion/akshare_bars/data/`、`DataIngestion/akshare_bars/logs/` 是 AkShare 脚本运行产物，不提交到仓库。
- 同一字段不可将多个来源按缺失值静默拼接；来源切换或补源必须生成新的数据版本，并记录口径和质量差异。

数据契约与发布要求见 `docs/04-features/FEAT-010-research-data-foundation/`，多源整合规则见 `docs/06-decisions/ADR-010-为什么采用统一数据引擎和多数据源适配.md`。
