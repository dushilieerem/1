# ResearchEngine 模块

> 文档版本：v2.0
> 最后更新：2026-07-15

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
├── runner.py                # 核心执行器：编译代码 → 跑回测 → 返回结果（替代旧的 experiment.py）
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
│   ├── runner.py            # HTTP 请求 → 调用核心 runner
│   └── routes/              # 路由模块
│       ├── __init__.py      # 路由注册
│       ├── health.py        # GET /api/health
│       ├── backtest.py      # POST /api/backtest（同步 + 异步）
│       └── analysis.py      # POST /api/analysis/attribution 等
│
└── result/                  # （可选保留，但不作为核心依赖）
    ├── manager.py           # ResultManager
    └── storage/             # 存储后端（CSV/Parquet/SQLite）
```

### 已移除 / 降级的模块

| 旧模块 | 变更 | 原因 |
|--------|------|------|
| `experiment.py` | 移除 | 实验管理逻辑不再由 RE 负责，职责转移到 `runner.py` |
| `manager.py` | 移除 | ExperimentManager 管理实验状态，与无状态设计冲突 |
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

## 4. 无状态设计要点

### 4.1 每个请求独立

```
请求 A ──► runner.run_backtest(code_A, ...) ──► 结果 A
请求 B ──► runner.run_backtest(code_B, ...) ──► 结果 B
```

- 没有共享的 `experiments` 字典
- 没有共享的 `factors` 注册表
- 每个请求独立编译、执行、返回

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
| `POST /api/backtest` | 同步回测 |
| `POST /api/backtest/async` | 异步回测（可选） |
| `GET /api/backtest/{run_id}` | 查询异步回测结果（可选） |

不再提供以下端点（因 RE 不管理因子/策略）：

- ~~`GET /api/factors`~~ —— 因子列表由前端管理
- ~~`GET /api/factors/{name}`~~ —— 因子详情由前端管理
- ~~`GET /api/factors/alpha101`~~ —— 因子库由前端管理
- ~~`POST /api/factors/analyze`~~ —— 因子分析由前端调用回测完成
- ~~`POST /api/analysis/report`~~ —— 报告生成由 AI Agent 完成
- ~~`GET /api/industry`~~ —— 行业分析由数据服务层提供
- ~~`GET /api/policy`~~ —— 政策分析由数据服务层提供

> 行业分析、政策分析等非回测核心功能，由独立的数据服务层提供，不属于 ResearchEngine。
