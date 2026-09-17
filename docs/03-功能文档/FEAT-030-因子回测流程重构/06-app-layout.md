# FEAT-030：ResearchEngine 目录与职责修订

- 日期：2026-08-28
- 状态：目录与模型归属迁移完成；528 项全量回归通过，原 FEAT-030 专项验收未全部关闭
- 优先级：P0；所属 INIT-001；本修订是 FEAT-030 的宏观架构纠偏。
- 决策：[ADR-029](../../05-技术决策/ADR-029-研究服务采用services与models分层.md)

## 1. 目标与范围

用户确认采用常规 FastAPI 分层，取消 QuantCore 的跨应用定位。收益是减少重复包装和维护成本，
使业务逻辑与数据模型归属明确；不承诺未经验证的性能或商业收入提升。
本轮只做职责提取、模块迁移和导入调整；不改变因子/策略公式、HTTP 协议、调度规则或存储格式。
不改 WebApp、因子数据库、行情发布、历史结果，不新增 DDD 目录、接口层或占位模型。

## 2. 目标结构与责任表

```text
ResearchEngine/app/
├── main.py
├── api/                 # 路由、FastAPI 依赖与 HTTP 适配
├── schemas/             # Pydantic 请求/响应
├── models/              # 内部数据模型，非仅数据库实体
├── services/            # 引擎、实验、批量、目录和结果管理
│   ├── data/            # DataEngine
│   ├── factor/          # FactorEngine、因子定义/加载/预处理
│   ├── portfolio/       # PortfolioEngine
│   ├── metric/          # MetricEngine、指标计算
│   ├── backtest/        # BacktestEngine
│   ├── strategy/        # 既有向量化/事件策略服务
│   ├── experiment/     # Manager、Experiment（只负责调度）
│   ├── catalog/
│   ├── results/
│   └── factor_backtest_batch/
├── database/            # Provider、缓存、结果存储、SQLite 访问
├── utils/               # 不含回测业务的通用辅助函数
├── config.py
├── assets/              # 保留运行时因子/策略资产
└── cli/                 # 保留命令行入口
```

| 现有内容 | 新归属 | 判断依据 |
|---|---|---|
| Data/Factor/Portfolio/Metric Engine | services 对应业务包 | 读取协调、计算和处理流程 |
| BacktestEngine、ExperimentManager、Experiment | services | 完整用例与任务管理 |
| Panel、IndexPanel | models/data.py | 面板字段访问与惰性视图，不管理 provider 生命周期 |
| MetricContext | models/metric.py | 指标计算输入 |
| FactorBacktestSpec/FactorBacktestResult | models/factor_backtest.py | 配置、结果与纯身份计算 |
| 旧配置到 Spec 的转换 | services/factor | 环境配置适配不能混入数据模型 |
| ExperimentStatus | models | 任务状态；数据 release 由全局 DataEngine 表达 |
| BaseFactor/FactorLibrary、BaseMetric、计算 backend | services/factor、services/metric | 可执行扩展契约及逻辑，不是单纯 DTO |
| BacktestConfig/Signals/Result、EventOrder/Fill/Config/Result | models | 仅策略路径继续使用的数据契约 |
| Native/Event 实现及策略实现 | services/strategy | 保留既有行为，不混入因子 BacktestEngine |
| Provider、字段缓存 | database/data | 具体数据访问及缓存资源 |
| ResultStorage、FileBacktestCache、FactorBacktestRepository/Store | database | 存取实现，历史表结构不变 |
| ResultManager | services/results | 结果组织、保存协调和绘图 |
| ResultData | models/results.py | 纯结果字段；存储读取返回数据，不反向构造 service |
| 因子 loader、目录发现/查询 | services/factor、services/catalog | 业务资产加载与编译，不是数据库连接 |
| ConfigManager | config.py | 配置读取 |
| 通用异常、日期切片和可选依赖导入 | utils | 通用辅助；分组/指标公式仍属于 service |

不为尚不存在的 PortfolioResult 等类型新增空类；现有 DataFrame 和映射继续使用。
models 的服务类型注解可使用 TYPE_CHECKING，但运行时不得反向导入 services、api、schemas、database。
`ResultStorage.read()` 返回 ResultData；需要继续保存、调用管理方法时使用 `ResultManager.load()`。
已删除旧 `FactorExperiment` 和 `services/factor/spec.py` 的兼容配置适配。Python、HTTP 和
批量入口统一构造 `FactorBacktestSpec` 并提交 `FactorBacktestExperiment`，不再接受内存
`BaseFactor` 作为回测请求输入。项目/资产路径统一由 `utils/paths.py` 提供。
Pydantic HTTP 模型继续留在 schemas；已有 service 的 HTTP 投影辅助本轮保持兼容，不据此宣称 DTO 解耦全部完成。

## 3. 调用和生命周期

api → services；services 使用 models，并在需要时调用 database；database 使用底层依赖和 models。
utils 不依赖 api/services；models 不负责 I/O。`main.py` 负责 FastAPI 与 Manager 的组装。
实际调用不是“MetricEngine 执行完再去 database”：DataEngine 在读取时调用 Provider，结果在计算后保存。

保持单 Uvicorn worker、进程级 Manager、固定 release 的只读数据共享。DataEngine 无任务状态；
FactorEngine 的注册表和因子面板、PortfolioEngine 和 MetricEngine 的任务结果不跨实验共享。
本轮不增加进程、不把所有 Engine 做成单例，也不为每个实验复制整套行情。

## 4. 实施计划

| 步骤 | 工作 | 复杂度 | 估计人天 | 风险 | 依赖 |
|---|---|---:|---:|---|---|
| R1 | 依赖清单、修订文档、迁移前测试 | 3 | 0.5 | 中 | 用户结构确认 |
| R2 | 模型提取与服务/数据访问迁移、导入接线 | 4 | 1.5 | 高 | R1 |
| R3 | 动态源码/资源路径/依赖边界、全量回归及文档 | 4 | 1 | 高 | R2 |

合计约 3 人天，为原 M5 前追加的架构纠偏估计，不是已经完成的工时或上线承诺。
负责人：ResearchEngine 实施者；用户最终验收。先完成模型提取，再迁移服务及调用方，最后验证。
迁移脚本仅生成定点补丁，不清理用户未提交改动；迁移前逐符号检查影响。

R1–R3 的本轮实现及自动化验证已完成，实际记录见 [Verification §1.2](05-verification.md#12-servicesmodels-目录修订验证adr-029)。
旧包的忽略缓存目录因清理受限而保留，不含 Python 源码，不作为运行时兼容包。

## 5. 验收与风险

- app 不再包含 quantcore、domain、application、infrastructure、core、repositories 运行时包。
- 五个 Engine 在 services 定义，现有模型各有唯一的 models 定义；不要以空壳兼容包伪装迁移完成。
- 所有现有入口、内置资产、动态代码模板和测试采用新路径；保留函数/类名及数值期望。
- models 无运行时服务/HTTP/存储依赖；配置适配移到 service；新增架构检查覆盖这些边界。
- 全量 ResearchEngine 测试使用 svquant 环境，记录真实结果；不得沿用迁移前 523 passed 当新证据。
- Python 外部用户需要修改导入；HTTP 请求响应不变。配置默认路径和 assets 路径不能因文件深度变化而漂移。
- API 内原有 AI 业务辅助和 service 内响应投影若未在本轮拆分，明确保留现状，避免无边界扩大迁移。
- 不修改数据库内容、WebApp、调度算法与执行/缓存版本。外部保存的旧 Python 源码导入需调用方迁移。

发布仍要求停收新任务、等待在途任务结束，再切换已验收版本。回滚部署上一已验收版本，
不重置工作区，不删除历史数据库/行情/输出。原 FEAT-030 尚未关闭的数值与资源验收仍保持未完成。
