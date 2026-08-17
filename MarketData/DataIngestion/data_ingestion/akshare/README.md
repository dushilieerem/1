# AkShare 日频基本面历史回填

本目录提供基于 AkShare `stock_value_em` 的全 A 股日频估值与股本历史回填脚本。
数据来自东方财富公开接口，脚本只负责下载、标准化和生成候选 Parquet，不会直接修改
`MarketData/current/`。

当前入口文件为：

```text
update_float_mv.py
```

虽然文件名沿用了早期“流通市值”脚本名称，但当前脚本会完整处理以下十个字段。

## 1. 数据源与字段

脚本逐证券调用：

```python
ak.stock_value_em(symbol="000001")
```

`stock_value_em` 不接收日期参数，会返回该证券可用的估值历史；脚本在本地按
`--start-date` 和 `--end-date` 筛选。字段直接使用东方财富原始字段编码，并统一转成小写，
不使用价格和股本重新计算市值或估值指标。

| 东方财富原始字段 | 输出字段 | 含义 | 单位 |
|---|---|---|---|
| `TOTAL_MARKET_CAP` | `total_market_cap` | 总市值 | 元 |
| `NOTLIMITED_MARKETCAP_A` | `notlimited_marketcap_a` | 流通市值 | 元 |
| `TOTAL_SHARES` | `total_shares` | 总股本 | 股 |
| `FREE_SHARES_A` | `free_shares_a` | 流通股本 | 股 |
| `PE_TTM` | `pe_ttm` | 市盈率（TTM） | 倍 |
| `PE_LAR` | `pe_lar` | 市盈率（静态） | 倍 |
| `PB_MRQ` | `pb_mrq` | 市净率 | 倍 |
| `PEG_CAR` | `peg_car` | PEG | 倍 |
| `PCF_OCF_TTM` | `pcf_ocf_ttm` | 市现率（经营现金流 TTM） | 倍 |
| `PS_TTM` | `ps_ttm` | 市销率（TTM） | 倍 |

字段映射可对照 [AkShare `stock_value_em` 源码](https://raw.githubusercontent.com/akfamily/akshare/main/akshare/stock_feature/stock_value_em.py)
和 [AkShare 股票数据文档](https://akshare.akfamily.xyz/data/stock/stock.html)。

`date` 和 `symbol` 是 SVQuant 面板的结构字段，不参与上述原始字段重命名。

## 2. 前置条件

### 安装依赖

在项目根目录执行：

```powershell
cd D:\project\SVQuant
pip install -e ".[akshare]"
```

脚本还需要 `pandas`、`numpy`、`pyarrow`，这些依赖已经包含在项目运行环境中。

### 准备全 A 证券池

默认读取：

```text
D:\project\SVQuant\MarketData\current\universe\a_share.parquet
```

该 Parquet 必须包含 `thscode` 列，代码格式为完整 iFinD 代码，例如：

```text
000001.SZ
600000.SH
920001.BJ
```

脚本会把完整代码转换成 AkShare 所需的六位代码（例如 `000001.SZ` → `000001`），并拒绝
非法代码或重复的六位代码。

## 3. 基本运行

建议从 `MarketData/DataIngestion` 目录执行模块入口：

```powershell
cd D:\project\SVQuant\MarketData\DataIngestion

python -m data_ingestion.akshare.update_float_mv `
  --start-date 2017-01-03 `
  --end-date 2026-08-14
```

在当前项目环境中，也可以显式使用解释器：

```powershell
D:\Devtools\anaconda3\envs\svquant\python.exe `
  -m data_ingestion.akshare.update_float_mv `
  --start-date 2017-01-03 `
  --end-date 2026-08-14
```

运行过程会逐只股票打印进度。默认每只股票间隔 0.5 秒，失败自动重试 3 次。

## 4. 输出目录与文件

默认输出结构如下：

```text
MarketData/
└── sources/
    └── akshare/
        └── daily_basic/
            ├── by_symbol/
            │   ├── 000001_SZ_20170103_20260814.parquet
            │   ├── 600000_SH_20170103_20260814.parquet
            │   └── ...
            ├── daily_basic_20170103_20260814.parquet
            ├── daily_basic_20170103_20260814.json
            └── checkpoint_20170103_20260814.json
```

### 证券级缓存

`by_symbol/` 中每个文件只保存一只证券，列为：

```text
date, symbol,
total_market_cap, notlimited_marketcap_a,
total_shares, free_shares_a,
pe_ttm, pe_lar, pb_mrq, peg_car, pcf_ocf_ttm, ps_ttm
```

### 候选宽面板

`daily_basic_*.parquet` 的行是日期，列为 `(symbol, field)` 两级列索引，例如：

```text
                       000001.SZ                         600000.SH
field       total_market_cap  pe_ttm  ...  total_market_cap  pe_ttm  ...
date
2017-01-03          ...          ...          ...                ...
```

同目录的 JSON 文件保存来源、字段、单位、日期范围、缓存数量和失败证券清单；检查历史
起点时应优先查看该报告。checkpoint 文件用于记录逐证券进度，便于网络中断后重跑。

## 5. 参数说明

执行 `python -m data_ingestion.akshare.update_float_mv --help` 可查看完整参数。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--start-date` | 必填 | 历史起始日期，格式 `YYYY-MM-DD` |
| `--end-date` | 必填 | 历史结束日期，格式 `YYYY-MM-DD` |
| `--data-root` | 项目下 `MarketData` | 数据根目录；会影响默认证券池、缓存和输出路径 |
| `--universe` | `current/universe/a_share.parquet` | 自定义证券池 Parquet |
| `--cache-dir` | `sources/akshare/daily_basic/by_symbol` | 自定义逐证券缓存目录 |
| `--output` | `sources/akshare/daily_basic/daily_basic_起止日期.parquet` | 自定义候选宽面板路径 |
| `--sleep-seconds` | `0.5` | 证券之间的请求间隔；网络不稳定时可调大 |
| `--retries` | `3` | 单只证券失败后的最大尝试次数 |
| `--retry-delay` | `2.0` | 重试等待秒数，按尝试次数递增 |
| `--chunk-size` | `64` | 合并宽表时一次处理的日期数量 |
| `--force` | 关闭 | 重新抓取兼容缓存，并覆盖已存在的输出文件 |

例如，降低请求频率并使用较小合并块：

```powershell
python -m data_ingestion.akshare.update_float_mv `
  --start-date 2017-01-03 `
  --end-date 2026-08-14 `
  --sleep-seconds 1.0 `
  --chunk-size 32
```

如果目标输出文件已经存在，需要显式使用 `--force`；否则脚本会停止，避免意外覆盖。

## 6. 断点、缓存与内存控制

- 抓取阶段一次只请求一只证券，并立即把标准化结果写入该证券的 Parquet 缓存。
- 合并阶段按 `chunk-size` 分批处理日期，一次只读取一个证券缓存文件。
- 不会加载全部缓存，也不会读取或覆盖 `MarketData/current/panels/daily_basic.parquet`。
- 已存在且包含完整十字段的证券缓存会自动跳过；需要重新拉取时使用 `--force`。
- 中途失败时，checkpoint JSON 会保存已完成位置和失败清单；再次运行会复用成功缓存，只重试缺失证券。

`chunk-size` 越小，合并时峰值内存越低，但写入批次越多；内存不足时优先尝试 `32` 或 `16`。

## 7. 结果检查

先查看 JSON 报告：

```powershell
Get-Content `
  D:\project\SVQuant\MarketData\sources\akshare\daily_basic\daily_basic_20170103_20260814.json
```

至少检查以下内容：

- `source` 是否为 `akshare.stock_value_em`；
- `fields` 是否包含十个小写原始字段；
- `start_date`、`end_date` 是否覆盖目标区间；
- `failed_symbols` 是否为 0；
- `failed` 是否包含网络错误或字段缺失；
- `source_fields` 是否仍对应 `TOTAL_MARKET_CAP`、`PE_TTM` 等东财原始字段。

如需抽样读取，建议使用列投影或单只证券缓存，不要一次性加载所有 Parquet：

```python
from pathlib import Path
import pandas as pd

cache = (
    Path(r"D:\project\SVQuant\MarketData\sources\akshare\daily_basic\by_symbol")
    / "000001_SZ_20170103_20260814.parquet"
)
sample = pd.read_parquet(cache, columns=["date", "symbol", "total_market_cap", "pe_ttm"])
print(sample.head())
```

## 8. 当前限制与注意事项

1. AkShare 当前实现单次 `stock_value_em` 请求最多返回 5000 条记录。较早上市的证券可能无法覆盖完整历史区间，必须以 JSON 报告中的实际日期范围为准。
2. 数据源是东方财富公开接口，网络状态、接口限流、字段返回格式和可用历史长度可能变化；脚本保留失败清单，但不保证外部接口永久稳定。
3. `NaN` 表示源数据缺失或该日指标不可用，不应在采集层填充为 0 或前值。
4. 负 PE、缺失 PEG 或其他估值异常值按源返回保留，不在导入层进行业务判断。
5. 本脚本只生成 `sources/akshare/` 下的候选数据，不负责把候选数据发布到 `current/`，也不负责把旧字段名迁移成新字段名。发布前应先完成字段、日期、证券集合和缺失率校验。

## 9. 常见错误

### `缺少 AkShare`

在项目根目录安装可选依赖：

```powershell
pip install -e ".[akshare]"
```

### `A 股证券池不存在` 或 `缺少 thscode 列`

检查 `--universe` 指向的 Parquet 文件，并确认其中存在 `thscode` 列和完整证券代码。

### `输出文件已存在`

确认是否要覆盖该候选版本；确认后追加 `--force`。`--force` 会重新请求并覆盖逐证券缓存，
不要在未确认日期范围和证券池的情况下使用。

### 失败证券较多

先增加 `--sleep-seconds` 和 `--retry-delay`，再单独重跑失败区间；同时保留 JSON 报告，便于
区分网络错误、源字段变化和空历史返回。

### 历史起点不完整

检查报告中的实际 `start_date`、单只证券缓存的最早日期和 5000 条返回限制。必要时将历史
回填拆成多个日期区间，并分别生成候选文件后再做版本化合并。

## 10. 测试

在项目根目录执行 AkShare 回填模块测试：

```powershell
D:\Devtools\anaconda3\envs\svquant\python.exe `
  -m pytest -q MarketData\DataIngestion\tests\test_akshare_float_mv.py
```

测试使用模拟数据验证字段映射、历史日期筛选、逐证券缓存、分块宽表合并、失败重试和
AkShare 六位代码调用约定，不会访问真实外部接口。
