# ResearchEngine 模块

> 文档版本：v2.1
> 最后更新：2026-08-18

---

## 1. 模块职责

ResearchEngine 是**纯计算服务层**，核心职责：

1. **接收代码** → 编译因子代码 + 策略代码
2. **执行回测** → 委托 QuantCore 完成数据读取、因子计算、回测模拟、指标计算
3. **返回结果** → 序列化指标 + 净值 + 归因，返回给调用方

---

## 2. 模块结构

```
researchengine/
├── __init__.py              # 包入口
├── experiment.py            # 单次因子实验流程，实际计算委托 QuantCore
├── manager.py               # 进程级回测任务调度器、线程池和状态管理
├── config.py                # 配置工具函数（可选，非核心）
├── portfolio.py             # 回退兼容的薄包装（可选）
├── plotting.py              # 绘图工具（被前端替代，可选保留）
│
├── api/                     # HTTP 层（FastAPI）
│   ├── __init__.py
│   ├── app.py               # FastAPI 应用工厂 + CORS
│   ├── server.py            # uvicorn __main__
│   ├── schemas.py           # Pydantic 请求/响应模型
│   ├── serializers.py       # pandas → JSON 序列化
│   ├── runner.py            # HTTP 回测提交与结果适配
│   ├── strategy_backtest.py # 策略执行单元
│   └── routes.py            # 路由注册、同步/异步回测接口
│
└── result/                  # （可选保留，但不作为核心依赖）
    ├── manager.py           # ResultManager
    └── storage/             # 存储后端（CSV/Parquet/SQLite）
```

### 已移除 / 降级的模块

| 旧模块 | 变更 | 原因 |
|--------|------|------|
| `experiment.py` | 保留 | 作为单次因子实验执行单元，由 Manager 调度 |
| `manager.py` | 恢复为核心运行时模块 | 只管理进程内任务和计算资源，不管理用户资产或持久化业务结果 |
| `factor_loader.py` | 移除 | 因子代码由前端提交，不再从本地文件加载 |
| `factor/alpha_library.py` | 移至可选示例 | 不再作为 RE 核心依赖，作为参考示例保留 |

---

## 3. 核心执行流程（runner.py）

```
run_backtest(
    factor_code: str,        # 因子 Python 源码
    factor_name: str,        # 因子名（FactorLibrary 方法名）
    universe: str,           # 标的池
    start: str,              # 开始日期
    end: str,                # 结束日期
    params: dict             # 回测参数（engine, rebalance, stock_num 等）
) -> BacktestResult
```

内部流程：

```
1. 编译因子代码（exec/importlib）
   ↓
2. 获取因子实例（factor_name 对应的方法/类）
   ↓
3. 初始化 QuantCore DataEngine（从共享数据目录读取）
   ↓
4. 获取面板数据 + 计算因子值
   ↓
5. 构建 FactorQuantileStrategy → 目标权重
   ↓
6. NativeEngine → 净值 / 收益 / 持仓
   ↓
7. MetricEngine 计算指标
   ↓
8. 序列化结果（metrics + equity_curve + 归因）
   ↓
9. 返回 BacktestResult
```

---

## 4. 执行隔离与运行状态

### 4.1 每个请求独立

```
请求 A ──► runner.run_backtest(code_A, ...) ──► 结果 A
请求 B ──► runner.run_backtest(code_B, ...) ──► 结果 B
```

- `ExperimentManager` 共享的是进程内任务调度资源，不共享因子实例或 QuantCore 实验对象
- 每次任务独立编译、执行、返回
- `run_id`、Future 和任务状态只在当前进程有效

### 4.2 代码执行沙箱

```python
def compile_factor(factor_code: str, factor_name: str) -> BaseFactor:
    """编译因子代码，返回因子实例。"""
    namespace = {}
    exec(compile(factor_code, '<factor>', 'exec'), namespace)
    # 从 namespace 中找到 FactorLibrary 子类
    for name, obj in namespace.items():
        if isinstance(obj, type) and issubclass(obj, FactorLibrary) and obj is not FactorLibrary:
            library = obj()
            return getattr(library, factor_name)
    raise ValueError(f"因子 {factor_name} 未找到")
```

### 4.3 数据共享

所有实例通过只读方式访问同一份 MarketData：

```python
data_dir = os.environ.get("SVQUANT_DATA_DIR", "/data/market")
# 所有实例读取同一路径，不写入
```

---

## 5. HTTP API 层

详见 `06-research-api.md`。

核心端点：

| 端点 | 说明 |
|------|------|
| `GET /api/health` | 健康检查 |
| `POST /api/backtest/factor` | 同步因子回测 |
| `POST /api/backtest/strategy` | 同步策略回测 |
| `POST /api/experiments/factor` | 异步因子回测 |
| `POST /api/experiments/strategy` | 异步策略回测 |
| `GET /api/experiments/{run_id}` | 查询异步回测结果 |
| `DELETE /api/experiments/{run_id}` | 取消排队任务 |

不再提供以下端点（因 RE 不管理因子/策略）：

- ~~`GET /api/factors`~~ —— 因子列表由前端管理
- ~~`GET /api/factors/{name}`~~ —— 因子详情由前端管理
- ~~`GET /api/factors/alpha101`~~ —— 因子库由前端管理
- ~~`POST /api/factors/analyze`~~ —— 因子分析由前端调用回测完成
- ~~`POST /api/analysis/report`~~ —— 报告生成由 AI Agent 完成
- ~~`GET /api/industry`~~ —— 行业分析由数据服务层提供
- ~~`GET /api/policy`~~ —— 政策分析由数据服务层提供

> 行业分析、政策分析等非回测核心功能，由独立的数据服务层提供，不属于 ResearchEngine。

## 6. ExperimentManager 任务调度边界

`ExperimentManager` 是每个 ResearchEngine 进程一个的应用级对象，由
`api/app.py` 的 FastAPI lifespan 创建和关闭。FastAPI 负责 HTTP 连接和路由，
不负责回测线程；所有因子、向量化策略和事件策略回测都通过 Manager 提交。

### 6.1 Manager 负责什么

- 持有 `ThreadPoolExecutor`，默认同时运行 2 个回测；
- 通过有界容量限制额外排队任务，默认排队 8 个；
- 维护 `created → queued → running → succeeded/failed/cancelled` 状态；
- 为同一缓存键的并发请求复用同一个 Future；
- 队列满时立即拒绝，不让 HTTP 请求无限堆积；
- 关闭时停止接收任务、取消排队任务并等待运行中的任务结束。

### 6.2 Manager 不负责什么

- 不计算因子、收益、指标或订单；
- 不解析 HTTP 请求和响应；
- 不管理用户、因子/策略资产；
- 不把进程内 `run_id` 当作跨实例可靠存储。

### 6.3 执行入口

```text
POST /api/backtest/factor   ─┐
POST /api/backtest/strategy  ─┼─> ExperimentManager.submit()
POST /api/experiments/*     ─┘             │
                                          ▼
                               FactorExperiment / Strategy runner
                                          │
                                          ▼
                                      QuantCore
```
