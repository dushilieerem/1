# FEAT-029：数据库因子加载与回测执行器最小改造

> 2026-08-28 架构修订：用户已确认 ADR-029 的常规 FastAPI 分层。
> 原 QuantCore 运行时边界取消；五个 Engine 的业务逻辑进入 `app.services`，
> Panel、MetricContext、回测规格/结果和实验上下文进入 `app.models`，数据访问进入 `app.database`。
> 配置为 `app.config`，通用工具为 `app.utils`；不增加 domain/application/infrastructure。
> 下文中的旧目录和旧分层仅作历史设计追溯，不再作为新代码约束；既有业务规则和历史验证记录保留。
> 详见根目录 FEAT-030/06-app-layout.md 与 ADR-029。FEAT-029 因子来源加载目标保持不变。


> 2026-09-08：数据库因子主路径已实施。默认内置因子读取
> `app/assets/factors/factor_library.db`，公共算子读取 `app/assets/factors/tool.py`；
> 可通过 `SVQUANT_FACTOR_DB_PATH`、`SVQUANT_FACTOR_TOOL_PATH` 覆盖。旧
> `.py + index.yaml` 仅保留迁移期兼容。
>
> [FEAT-030 已实施演进](../../../../docs/03-功能文档/FEAT-030-因子回测流程重构/README.md) 已接替本 Feature 原阶段的执行器设计。
> “Executor 与算法不变”是本阶段最小改造的范围约束，不是未来永久接口承诺。
> 因子来源加载仍通过 FactorEngine loader 门面，回测算法和 `FactorBacktestSpec` 不变。

- 状态：已完成主路径切换（SQLite 因子库；旧文件路径迁移期兼容）
- 所属 Initiative：INIT-001 投研核心
- 所属能力：因子研究、研究基础设施
- 优先级：P0

## 目标

- 用数据库保存因子名、代码、说明、版本、标签、校验状态、指标快照、别名和所属库等管理信息。
- 让回测执行时不再依赖因子 `.py` 文件路径和 `index.yaml` 才能找到内置因子。
- 保留现有因子代码执行契约、`FactorBacktestSpec`、`FactorEngine` 和单因子/批量回测入口。
- 继续使用项目内 `app/assets/factors/tool.py`。Python 模块级函数作为无状态公共算子，数据库
  因子统一用 `tool.<method>()` 调用。

## 明确不做

- 不新增 `FactorSelector`、`FactorResolutionService`、`ResolvedFactor`、`FactorIdentity` 等
  运行时中间层。
- 不改变 `FactorBacktestSpec` 的字段、构造方式和序列化契约。
- 不保留已删除的 `FactorBacktestExecutor` 兼容签名；完整流程统一调用 `BacktestEngine.run()`。
- 不改变 `FactorEngine` 的既有计算逻辑；先增加 `load_factor()` 加载门面并完成兼容接线，
  不改回测算法、批量协调器或 WebApp 文件。
- 不首期建设独立 FactorRegistry 服务、权限系统、沙箱或新的 DSL。

## 运行时链路

```text
FactorBacktestRequest
        ↓（现有 _request_spec，Spec 不变）
FactorBacktestSpec
  ↓
BacktestEngine.run(spec, context)
        ↓
FactorEngine.load_factor(source=...)
        ↓（由 FactorEngine 持有的统一 loader 选择实现）
SQLite / 代码 loader（旧文件仅迁移兼容）
        ↓ 读取 factor_code，编译/实例化现有 BaseFactor
FactorEngine 私有保存 base_factor，原始 spec 保持不变
        ↓
DataEngine → FactorEngine → PortfolioEngine → MetricEngine → 回测结果
```

`FactorBacktestExperiment` 只负责把 Experiment 任务交给 `BacktestEngine.run(spec, context)`；
不再保留单独的 Executor 文件或兼容入口。

`factor_definition`、`factor_version`、`factor_tag`、`factor_validation`、
`factor_metric_snapshot`、`factor_alias` 和 `factor_library` 是数据库中的字段或关联数据，
不是每次回测都要创建的运行时对象。

`FactorEngine` 只新增统一的 `load_factor(...)` 门面，不直接写 SQL；文件、数据库和代码加载
实现通过 loader 提供。这样调用方只面对 FactorEngine，QuantCore 也不绑定数据库实现。

## 关联决策

- `../../05-技术决策/ADR-026-因子数据库加载与执行器最小改造.md`
- `../../../../docs/05-技术决策/ADR-027-QuantCore三引擎兼容式重构.md`

## 文档索引

- `01-feature-proposal.md`：背景、价值、MVP 范围和成本。
- `02-product-requirements.md`：用户流程、规则和验收标准。
- `03-technical-design.md`：数据库记录、加载器、编译方式、兼容与影响分析。

## 1. 计划与里程碑

> 计划衔接已完成：[FEAT-030](../../../../docs/03-功能文档/FEAT-030-因子回测流程重构/README.md) 已单独承担因子流程重构。
> 下列原计划中的 Executor 接线任务改接到 FactorEngine loader / BacktestEngine，不为已移除的算法
> 主链开发第二条路径。数据库主路径已经接入，旧文件仅保留迁移期回退。

### Sprint 目标

在不修改 `FactorBacktestSpec`、FactorEngine 计算 API 和 WebApp 的前提下，复用已完成的
BacktestEngine 引擎边界，把内置因子主加载源切换到数据库，并保留旧 `.py + index.yaml` 回退路径。

### 任务拆解

| 任务 | 交付物 | 复杂度 | 预计人天 | 风险 | 依赖 |
|------|--------|--------|----------|------|------|
| 设计与 ADR 更新 | 本 Feature 文档、ADR-026 | 1 | 1 | 低 | 无 |
| QuantCore 引擎兼容式重构 | FactorEngine loader 门面、MetricEngine 注册/计算边界、DataEngine provider 校验 | 3 | 2 | 中 | ADR-027 |
| 因子数据库表与仓库 | 当前表、版本表（可选）、SQLite 实现、读取/写入测试 | 3 | 3 | 中 | 设计 |
| 数据库加载器 | 内存编译、现有模板复用、`BaseFactor` 校验、错误映射 | 4 | 3 | 中 | 仓库 |
| FactorEngine 接线 | 默认 loader 改为数据库；保留 inline code 和已传入 factor | 2 | 1 | 低 | 加载器 |
| Runner 与哈希接线 | 停止 API 路径绕过数据库；哈希读取 `code_hash` | 3 | 1 | 中 | Executor |
| 导入脚本 | `.py + index.yaml` 导入、幂等比较、差异报告 | 3 | 2 | 中 | 仓库 |
| 回归与数值验证 | 单因子、批量、缓存和固定面板对比 | 3 | 2 | 中 | 全部 |

合计约 15 人天，按一名开发者为 2–3 周；不包含后续权限、服务化和 WebApp 页面。

### 开发顺序与里程碑

#### Week 0：引擎边界稳定（当前阶段）

- 保持 `FactorBacktestSpec` 和 `FactorEngine` 计算入口不变。
- 将来源解析收敛到 `FactorEngine._resolve_factor(spec)`，由 loader 提供具体来源实现。
- 完成 MetricEngine/DataEngine 的小步重构和 QuantCore 回归。

**M0：** 三个引擎的公开计算/读取契约稳定，后续数据库只替换 loader。

#### Week 1：仓库与加载器验证

- 冻结数据库字段和代码保存形态。
- 实现仓库读取、代码哈希和一个完整库/一个方法因子的内存加载。
- 用固定小面板验证数据库来源与旧文件来源结果一致。

**M1：** 数据库的一条因子记录可以返回现有 `BaseFactor`，并通过 `FactorEngine`。

#### Week 2：FactorEngine 主路径

- 接入数据库 loader，并保持 `FactorEngine._resolve_factor(spec)` 的规格入口。
- 调整 runner 的来源哈希读取方式。
- 补单因子、批量和 inline code 回归测试。
- 增加缺失、语法错误、连接错误和缓存失效测试。

**M2：** 现有回测请求无字段变化，但内置因子默认从数据库加载。

#### Week 3：导入、灰度与验收

- 导入全部现有因子并输出差异报告。
- 执行代表性和全量目录校验，保留旧文件回退开关。
- 观察回测数值、加载延迟和缓存命中情况。

**M3：** 数据库主路径稳定，旧路径可在一个配置开关内恢复。

### 发布与回滚

- 数据库初始化和导入脚本支持 dry-run；先只读验证，再开启主路径。
- 发布前保留 `.py` 和 `index.yaml`，不做删除性迁移。
- 数据库不可用或数值验证失败时切回上一已验收版本或旧文件 loader。
- 使用 `svquant` 环境运行相关 pytest；文档和配置变更通过 `git diff --check`。

### 验收清单

- [x] `FactorBacktestSpec` 无字段改动。
- [x] 历史阶段 `FactorBacktestExecutor.execute(spec, context)` 无签名改动；该兼容入口已由 FEAT-030 删除。
- [x] 内置因子默认读取数据库，不读取 `.py` 文件。
- [x] `factor_code` 自定义兼容路径继续工作。
- [x] `factor_source_hash` 来自数据库因子源码和公共 `tool.py` 哈希。
- [x] 单因子与批量回测结果保持一致（全量回归通过）。
- [x] 数据库失败、代码错误和记录缺失有明确错误。
- [ ] 导入脚本可重复执行并生成差异报告。
- [x] 旧 `.py + index.yaml` 回退路径可用。

## 2. 当前结论

因子管理已经从 `.py + index.yaml` 迁移到数据库，但不需要重做回测运行时。
`FactorBacktestSpec` 保持不变，来源加载仍通过 FactorEngine 的 loader 门面完成；完整因子
流程由 `BacktestEngine.run(spec, context)` 负责。数据库阶段只替换因子来源 loader：按
`library_name + factor_name`（默认使用稳定 `sv_id`，兼容名称和源码函数名）读取代码，
结合项目内 `tool.py` 编译/实例化为现有的 `BaseFactor`，再交给 BacktestEngine。
