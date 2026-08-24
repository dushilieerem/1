# SVQuant

SVQuant 是一站式 AI 量化投研平台。当前投研运行时统一放在
`ResearchEngine/app`，公开 Python 命名空间只有 `app.*`。

## 架构

```text
FastAPI app.main
    └── api/routes        HTTP 参数与响应适配
        └── services      Experiment、因子/策略回测、因子批量回测业务
            └── repositories/database
                └── app.quantcore   数据、因子、指标、回测基础设施
```

- `app.main` 是唯一正式 FastAPI 入口。
- `app.quantcore` 不依赖 FastAPI、schemas 或业务 service。
- 因子和策略资产位于 `app.assets`，SQLite 结果通过 repository 访问。
- `Experiment` 是抽象基类；具体实验为 `FactorExperiment`、`StrategyExperiment`
  和因子批量回测业务中的 `FactorBacktestBatchExperiment`。
- `ExperimentManager` 只有一个普通 FIFO 队列。因子批量业务自己维护容量为 2
  的批量窗口，只有一个批量因子进入终态后才提交下一个。

## 安装与启动

```bash
pip install -e .
pip install -e ".[api]"

# 生产/内网部署：单实例、单 Worker
python -m uvicorn app.main:app --host 0.0.0.0 --port 9527 --workers 1
# 或
python -m app.main
```

不支持多 Uvicorn Worker 或多实例部署，因为当前进程内只有一个
`ExperimentManager` 和一个行情运行时。

## 因子与批量回测

因子源码和索引分别位于：

```text
ResearchEngine/app/assets/factors/libraries/
ResearchEngine/app/assets/factors/index.yaml
```

批量回测由可信内网中的 FastAPI 进程执行，CLI 只是 HTTP 客户端：

```bash
python -m app.cli.factor_backtest_batch run --as-of YYYY-MM-DD
python -m app.cli.factor_backtest_batch run --as-of YYYY-MM-DD --force-retry
python -m app.cli.factor_backtest_batch run --as-of YYYY-MM-DD --dry-run
python -m app.cli.factor_backtest_batch run --as-of YYYY-MM-DD --wait
```

API 契约使用 `/api`，批量触发接口为
`POST /api/internal/factor-backtest-batches`；任务查询和批次、因子明细、历史结果
的接口见 `docs/04-features/FEAT-027-factor-backtest-batch/`。

研究代码示例：

```python
from app.repositories.catalogs.factor_loader import FactorLoader
from app.services.experiment import FactorExperiment, ExperimentManager

loader = FactorLoader()
loader.load("momentum_lib")
experiment = FactorExperiment(loader.factors["momentum_5d"])

with ExperimentManager(max_workers=2) as manager:
    result = manager.submit(experiment).result()
    print(result.summary())
```

实验不自行创建 `DataEngine` 或 `ExperimentManager`；行情上下文由 Manager 注入。

## 测试

```bash
pytest
pytest ResearchEngine/tests
```

完整产品、架构和交付文档入口：`docs/README.md`。
