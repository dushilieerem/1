# ResearchEngine

ResearchEngine 是 SVQuant 的投研应用层。运行时代码全部位于
`ResearchEngine/app`，包名统一为 `app.*`；旧的 `researchengine.*` 和教学入口已移除。

## 分层结构

```text
app/
├── main.py                         # FastAPI 唯一正式入口
├── api/routes/                     # health、catalog、factor、strategy、batch
├── schemas/                        # Pydantic HTTP DTO
├── services/
│   ├── experiment/                 # Experiment 契约、Manager、具体实验
│   ├── factor/                     # 因子回测用例
│   ├── strategy/                   # 策略回测用例
│   ├── catalog/                    # 目录查询用例
│   └── daily_factor_backtest/      # 每日因子这一具体业务能力
├── repositories/                   # 目录、结果和批次持久化边界
├── database/                       # SQLite 与 Parquet 访问边界
├── core/                           # 配置、运行时、异常
├── quantcore/                      # 量化基础设施内层
└── assets/                         # 因子/策略源码与索引
```

依赖方向固定为 `api → services → repositories/database → quantcore`。
`app.quantcore` 不反向依赖 FastAPI、业务 service、repository 或 schemas；Pydantic
只出现在 HTTP 边界。

每日因子回测不是通用 `FactorBatchService`：它由
`DailyFactorBacktestCoordinator` 作为具体业务协调器实现。Manager 保持普通 FIFO；
协调器自己维护最多两个未完成因子，完成一个才提交下一个。交互式任务若已先进入
Manager 队列，会按 FIFO 先于后提交的批量因子执行。

## 启动

在仓库根目录执行：

```bash
pip install -e .
pip install -e ".[api]"

uvicorn app.main:app --workers 1
# 或
python -m app.main
```

当前只支持单实例、单 Worker。FastAPI 进程的 lifespan 负责启动和关闭唯一的
`ExperimentManager`；每日批量协调器复用该 Manager，不创建自己的回测运行时。

## 资产与 API

因子和策略资产位于：

```text
app/assets/factors/libraries/
app/assets/factors/index.yaml
app/assets/strategies/libraries/
app/assets/strategies/index.yaml
```

API 使用 `/api` 契约：

```text
POST /api/backtest/factor
POST /api/backtest/strategy
POST /api/internal/factor-backtests/batches
GET  /api/factor-libraries
GET  /api/strategies
```

每日批量 CLI 只发送 HTTP 请求，不在本地创建 Manager 或执行回测：

```bash
python -m app.cli.factor_batch run --as-of YYYY-MM-DD
python -m app.cli.factor_batch run --as-of YYYY-MM-DD --force-retry
```

批量结果写入 `Factor/database/factor_backtest.db`（可由环境变量覆盖），行情仍由
`app.quantcore` 的 Parquet provider 读取。

## 开发与测试

```bash
pytest ResearchEngine/tests
```

设计文档：

- `docs/04-features/FEAT-002-research-engine/`
- `docs/04-features/FEAT-003-backtest-adapter/`
- `docs/04-features/FEAT-027-daily-factor-backtest/`
- `docs/04-features/FEAT-028-layered-application-architecture/`
