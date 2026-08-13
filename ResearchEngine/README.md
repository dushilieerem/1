# ResearchEngine

一站式 AI 量化投研平台 SVQuant 的**投资研究层**，是用户入口。依据根目录 `docs/04-features/FEAT-002-research-engine/` 下的类设计与流程图实现。

> 研究员工作流：在根目录 `Factor/libraries/` 下写因子库 -> 修改 `examples/main.py` 调用 -> 运行 ->
> 系统读数据、算因子值、算年化收益/最大回撤/calmar/胜率/IC 等指标。

## 架构

```
SVQuant 界面 / 前端
    │  HTTP（FastAPI）
    ▼
researchengine.api            # HTTP 适配层：/api/health · /api/factor-libraries · /api/factors/{library_name} · /api/backtest
    │  调 SDK
    ▼
ResearchEngine（用户入口）
├── ExperimentManager   # 核心：组织实验流程（只编排，不计算）
├── Experiment          # 核心对象：一次实验
├── FactorLoader        # 动态加载因子（importlib，FactorLibrary + BaseFactor）
├── ConfigManager       # 统一配置读取（YAML/JSON，含 backtest.engine）
├── portfolio.py        # build_factor_portfolio（薄包装，委托适配器）
├── plotting.py         # 累计收益-回撤 / 分组 IC 图
└── result/             # ResultManager + storage（csv/parquet/sqlite/clickhouse）
        │  调用
        ▼
   QuantCore（底层引擎：data / factor / metric / backtest.adapter）
```

回测统一经 `QuantCore.backtest.adapter` 的 `native` 自研向量化引擎完成。详见顶层
`docs/04-features/FEAT-003-backtest-adapter/03-technical-design.md`、`docs/04-features/FEAT-002-research-engine/06-research-api.md`。

## 模块结构

```
researchengine/
├── experiment.py        # Experiment.run() 编排流程（经回测适配器）
├── manager.py           # ExperimentManager
├── factor_loader.py     # FactorLoader（动态加载）
├── config.py            # ConfigManager
├── portfolio.py         # build_factor_portfolio（薄包装，委托 NativeEngine）
├── plotting.py          # 累计收益-回撤 / 分组 IC 图
├── api/                 # HTTP 适配层（FastAPI）：/api/health · /api/factor-libraries · /api/factors/{library_name} · /api/backtest
└── result/
    ├── manager.py      # ResultManager
    └── storage/        # ResultStorage + CSV/Parquet/SQLite/ClickHouse

../Factor/libraries/     # 研究员写入的因子库
├── alpha_library.py    # AlphaLibrary（alpha101/alpha158/marketcap/macdboll/futureRes）
├── worldquant_alpha101.py # WorldQuant Alpha 101（alpha001-alpha101）
examples/
├── main.py             # 端到端入口（CLI/SDK）
└── gen_data.py         # 生成宽表样本数据
config.yaml             # 实验配置（含 backtest.engine）
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
2. `FactorLoader.load("alpha_library")` 动态加载因子库（注册 alpha101、marketcap 等）
3. `loader.factors["marketcap"]` 挑一个因子
4. `ExperimentManager.create(...)` 创建实验
5. `experiment.run()`：
   - `data_engine.get_panels` 取宽表面板 -> `factor_engine.compute_panel` 算因子值
   - `FactorQuantileStrategy` 产出目标权重 -> NativeEngine -> 净值/收益/持仓
   - `MetricEngine.calculate_all(MetricContext)` 算 10 指标（年化/Sharpe/Sortino/Calmar/最大回撤/波动率/IC/RankIC/胜率/换手）
6. `ResultManager.save()` 保存结果到 `output/`（`output_path` 非空时）

## HTTP API（供界面调用）

把 SDK 能力暴露为 HTTP，界面提交因子代码 -> 跑回测 -> 返回指标 + 净值。

```bash
pip install -e ".[api]"                       # fastapi + uvicorn
uvicorn researchengine.api.app:app --reload   # Swagger UI: http://localhost:8000/docs
```

```jsonc
// POST /api/backtest/factor
{ "factor_code": "def momentum(self, w=5):\n    return self.close.pct_change(w)",
  "factor_name": "momentum", "universe": "CSI500",
  "rebalance_days": 15, "groups": 5, "benchmark": "CSI500" }
// -> { "metrics": {...}, "equity_curve": [{date,value}...], "final_equity": ..., "error": null }

// 内置因子库：不传 factor_code
{ "library_name": "risk_indicators", "factor_name": "kurtosis60",
  "universe": "CSI300", "portfolio_type": "long_only",
  "rebalance_days": 1, "groups": 5, "benchmark": "CSI300" }
```

内置因子也可以只提交 `library_name` 和 `factor_name`；未填写的因子回测参数默认使用纯多头、沪深300、每日调仓，手续费、印花税和滑点均为 0。

因子代码出错 -> `error` 字段填充，HTTP 200（不抛 500）。详见顶层 `docs/04-features/FEAT-002-research-engine/06-research-api.md`。

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
loader = FactorLoader(factor_dir=".../Factor/libraries")
loader.load("my_lib")
factor = loader.factors["myalpha"]   # 方法名即因子名
experiment = Experiment(factor=factor, ...)
result = experiment.run()
```

也兼容传统 `BaseFactor` 子类写法（一个文件一个类 + `compute` 方法）。

## 配置项（`config.yaml`）

| 项 | 说明 |
|----|------|
| `data_dir` | 数据路径；指向**文件**用 WideCSVProvider（宽表），指向**目录含 *.parquet** 用 FieldParquetProvider，否则逐只 CSV |
| `benchmark` | 股票池名称（对应 universe.csv 的 pool；无 universe.csv 时用全部标的） |
| `rebalance` | 调仓频率 daily/weekly/monthly |
| `n_groups` | 分组评估数（分组 IC 图） |
| `long_short` | 是否多空对冲 |
| `ic_horizon` | IC 远期收益天数 |
| `backtest.engine` | 回测后端 `native`（唯一的自研向量化引擎） |
| `backtest.initial_capital` / `backtest.commission_rate` / `backtest.slippage_rate` | 回测成本（默认 0，不改默认结果） |
| `storage` | 结果存储 csv/parquet/sqlite/clickhouse |
| `output_path` | 结果输出目录 |

## 文档

模块设计（顶层 Feature 文档包）：
- `docs/04-features/FEAT-002-research-engine/02-architecture.md`
- `docs/04-features/FEAT-002-research-engine/03-modules.md`
- `docs/04-features/FEAT-002-research-engine/04-class-design.md`
- `docs/04-features/FEAT-002-research-engine/05-runtime-flow.md`
- `docs/04-features/FEAT-002-research-engine/06-research-api.md`

跨模块设计：
- `docs/04-features/FEAT-003-backtest-adapter/03-technical-design.md` - Native 向量化回测设计

## 测试

```bash
pytest ResearchEngine/tests
```
