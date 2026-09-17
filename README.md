# SVQuant

SVQuant 是一站式 AI 量化投研平台。当前投研运行时统一放在
`ResearchEngine/app`，公开 Python 命名空间只有 `app.*`。

## 架构

```text
ResearchEngine/app
├── main.py          # FastAPI 入口与生命周期
├── api              # 控制器
├── models           # 内部数据结构
├── schemas          # HTTP 请求/响应
├── services         # 五个 Engine、实验、批量与目录业务
├── database         # Provider、缓存和持久化
├── utils            # 通用辅助
└── config.py        # 配置
```

QuantCore 的独立共享库边界已取消，研究计算全部属于 ResearchEngine。WebApp 通过 HTTP 调用，
TradingEngine 仍规划中，不预设代码共享。运行时 assets 和 cli 目录保留。
ExperimentManager 保持单进程 FIFO，批量协调器保持两个未完成因子的业务窗口。
具体架构见 [ADR-029](docs/05-技术决策/ADR-029-研究服务采用services与models分层.md)。

## 安装与启动

```bash
pip install -e .
pip install -e ".[api]"

# SSH/生产部署：后台运行，单实例、单 Worker
ResearchEngine/scripts/research-engine.sh start

# 前台调试
python -m uvicorn app.main:app --host 0.0.0.0 --port 9527 --workers 1
# 或
python -m app.main
```

如果通过 SSH 启动，建议使用仓库内的后台控制脚本。它会让进程脱离 SSH 会话，保存 PID，
并把服务输出写入 `ResearchEngine/logs/app.log`：

```bash
ResearchEngine/scripts/research-engine.sh start
ResearchEngine/scripts/research-engine.sh status
ResearchEngine/scripts/research-engine.sh logs
```

常用操作：

```bash
ResearchEngine/scripts/research-engine.sh restart
ResearchEngine/scripts/research-engine.sh stop
ResearchEngine/scripts/research-engine.sh logs --no-follow
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
的接口见 `ResearchEngine/docs/03-功能文档/FEAT-027-因子批量回测/`。

研究代码示例：

```python
from app.services.factor.loader import FactorLoader
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
