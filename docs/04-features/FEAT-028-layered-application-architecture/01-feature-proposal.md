# Feature Proposal：ResearchEngine 分层应用架构

## 背景

原工程把核心量化引擎、投研编排、FastAPI 路由、因子资产和策略资产分散在多个顶层
包中。随着每日因子回测、策略资产版本化和异步任务加入，旧入口容易被误用，API 也
可能直接触碰行情或 SQLite 细节，增加迁移和回归成本。

## 用户价值

- 研究员使用同一个 `app.*` 命名空间，不需要记忆多个包的安装与导入规则；
- API、业务用例、持久化和 QuantCore 的职责可独立测试；
- 因子、策略资产随应用发布，索引和源码路径稳定；
- 批量因子回测成为清晰的具体业务能力，不与通用任务 Manager 混淆。

## 商业价值

稳定的运行时边界降低新因子、新策略和 Web API 交付成本，为后续研究订阅、评分卡和
策略组合能力提供可演进的基础，而不把当前 MVP 过早绑定到分布式基础设施。

## MVP 范围

### 必须做

- `ResearchEngine/app` 单一命名空间和 `app.main` 唯一 FastAPI 入口；
- API、schemas、业务能力、repository/database、QuantCore 的固定依赖方向；
- `Experiment` 抽象基类、Factor/Strategy/DailyFactor 三类具体实验；
- 唯一 Manager、普通 FIFO、有界容量和 FastAPI lifespan 生命周期；
- `DailyFactorBacktestCoordinator` 自有容量为 2 的批量窗口；
- 因子/策略资产迁移、SQLite repository 边界和 `/api` 契约；
- 删除旧运行时包和历史教学入口。

### 可以以后做

- 多实例调度、分布式锁、外部消息队列；
- WebApp `/api` 适配；
- ORM、PostgreSQL/ClickHouse 结果仓库；
- 用户鉴权、多租户和权限模型。

### 明确不做

- Manager 内部优先队列或 lane 插队；
- 本次重构修改 WebApp；
- 为兼容旧 Python 导入路径保留转发模块。
