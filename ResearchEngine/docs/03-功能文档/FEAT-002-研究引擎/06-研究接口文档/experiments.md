# ExperimentManager 任务调度与因子回测异步契约

> 文档版本：v2.2
> 最后更新：2026-08-19

`ExperimentManager` 是 ResearchEngine 进程内的并发边界。因子回测通过公开任务资源
提交和轮询，策略回测继续使用同步 POST：

```http
POST /api/backtest/factor
GET /api/backtest/factor/{run_id}
DELETE /api/backtest/factor/{run_id}

POST /api/backtest/strategy
```

## 因子任务生命周期

```text
POST /api/backtest/factor
  → 202 + run_id
  → queued
  → running
  → succeeded + result
            或 failed + error
            或 cancelled
```

提交阶段只做 Pydantic 参数校验、请求哈希计算和 Manager 入队。行情数据指纹、缓存扫描、
缓存读取以及实际回测都在线程池工作线程中执行，因此 POST 不等待回测完成。

任务状态查询返回：

```json
{
  "run_id": "uuid",
  "status": "running",
  "created_at": 1720000000.0,
  "started_at": 1720000001.0,
  "finished_at": null,
  "cancel_requested": false,
  "error": null,
  "result": null
}
```

成功时 `result` 是旧版完整 `FactorBacktestResponse`；因子代码、数据和运行时业务错误
统一映射为 `failed`，错误放在顶层 `error`。Future 技术异常也映射为 `failed`。排队任务
取消会释放一个容量槽；运行中取消只设置 `cancel_requested`，不强杀执行用户 Python 代码。

## 容量、去重和结果保留

默认配置为 2 个工作线程和额外 8 个排队槽位。容量是有界的，不能无限增长；队列满时提交
返回 `429`。同一进程内相同请求的并发提交使用请求哈希复用同一个 `run_id`。实际文件缓存
键仍包含缓存版本、请求参数和行情数据指纹，避免数据变更时错误命中。

终态任务保留 60 秒。清理任务会从 Manager 的 `_runs` 中移除任务记录并释放完整回测结果；
过期或未知 `run_id` 查询返回 `404`。WebApp 必须在 1 分钟内取走并持久化成功结果。

## 部署限制

任务状态保存在单个 ResearchEngine 进程内。当前必须使用单个 Uvicorn worker 和单个实例，
确保 POST 返回的 `run_id` 能由后续 GET/DELETE 查询。多 worker 或多实例会产生相互隔离的
Manager、队列和任务表；需要跨进程调度时再引入 Redis/数据库等外部任务系统。
