# akshare_bars · 日历 / 指数 / A股日线

独立采集包，不依赖 SVQuant 运行时。用 **akshare** 拉：

1. 交易日历
2. 全 A 列表（在市）
3. 核心指数日 K
4. A 股**后复权**日线（增量；无文件则从 2010 起拉）

数据写在本目录 `data/a_share/`，日志在 `logs/`。

---

## 环境

```powershell
conda create -n bars-only python=3.11 -y
conda activate bars-only
cd <本目录>
pip install -r requirements.txt
```

（已有带 `akshare`、`pandas` 的环境也可直接用。）

---

## 怎么跑

```powershell
cd <本目录>

# 建议先小批量试跑（前 5 只在市股票）
python run.py --max-symbols 5 --bar-workers 1

# 全市场（较慢，建议 workers=1）
python run.py --bar-workers 1

# 只更日历 + 指数
python run.py --skip-bars
```

常用参数：

| 参数 | 说明 |
|------|------|
| `--max-symbols N` | 只拉前 N 只（调试） |
| `--bar-workers 1` | 并行进程数，内存紧用 1 |
| `--end-date 2026-07-23` | 指定截止日；默认自动（未收盘用上一交易日） |
| `--data-dir D:\mydata\a_share` | 自定义落盘目录 |

---

## 产出目录

```text
data/a_share/
  01_meta/trading_calendar.csv
  01_meta/stock_basic.csv
  04_index/daily/*.csv
  03_market/daily/bars_hfq/{symbol}.csv
logs/bars_only_*.log
logs/bars_only_*.json
```

---

## 给同事

把整个 `akshare_bars` 文件夹拷过去即可（不必带已有 `data/`，对方会重新拉）。
需能访问外网（东财/新浪）。单票失败会跳过，不中断整次任务。
