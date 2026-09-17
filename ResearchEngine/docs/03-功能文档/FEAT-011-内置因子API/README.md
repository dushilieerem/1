# FEAT-011：内置因子库回测 API

> [FEAT-030 已批准变更](../../../../docs/03-功能文档/FEAT-030-因子回测流程重构/README.md) 保留内置/自定义因子来源契约，
> 回测改为统一 BacktestEngine；停牌/涨停过滤默认关闭、可独立开启，并返回实际过滤状态及告警。
> 因子主链已切换；本期不迁移因子数据库、不修改 WebApp；以下来源功能设计继续保留。

- 状态：开发中
- 所属 Initiative：INIT-001 投研核心
- 所属能力：因子研究 / 研究 API
- 优先级：P0

区分内置因子库与用户自定义因子的回测请求：内置因子由服务端完整加载库文件；用户因子继续只提交单个函数源码，并可声明一个或多个内置库，使组合函数直接调用 `self.<内置因子>()`。

## 1. 价值与范围

内置因子常依赖同库的私有辅助方法。前端若只提交被选中的公开函数，服务端生成的临时类缺失这些辅助方法而失败。MVP 增加 `library_name`，使内置因子以“库名 + 因子名”回测；保留 `factor_code` 的单函数自定义因子体验。

必须做：两种来源二选一校验、基于 `Factor/libraries/index.yaml` 的内置库注册、回归测试与 API 文档更新。

明确不做：前端拼接函数依赖、执行任意模块、改变自定义因子的模板协议。

## 2. 业务规则与场景

### 规则

- 未提供 `factor_code` 时，必须提供单个 `library_name`；服务端加载完整库后按 `factor_name` 取因子。
- 提供 `factor_code` 时，用户只提交一个因子函数，服务端生成 `FactorLibrary` 模板；可选传一个或多个 `library_name`，使函数直接调用相应内置因子方法。
- `library_name` 仅能是服务端登记的内置库；多库组合的因子方法名不得重名。
- 未提供来源，或直接执行内置因子时传多个库名，返回 HTTP 422。

### 验收

1. `risk_indicators` 中依赖 `_returns` 的 `kurtosis60` 可只凭库名和因子名完成回测。
2. 自定义 `combo_factor` 可在同一函数内调用 `self.kurtosis20()` 与 `self.alpha158_kmid()` 并成功回测。
3. 现有单函数自定义因子请求保持成功；未登记库名、未知因子名返回可读业务错误，不能导入任意模块。

## 3. 方案设计

> 2026-08-28 架构修订：用户已确认 ADR-029 的常规 FastAPI 分层。
> 原 QuantCore 运行时边界取消；五个 Engine 的业务逻辑进入 `app.services`，
> Panel、MetricContext、回测规格/结果和实验上下文进入 `app.models`，数据访问进入 `app.database`。
> 配置为 `app.config`，通用工具为 `app.utils`；不增加 domain/application/infrastructure。
> 下文中的旧目录和旧分层仅作历史设计追溯，不再作为新代码约束；既有业务规则和历史验证记录保留。
> 详见根目录 FEAT-030/06-app-layout.md 与 ADR-029。FEAT-029 因子来源加载目标保持不变。


> FEAT-030 当前实现：来源加载仍经过 FactorEngine，入口形成 Spec 后交由 Experiment / BacktestEngine。
> 新默认关闭停牌/涨停过滤，预处理仍默认 0；结果兼容新增过滤诊断，缓存使用新执行身份。
> [完整设计](../../../../docs/03-功能文档/FEAT-030-因子回测流程重构/README.md) 已进入实施；下面的来源解析说明不构成保留旧 Executor 的长期约束。

`FactorBacktestRequest` 将 `factor_code` 改为可选，并新增可接受字符串或字符串列表的 `library_name`。未传 `factor_code` 时仅允许一个库名；传了 `factor_code` 时允许多个库名。`Factor/libraries/index.yaml` 是内置库注册的唯一来源：API 每次根据索引中的库名和 `file` 声明校验并通过 `FactorLoader` 加载，不再在 `runner.py` 维护第二份手工白名单。自定义请求继续写入临时模块并包装函数代码，再将索引登记库中的公开因子方法注入临时库。注入方法调用原库的 `BaseFactor.compute()`，因此原库私有辅助方法仍在原库上下文执行。

因子目录接口拆分为两级：`GET /api/factor-libraries` 返回 `index.yaml` 登记的全部因子库（名称、说明、标签和因子数量）；`GET /api/factors/{library_name}` 返回指定因子库中的全部因子（名称和 docstring）。指定库接口仍通过 `FactorLoader` 实际加载并校验源码、索引中的因子清单和数量，库不存在返回 404，库登记但实现不可用返回 503。

该设计不新增运行时依赖、不改变缓存键构成方式（请求对象本身包含来源），也不执行任意前端指定模块。回滚时停止前端发送 `library_name`，旧的 `factor_code` 请求持续兼容。

## 4. 计划与里程碑

| 任务 | 复杂度 | 风险 | 完成条件 |
|---|---:|---|---|
| 增加来源契约与校验 | 2 | 低 | 两种来源互斥且响应明确。 |
| 按 `index.yaml` 加载内置库并限制 API 注册范围 | 2 | 中 | 私有辅助方法可用，任意未登记模块不能导入。 |
| 测试与文档 | 2 | 低 | 内置与自定义回测均通过回归。 |

里程碑：M1 契约和加载完成；M2 API 回归通过并完成前端对接。
