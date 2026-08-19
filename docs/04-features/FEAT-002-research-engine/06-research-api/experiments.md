# 回测任务 API

ResearchEngine 的异步任务接口由进程级 `ExperimentManager` 管理。接口只返回任务标识，
不会创建 FastAPI 自己的回测线程。

## 提交因子回测

```http
POST /api/experiments/factor
```

请求体与 [`POST /api/backtest/factor`](backtest-factor.md) 相同。

```json
{
  "run_id": "7c2...",
  "experiment_type": "factor",
  "status": "queued",
  "metadata": {"type": "factor", "cache": "MISS"}
}
```

## 提交策略回测

```http
POST /api/experiments/strategy
```

请求体与 [`POST /api/backtest/strategy`](backtest-strategy.md) 相同，返回的
`experiment_type` 为 `strategy`。

## 查询任务

```http
GET /api/experiments/{run_id}
```

状态包括：

- `queued`：已进入 Manager 的有界队列；
- `running`：已由 Manager 工作线程开始执行；
- `succeeded`：结果位于 `result`；
- `failed`：执行失败，错误摘要位于 `error`；
- `cancelled`：任务尚未开始时被取消。

完成后的 `result` 与同步接口的响应结构一致。

## 取消任务

```http
DELETE /api/experiments/{run_id}
```

尚未开始执行的任务可以真正取消。已经运行的 Python 线程不能安全强杀，接口会返回
`cancel_requested: true`，但任务仍可能完成。

## 部署限制

`run_id`、Future 和任务状态当前保存在单个 ResearchEngine 进程内。Uvicorn 多 worker
会为每个 worker 创建独立的 Manager；多实例部署需要外部 RunStore、分布式队列和结果存储。
