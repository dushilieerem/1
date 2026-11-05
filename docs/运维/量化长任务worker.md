# 量化长任务 worker

量化候选的研发/样本外复验/对照重试是分钟级任务，默认仍走 API 进程内线程池
（`QUANT_FACTOR_JOB_MODE=inline`）。需要重启恢复或多实例时切换到队列模式：

```bash
# deploy/.env
QUANT_FACTOR_JOB_MODE=queue
```

然后启动 `worker` 服务：

```bash
docker compose -f deploy/compose.yml --env-file deploy/.env up -d worker
```

## 行为

- API 的 `create` / `validate` / `retry_novelty` 不再提交线程池，而是写
  `background_jobs`（`quant.factor.run` / `quant.factor.retry_novelty`）；
- `worker.py` 用 PostgreSQL `SKIP LOCKED` 领取任务，独立进程执行；
- 任务本身仍写回 `quant_factor_candidates`，状态机不变；
- worker 不跑迁移、不启 HTTP；必须在 API 完成迁移后启动。

## 注意

- 只部署 API 不部署 worker 时，不要设 `queue`，否则任务会积压；
- `background_jobs` 里 `quant.factor.*` 的排队/失败数应纳入监控；
- 这是长任务外移的第一步；资讯/面板/模拟盘调度器仍在 API 进程内，后续可复用同一 worker。
