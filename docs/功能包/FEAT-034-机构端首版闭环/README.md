# FEAT-034 主观投研端首版闭环

| 项 | 内容 |
|---|---|
| 状态 | 首版可运行（真实数据 + 模拟执行） |
| 日期 | 2026-10-30 |
| 前置 | [FEAT-033 机构端入口](../FEAT-033-机构端入口/README.md)、[主观投研端需求评估](../../产品与需求/主观投研端需求评估.md)、[数据接入与库表设计](../../数据设计/机构端与手机端-数据接入与库表设计-v0.1.md) |
| 需求 | `Sunvalley_AI_Value_Investment_Requirements_v1.1.md`（v1.1） |

## 1. 目标与范围

把「机会发现 → 公司研究 → 投资辩论 → 组合配置 → 两级审批 → 执行前风控 → 授权 → 模拟执行 → 投后」在工作台里打通；数据来自 PG 服务层，AI 只给建议。

**做**：

- 24 个研究对象（A 股 8 + 美股 8 + 港股 8）；A 股用真实行情与财务，其余标注「待补充」。
- 六维研究生成、证据落库、版本化审核、辩论（两轮正反 + 主持）、议案/审批/授权、SimBroker、组合与投后。
- 九工作区首版页面；驾驶舱与待办接真实计数。
- 服务端职责分离与硬阻断：单股 ≤15%、交易后现金 ≥10%、版本一致、无有效批准不得授权。

**不做**：真实券商、QMT、基金会计/净值核算、申赎、监管报送、双语完整版、SSO。

## 2. 关键决策

| 决策 | 选择 |
|---|---|
| 产品线 | 主观价值机构端（旸谷资本），不混用量化机构端 PRD |
| 市场 | A 股优先；美股/港股只做流程占位 |
| 数据 | parquet 只读权威源；PG 服务层 2016 起；免费源补财务/公告 |
| AI | 复用 ADR-037 路由层；辩论 TaskSpec；证据 ID 强校验 |
| 执行 | SimBroker 纸面撮合；授权不可变快照 |
| 前端 | 同一 SPA 的 `/inst/*` 路由树，独立机构壳 |

## 3. 实现

### 3.1 后端

| 文件 | 内容 |
|---|---|
| `backend/services/institution/inst_schema.py` | 18 张业务表：公司池、组合、研究、证据、辩论、议案、审批、授权、订单/成交/持仓、监控、退出、审计 |
| `backend/services/institution/inst_service.py` | 种子、六维研究、审核、辩论、议案状态机、风控检查、授权、SimBroker、组合、投后 |
| `backend/app/routers/inst_workflow.py` | `/api/inst/overview|companies|cases|debates|proposals|authorizations|portfolio|monitor|audit` |
| `backend/ai/router/tasks/institution.py` | `inst.debate` / `inst.research_memo` / `inst.risk_review` / `inst.chairman_memo` |
| `backend/services/marketdata/store.py` | 行情/估值/财务/风险/行业同行查询 |

### 3.2 前端

| 文件 | 内容 |
|---|---|
| `frontend/src/pages/institution/InstOverviewPage.tsx` | 真实净值、在研、待审批、风控阻断、监控预警 |
| `InstIdeasPage.tsx` | 24 家公司池、市场筛选、立项/观察/放弃 |
| `InstResearchPage.tsx` | 六维研究、证据、版本审核、进入辩论 |
| `InstDebatePage.tsx` | 正/反/主持三栏、证据 ID、结论 |
| `InstPortfolioPage.tsx` | 净值/现金/持仓/行业敞口 |
| `InstApprovalsPage.tsx` | 议案快照、审批链、风控检查、授权 |
| `InstExecutionPage.tsx` | 有效授权、幂等执行、持仓 |
| `InstMonitorPage.tsx` | 持仓台账、预警、退出研究 |
| `InstAboutPage.tsx` | 角色边界、AI 能力、免责声明 |

## 4. 状态机

```text
draft → pending_review → approved → (debate completed) → proposal
proposal: draft → partner_review → chairman_review → risk_precheck → authorized → executed
任一审批拒绝 → rejected；风控 block/veto → frozen
```

硬约束：

- `inst_authorization` 只增不改；撤销写新行。
- `inst_order.authorization_id` 唯一，重复提交返回原结果。
- 提案人不得审批自己的议案；风控阻断后 Chairman 不能批准。
- 未复权行情未就绪时，执行会回退后复权价；正式演示前应确认 `adjust='none'` 已同步。

## 5. 验证

| 项 | 结果 |
|---|---|
| 机构端登录与 8 条权限测试 | 通过（`pytest tests/test_inst_auth.py`） |
| 全链路服务层测试 | 通过：建案 → 研究 → 审核 → 辩论（真实模型）→ 议案 → 合伙人 → Chairman → 风控 → 授权 → SimBroker 成交 |
| 真实数据演示 | 600519：PE 21.37 / PB 6.93 / 毛利 89.73% / 营收 922.78 亿；成交 300 股 @1392.05，现金 9.58M，净值 10.00M |
| 角色隔离回归 | 通过：六个角色 org_id 均为 1；partner/chairman/risk 的审批链可用（修复了成员 ID 被误当机构 ID 的缺陷） |
| 前端 TypeScript | 通过（`tsc --noEmit`） |
| 真实模型辩论 | 通过；证据 ID 校验生效；无有效证据的论点标记为不计入裁决 |
| 24 家公司种子 | 通过（PG `inst_company`） |
| 浏览器走查 | **未做**（本机未启动浏览器） |

## 6. 已知缺口

- 六维研究仍是「数据 + 规则模板」；研究一页纸/风控/Chairman 的 AI 接口已接到页面（2026-11-02 自动化）。
- 美股/港股无基本面与公告，不能进入审批；页面显示「待补充」。
- 退出议案只建表与展示，尚未串起「原授权撤销 + 新议案」完整流程。
- 审计查询页未做；`inst_audit_event` 已写入。
- 双语、SSO、多机构、WORM 审计、受控导出未做。
- 真实数据覆盖：A 股 5 只财务，其余 A 股只有行情/估值；港股无数据。

## 7. 下一步

1. 接研究一页纸、风控复核、Chairman 摘要三个 AI 接口。
2. 退出流程：撤销原授权 → 建 sell/exit 议案 → 重新研究/辩论/审批。
3. 授权与审计的只读查询页。
4. 浏览器 E2E 与六角色走查。
5. 数据补齐：A 股全池财务、公告正文锚点、行业中文名。

## 8. 六 Agent 研究与自动化（2026-11-02）

机构端研究改为 6 个独立 AI Agent，每个 Agent 有自己的 TaskSpec、提示词、输入与输出：

| 维度 | TaskSpec | 分析方向 |
|---|---|---|
| 商业与产业 | `inst.dim.industry` | 行业规模、竞争结构、供需周期 |
| 公司商业模式 | `inst.dim.business_model` | 收入结构、客户价值、单位经济性、资本强度 |
| 护城河 | `inst.dim.moat` | 品牌、成本、网络、转换成本与侵蚀路径 |
| 财务质量 | `inst.dim.financial` | 三表勾稽、ROIC/FCF、会计风险 |
| CEO 与治理 | `inst.dim.governance` | 资本配置、承诺兑现、关联交易 |
| 估值与价格 | `inst.dim.valuation` | PE/PB 分位、DCF 假设、安全边际 |

编排器 `_run_dimension_agents` 默认并发 3（`INST_AGENT_CONCURRENCY` 可调），每维独立重试，失败时回退到确定性规则模板并标记 `engine=rule`。Agent 证据写入 `inst_evidence`，按 hash 去重。

前端每 2 秒轮询研究案任务：6 个 Agent 分别为 pending/running/done/needs_review/failed，完成一个就展示该维摘要；全部完成后再生成 AI 一页纸。

前端把研究到辩论的串行动作自动化：

1. 进入研究案：若尚无研究版本，自动执行 6 Agent 分析（`POST /cases/{id}/research`，full）。
2. 6 个 Agent 完成后：自动调用 `POST /cases/{id}/ai/memo` 生成 AI 一页纸摘要（汇总 6 份结果）。
3. 人工审核：保留「审核通过 / 退回」人工动作，不自动批准。
4. 审核通过：自动跳转投资辩论，并自动调用 `POST /cases/{id}/debate`（`use_ai=true`）开始 AI 辩论。
5. 若某个 Agent 失败：该维回退规则模板并标记 `engine=rule`、`agent_error`；其余 Agent 不受影响。
6. 若 AI 全部不可用：研究流程不阻断，保留手动按钮与错误提示；辩论仍可由规则模板兜底。

已用真实浏览器验证：新建深振业A研究案 → 6 个 Agent 完成 → AI 摘要 → 审核通过 → 自动辩论。
