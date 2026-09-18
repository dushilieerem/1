# ADR-029：研究服务采用 services 与 models 分层

- 日期：2026-08-28
- 状态：已采纳，目录与模型归属迁移完成；528 项全量回归通过
- 决策依据：用户明确指定 `main.py / api / models / schemas / services / database / utils / config.py`。
- 关联：[FEAT-030 因子回测服务集成](../03-功能文档/FEAT-030-因子回测流程重构/README.md)

## 问题

QuantCore 最初按因子回测流程抽象为跨应用基础库，但目前实际消费者只有 ResearchEngine。
SVQuant 通过 HTTP 使用研究服务，TradingEngine 尚未建立，也没有复用这些实现的已确认需求。
把完整业务逻辑放在 QuantCore，同时在 services 再包装一遍，造成职责分散；
继续引入 application/domain/infrastructure 目录不符合当前团队采用的简单分层方式。

## 选择

1. 删除 QuantCore 运行时包边界，计算能力归 ResearchEngine 所有。不建设独立 QuantCore 进程、单例或公共 SDK。
2. 使用用户指定的目录：api 控制器，schemas HTTP DTO，services 业务逻辑，models 内部数据结构，
   database 数据读取/持久化，utils 通用工具，config.py 配置。assets 和 cli 保留现有用途。
3. 五个 Engine 都是 services 中的普通 Python 业务对象；按职责提取 Panel、MetricContext、
   FactorBacktestSpec/Result、实验上下文与策略回测数据结构到 models。
   BaseFactor、FactorLibrary、BaseMetric 等可执行扩展契约和实现留在相应 service 包。
4. models 不是 ORM 的别名：它可包含 dataclass、枚举、面板及保持数据不变量的方法；
   不读取环境/文件/数据库、不调度任务、不执行回测流程、不导入 HTTP schemas。
5. 数据源 Provider、字段缓存、结果缓存及存储归 database；因子源码加载与目录发现是业务服务，
   不因原目录叫 repositories 就全部塞进 database。ResultManager 的结果管理/绘图行为归 services。
6. 不改变部署：当前一个 Uvicorn worker 持有一个应用级 DataEngine 和一个 ExperimentManager。
   DataEngine 按固定 release 共享只读行情，Manager 只调度；每个实验独立持有因子/组合/指标引擎和中间数据。
   不把任务 spec、筛选掩码、因子值或组合写进共享行情对象；多 worker 协调不在本轮实现。
7. 内部导入一次切换到新路径，不保留 app.quantcore/core/repositories 的空壳层。
   内置因子/策略、测试、脚本和生成代码模板同步导入路径。HTTP 路径、请求响应、数据库 schema、
   计算公式、缓存及执行版本不因目录迁移改变。外部 Python 代码需同步新导入路径。

## 备选方案

- 保留 QuantCore 为未来交易系统复用：没有当前需求支持，继续增加维护边界，不采用。
- 新建 application/domain/infrastructure：用户选择熟悉的 Controller/Service/Model 组织，不采用。
- 所有文件整包移到 services：模型与逻辑仍混杂，不采用；按现有类的真实职责拆分。
- 将所有类都搬到 models：会把计算服务与数据结构混淆，不采用。

## 后果

目录与运行时所有权一致，单个 ResearchEngine 可以独立解释、测试和部署。代价是 Python 导入路径
需要统一迁移；动态源码、测试 monkeypatch、资源相对路径也必须检查。保留策略执行行为，
仅搬迁其服务和数据结构；不借本轮改变撮合与费用口径。

ADR-023/027/028 中有关 QuantCore 包边界的部分由本 ADR 接替；其单 app 命名空间、FIFO、
只读 release、四引擎流程和已确认计算规则仍有效。历史记录保留，不据新结构声称历史测试通过。

## 验证与回滚

迁移前记录工作区基线；迁移后验证所有模块可导入、无旧运行时路径、models 无运行时反向依赖、
HTTP/OpenAPI 契约及现有全量测试。测试使用 svquant 环境。保持 SVQuant、数据库、行情和输出不变。
部署回滚使用上一已验收版本；不能 reset 用户工作区或清空历史数据。
