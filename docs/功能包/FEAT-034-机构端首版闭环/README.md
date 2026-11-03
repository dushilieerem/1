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

编排器 `_run_dimension_agents` 默认 6 个并发（`INST_AGENT_CONCURRENCY` 可调），每维独立重试，失败时回退到确定性规则模板并标记 `engine=rule`。Agent 证据写入 `inst_evidence`，按 hash 去重。

前端每 2 秒轮询研究案任务：6 个 Agent 分别为 pending/running/done/needs_review/failed，完成一个就展示该维摘要；全部完成后再生成 AI 一页纸。

前端把研究到辩论的串行动作自动化：

1. 进入研究案：若尚无研究版本，自动执行 6 Agent 分析（`POST /cases/{id}/research`，full）。
2. 6 个 Agent 完成后：自动调用 `POST /cases/{id}/ai/memo` 生成 AI 一页纸摘要（汇总 6 份结果）。
3. 人工审核：保留「审核通过 / 退回」人工动作，不自动批准。
4. 审核通过：自动跳转投资辩论，并自动调用 `POST /cases/{id}/debate`（`use_ai=true`）开始 AI 辩论。
5. 若某个 Agent 失败：该维回退规则模板并标记 `engine=rule`、`agent_error`；其余 Agent 不受影响。
6. 若 AI 全部不可用：研究流程不阻断，保留手动按钮与错误提示；辩论仍可由规则模板兜底。

已用真实浏览器验证：新建深振业A研究案 → 6 个 Agent 完成 → AI 摘要 → 审核通过 → 自动辩论。

## 9. 退出流程闭环（2026-11-03）

补齐「投后退出研究 → 研究/辩论 → 退出议案 → 审批 → 授权 → 执行」的断点。

### 9.1 缺口与修复

| 缺口 | 修复 |
|---|---|
| 辩论页创建议案硬编码 `direction: "buy"` | 根据研究案是否关联退出案决定方向：退出案默认 `exit`，普通研究案仍为 `buy` |
| 退出案状态只写 `draft`，复盘分支不可达 | 新增退出案状态机，议案提交/审批/授权/执行时合法迁移并写审计 |
| 议案与投后列表看不到退出案进度 | 议案详情返回 `exit_case`；投后列表返回 `case_id/case_no/proposal_id/proposal_status/authorization_status`，页面可回链 |

### 9.2 状态机

```text
draft --提交议案--> submitted
submitted --Chairman 通过--> approved
submitted/approved --Chairman 拒绝/风控阻断--> rejected
submitted/approved --执行成交/退出复盘--> closed
```

- 迁移由 `_transition_exit_case` 校验，非法迁移返回 403；并发写入用 `WHERE status=<旧状态>` 保护。
- 每次迁移写 `inst_audit_event`：`monitor.exit.submit|approve|reject|risk_block|authorize|close`。
- 退出案没有独立「已授权」状态：授权保持 `approved`，另写 `monitor.exit.authorize` 审计（含 `authorization_id`），执行成交后才 `closed`。
- 旧数据里仍为 `draft` 的退出案，在审批/授权/执行前先补一条 `submitted` 迁移，保持审计链完整。

### 9.3 方向与默认值

- `POST /api/inst/cases/{id}/proposals`：带退出案的 case 只接受 `sell/exit`，传 `buy` 返回 400；未传方向/仓位时默认 `exit` + `0`（清仓）。
- 普通研究案默认值仍为 `buy` + `0.05`。
- `config` 快照新增 `exit_case_id`，授权快照可追溯退出案。

### 9.4 前端

- `InstDebatePage`：退出案显示「退出辩论」，选择栏提示只能建退出议案，目标仓位默认 0，按钮为「创建退出议案」。
- `InstMonitorPage`：退出案卡片显示 `EX-{id}`、研究案编号、研究案/议案回链、议案与授权状态。
- `InstApprovalsPage`：议案快照增加退出案区块（原因、状态、回链研究案）。

### 9.5 验证

| 项 | 结果 |
|---|---|
| `pytest tests/test_inst_exit_flow.py` | 通过：方向校验、默认 exit/0、状态迁移顺序、审计顺序、投后回链 |
| `pytest tests/test_inst_*.py` | 42 passed（含既有机构端全链路） |
| `tsc --noEmit` | 通过 |
| `npm run test:inst` | 5 passed |
| `playwright test tests/e2e/e2e-09-inst.spec.ts` | 4 passed：登录/九工作区/无横向溢出/退出路径 |

### 9.6 边界

- 未新增表或列；`inst_exit_case` 既有 `case_id/proposal_id/status` 足够承载。
- 退出议案被拒后目前不能在同一退出案上重新建案；如需重试需新建退出研究案。

### 9.7 E2E 写库安全（2026-11-03）

`e2e-09-inst.spec.ts` 默认只跑只读用例（登录、九工作区、无横向溢出）。退出流程会创建持仓、研究案、退出案与议案，属于写库用例，必须显式开启：

```bash
# 只读（默认，可指向演示库）
npx playwright test e2e-09-inst.spec.ts

# 写库：必须使用独立测试库，禁止指向生产库 svquant
INST_E2E_ALLOW_WRITE=1 INST_E2E_DB=safe \
  npx playwright test e2e-09-inst.spec.ts
```

- `INST_E2E_ALLOW_WRITE=1` 才会考虑写库；未设置时写库用例 skip。
- `INST_E2E_DB` 必须为 `safe`，或库名含 `_test` / `_e2e`（如 `svquant_test`）。
- 只设 `INST_E2E_ALLOW_WRITE=1` 但目标库不安全时，`beforeAll` 直接失败，不会静默写入。
- `backend/.env` 的 `DATABASE_URL` 也必须指向该独立测试库；本地调试用的 `.env` 不提交。
- guard 逻辑在 `tests/e2e/helpers/write-guard.mjs`，单测：`cd tests/e2e && npm run test:guard`。
