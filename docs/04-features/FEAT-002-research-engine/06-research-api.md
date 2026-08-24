# ResearchEngine HTTP API（FastAPI）

> 文档版本：v2.7
> 最后更新：2026-08-19

ResearchEngine 是研究计算服务：接收代码与参数、执行回测、返回结构化结果；不管理用户、
因子/策略资产或可靠的业务结果历史。每个进程由 `ExperimentManager` 管理回测线程池、
有界队列和内部任务状态；FastAPI 只负责 HTTP 适配，不拥有回测线程池。开发期临时承载的
AI 因子草稿端点只生成并静态校验代码，不执行回测，待 SaaS 应用层具备身份与资产治理后迁出。

## 运行

```bash
pip install -e ".[api]"
uvicorn app.main:app --workers 1
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
| 因子回测任务 | GET | `/api/backtest/factor/{run_id}` | [因子回测](06-research-api/backtest-factor.md) |
| 因子回测任务 | DELETE | `/api/backtest/factor/{run_id}` | [因子回测](06-research-api/backtest-factor.md) |
| 策略资产 | GET | `/api/strategies` | [策略目录](06-research-api/strategy-list.md) |
| 策略回测 | POST | `/api/backtest/strategy` | [策略回测](06-research-api/backtest-strategy.md) |

## 共同约束

- 市场数据与回测均只读服务端配置的已发布历史 Parquet；当前优先使用环境变量 `SVQUANT_DATA_DIR`。用户资产的 CRUD、鉴权和资产引用解析均由 WebApp 负责；ResearchEngine 只接收已解析快照。
- 请求体不符合契约或含未知字段时返回 `422`；队列满时返回 `429`；Manager 已关闭时返回 `503`。
- `POST /api/backtest/factor` 只提交任务并立即返回 `202`、`run_id` 和轮询地址；因子代码、数据读取或执行错误在任务查询中统一表现为 `status=failed` 和 `error`。
- Manager 默认最多同时执行 2 个回测，额外排队 8 个；容量可通过 `SVQUANT_EXPERIMENT_MAX_WORKERS` 和 `SVQUANT_EXPERIMENT_MAX_QUEUE_SIZE` 配置。队列是有界的，不能无限增长。
- 已完成任务在内存中保留 60 秒；单实例模式下，WebApp 应在 1 分钟内取走并持久化完整结果。
- 这是 `/api` 新契约；旧版 WebApp 不能继续把 POST 响应当作完整回测结果，WebApp 适配需单独安排。
- 生产部署使用 `uvicorn app.main:app --workers 1`；不要启动多个 worker 或多个 ResearchEngine 实例。
- 执行用户提交的 Python 源码具有任意代码执行风险；生产环境须使用子进程/容器隔离、资源限制、只读数据目录、无出网权限，并收紧 CORS 和鉴权。

## 回测任务调度

### 异步因子回测

因子回测采用提交、轮询、取结果的任务契约：

```text
POST /api/backtest/factor
        ↓ 202 + run_id
GET /api/backtest/factor/{run_id}
        ↓ queued/running
GET /api/backtest/factor/{run_id}
        ↓ succeeded + result
```

提交响应包含 `Location: /api/backtest/factor/{run_id}` 和 `Retry-After: 1`。WebApp
第一次等待 1 秒，之后可按 2 秒轮询，最高不超过 3 秒；`succeeded` 后持久化 `result`，
`failed` 后展示 `error`。用户重新提交或取消时调用对应的 POST/DELETE。

排队任务 DELETE 后会变为 `cancelled` 并立即释放队列槽位；运行中的 DELETE 只设置
`cancel_requested=true`，用户 Python 代码会继续执行，不能被线程安全地强制终止。

### 策略回测与内部调度

`POST /api/backtest/strategy` 本次保持同步契约，仍等待 Future 并返回完整的
`StrategyBacktestResponse`。两类回测都由 `ExperimentManager` 的专用线程池执行，
不会占用 FastAPI/AnyIO 通用线程池。Manager 内部状态为
`queued → running → succeeded/failed/cancelled`；终态任务 60 秒后清理并释放大结果。

因子任务使用请求哈希进行进程内同请求去重；实际缓存键仍包含缓存版本、请求参数和
行情数据指纹，行情指纹扫描与缓存读取在工作线程中执行。跨 Uvicorn worker 或跨服务实例
不共享内存任务表，因此当前部署必须使用单个 Uvicorn worker 和单个 ResearchEngine 实例。

## 包结构

```text
ResearchEngine/app/
  main.py              FastAPI 应用工厂、lifespan + CORS
  api/routes/           health/catalog/factor/strategy/batch 控制器
  schemas/              Pydantic 请求/响应模型
  services/             实验、因子、策略和因子批量业务
  repositories/         目录、结果和批次持久化边界
  database/             SQLite store
  quantcore/            data/factor/metric/backtest 基础设施
  assets/               因子/策略源码与 index.yaml
```

## 与前端的分工

前端负责股票选择、因子/策略资产管理、请求组装、异步轮询、结果展示与持久化；ResearchEngine
仅执行本页索引中的计算或只读数据查询，不保存超过 60 秒的业务结果历史。
