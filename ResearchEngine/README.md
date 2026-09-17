# ResearchEngine

ResearchEngine 是 SVQuant 的投研应用层。运行时代码全部位于
`ResearchEngine/app`，包名统一为 `app.*`；旧的 `researchengine.*` 和教学入口已移除。

## 分层结构

```text
ResearchEngine/app/
├── main.py                         # FastAPI 入口、生命周期和依赖组装
├── api/                            # 路由与控制器
├── models/                         # 面板、配置、结果、上下文和状态
├── schemas/                        # HTTP 请求/响应
├── services/
│   ├── data/                       # DataEngine
│   ├── factor/                     # FactorEngine、加载和预处理
│   ├── portfolio/                  # PortfolioEngine
│   ├── metric/                     # MetricEngine
│   ├── backtest/                   # BacktestEngine
│   ├── experiment/                 # Experiment、Manager、runtime
│   ├── strategy/                   # 既有向量化/事件策略计算
│   ├── catalog/                    # 资产目录业务
│   ├── results/                    # ResultManager
│   └── factor_backtest_batch/      # 批量协调和任务注册表
├── database/                       # Provider、缓存、存储、SQLite 访问
├── utils/                          # 通用工具、异常和路径
├── config.py                       # ConfigManager
├── assets/                         # 策略资产；因子旧源码仅作迁移兼容
└── cli/                            # 现有命令行入口
```

五个 Engine 属于 services；面板、回测规格/结果及上下文属于 models；数据读取和保存属于 database。
配置使用 app.config，通用辅助位于 utils，不保留 QuantCore、core、repositories 包。
内部导入路径已调整；HTTP、行情/数据库格式和回测公式保持不变。

因子批量回测不是通用 `FactorBatchService`：它由
`FactorBacktestBatchCoordinator` 作为具体业务协调器实现。Manager 保持普通 FIFO；
协调器自己维护最多两个未完成因子，完成一个才提交下一个。协调器按请求创建，
不保存跨请求状态；异步任务由独立单线程注册表编排。交互式任务若已先进入
Manager 队列，会按 FIFO 先于后提交的批量因子执行。

## 启动

在仓库根目录执行：

```bash
pip install -e .
pip install -e ".[api]"

# SSH/生产部署：后台运行，单实例、单 Worker
ResearchEngine/scripts/research-engine.sh start

# 前台调试
uvicorn app.main:app --workers 1
# 或
python -m app.main
```

通过 SSH 部署时使用仓库根目录的后台控制脚本，避免 SSH 断开后进程收到挂断信号：

```bash
ResearchEngine/scripts/research-engine.sh start
ResearchEngine/scripts/research-engine.sh status
ResearchEngine/scripts/research-engine.sh logs
```

日志默认写入 `ResearchEngine/logs/app.log`，PID 默认写入
`ResearchEngine/run/app.pid`。停止、重启和查看最近日志：

```bash
ResearchEngine/scripts/research-engine.sh stop
ResearchEngine/scripts/research-engine.sh restart
ResearchEngine/scripts/research-engine.sh logs --no-follow
```

当前只支持单实例、单 Worker。FastAPI 进程的 lifespan 负责启动和关闭唯一的
`ExperimentManager`；批量协调器复用该 Manager，不创建自己的回测运行时。应用关闭时先
等待批量任务注册表，再关闭 Manager；启动 FastAPI 不会自动执行批量回测。

## 资产与 API

策略资产位于：

```text
app/assets/strategies/libraries/
app/assets/strategies/index.yaml
```

内置因子运行时使用项目内 SQLite 因子库和公共算子模块：

```text
app/assets/factors/factor_library.db
app/assets/factors/tool.py
```

可分别通过 `SVQUANT_FACTOR_DB_PATH`、`SVQUANT_FACTOR_TOOL_PATH` 覆盖路径。
旧的 `app/assets/factors/index.yaml` 与 `libraries/*.py` 已废弃，不参与默认目录、回测和批量任务；
旧加载器仅保留迁移期兼容。
因子目录 API 使用数据库中的 `sv_id` 作为稳定因子标识，同时保留中文名、英文名和源码函数名
作为加载别名。

API 使用 `/api` 契约：

```text
POST /api/backtest/factor
POST /api/backtest/strategy
POST /api/internal/factor-backtest-batches
GET  /api/factor-backtest-batch-tasks/{task_id}
GET  /api/factor-backtest-batches
GET  /api/factor-libraries
GET  /api/strategies
```

批量 CLI 只发送 HTTP 请求，不在本地创建 Manager 或执行回测：

```bash
python -m app.cli.factor_backtest_batch run --as-of YYYY-MM-DD
python -m app.cli.factor_backtest_batch run --as-of YYYY-MM-DD --force-retry
python -m app.cli.factor_backtest_batch run --as-of YYYY-MM-DD --wait
```

批量结果写入 `app/assets/factors/factor_backtest.db`（可由环境变量覆盖），行情仍由
`app.database.data.providers` 的 Parquet provider 读取。

## 开发与测试

```bash
pytest ResearchEngine/tests
```

设计文档：

- `ResearchEngine/docs/03-功能文档/FEAT-002-研究引擎/`
- `../docs/03-功能文档/FEAT-003-回测适配层/`
- `ResearchEngine/docs/03-功能文档/FEAT-027-因子批量回测/`
- `ResearchEngine/docs/03-功能文档/FEAT-028-分层应用架构/`
- `ResearchEngine/docs/02-架构文档/researchengine_architecture.md`
