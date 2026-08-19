# ResearchEngine HTTP API（FastAPI）

> 文档版本：v2.5
> 最后更新：2026-08-18

ResearchEngine 是研究计算服务：接收代码与参数、执行回测、返回结构化结果；不管理用户、
因子/策略资产或可靠的业务结果历史。每个进程由 `ExperimentManager` 管理回测线程池、
有界队列和临时 `run_id`；FastAPI 只负责 HTTP 适配，不拥有回测线程池。开发期临时承载的
AI 因子草稿端点只生成并静态校验代码，不执行回测，待 SaaS 应用层具备身份与资产治理后迁出。

## 运行

```bash
pip install -e ".[api]"
uvicorn researchengine.api.app:app --reload
```

- Swagger UI：<http://localhost:8000/docs>
- ReDoc：<http://localhost:8000/redoc>

## API 索引

每个端点拥有独立契约文档；新增端点时必须新增独立页面并更新本表。

| 模块 | 方法 | 端点 | 文档 |
|------|------|------|------|
| 系统 | GET | `/api/health` | [健康检查](06-research-api/health.md) |
| 因子目录 | GET | `/api/factor-libraries` | [因子库目录](06-research-api/factor-libraries.md) |
| 因子目录 | GET | `/api/factors/{library_name}` | [指定库因子列表](06-research-api/factor-library-factors.md) |
| AI 因子草稿 | POST | `/api/ai/factor-generations` | [AI 因子草稿生成](06-research-api/ai-factor-generations.md) |
| AI 策略草稿 | POST | `/api/ai/strategy-generations` | [AI 向量化策略草稿生成](06-research-api/ai-strategy-generations.md) |
| AI 回测解读 | POST | `/api/ai/backtest-interpretations` | [AI 回测解读与优化建议](06-research-api/ai-backtest-interpretations.md) |
| 市场数据 | GET | `/api/market-data/symbols` | [股票代码列表](06-research-api/market-data-symbols.md) |
| 市场数据 | GET | `/api/market-data/daily/{symbol}` | [个股日线](06-research-api/market-data-daily.md) |
| 市场数据 | GET | `/api/market-data/indices` | [股指列表](06-research-api/market-data-indices.md) |
| 市场数据 | GET | `/api/market-data/indices/{code}/constituents` | [股指成分股](06-research-api/market-data-index-constituents.md) |
| 因子回测 | POST | `/api/backtest/factor` | [因子回测](06-research-api/backtest-factor.md) |
| 策略资产 | GET | `/api/strategies` | [策略目录](06-research-api/strategy-list.md) |
| 策略回测 | POST | `/api/backtest/strategy` | [策略回测](06-research-api/backtest-strategy.md) |
| 异步因子/策略回测 | POST/GET/DELETE | `/api/experiments/*` | [回测任务](06-research-api/experiments.md) |

## 共同约束

- 市场数据与回测均只读服务端配置的已发布历史 Parquet；当前优先使用环境变量 `SVQUANT_DATA_DIR`。用户资产的 CRUD、鉴权和资产引用解析均由 WebApp 负责；ResearchEngine 只接收已解析快照。
- 回测源码、数据读取或执行错误返回 HTTP `200` 并在响应 `error` 中说明；请求体不符合契约或含未知字段时返回 `422`。
- 同步接口会把任务提交给 Manager 后等待 Future；异步接口立即返回 `run_id`。任务状态当前只保存在本进程，重启或多实例部署前需要外部 RunStore。
- Manager 默认最多同时执行 2 个回测，额外排队 8 个；容量可通过 `SVQUANT_EXPERIMENT_MAX_WORKERS` 和 `SVQUANT_EXPERIMENT_MAX_QUEUE_SIZE` 配置。队列满时返回 HTTP `429`。
- 执行用户提交的 Python 源码具有任意代码执行风险；生产环境须使用子进程/容器隔离、资源限制、只读数据目录、无出网权限，并收紧 CORS 和鉴权。

## 回测任务调度

### 同步接口

`POST /api/backtest/factor` 和 `POST /api/backtest/strategy` 仍返回完整结果。
路由本身是异步 HTTP handler：它向 `ExperimentManager` 提交任务，再异步等待 Manager
的 Future。因此 FastAPI/AnyIO 的通用线程池不会执行回测计算。

### 异步接口

```text
POST /api/experiments/factor
POST /api/experiments/strategy
    → 202 {run_id, experiment_type, status}

GET /api/experiments/{run_id}
    → {status, metadata, result}

DELETE /api/experiments/{run_id}
    → 取消排队任务并返回当前状态
```

任务状态为 `created → queued → running → succeeded/failed/cancelled`。已经进入工作线程
的 Python 任务不能被安全强杀，取消请求只能标记 `cancel_requested`；需要硬超时时应切换
到进程或容器执行后端。

相同任务键的并发提交会复用同一个 Future。因子任务键包含请求、数据指纹和缓存版本；
策略任务键用于进程内的同键并发去重。跨 Uvicorn worker 或跨服务实例不共享任务表。

## 包结构

```text
ResearchEngine/researchengine/api/
  app.py               FastAPI 应用工厂 + CORS
  routes.py            HTTP 路由
  ../manager.py        进程级回测任务、线程池和状态管理
  schemas.py           Pydantic 请求/响应模型
  market_data.py       已发布市场数据查询
  runner.py            回测编排
  serializers.py       pandas/指标 → JSON
```

## 与前端的分工

前端负责股票选择、因子/策略资产管理、请求组装、结果展示与持久化；ResearchEngine 仅执行本页索引中的计算或只读数据查询，不保存任何业务状态。
