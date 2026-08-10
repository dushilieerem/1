# DataIngestion

使用 WindPy 将**历史**市场数据批量下载并发布为 SVQuant 标准字段 Parquet。此工具只负责采集、标准化和发布；`ResearchEngine` 仅读取 `MarketData/current/` 中的已发布数据，不在回测请求中调用 Wind。

## 目录约定

```text
MarketData/
├── DataIngestion/            # 采集工具（纳入 Git）
│   ├── akshare_bars/         # AkShare 日线增量采集脚本；data/、logs/ 为运行产物
│   └── data_ingestion/       # 按数据源组织的采集、校验与发布代码
│       ├── akshare/          # AkShare 原始日线校验、候选版本与运行时资产发布
│       ├── ifind/            # iFinD HTTP 数据管道（按公共层和数据域分包）
│       ├── wind/             # Wind 历史日频下载
│       └── shared/           # 跨数据源复用的标准面板质量检查
├── current/                  # 当前运行时数据版本（不纳入 Git）
│   ├── panels/               # 一个字段一个 日期 × 标的 Parquet
│   ├── benchmark/            # 指数与成分数据
│   └── metadata/             # stock_info 等非面板数据
├── sources/akshare/          # AkShare / Baostock 原始历史库，待校验数据
└── releases/                 # 后续不可变历史发布版本（不纳入 Git）
```

`FieldParquetProvider("MarketData")` 会自动解析 `current/panels` 与 `current/benchmark`，因此 API 的 `SVQUANT_DATA_DIR` 可继续指向 `MarketData`。

## iFinD HTTP 数据采集

iFinD 的交易日历、全 A 证券池、后复权 OHLC 全量回填和收盘后日增量说明已独立维护在 [data_ingestion/ifind/README.md](data_ingestion/ifind/README.md)。

## Wind 日频下载

在配置 WindPy 的环境中执行：

```powershell
cd MarketData/DataIngestion
python -m data_ingestion.wind.daily `
  --symbols-file symbols.txt `
  --start 2020-01-01 --end 2024-12-31 `
  --output ../current/panels
```

`symbols.txt` 每行一个 Wind 代码（如 `000001.SZ`）。工具按“单个 Wind 字段 × 一批证券”下载，避免 Wind `wsd` 不支持多证券、多字段组合的问题；已存在输出文件默认拒绝覆盖，只有传入 `--overwrite` 才会替换。

首期支持：OHLC、成交量额、换手率、市值、股本、PE/PB/PS 与复权因子。财务三表、证券状态、公告日点时转换和基准构建仍按 FEAT-010 后续任务实现。

## AkShare 日线增量采集

`akshare_bars/` 是独立的日线更新脚本，负责交易日历、在市股票、核心指数和 A 股后复权日线。脚本默认将运行数据写入自身的 `data/a_share/`，不能直接写入 `current/`；将其发布为标准 Parquet 前，必须完成复权口径、证券范围和质量校验。

```powershell
cd MarketData/DataIngestion/akshare_bars
python run.py --bar-workers 1
```

完整参数与产出结构见 `akshare_bars/README.md`。

### 发布前质量检查

AkShare 原始日线在转换为标准面板前运行以下检查。报告仅写到原始数据目录，不会修改 `current/`：

```powershell
cd MarketData/DataIngestion
python -m data_ingestion.akshare.quality `
  --as-of 2026-07-23 `
  --report ../sources/akshare/01_meta/quality_reports/daily_bars_20260723.json
```

检查项包括必填字段、可选 `volume` / `turn` 字段、日期重复与乱序，以及相对基准日的停更天数。发现问题的数据不可直接发布。

### 当前标准面板质量检查

对 `current/panels` 运行相同的发布前检查，确认字段面板日历一致、证券代码格式正确，并检查发布清单是否存在：

```powershell
cd MarketData/DataIngestion
python -m data_ingestion.shared.panel_quality `
  --report ../current/metadata/quality_reports/current_panels.json
```

### AkShare 候选发布

AkShare 是当前主历史来源。先将通过质量门禁的证券范围生成 `releases/<version>/` 候选版本；该命令不会覆盖 `current/`：

```powershell
cd MarketData/DataIngestion
python -m data_ingestion.akshare.publish `
  --symbols-file symbols.txt `
  --start 2025-01-01 --end 2025-12-31 `
  --data-version akshare-2025-sample-v1 `
  --output ../releases/akshare-2025-sample-v1
```

全量候选发布使用 `--all-symbols` 代替 `--symbols-file`；建议在后台运行，并只在候选目录完整生成清单和质量报告后再评审。

候选版本生成后，可追加 `valuation/wide` 中已验证的总/流通市值、总/流通股本及 PE/PB/PS；这些字段按既有 OHLC 交易日历对齐，早期或缺失记录保留为 `NaN`：

```powershell
python -m data_ingestion.akshare.publish `
  --all-symbols --append-valuations `
  --start 1990-01-01 --end 2026-07-23 `
  --data-version akshare-full-hfq-v1 `
  --output ../releases/akshare-full-hfq-v1
```

### 运行时基准与元数据

候选版本已具备面板字段后，可从 AkShare 原始库补齐 API 读取所需的四个核心指数、历史成分矩阵及证券主数据：

```powershell
python -m data_ingestion.akshare.runtime_assets `
  --source-root ../sources/akshare `
  --release ../releases/akshare-full-hfq-v1
```

候选版本只包含 AkShare 原始库中可直接映射的 OHLC、成交量额和换手率，并在清单中固定标记为 `hfq`。单证券停更或缺少 `volume` / `turn` 时，对应字段保留为 `NaN`，禁止填零、前值填充或改用其他来源。`adj_factor`、财务、证券状态等未就绪字段不写入候选版本，不能据此切换 `current/`。
