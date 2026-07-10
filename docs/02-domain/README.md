# YGQuant 领域建模（02-domain）

> 本目录用 DDD（领域驱动设计）方法对 YGQuant 平台进行领域建模。
> **设计原则：战略设计全局化，战术设计分波次聚焦，接口先行（API-first）。**

## 为什么这样组织

- **战略边界（上下文边界、协作关系）全局定** —— 它是接口契约与数据所有权的"合同"，划错后期返工成本极高。集中在 `00-strategy.md`。
- **战术细节只对"即将开发"的上下文深做** —— 聚合内部实体/值对象/方法/状态机会随实现演化，分波次落到独立文件。
- **接口先行（API-first）** —— 阶段一/二引擎暴露 Python API + CLI + 预留 HTTP 适配层，阶段三 AI 平台通过这些接口调用引擎。
- **为未实现的上下文预留契约** —— 例如 BC3 Backtest 现在就为 BC8 Execution 预留执行抽象，做实盘时无需重构研究侧。

## 实现路径（对齐 PRD §10：先研究、后实盘、再 AI）

```
阶段一 ResearchEngine（CLI/SDK，无 AI 无 SaaS） → 阶段二 实盘交易（CLI/SDK，无 AI 无 SaaS） → 阶段三 AI 完整平台（Web SaaS）
   BC2/3/4/5/6/9/10                            BC7/8                              BC1 + BC11/BC12(SaaS) + 多市场/机构
```

## 文档结构

| 文件 | 内容 | 状态 |
|---|---|---|
| `00-strategy.md` | 全局战略：子域、12 限界上下文、上下文映射、波次总览、通用语言、多租户 | v0.1 |
| `01-wave1-research-core.md` | Wave1 战术详设：研究引擎（BC2/3/4/5/6/9/10，CLI，**无 SaaS**） | v0.1 ⭐当前焦点 |
| `02-wave2-trading-execution.md` | Wave2：实盘交易系统（BC7/8，CLI） | 占位 |
| `03-wave3-ai-platform.md` | Wave3：AI 完整平台（BC1 + BC11/BC12 SaaS 层 + 多市场/机构，Web） | 占位 |

## 阅读顺序

1. **`00-strategy.md`** —— 建立全局边界认知（必读）
2. **`01-wave1-research-core.md`** —— 当前实现焦点（阶段一研究引擎，CLI/SDK）
3. 后续波次文档随实现推进逐步深化

## 波次总览（对齐 `../01-prd.md` §10）

| Wave | 阶段 | 形态 | 限界上下文 | 文档 |
|---|---|---|---|---|
| Wave 1 | 阶段一 研究引擎 | CLI/SDK | BC2 Strategy + BC3 Backtest + BC4 Data + BC5 Factor + BC6 MarketRule + BC9 Analysis + BC10(社区) | `01-...` |
| Wave 2 | 阶段二 实盘交易 | CLI/SDK | BC7 Portfolio & Risk + BC8 Execution | `02-...` |
| Wave 3 | 阶段三 AI 平台 | Web SaaS | BC1 AI Assistant + BC11 IAM + BC12 Billing + 多市场/机构 | `03-...` |

> Wave 1 覆盖 QuantCore + ResearchEngine，即研究员做策略与因子研究的最小闭环（CLI/SDK，**无 AI、无 SaaS**）。
> AI 与 SaaS 层（登录/计费/多租户）在 Wave 3 才引入，建立在已成熟的研究引擎与实盘交易之上。
> 接口先行：Wave 1/2 引擎暴露 Python API + CLI + 预留 HTTP 适配层，Wave 3 AI 平台通过这些接口调用引擎。

## 关联文档

- 上游：`../01-prd.md`（业务需求）
- 下游：`../03-architecture.md`（引擎分层架构）

## 全局原则备忘

- **接口先行（API-first）**：引擎能力可被程序与 AI 调用
- **`TenantId` 预留**：Wave 1/2 单租户默认值，Wave 3 启用多租户时无需改模型
- **AI 助手（BC1）是编排者**，不持有业务实体，Wave 3 引入
- **SaaS 层（BC11/BC12 多租户/计费）** Wave 3 引入，前两阶段无 SaaS
- **MarketRule（BC6）** 是多市场扩展的唯一改动点
- **BC3 为 BC8 预留 `ExecutionEngine` 抽象**，Wave 2 兑现（回测/实盘共用策略代码与撮合接口）
