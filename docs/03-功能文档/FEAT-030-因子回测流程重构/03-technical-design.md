# FEAT-030：因子回测流程重构 — Technical Design

- 状态：开发中（主链已实施，专项验收中）
- 日期：2026-08-28
- 关联：[需求](02-product-requirements.md)、[实施计划](04-project-plan.md)、[ADR-028](../../05-技术决策/ADR-028-因子回测由BacktestEngine编排四引擎.md)

## 1. 当前实现与重构目标

重构前的代码经过以下路径，作为迁移基线保留：

```text
API / 批量 / Python
  → FactorBacktestSpec
  → FactorBacktestExperiment
  → FactorBacktestExecutor.execute
  → _FactorBacktestAlgorithm.run
    → DataEngine / FactorEngine
    → 应用层过滤和预处理
    → FactorQuantileStrategy / FactorGroupStrategy
    → BacktestSignals → NativeEngine → adapter BacktestResult
    → MetricEngine + 应用层分层/预测性/基准分析
 → FactorBacktestResult / ResultManager
```

当前代码路径已切换为：

```text
API / 批量 / Python
  → FactorBacktestSpec
  → FactorBacktestExperiment
  → BacktestEngine.run
    → DataEngine：行情、股票池、可选筛选掩码和告警
    → FactorEngine：因子计算、有效池、去极值、标准化
    → PortfolioEngine：分组、权重、持仓、前瞻收益对齐
    → MetricEngine：收益、净值、指标、分层和扩展评价
  → FactorBacktestResult / ResultManager
```

旧 `FactorBacktestExecutor` 已删除；`FactorBacktestExperiment` 只负责实现 Experiment
任务契约并直接调用 BacktestEngine，策略回测仍使用 services/strategy 下的 Native/Event 组件。

目标为一个具体 BacktestEngine 组织四个责任引擎。新 run 必须直接调用各阶段能力，
不得继续委托旧 Executor、_FactorBacktestAlgorithm 或 NativeEngine 完成因子回测。

| 范围 | 重构前基线 | 当前实现 |
|---|---|---|
| 完整计算入口 | FactorBacktestExecutor.execute | BacktestEngine.run |
| 筛选条件 | 应用层 _apply_factor_batch_filters | DataEngine 生成掩码与诊断 |
| 因子预处理 | 应用层直接调用 factor.tool | FactorEngine 统一计算和加工 |
| 组合构建 | 分位/分组策略包装和分层辅助函数 | PortfolioEngine |
| 效果计算 | NativeEngine、MetricEngine、应用辅助模块 | MetricEngine |
| 执行/缓存版本 | factor-execution-v2 / factor-backtest-v9 | factor-execution-v4 / factor-backtest-v10 |
| 指标公式版本 | factor-scorecard-v2 | 保持 factor-scorecard-v2 |
| 数据库 | 现有批量历史 schema | 不变，不清理历史 |

## 2. 模块位置与依赖方向

用户已修订本节，见 [ADR-029](../../05-技术决策/ADR-029-研究服务采用services与models分层.md) 和
[目录与职责修订](06-app-layout.md)。取消 QuantCore 包，位置为：

- BacktestEngine：`ResearchEngine/app/services/backtest/engine.py`。
- 四个责任引擎：`ResearchEngine/app/services/{data,factor,portfolio,metric}/engine.py`。
- 内部数据模型：`ResearchEngine/app/models/`；Provider、缓存和存储：`ResearchEngine/app/database/`。
- 配置：`ResearchEngine/app/config.py`；通用工具：`ResearchEngine/app/utils/`。

```text
API / CLI / Python
        ↓
ExperimentManager → FactorBacktestExperiment
                                   ↓
                          BacktestEngine（services）
                                   ↓
               DataEngine / FactorEngine / PortfolioEngine / MetricEngine
                                （services）
```

api 控制器调用 services；services 使用 models 和 database；models 不在运行时依赖服务、
HTTP 或存储。schemas 继续负责 Pydantic HTTP 请求/响应，业务计算不迁入 schemas。
这是 ResearchEngine 的内部组织，不是全 SVQuant 的共享量化库。

不新增 IBacktestEngine、NativeBacktestEngine、Simulator 或通用工作流框架。
策略侧已有 IBacktestEngine 等接口属于未迁移链路，保留不等于新因子引擎依赖它们。

### 生命周期

FastAPI 应用持有固定 release 的 DataEngine；Manager 只注入该快照。每次实验使用独立的
FactorEngine、PortfolioEngine、MetricEngine 及中间结果；BacktestEngine 不在并发任务之间
保存可变的 spec、close、掩码或因子注册状态。共享 provider 返回的数据按只读输入处理，
加工阶段只修改自己产生的结果。

缓存、去重、重试及业务窗口不迁入 BacktestEngine。文件保存、CSV/Parquet 输出、绘图与
HTTP/SQLite 投影仍在应用层计算完成后处理，复用既有 ResultManager 和输出组件。

## 3. 核心输入输出

### BacktestEngine

统一公开入口：

```python
BacktestEngine.run(spec: FactorBacktestSpec, context: ExperimentContext) -> FactorBacktestResult
```

保留现有因子来源/源码哈希、日期、股票池、基准、分组、调仓、费用和分析级别语义。
因子解析由 `FactorEngine(spec)` 初始化时私有完成：它依据因子名、
因子库和因子代码调用 FactorEngine 的默认/注入式 loader，并把解析结果保存为本次引擎实例的
`self._factor`。`FactorBacktestSpec` 不携带 `BaseFactor`，BacktestEngine 也不读取原始因子对象。
文件/代码 loader 保持现有行为；
FEAT-029 的数据库来源切换不在本期实现。

run 负责调用四引擎、整理 provenance、组装结果并映射已有领域错误。FactorEngine 记录
运行时 `actual_end`，但不修改原始 Spec。
不直接实现分组、收益或指标公式，不获取新的 provider，不重复扫描行情来创建第二套上下文。

### DataEngine

沿用 get_panels、get_universe_at、get_index 等读取接口，增加数据源无关的
build_filter_mask 能力，返回有效性掩码、过滤状态和告警。辅助数据读取也通过 DataEngine /
provider 完成；不要求所有 provider 新增强制抽象方法，不在 MetricEngine 中读取文件。

| 输出 | 语义 |
|---|---|
| 行情面板及 close | `start/end` 范围内的日期 × 股票，升序统一交易日索引，保持原始精度和缺失位置 |
| universe / benchmark 数据 | 沿用当前命名股票池及自定义快照语义；股票池仍按既有规则解析 |
| eligible_mask | 与行情可对齐的布尔面板；true 表示当日允许进入研究样本 |
| filter_status / warnings | 请求状态、实际应用情况、缺失字段或覆盖不足原因 |

build_filter_mask 不修改行情，不保存任务配置。两项过滤均关闭时输出全允许掩码，
不为过滤额外读取状态字段。当前版本不提供独立的 `is_suspended` 字段，停牌过滤所需字段
缺失时按放行处理；涨跌停统一读取 `up_and_down_status` 原始文本判断，避免把状态字段
静默映射成不存在的布尔字段。

### FactorEngine

保留 `load_factor`、`compute_panel` 及现有注册/后端接口。主链由
`FactorEngine(spec)` 根据规格中的 `factor_name`、
`library_names` 和 `factor_code` 加载或生成因子，并写入本次实例私有的 `self._factor`；
BacktestEngine 不再实现因子来源判断或持有原始因子对象。另增加统一的 `preprocess` 入口，
接收因子面板、eligible_mask、winsorize、standardize，输出处理后的 DataFrame。

固定顺序：

```text
按 spec 的 start/end 读取数据并计算因子（不补读预热历史）
  → 对齐并应用 DataEngine 的 eligible_mask
  → winsorize（0 跳过）
  → standardize（0 跳过）
  → 裁剪评价区间
```

factor.tool 保持纯函数并由 FactorEngine 复用。已有中性化工具及策略静态方法兼容能力保留，
但本期不增加中性化的回测请求配置。应用入口不再自行调用预处理函数拼装流程。

### PortfolioEngine

接收处理后的因子面板、完整索引 close 及组合配置，通过 build 产生普通映射；
不返回 BacktestSignals，不实例化 FactorGroupStrategy / FactorQuantileStrategy。

输出至少包括：

| 数据 | 用途 |
|---|---|
| factor_values | 处理后的原始数值，用于 IC/RankIC；不被分组编号覆盖 |
| group_assignments | 同形状组号面板，Q1 为最高组 |
| 组合/分组权重与持仓信息 | 由组合规则确定；MetricEngine 不重新选股或决定调仓 |
| rebalance_logs | 组合调整意图，用于现有输出投影；不标记为真实成交 |
| forward_returns | 信号日索引上的远期收益评价标签 |
| close / 日期对齐信息 | 保留用于日收益及现有缺失值口径，不重新读行情 |

权重仍是必要数据，但不沿用旧信号包装体系。沿用当前 qcut、重复边界及退化截面处理，
不引入新的排名/分组算法；支持既有分组及 Python 分位组合能力。相同因子分组只计算一次，
组合和分层评价复用。full 分析的行业、市值等不同分组依据另行处理，不混用因子组号。

组合可以根据截至当日的信息生成；不能根据 forward_returns 是否存在决定选股、成员数、
权重分母或调仓日期。不能把评价数据内连接后的股票集反向写回组合。

### MetricEngine

保留 register、calculate、calculate_all 等既有接口和返回约定，新增 evaluate 完整评价入口。
evaluate 消费组合、行情/前瞻评价数据及参数，返回普通映射：

- 主组合收益、展示净值、交易成本及换手等统计；
- 交易评价摘要包含按权重变化计数的调仓意图次数、总换手、佣金、印花税、滑点和总成本；
  其中调仓意图次数不等同于事件引擎的真实成交笔数；
- 分组收益、分组展示净值、基准及相对基准指标；
- IC、RankIC、ICIR、core/full 分析数据和现有扩展评价；
- 供序列化及绘图使用的年度、回撤等预计算结果。

复用现有 MetricContext，按需要增加可选数据，不引入新的结果类继承体系。
持仓与调仓决策由 PortfolioEngine 提供，MetricEngine 只评价，不生成订单或修改组合。
指标公式归入 services/metric；应用层残留函数只能投影/兼容委托，不能保留第二份公式。

## 4. 价格、收益与处理顺序

### 时间轴与 as-of

- `start/end` 是因子计算、组合与评价的完整数据边界；不读取 start 前预热历史，实际可用数据上界单独记录为 `actual_end`。
- 本次 complete close 指交易日索引完整，并不表示价格一定非空；不补造缺失价格。
- 计算远期收益前不能删掉停牌/涨停日期、先 dropna 或按股票压缩时间轴。
- 因子值与前瞻收益按信号日对应，持仓收益及展示曲线按收益实现日对应。

默认一期远期收益：

```python
forward_returns = close.shift(-horizon) / close - 1
```

PortfolioEngine 先在未因筛选而压缩的价格索引上计算，再对齐因子日期及股票。默认 horizon=1；
已有多期标签能力不得直接用于每日净值复利。尾部不足 horizon 的标签保持缺失，仅从相关
评价样本中排除；不向 end 之后读取数据补齐。

### 保留的收益约定

t 日收盘形成的组合承担 t → t+1 收盘收益；结果收益索引落在 t+1。收益序列保留首期收益，
展示净值首个输出点归一为 1，之后按当前规则累计。此约定描述研究评价口径，不承诺
使用收盘数据计算出的信号一定可以在同一收盘价真实成交。

纯价格小样例：价格 100、110、121、133.1，持续全仓，零成本。

| 实现日期 | 原始组合收益 | 展示净值 |
|---|---:|---:|
| 第二个交易日 | 0.10 | 1.00 |
| 第三个交易日 | 0.10 | 1.10 |
| 第四个交易日 | 0.10 | 1.21 |

MetricEngine 不从展示净值反推并覆盖首期原始收益。核心/分组/基准的既有样本处理、费用和
统计参数由 M1 冻结；本期不借迁移统一原本不同的公式。发现旧费用接线或缺失值问题，
记录差异并另行审核，不自动“修正”后宣称与旧版一致。

## 5. 参数、诊断及对外兼容

### 默认值和入口归一化

单次请求、FactorBacktestSpec、Python 默认配置及批量 Profile 的两项过滤默认 false，
winsorize/standardize 默认 0。已有部署显式配置仍有效，不用新默认覆盖显式选择。

旧 filters_enabled 总开关只在兼容入口消解：显式 false 关闭两项；其他情况下使用各自
布尔值，不能因为总开关为 true 就自动开启某项。核心引擎只接收最终明确布尔值。
全局 backtest.engine 配置仍可服务策略侧；因子链路不再据此选择 Native/Event 后端。

批量触发请求兼容新增以下四字段，CLI 提供同名语义的显式选项：

| HTTP/Profile 字段 | CLI 选项 | 默认 |
|---|---|---|
| filter_suspended | --filter-suspended | false |
| filter_limit_up | --filter-limit-up | false |
| winsorize | --winsorize，取值 0–3 | 0 |
| standardize | --standardize，取值 0–3 | 0 |

不改变其余批量固定研究配置、路径、异步 202/轮询模式或窗口大小。

### 告警行为

缺少可选状态字段时继续回测；部分状态缺失时已知部分生效、未知部分沿用放行。
filter_status 表达每项是否请求、完整/部分应用或跳过，以及原因；warnings 包含可定位信息。
日志按任务及过滤项汇总，避免逐股票刷屏。

在现有 FactorBacktestMeta 中兼容增加 filter_status 和 warnings；同一内容写入
ResultManager.meta、标准缓存报告和批量当次任务摘要。现有 requested 过滤布尔字段保留，
实际状态以新增诊断为准。缓存恢复路径必须原样保留诊断。

不增加 SQLite 列，不将告警塞进 error_code/error_message 冒充失败，不把实际状态混入
不可变的请求 Profile。历史查询不返回未持久化的诊断，文档明确此限制。

### 结果和公式边界

高层 FactorBacktestResult 保留，继续向 API、Python 和批量提供统一结果；只有低层
adapter BacktestResult 从因子链路移除。API 模型、ResultManager 的保存职责、绘图及
数据库投影不进入内部 models 或计算公式。

core/full 现有可选分析在数据不满足时沿用降级规则，并记录原因；核心缺少 close 或
没有有效评价区间仍失败，不能以“可选”名义返回空成功。

## 6. 迁移与版本

1. 审核通过后，冻结当前源码和显式参数基准，保留已有未提交改动。
2. 迁移 Data/Factor 职责，新增 PortfolioEngine 与 MetricEngine.evaluate，独立验证。
3. BacktestEngine 接入四引擎；两个现有因子 Experiment 只调整内部委托，不改变 Manager。
4. API、批量和 Python 全部切到该入口，更新配置、诊断、序列化、缓存和绘图接线。
5. 因子专属旧 Executor、算法及策略包装在调用方迁移后移除；共享旧 adapter 和策略接口暂留。
   已有公共辅助函数若必须保留，只能薄委托新能力，不继续走旧因子主链。
6. 移除计算重复实现并执行完整验收，最后更新当前实现文档。

新执行身份使用 factor-execution-v4，文件缓存使用 factor-backtest-v10，metric_version 仍为
factor-scorecard-v2。Spec、缓存键、批次身份、去重和断点续跑必须使用相同版本来源，
避免残留硬编码 v2。配置、源码、release 和执行版本参与身份；耗时、告警文本、保存路径不
作为计算参数。告警依赖的数据可用性由固定 release 约束。

不删除旧缓存或批量历史，不执行 ADR-025 原阶段的数据库清理步骤。新旧执行结果按版本
区分；新代码不能把旧完成批次视作新版本已经完成。

## 7. 验证、影响与回滚

2026-08-28 规划阶段已运行七组相关旧实现测试，共 82 passed，具体命令及边界见
[Verification](05-verification.md)。该结果不能代替新实现测试。

规划阶段 GitNexus 的类级依赖分析为 MEDIUM：Executor 涉及 API、批量、Python 和测试；
DataEngine/MetricEngine 经公共导出影响其他服务。索引日期为 2026-08-26，早于工作区
部分修改，因此它只是依赖线索，空 process 列表不代表没有流程影响。实现前刷新/核对索引，
逐符号 impact；HIGH/CRITICAL 必须先报告，提交前 detect_changes。

验收覆盖需求 AC-01–AC-12，数值只允许默认过滤关闭、有效池先于预处理及新增告警的差异。
其他差异须返回审核，不通过改期望值掩盖。

上线前停止接收新任务、等待在途任务结束，再单次切换已验收版本；不长期维护双套因子
计算路径。回滚部署上一已验收代码/配置版本，保留数据库、缓存和原有未提交工作。
由于 schema 不变，无须恢复或删除数据库。详细发布关卡见 [Project Plan](04-project-plan.md)。
