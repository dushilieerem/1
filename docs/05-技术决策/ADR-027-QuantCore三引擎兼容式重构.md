# ADR-027：QuantCore 三引擎兼容式重构（先引擎、后数据库）

- 日期：2026-08-26
- 状态：已采纳

> 后续决定：[ADR-029](ADR-029-研究服务采用services与models分层.md) 取消 QuantCore 包边界；
> Engine 业务归 services，内部数据结构归 models。下文记录本 ADR 采纳时的设计与测试，不是当前目录规范。

> 后续提议（2026-08-28）：[ADR-028](ADR-028-因子回测由BacktestEngine编排四引擎.md)
> 将在保留 loader 注入、provider 隔离和既有指标接口的基础上，调整 Data/Factor/Metric 职责并增加 PortfolioEngine。
> 原阶段“Executor/算法不变、DataEngine 仅委托”的约束拟由新方案局部接替。
> 提议未实施，数据库迁移仍单独待决策，本 ADR 的当前状态和历史验证记录不变。

> 2026-08-28 实施修订：FEAT-030 已删除因子链路中的 `FactorBacktestExecutor`，并将
> `_resolve_factor(spec)` 收归 `FactorEngine`。因子名、因子库和因子代码的来源
> 解析由 FactorEngine 的默认/注入式 loader 完成；本 ADR 下文关于 `factor_resolver` 和
> Executor 的内容仅保留为历史决策记录，不再是当前运行时约束。

## 问题

当前 `FactorEngine`、`MetricEngine` 和 `DataEngine` 的公开接口可以工作，但职责边界和扩展
入口不够清晰：因子来源解析容易回落到 Executor 的流程代码，指标注册与执行没有统一的单指标
入口，数据引擎也没有在 provider 切换时尽早检查基本契约。

本阶段需要先整理运行时引擎，同时保持数据库迁移前的 `.py + index.yaml` 路径可用。

## 选择

1. `FactorEngine` 保留 `register`、`compute`、`compute_panel`、`compute_all` 及
   `factors` 注册表；新增注入式 `factor_loader` 和 `load_factor()` / `factor_loader()` 门面。
   Loader 可按 `file`、`code`、`database` 等 source 自行路由，Engine 不直接依赖 SQL、文件
   系统或代码编译实现；同时兼容现有 `FactorLoader.load(module_name)`。
2. 历史 `FactorBacktestExecutor` 在 `spec.factor is None` 时调用 FactorEngine 加载门面。现有
   `factor_resolver(spec)` 只作为兼容 loader 适配，`FactorBacktestSpec`、Executor 公开签名、
   回测算法和结果契约不变。
3. `MetricEngine` 保留 `metrics`、`register`、`calculate`、`calculate_all` 和原有返回值；
   增加 `register_many`、`names`、`get_metric`、`calculate_one`，并将字符串指标名按单个指标
   处理。标准指标实现和 `MetricContext` 不迁移。
4. `DataEngine` 保留透明代理职责；增加 provider 核心方法的结构化校验、统一委托和
   `provider_name`，对只实现逐标的核心方法的轻量 provider 使用 `IDataProvider.get_panels`
   默认拼装。暂不修改 `IDataProvider` 抽象，以控制高风险公共接口变更。
5. 本阶段不建立因子数据库、不改表结构、不删除旧因子文件；数据库 loader 作为后续替换的
   注入实现接入。

## 备选方案

### 立即迁移数据库并重写执行链

不采用。数据库迁移会同时放大代码编译、缓存哈希、批量目录和回测回归风险；先稳定 Engine
边界可以让后续迁移只替换 loader。

### 新增 Selector / ResolutionService / ResolvedFactor 等运行时层

不采用。当前问题是来源路由与职责边界，不需要增加运行时身份对象或改变 Spec。

### 修改 IDataProvider 抽象并要求所有 provider 实现新方法

不采用。该接口有多个 provider 和调用方，影响面高；DataEngine 内部增强已经足够解决当前
问题。

## 后果

### 正面

- 因子来源路由集中到 FactorEngine，数据库、文件和源码 loader 可以独立替换。
- 现有 Spec、算法、批量入口和 WebApp 无需迁移；旧 resolver 可逐步下线。
- 指标调用获得统一的单指标入口，错误信息和注册快照更一致。
- provider 配置错误在 DataEngine 初始化/切换时尽早暴露，面板默认实现仍兼容轻量 provider。

### 负面

- FactorEngine 现阶段仍需由应用层注入 loader；数据库 loader 尚未实现。
- `factor_resolver` 兼容代码会暂时保留，直到数据库主路径完成灰度。
- 三个公共类仍处于兼容演进期，后续若改变返回契约需另建 ADR 并重新做影响分析。

## 验证

- QuantCore 相关回归：39 passed。
- Executor、API、批量及架构相关回归：96 passed。
- 全量回归（含本次引擎与 Executor 接线改动）：521 passed，1 个既有 FastAPI/Starlette 弃用警告。

## 关联文档

- FEAT-029：数据库因子加载与回测执行器最小改造
- ADR-025：回测采用单一应用执行管线与可插拔后端
