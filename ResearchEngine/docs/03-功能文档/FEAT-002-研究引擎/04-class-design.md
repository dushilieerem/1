# ResearchEngine 类设计

> 文档版本：v2.1
> 最后更新：2026-08-18
> 关联：`02-architecture.md`（状态与扩展）、`03-modules.md`（模块职责）、`06-research-api.md`（HTTP API）

---

## 1. 设计原则

ResearchEngine 是**纯计算服务层**，遵循以下原则：

1. **业务无状态**：不持有用户资产和可靠的持久化实验历史；进程内允许持有临时任务状态
2. **薄适配**：只编排流程，不实现计算逻辑（所有计算委托 QuantCore）
3. **水平扩展**：多实例部署，shared-nothing

---

## 2. 核心执行单元：Experiment 与 API runner

```
app/services/experiment/ + app/services/factor/runner.py

因子回测执行单元
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
  ② FactorBacktestExperiment 通过 BacktestEngine 进入完整因子流程
  ③ DataEngine.get_panels(...) → 完整历史 Panel、有效池掩码和过滤诊断
  ④ FactorEngine.compute_panel(...) → 完整历史 factor_values
  ⑤ FactorEngine.preprocess(...) → 应用有效池、去极值和标准化
  ⑥ PortfolioEngine.build(...) → 分组、目标权重、持仓、调仓记录和远期收益
  ⑦ MetricEngine.evaluate_factor_portfolio(...) → 收益、净值、指标和分层结果
  ⑧ BacktestEngine 汇总 provenance、告警和 FactorBacktestResult
  ⑨ 应用层序列化 → FactorBacktestResponse
```

旧设计中的 `FactorBacktestExecutor` 已删除；策略回测的 `BacktestSignals`、
`NativeEngine` 和事件引擎不属于上述因子流程。

`start/end` 只定义收益确认区间。因子计算使用当前数据版本的完整可用历史，以自动覆盖不同因子的预热需求；因子值、收益、指标和分析结果在计算后裁剪回请求区间。命名股票池仍按该区间内首个实际交易日解析并固定。

**执行单元与任务调度的边界：**

| 维度 | Experiment/runner | ExperimentManager |
|------|-----------------|---------------------|
| 负责内容 | 编译因子、组织一次回测并生成结果 | 调度任务、控制并发、保存运行状态 |
| 因子来源 | 内置库或前端传入的代码字符串 | 不解析因子代码 |
| 结果处理 | 生成 `FactorBacktestResponse` | 保存 Future 和进程内任务快照 |
| 线程归属 | 不创建服务级线程池 | 自有 `ThreadPoolExecutor` |

---

## 3. ExperimentManager：进程级任务调度器

```
app/services/experiment/manager.py

ExperimentManager
─────────────────────────────────────────
属性：
  max_workers: int              # 同时执行的回测数，默认 2
  max_queue_size: int           # 额外排队数，默认 8
  runs: Dict[run_id, Run]       # 进程内任务状态
  inflight: Dict[key, run_id]   # 同键任务去重

方法：
  submit(callable, key, metadata) -> ExperimentHandle
  completed(result) -> ExperimentHandle
  get(run_id) -> ExperimentHandle | None
  cancel(run_id) -> bool
  shutdown() -> None
```

`ExperimentManager` 自己拥有 `ThreadPoolExecutor` 和有界容量。FastAPI lifespan
只负责调用 `start()` / `shutdown()`；路由不能直接创建回测线程，也不能绕过 Manager
调用 `Experiment.run()`。

### 3.1 任务状态

```text
CREATED → QUEUED → RUNNING → SUCCEEDED
                         ├→ FAILED
                         └→ CANCELLED（仅能真正取消尚未开始的任务）
```

线程已经开始执行后，Python 无法安全强杀；此时 `cancel()` 只记录取消请求。
需要硬超时和用户代码隔离时，后续增加进程/容器执行后端。

### 3.2 任务键

因子任务键包含请求参数、因子代码/库、数据指纹和缓存版本；策略任务键包含
规范化请求。相同键的并发请求共享一个 Future，不会重复占用线程。

## 5. 值对象

```
app/services/factor/runner.py

BacktestParams
────────────────
属性：
  backtest_engine: str       # native
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

## 6. HTTP API 层

```
app/api/

schemas.py
────────────────
BacktestRequest     # Pydantic 请求模型（factor_code, factor_name, params...）
BacktestResponse    # Pydantic 响应模型（metrics, equity_curve, error...）

routes.py
────────────────
backtest_factor(req: FactorBacktestRequest) -> FactorBacktestResponse
  # 提交给 ExperimentManager，异步等待 Future，再序列化结果

api/runner.py
────────────────
run_factor_backtest_async(req: FactorBacktestRequest) -> FactorBacktestResponse
  # HTTP 层适配：请求 → Manager.submit() → 执行单元 → 响应

app.py
────────────────
create_app() -> FastAPI
  # CORS + 路由挂载
```

---

## 7. 已移除或调整的类

| 旧类 | 移除原因 | 替代方案 |
|------|---------|---------|
| `Experiment` | 旧版由调用方直接运行 | 保留为单次因子实验执行单元，由 Manager 调度 |
| `ExperimentManager` | 旧版只管理 experiments 字典 | 升级为进程级任务调度器，不管理用户资产 |
| `FactorLoader` | 从本地文件加载因子 | 前端提交因子代码字符串 |
| `ConfigManager` | 从本地 YAML 读取配置 | 参数通过请求传入 |

---

## 8. 可选保留的类（非核心依赖）

```
ResultManager（可选）
────────────────
属性：metrics, equity_curve, positions, meta
方法：save(path), load(path), summary

用途：前端如果需要 RE 侧提供结果存储能力，可启用
注意：与无状态设计冲突，建议前端自行存储
```

---

## 9. 核心设计约束

| 约束 | 含义 |
|------|------|
| **Experiment / API runner** | 只编排流程，不计算因子/收益/指标（委托 QuantCore） |
| **代码编译** | 只编译执行因子/策略代码，不管理因子文件 |
| **状态边界** | 业务资产和结果历史不由 RE 管理；线程池与运行中任务属于进程内临时状态 |
| **薄 HTTP 层** | API 只提交 ExperimentManager，不新增回测逻辑 |
| **QuantCore 无感** | ResearchEngine 只调用 QuantCore，不关心其内部实现 |
| **前端负责** | 因子管理、结果存储、可视化由前端处理 |
