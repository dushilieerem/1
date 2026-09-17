# FEAT-002：ResearchEngine 研究服务

> 2026-08-28 架构修订：用户已确认 ADR-029 的常规 FastAPI 分层。
> 原 QuantCore 运行时边界取消；五个 Engine 的业务逻辑进入 `app.services`，
> Panel、MetricContext、回测规格/结果和实验上下文进入 `app.models`，数据访问进入 `app.database`。
> 配置为 `app.config`，通用工具为 `app.utils`；不增加 domain/application/infrastructure。
> 下文中的旧目录和旧分层仅作历史设计追溯，不再作为新代码约束；既有业务规则和历史验证记录保留。
> 详见根目录 FEAT-030/06-app-layout.md 与 ADR-029。FEAT-029 因子来源加载目标保持不变。


> 已批准实施：[FEAT-030](../../../../docs/03-功能文档/FEAT-030-因子回测流程重构/README.md) 保留
> Manager 与 Experiment 职责，由一个应用层 BacktestEngine 组织完整因子流程；单次、批量、Python 同路。
> 本 Feature 的基础能力状态不变，因子主链已切换，专项验收见 FEAT-030 Verification。

- 状态：已完成（基础版 + 因子分析 API + 策略回测 API MVP 增量）
- 所属 Initiative：INIT-001 投研核心
- 所属能力：因子研究、策略研究、研究 API
- 代码位置：`ResearchEngine/app/`

## 文档索引

- `01-feature-proposal.md`：功能背景和范围
- `02-architecture.md`：业务无状态、进程级 Manager 与并发架构
- `03-modules.md`：模块职责
- `04-class-design.md`：类设计
- `05-runtime-flow.md`：运行流程
- `06-research-api.md`：HTTP API 索引；回测接口和 Manager 内部任务调度说明位于 `06-研究接口文档/`
- `07-factor-strategy-guide.md`：因子与策略编写指南入口；按因子、向量化策略、事件策略、示例和前端映射拆分为独立文档
- `08-factor-analysis-api-extension.md`：因子分析序列与行业曲线 API 增量交付材料
- `09-factor-analysis-api-verification.md`：因子分析 API 增量验证记录
- `10-strategy-backtest-api-verification.md`：策略回测 API MVP 验证记录

## 文档缺口

该 Feature 在新工作流建立前已实现，尚需补充正式 Project Plan 和 Verification。本次因子分析 API 增量按当前 Feature 文档包交付；后续新增 AI、持久化、团队协作等独立业务能力应拆分为新的 Feature。
