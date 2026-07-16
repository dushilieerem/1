# ResearchEngine 类设计

> 文档版本：v2.0
> 最后更新：2026-07-15
> 关联：`02-architecture.md`（无状态设计）、`03-modules.md`（模块职责）、`06-research-api.md`（HTTP API）

---

## 1. 设计原则

ResearchEngine 是**纯计算服务层**，遵循以下原则：

1. **无状态**：不持有因子注册表、实验状态、持久化结果
2. **薄适配**：只编排流程，不实现计算逻辑（所有计算委托 QuantCore）
3. **水平扩展**：多实例部署，shared-nothing

---

## 2. 核心类：Runner（替代旧 Experiment）

```
researchengine/runner.py

BacktestRunner（核心执行器）
─────────────────────────────────────────
方法：
  run(factor_code: str,
      factor_name: str,
      universe: str,
      start: str | None,
      end: str | None,
      data_dir: str | None,
      params: BacktestParams) -> BacktestResult

内部流程：
  ① 编译因子代码（exec → FactorLibrary 子类 → 获取因子方法）
  ② 初始化 QuantCore 引擎（DataEngine / FactorEngine / MetricEngine，可注入）
  ③ data_engine.get_panels(start, end) → Panel
  ④ factor_engine.compute_panel(factor, panel) → factor_values
  ⑤ forward_returns(close_panel, horizon) → 远期收益
  ⑥ FactorQuantileStrategy(factor_values, close_panel, rebalance, stock_num, long_short)
  ⑦ get_backtest_engine(engine).run(strategy.signals(), config) → equity/returns/positions
  ⑧ metric_engine.calculate_all(MetricContext(...)) → metrics
  ⑨ 序列化 → BacktestResult
```

**与旧 Experiment 的关键差异：**

| 维度 | Experiment（旧） | BacktestRunner（新） |
|------|-----------------|---------------------|
| 因子来源 | FactorLoader 加载本地文件 | 接收前端传入的代码字符串 |
| 配置来源 | ConfigManager + config.yaml | 所有参数通过方法参数传入 |
| 结果处理 | ResultManager 持久化 | 返回序列化结果，不持久化 |
| 状态 | 持有 factor/result 引用 | 无状态，每次调用独立 |

---

## 3. 值对象

```
researchengine/runner.py

BacktestParams
────────────────
属性：
  backtest_engine: str       # native | vectorbt
  rebalance: str             # monthly | weekly | daily
  stock_num: int             # 持仓数量
  long_short: bool           # 是否多空
  commission_rate: float     # 手续费率
  slippage_rate: float       # 滑点率
  initial_capital: float     # 初始资金
  include_equity: bool       # 是否返回净值序列
  include_chart: bool        # 是否返回图表

BacktestResult
────────────────
属性：
  metrics: Dict[str, float]    # 指标（sharpe/calmar/ic 等）
  equity_curve: List[Point]    # 净值序列 [{date, value}]
  date_range: DateRange        # 回测区间
  final_equity: float          # 最终净值
  meta: BacktestMeta           # 元信息（factor/universe/engine 等）
  chart_png_b64: str | None    # 图表 base64
  error: str | None            # 错误信息（不抛异常）
```

---

## 4. HTTP API 层

```
researchengine/api/

schemas.py
────────────────
BacktestRequest     # Pydantic 请求模型（factor_code, factor_name, params...）
BacktestResponse    # Pydantic 响应模型（metrics, equity_curve, error...）

routes/backtest.py
────────────────
backtest(req: BacktestRequest) -> BacktestResponse
  # 调用 runner.BacktestRunner.run()，序列化结果返回

runner.py
────────────────
run_backtest_from_code(req: BacktestRequest) -> BacktestResponse
  # HTTP 层适配：请求 → BacktestRunner → 序列化 → 响应

app.py
────────────────
create_app() -> FastAPI
  # CORS + 路由挂载
```

---

## 5. 已移除的类

| 旧类 | 移除原因 | 替代方案 |
|------|---------|---------|
| `Experiment` | 持有状态（factor/result 引用） | `BacktestRunner`（无状态函数式） |
| `ExperimentManager` | 管理 experiments 字典，有状态 | 无，前端管理实验状态 |
| `FactorLoader` | 从本地文件加载因子 | 前端提交因子代码字符串 |
| `ConfigManager` | 从本地 YAML 读取配置 | 参数通过请求传入 |

---

## 6. 可选保留的类（非核心依赖）

```
ResultManager（可选）
────────────────
属性：metrics, equity_curve, positions, meta
方法：save(path), load(path), summary

用途：前端如果需要 RE 侧提供结果存储能力，可启用
注意：与无状态设计冲突，建议前端自行存储
```

---

## 7. 核心设计约束

| 约束 | 含义 |
|------|------|
| **BacktestRunner** | 只编排流程，不计算因子/收益/指标（委托 QuantCore） |
| **代码编译** | 只编译执行因子/策略代码，不管理因子文件 |
| **无状态** | 每次调用独立，不持有跨请求状态 |
| **薄 HTTP 层** | API 只调 BacktestRunner，不新增回测逻辑 |
| **QuantCore 无感** | ResearchEngine 只调用 QuantCore，不关心其内部实现 |
| **前端负责** | 因子管理、结果存储、可视化由前端处理 |
