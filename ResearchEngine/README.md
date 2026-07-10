# ResearchEngine

一站式 AI 量化投研平台 YGQuant 的**投资研究层**，是用户入口。依据 `docs/` 下的类设计与流程图实现。

> 研究员工作流：在 `factor/` 下写因子库 -> 修改 `examples/main.py` 调用 -> 运行 ->
> 系统读数据、算因子值、算年化收益/最大回撤/calmar/胜率/IC 等指标。

## 架构

```
ResearchEngine（用户入口）
├── ExperimentManager   # 核心：组织实验流程（只编排，不计算）
├── Experiment          # 核心对象：一次实验
├── FactorLoader        # 动态加载因子（importlib，支持 FactorLibrary + BaseFactor）
├── ConfigManager       # 统一配置读取（YAML/JSON）
└── ResultManager       # 保存结果（不计算），支持 CSV/SQLite/ClickHouse
        │
        ▼ 调用
   QuantCore（底层引擎）
```

## 模块结构

```
researchengine/
├── experiment.py        # Experiment.run() 编排五步流程
├── manager.py           # ExperimentManager
├── factor_loader.py     # FactorLoader（动态加载）
├── config.py            # ConfigManager
├── portfolio.py         # 因子->组合净值（研究编排辅助）
└── result/
    ├── manager.py      # ResultManager
    └── storage/        # ResultStorage + CSV/SQLite/ClickHouse

factor/                  # 研究员写入的因子库
├── alpha_library.py    # Alpha101 + Alpha158 方法因子（FactorLibrary 风格）
examples/
├── main.py             # 端到端入口
└── gen_data.py         # 生成宽表样本数据
config.yaml             # 实验配置
```

## 安装

在仓库根目录执行：

```bash
pip install -e .
```

## 快速开始

数据为 Wind/Choice 风格**宽表面板**（3 行表头/GBK/OHLCV+市值）。真实数据放根目录
`data/price.CSV`（`main.py` 默认读它）；无真实数据时可生成样本：

```bash
# （可选）生成宽表样本数据到 ResearchEngine/data/price.CSV
python ResearchEngine/examples/gen_data.py

# 运行端到端示例（默认读根目录 data/price.CSV）
python ResearchEngine/examples/main.py
```

> `main.py` 默认指向根目录 `data/price.CSV`。若用生成的样本，把
> `config.yaml` 的 `data_dir` 改为 `./data/price.CSV`（相对 ResearchEngine）。

`main.py` 流程：

1. `ConfigManager.load("config.yaml")` 读取配置
2. `FactorLoader.load("alpha_library")` 动态加载因子库（注册 alpha101、alpha158 等）
3. `loader.factors["alpha101"]` 挑一个因子
4. `ExperimentManager.create(...)` 创建实验
5. `experiment.run()`：
   - 调用 QuantCore：`DataEngine.get_bars` -> `FactorEngine.compute` -> `MetricEngine.calculate`
   - 由因子值构组合净值，计算年化收益/Sharpe/Sortino/Calmar/最大回撤/波动率/IC/RankIC/胜率/换手
6. `ResultManager.save()` 保存结果到 `output/`

## 写因子（FactorLibrary 风格）

你只需要写一个库类，每个公开方法就是一个因子：

```python
from quantcore import FactorLibrary

class MyLib(FactorLibrary):
    author = "你"

    def myalpha(self, window=5):
        # self.close 就是 日期×标的 收盘价宽表，直接向量化
        return self.close - self.close.rolling(window).mean()
```

然后在 main.py 里：

```python
loader = FactorLoader(factor_dir=".../factor")
loader.load("my_lib")
factor = loader.factors["myalpha"]   # 方法名即因子名
experiment = Experiment(factor=factor, ...)
result = experiment.run()
```

也兼容传统 `BaseFactor` 子类写法（一个文件一个类 + `compute` 方法）。

## 配置项（`config.yaml`）

| 项 | 说明 |
|----|------|
| `data_dir` | 数据路径；指向**文件**用 WideCSVProvider（宽表），指向**目录**用 CSVDataProvider（逐只） |
| `benchmark` | 股票池名称（对应 universe.csv 的 pool；无 universe.csv 时用全部标的） |
| `rebalance` | 调仓频率 daily/weekly/monthly |
| `n_groups` | 分位数 |
| `long_short` | 是否多空对冲 |
| `ic_horizon` | IC 远期收益天数 |
| `commission` / `slippage` | 交易成本（供 BacktestEngine） |
| `storage` | 结果存储 csv/sqlite/clickhouse |
| `output_path` | 结果输出目录 |

## 文档

- `docs/04-类设计.md` - 各模块类设计（实现依据）
- `docs/05-运行流程图.md` - 运行流程（实现依据）

## 测试

```bash
pytest ResearchEngine/tests
```
