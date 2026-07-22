# ResearchEngine HTTP API（FastAPI）

> 文档版本：v2.1
> 最后更新：2026-07-20
> 关联：`02-architecture.md`（无状态设计）、`03-modules.md`（模块职责）

---

## 1. 概述

ResearchEngine HTTP API 是 SVQuant 的**纯计算服务层**。

**核心职责**：接收前端提交的代码 + 参数 → 执行回测 → 返回指标 + 净值。

**两种回测模式**：

| 模式 | 端点 | 适用场景 | 策略逻辑 |
|------|------|---------|---------|
| **因子回测** | `POST /api/backtest/factor` | 因子选股研究 | 系统内置 FactorQuantileStrategy（因子分位选股） |
| **策略回测** | `POST /api/backtest/strategy` | 自定义策略逻辑 | 用户提供完整策略代码 |

**不做的事**：
- ❌ 不管理因子库、因子列表
- ❌ 不管理策略版本
- ❌ 不持久化回测结果（结果由前端处理）
- ❌ 不提供行业/政策分析（由独立数据服务层提供）
- ❌ 不加载本地因子文件

**核心原则**：
- **无状态**：每个请求独立执行，实例间无共享状态
- **水平可扩展**：多实例部署，负载均衡分发
- **薄适配层**：不新增回测逻辑，所有计算委托 QuantCore

---

## 2. 运行

```bash
pip install -e ".[api]"                          # fastapi + uvicorn
uvicorn researchengine.api.app:app --reload      # 开发（热重载）
# 或 python -m researchengine.api.server         # 生产式启动
```

- Swagger UI：<http://localhost:8000/docs>
- ReDoc：<http://localhost:8000/redoc>

---

## 3. 端点总览

| 模块 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 系统 | GET | `/api/health` | 健康检查 |
| 因子回测 | POST | `/api/backtest/factor` | 因子选股回测（系统内置选股策略） |
| 策略回测 | POST | `/api/backtest/strategy` | 自定义策略回测（用户提供完整策略逻辑） |

> 因子管理、行业分析、政策分析等非回测功能由前端或独立数据服务提供，不属于 ResearchEngine。
>
> 当前 MVP 仅提供同步端点。异步提交、任务查询和结果持久化尚未实现，不能调用文档中不存在的 `/async` 或 `run_id` 查询接口。

---

## 4. 端点详情

### 4.1 系统

#### `GET /api/health`

```json
{ "status": "ok", "version": "2.0.0", "engines": ["native", "vectorbt"] }
```

---

### 4.2 因子回测

因子回测适用于**因子选股研究**——用户提交因子代码，系统使用内置 FactorQuantileStrategy
按因子值排序选股，生成组合净值。

#### `POST /api/backtest/factor`

**请求**：
```jsonc
{
  // ─── 1. 因子代码（用户编写） ───
  // 只需传函数体，系统自动补全 import 和 class 头
  "factor_code": "def momentum(self, window=5):\n    return self.close.pct_change(window)",
  "factor_name": "momentum",

  // ─── 2. 组合构建方式 ───
  "portfolio_type": "long_short",     // long_only=纯多头 | long_short=多空组合

  // ─── 3. 股票池 ───
  "universe": "CSI_ALL",              // CSI_ALL=中证全指 | CSI300=沪深300
                                      // CSI500=中证500 | CSI1000=中证1000
                                      // CSI2000=中证2000 | SSE50=上证50
  // ─── 4. 回测区间 ───
  "start": "2024-01-01", "end": "2024-12-31",

  // ─── 5. 过滤条件 ───
  "filter_limit_up": true,           // 是否过滤涨停股
  "filter_suspended": true,          // 是否过滤停牌股

  // ─── 6. 分层与调仓 ───
  "rebalance_days": 15,              // 每 15 个交易日调仓一次
  "groups": 5,                       // 因子等权分 5 组；主组合为最高组
  "benchmark": "CSI500",             // CSI300 | CSI500 | CSI1000 | SSE50

  // ─── 7. 分析深度 ───
  "analysis_level": "core"           // core=核心回测（默认） | full=额外分层、FF3、行业曲线
}
```

**请求参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `factor_code` | string | 是 | — | 因子函数体；系统自动包装为 `FactorLibrary`。 |
| `factor_name` | string | 否 | `alpha101` | 要执行的因子方法名，须与代码中的函数名一致。 |
| `portfolio_type` | string | 否 | `long_short` | `long_only` 为最高组纯多头；`long_short` 为最高组做多、最低组做空。 |
| `universe` | string | 否 | `CSI_ALL` | 股票池，如 `CSI300`、`CSI500`、`CSI1000`。 |
| `start` / `end` | string/null | 否 | `null` | 回测起止日期，格式 `YYYY-MM-DD`；均未传时使用全部可用数据。 |
| `filter_limit_up` | boolean | 否 | `true` | 涨停过滤开关（当前仅保留接口契约，尚未接入执行链路）。 |
| `filter_suspended` | boolean | 否 | `true` | 停牌过滤开关（当前仅保留接口契约，尚未接入执行链路）。 |
| `rebalance_days` | integer | 否 | `20` | 调仓间隔，单位为交易日；可传 `15`、`16` 等正整数。 |
| `groups` | integer | 否 | `5` | 因子分层数，支持 2–10 组；主组合持有最高组。 |
| `benchmark` | string | 否 | `CSI300` | `CSI300` / `CSI500` / `CSI1000` / `SSE50`。 |
| `commission_rate` | number | 否 | `0.0003` | 佣金率。 |
| `stamp_tax` | number | 否 | `0.001` | 卖出印花税率。 |
| `slippage_rate` | number | 否 | `0.001` | 滑点率。 |
| `analysis_level` | enum | 否 | `core` | `core` 计算核心回测、汇总指标和各分组区间收益；`full` 才额外计算 IC/IR 时序、FF3 与行业曲线。 |

净值、基准、超额收益和各分组区间收益固定返回；`full` 在此基础上增加 IC/IR 时序、FF3 与行业曲线。

**响应**：
```jsonc
{
  // ─── 1. 指标 ───
  "metrics": {
    "sharpe": 1.40, "annual_return": 0.45, "max_drawdown": -0.17,
    "volatility": 0.25, "calmar": 2.65, "win_rate": 0.55,
    "total_return": 1.80, "trade_count": 48,
    "ic": 0.0032, "rank_ic": 0.0115
  },

  // ─── 2. 净值曲线（含回撤，前端画收益+回撤图）───
  "equity_curve": [ { "date": "2017-01-04", "value": 1.0096, "drawdown": 0.0 }, ... ],

  // ─── 3. 回撤区间明细（前端画回撤标注）───
  "drawdowns": [
    { "start": "2022-01-05", "end": "2022-04-26", "peak": 1.85,
      "trough": 1.53, "recovery": "2022-07-15", "depth": -0.17, "days": 78 }
  ],

  // ─── 4. 分年收益（前端画柱状图）───
  "annual_returns": [
    { "year": 2020, "return_value": 0.32 },
    { "year": 2021, "return_value": 0.18 }
  ],

  // ─── 5. 因子分组收益（core 与 full 均返回；其余深度字段仅 full 返回）───
  "factor_analysis": {
    "ic_mean": 0.0032, "ic_std": 0.051, "rank_ic_mean": 0.0115,
    "layered_returns": {
      "groups": 5,
      "layer1": 0.22, "layer2": 0.15, "layer3": 0.10,
      "layer4": 0.05, "layer5": -0.08,
      "spread": 0.30,
      "long_short_return": 0.30
    },
    "cumulative_series": [
      { "date": "2017-01-04", "layer1": 1.0, "layer2": 1.0,
        "layer3": 1.0, "layer4": 1.0, "layer5": 1.0 },
      ...
    ],

    // ─── 5.1 前端因子诊断图所需的原始序列 ───
    "definition": {
      "ic_type": "pearson", "forward_return_days": 1,
      "signal_lag_days": 0, "rolling_ir_window": 60,
      "groups": 5,
      "industry_return_method": "equal_weight_fixed_capital",
      "industry_grouping_method": "daily_cross_sectional_equal_weight_fixed_capital"
    },
    "ic_series": [ { "date": "2017-01-04", "value": 0.0312, "sample_size": 486 }, ... ],
    "cumulative_ic_series": [ { "date": "2017-01-04", "value": 0.0312 }, ... ],
    "rolling_ir_series": [
      { "date": "2017-03-28", "value": 0.42, "window": 60, "sample_size": 60 }, ...
    ],
    "industry_equity_curves": [
      { "industry_code": "银行", "industry_name": "银行",
        "points": [ { "date": "2017-01-04", "value": 1.0 }, ... ] }
    ],
    "industry_group_equity_curves": [
      { "industry_code": "银行", "industry_name": "银行", "points": [
        { "date": "2017-01-04", "groups": { "G1": 1.0, "G2": 1.0, "G3": 1.0, "G4": 1.0, "G5": 1.0 } }, ...
      ] }
    ]
  },

  // ─── 6. 元信息 ───
  "date_range": { "start": "2017-01-04", "end": "2026-04-30" },
  "final_equity": 5.0530,
  "benchmark_curve": [ { "date": "2017-01-04", "value": 1.0, "drawdown": 0.0 }, ... ],
  "excess_return": 0.42,
  "meta": {
    "factor": "momentum", "universe": "CSI_ALL",
    "portfolio_type": "long_short",
    "rebalance_days": 15, "groups": 5, "benchmark": "CSI500",
    "filter_limit_up": true,
    "filter_suspended": true,
    "timings_seconds": {
      "engine_setup": 0.001,
      "panel_setup": 0.160,
      "factor_compute": 0.848,
      "signal_and_backtest": 0.375,
      "metric_calculation": 0.639,
      "factor_analysis": 0.0,
      "api_total": 2.133
    }
  },

  // ─── 7. 错误信息 ───
  "error": null
}
```

**返回参数**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `metrics` | object | 绩效指标，如年化收益、夏普、最大回撤、IC、Rank IC。 |
| `equity_curve` | array/null | 主组合净值点：`date`、`value`、`drawdown`。 |
| `drawdowns` | array | 最大的 10 段回撤区间。 |
| `annual_returns` | array | 各年度收益。 |
| `factor_analysis` | object | `core` 与 `full` 均返回 `layered_returns`（各组区间收益、组间价差）和分组净值；仅 `full` 返回 IC/IR 时序、FF3 与行业序列，核心模式中这些数组为空。 |
| `benchmark_curve` | array/null | 所选基准的归一化净值点。 |
| `excess_return` | number/null | 主组合相对基准的区间超额收益。 |
| `date_range` | object | 实际回测起止日期。 |
| `final_equity` | number/null | 主组合最终净值。 |
| `meta` | object/null | 实际使用的因子、股票池、调仓天数、分组数、基准和 `timings_seconds` 分段耗时（秒）。 |
| `error` | string/null | 业务或因子代码错误信息；成功时为 `null`。 |

> **因子代码出错不抛 500**：语法错 / 导入错 / 因子名不存在 / 运行错 → `error` 字段填充，HTTP 200，
> 便于前端统一处理（`meta` 置 `null`）。
>
> **默认成本结构**：佣金 3‱ + 印花税 1‰（卖出）+ 滑点 1‰，对标 A 股市场实际交易成本。
>
> **性能模式**：未传 `analysis_level` 时默认 `core`，适用于同步快速回测，并保留各分组区间收益；需要行业与归因诊断时显式传 `full`。当前 `CSI300`、`CSI500`、`CSI1000`、`SSE50` 按最新一期指数成分筛选，历史逐日成分调整尚未建模。
>
> **参数迁移**：因子回测不再接受 `backtest_period`、`data_dir`、`backtest_engine`、`initial_capital`、
> `include_equity`、`include_factor_values`、`include_positions`、`rebalance` 和 `stock_num`。服务端统一使用
> 配置的数据目录及 Native 回测后端；传入已移除字段会返回 `422`。

**因子诊断图口径**：`ic_series` 是当日因子值与 1 个交易日远期收益的截面 Pearson IC；
`cumulative_ic_series` 是 IC 简单累加，`rolling_ir_series` 是 60 个有效 IC 的均值除以样本标准差。
IC 分布图由前端使用 `ic_series[].value` 自行分桶。行业主数据不由本服务维护；当数据目录中的
`stock_info.parquet` 缺失有效的 `code/symbol/ts_code -> industry` 映射时，两个行业曲线数组为空而回测不失败。
行业曲线均使用固定本金净值，行业分组按日、在行业内独立分组。

### 4.3 策略回测

策略回测适用于**自定义策略逻辑**——用户提供完整的策略代码（含信号生成逻辑），
系统执行回测。当因子回测的 FactorQuantileStrategy 不满足需求时使用。

除自由编写 `generate_signals()` 外，也支持结构化的 `FactorPortfolioStrategy`：用户在同一个
Python 类中定义多个 `@factor` 因子函数与唯一 `@signal` 组合公式，平台自动执行 Top-N 选股、
等权和调仓，仍走本端点与向量化回测后端。

#### `POST /api/backtest/strategy`

**请求**：
```jsonc
{
  // ─── 推荐：结构化因子组合策略代码 ───
  "strategy_code": "from quantcore import EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal\n\nclass SmallCapMomentumStrategy(FactorPortfolioStrategy):\n    selector = TopN(30)\n    weighting = EqualWeight()\n    rebalance = EveryNTradingDays(20)\n\n    @factor\n    def momentum_20d(self):\n        return self.close.pct_change(20)\n\n    @factor\n    def value_ep(self):\n        return 1.0 / self.pe_ttm\n\n    @signal\n    def score(self):\n        return 0.6 * self.rank(self.momentum_20d()) + 0.4 * self.rank(self.value_ep())",

  // ─── 回测范围 ───
  "universe": "CSI500",
  "start": null, "end": null,

  // ─── 回测参数 ───
  "commission_rate": 0.0,
  "slippage_rate": 0.0,
  "initial_capital": 1000000,

  // ─── 返回控制 ───
  "include_positions": false
}
```

**请求参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `strategy_code` | string | 是 | — | 完整 Python 源码；推荐定义一个 `FactorPortfolioStrategy` 子类。高级自由策略则必须且只能定义一个包含 `generate_signals()` 的类。 |
| `universe` | string | 否 | `CSI500` | 传给数据提供者解析的股票池名称。 |
| `start` / `end` | string/null | 否 | `null` | 回测区间，格式 `YYYY-MM-DD`。 |
| `commission_rate` / `slippage_rate` | number | 否 | `0.0` | 按成交额计的费率与滑点率。 |
| `initial_capital` | number | 否 | `1000000` | 初始资金。 |
| `include_positions` | boolean | 否 | `false` | 是否返回采样后的持仓权重快照。 |

服务端统一使用配置的数据目录和 Native 回测后端，并始终返回逐日净值曲线。`strategy_params`、
`factor_code`、`factor_name`、`data_dir`、`backtest_engine` 和 `include_equity` 已移除；传入这些字段或其他未知字段会返回 HTTP `422`，不允许静默忽略。

**结构化因子组合策略示例**：

```python
from quantcore import (
    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,
)

class SmallCapMomentumStrategy(FactorPortfolioStrategy):
    selector = TopN(30)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(20)

    @factor
    def momentum_20d(self):
        return self.close.pct_change(20)

    @factor
    def value_ep(self):
        return 1.0 / self.pe_ttm

    @signal
    def score(self):
        return 0.6 * self.rank(self.momentum_20d()) + 0.4 * self.rank(self.value_ep())
```

所有策略所需因子均在 `strategy_code` 中定义。策略源码中的 `universe` 声明仅供展示，实际回测
股票池仍使用请求的 `universe` 字段。自由策略由服务注入 `close` 收盘价面板，例如
`__init__(self, close)`；其余行情字段或多因子组合应使用 `FactorPortfolioStrategy` 在策略代码中声明。

**响应**：
```jsonc
{
  // ─── 1. 指标 ───
  "metrics": {
    "sharpe": 1.25, "annual_return": 0.38, "max_drawdown": -0.20,
    "volatility": 0.28, "calmar": 1.90, "win_rate": 0.52,
    "total_return": 1.50, "turnover": 0.18,
    "ic": null, "rank_ic": null
  },

  // ─── 2. 净值曲线 ───
  "equity_curve": [ { "date": "2017-01-04", "value": 1.0, "drawdown": 0.0 }, ... ],

  // ─── 3. 回撤区间 ───
  "drawdowns": [ ... ],

  // ─── 4. 分年收益 ───
  "annual_returns": [ ... ],

  // ─── 5. 元信息 ───
  "date_range": { "start": "2017-01-04", "end": "2026-04-30" },
  "final_equity": 2.50,
  "meta": {
    "strategy": "MyStrategy",
    "universe": "CSI500"
  },

  // ─── 6. 可选数据 ───
  "positions": null,

  // ─── 7. 错误信息 ───
  "error": null
}
```

**响应字段**：

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `metrics` | object | 否 | 标准绩效指标对象，字段见下表；无可用输入的单项指标为 `null`。 |
| `equity_curve` | array | 是 | 逐日净值及回撤，始终尝试返回；无可用净值数据时为 `null`。 |
| `drawdowns` | array | 否 | 最大的 10 段回撤区间；无回撤时为空数组。 |
| `annual_returns` | array | 否 | 按自然年聚合的收益；无数据时为空数组。 |
| `date_range` | object | 否 | 实际参与回测的数据起止日期。 |
| `final_equity` | number | 是 | 回测结束日的组合净值。 |
| `meta` | object | 是 | 成功时的策略名称和实际股票池；业务错误时为 `null`。 |
| `positions` | array | 是 | `include_positions=true` 时返回的采样持仓快照，否则为 `null`。 |
| `error` | string | 是 | 业务或策略代码错误信息；成功时为 `null`。 |

`metrics` 字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `annual_return` | number/null | 年化收益率。 |
| `sharpe` | number/null | 年化夏普比率。 |
| `sortino` | number/null | 年化索提诺比率。 |
| `calmar` | number/null | 年化收益与最大回撤的比率。 |
| `max_drawdown` | number/null | 最大回撤率。 |
| `volatility` | number/null | 年化波动率。 |
| `win_rate` | number/null | 日收益为正的交易日占比。 |
| `turnover` | number/null | 平均换手率。 |
| `total_return` | number/null | 回测区间累计收益率。 |
| `ic` / `rank_ic` | number/null | 策略回测不计算因子诊断，通常为 `null`。 |

嵌套对象字段：

| 对象 | 字段 | 类型 | 说明 |
|------|------|------|------|
| `equity_curve[]` | `date`、`value`、`drawdown` | string、number、number/null | 交易日、归一化净值和相对历史高点的回撤。 |
| `drawdowns[]` | `start`、`end`、`peak`、`trough`、`recovery`、`depth`、`days` | string、string/null、number/null、number/null、string/null、number、integer | 回撤的开始、结束、峰值、谷值、恢复日、深度和持续天数。 |
| `annual_returns[]` | `year`、`return_value` | integer、number | 自然年及该年度收益率。 |
| `date_range` | `start`、`end` | string/null、string/null | 实际数据起止日期。 |
| `meta` | `strategy`、`universe` | string、string | 策略类名及实际使用的股票池。 |
| `positions[]` | `date`、`holdings` | string、array | 持仓快照日期及该日持仓列表。 |
| `positions[].holdings[]` | `symbol`、`weight` | string、number | 证券代码和目标权重。 |

策略源码、数据读取或回测运行错误均返回 HTTP `200`，并写入 `error` 字段；
此时 `meta` 为 `null`。请求体类型、枚举值或未知字段不合法时由接口契约返回 HTTP `422`。

**与因子回测的关键区别**：

| 维度 | 因子回测 | 策略回测 |
|------|---------|---------|
| 策略逻辑 | 系统内置 FactorQuantileStrategy | 用户自定义 |
| 调仓、选股、仓位 | 系统参数控制 | 由策略代码输出的目标权重控制 |
| `factor_analysis` | ✅ 有（IC/IR/分层） | ❌ 无 |
| 因子定义 | 请求中提交因子代码 | 在 `strategy_code` 中定义 |

## 5. 数据目录

策略回测不接受 `data_dir`；服务端按部署配置读取共享只读市场数据（当前优先使用 env `SVQUANT_DATA_DIR`，否则使用默认市场数据目录）。

所有实例挂载同一份只读数据：

```
/data/market/
├── stock_daily/        # A 股日线 parquet
├── stock_minute/       # 分钟数据（可选）
└── fundamentals/       # 基本面数据（可选）
```

---

## 6. 包结构

```
ResearchEngine/researchengine/api/
  __init__.py          包入口
  app.py               FastAPI 应用工厂 + CORS
  server.py            uvicorn __main__
  schemas.py           Pydantic 请求/响应模型（仅回测相关）
  serializers.py       pandas/指标 → JSON（NaN→null、净值→点、PNG→b64）
  runner.py            核心：编译因子代码 → 跑回测 → 序列化结果
  routes.py             GET /api/health、POST /api/backtest/factor、POST /api/backtest/strategy
```

---

## 7. 执行模型

### 7.1 同步回测

`POST /api/backtest/factor` 和 `POST /api/backtest/strategy` 阻塞到跑完直接返回结果。
FastAPI 把同步路由丢线程池执行，不阻塞事件循环，大回测（数十秒~分钟级）跑在线程池里，
不卡其他请求。

## 8. 安全说明 ⚠️

执行用户提交的 Python 源码 = 任意代码执行。安全模型：

| 威胁 | 风险 | 缓解措施 |
|------|------|---------|
| 恶意代码执行 | 高 | 子进程隔离执行（推荐）；Docker 容器限制资源 |
| 文件系统访问 | 中 | 容器只读挂载数据目录；限制文件系统权限 |
| 网络访问 | 中 | 容器仅暴露 API 端口；无出网权限 |
| 资源耗尽 | 中 | 限制 CPU/内存/执行时间；每个请求独立超时 |

当前实现为进程内执行（与 `FactorLoader` 同一信任模型）。生产部署建议使用子进程沙箱。

CORS 当前开发期放开（`allow_origins=["*"]`），生产应收紧到前端域名并加鉴权。

---

## 9. 与前端的分工

```
┌────────────────────────────────────────┐
│  前端 / 应用层                          │
│  - 管理因子库、策略库、因子定义          │
│  - 组装因子代码 + 参数                  │
│  - 调用 ResearchEngine API              │
│  - 接收结果，决定存储策略               │
│  - 可视化展示                           │
└──────────────────┬─────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────┐
│  ResearchEngine                        │
│  - 接收代码 → 执行回测 → 返回结果       │
│  - 不关心因子从哪来                     │
│  - 不存储任何状态                       │
└────────────────────────────────────────┘
```

### 前端负责

```python
# 前端管理因子代码（从自己的因子库中取出）
factor_code = """
from quantcore import FactorLibrary
class MyFactors(FactorLibrary):
    def momentum(self, window=5):
        return self.close.pct_change(window)
"""

# 组装请求，调用 ResearchEngine（因子回测）
response = requests.post("http://re-cluster:8000/api/backtest/factor", json={
    "factor_code": factor_code,
    "factor_name": "momentum",
    "universe": "CSI500",
    "rebalance": "monthly",
    "stock_num": 100,
    "long_short": True,
    ...
})

# 前端决定是否存储结果
result = response.json()
save_to_database(result)  # 前端存自己数据库
```

---

## 10. 部署

### 水平扩展

```yaml
# docker-compose.yml
services:
  re-api:
    image: svquant/researchengine:latest
    environment:
      - SVQUANT_DATA_DIR=/data/market
    volumes:
      - /mnt/shared-data:/data/market:ro  # 只读
    ports:
      - "8000"
    deploy:
      replicas: 5   # 水平扩展
      resources:
        limits:
          cpus: '4'
          memory: 8G

  nginx:
    image: nginx:latest
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    ports:
      - "80:80"
```

```nginx
# nginx.conf — 负载均衡
upstream re_cluster {
    least_conn;
    server re-api:8000 max_fails=3 fail_timeout=30s;
    server re-api:8000 max_fails=3 fail_timeout=30s;
}
server {
    listen 80;
    location /api/ {
        proxy_pass http://re_cluster;
    }
}
```

---

## 11. 后续扩展

- **子进程沙箱**：代码执行隔离，防止恶意因子代码影响主进程
- **结果外部存储**：异步回测结果存 Redis / DB，实例重启不丢失
- **批量回测**：一次提交多个因子/参数组合
- **WebSocket**：异步回测进度实时推送
- **函数计算集成**：回测作为 FaaS 函数运行，按需弹性伸缩
