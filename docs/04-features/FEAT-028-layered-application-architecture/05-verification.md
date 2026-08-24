# Verification：ResearchEngine 分层应用架构

## 自动化验证矩阵

| 验收项 | 验证方式 |
|---|---|
| `app.main` 生命周期 | `tests/api/test_v2_contract.py` |
| Experiment 抽象和 callable 拒绝 | `tests/services/test_experiment_contract.py` |
| Manager 普通 FIFO、容量和取消 | `tests/test_experiment_manager.py` |
| 批量两槽窗口和交互任务先到先执行 | `tests/services/test_factor_backtest_batch_queue.py` |
| SQLite repository 边界 | `tests/repositories/test_factor_backtest_repository.py`、`test_factor_batch.py` |
| 因子/策略资产索引 | `tests/assets/test_asset_namespace.py`、既有库测试 |
| API 响应契约 | `tests/test_api.py`、`test_factor_backtest_async.py` |
| QuantCore 结果与指标回归 | `tests/quantcore/`、ResearchEngine 因子/策略测试 |

## 交付命令

```bash
pip install -e .
uvicorn app.main:app --workers 1
pytest
```

启动验证必须确认：

1. `app.main:app` 可导入并可打开 `/api/health`；
2. lifespan 结束后 Manager/runtime 已关闭；
3. API 源码不直接导入 QuantCore 或 SQLite；
4. QuantCore 源码不导入 FastAPI、schemas、services 或 repositories；
5. 全量扫描不再发现旧 `researchengine.*`、`quantcore.*`、examples 工作流或
   旧式基于关键字参数的 `Experiment` 构造。
