# FEAT-034 主观投研端首版闭环

| 项 | 内容 |
|---|---|
| 状态 | v3 全量切换（真实数据 + 模拟执行） |
| 日期 | 2026-11-09 |
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

### 3.2 前端（v2 历史，2026-11-09 已被 v3 替换）

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

`e2e-09-inst.spec.ts` 默认只跑只读用例（登录、九工作区、无横向溢出）。退出流程会创建持仓、研究案、退出案与议案，属于写库用例：

```bash
# 只读（默认）
npx playwright test e2e-09-inst.spec.ts

# 写库：人工开关 + 服务端真实库名校验
INST_E2E_ALLOW_WRITE=1 \
  npx playwright test e2e-09-inst.spec.ts

# 可选：精确锁定服务端返回的库名
INST_E2E_ALLOW_WRITE=1 INST_E2E_EXPECT_DB=svquant_test \
  npx playwright test e2e-09-inst.spec.ts
```

- `INST_E2E_ALLOW_WRITE=1` 只是人工开关；未设置时写库用例 skip。
- 写库用例启动时请求 `GET /api/inst/_e2e/guard`，服务端用 `SELECT current_database()` 返回真实 `db_name` 与 `writable`。
- 只有真实库名含 `_test` / `_e2e` 且 `writable=true` 才放行；生产库 `svquant` 永远拒绝。
- 端点不可达、非 200、返回缺失、库名不是测试库、`INST_E2E_EXPECT_DB` 不一致，全部 `beforeAll` 直接失败，不会静默写入。
- `backend/.env` 的 `DATABASE_URL` 也必须指向该独立测试库；本地调试用的 `.env` 不提交。
- guard 逻辑在 `tests/e2e/helpers/write-guard.mjs`，单测：`cd tests/e2e && npm run test:guard`。

## 10. 研究页单维视图、单维追问与 AI 一页纸（2026-11-03）

按 2026-11-03 前端需求调整投资经理角色的公司研究流程。

### 10.1 生成态文案

- 首次进入且尚无研究版本时，按钮与进度卡显示「正在生成」；已有版本后才显示「重新生成六维分析 / 重新生成中」。

### 10.2 单维视图与单维分析

- 六维卡改为「目录 + 单维正文」：六个维度 Tab 放在「重新生成六维分析」按钮旁；正文只展示当前维度。
- 新增「单独分析该维度」：`POST /api/inst/cases/{id}/research`（`mode=<维度>`）只重跑该维 Agent，并合并进最近版本，保留其余五维；版本号 +1、回到 `pending_review`，旧版本保留。
- 未新增表；`inst_research_version` 增加 `dim_reviews JSONB`，在 `inst_schema.py` 用幂等 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 补列。该列与逐维审核接口保留为可选能力，当前页面流程不使用。

### 10.3 单维追问

- 每个维度下方新增 AI 对话框：`POST /api/inst/cases/{id}/dimensions/{key}/chat`，只带该维结论、检查项、反证、证据与最近 8 条对话。
- 新增 AI TaskSpec `inst.dim.chat`（`backend/ai/router/tasks/institution.py`）；AI 不可用时返回 503，不伪造回答。
- 对话仅保存在当前页面会话，不写入业务表；提问与回答摘要写 `inst_audit_event`。

### 10.4 审核方式

- 按 2026-11-03 用户确认：六个维度不需要逐维审批，页面只保留单维查看与追问；整体「审核通过 / 退回」仍在右侧一次完成。
- 逐维审核接口 `POST /api/inst/research/{version_id}/dimensions/{key}/review` 与 `dim_reviews` 列保留为可选能力，当前 UI 不再调用，也不作为整体审核的前置条件。
- 整体审核接口语义不变，既有自动化链路（研究 → 审核 → 辩论）不受影响。

### 10.5 AI 一页纸格式

- 一页纸改为结构化卡片：总结结论、关键指标（营业收入/净利润/ROE/PE）、01-06 六维要点、核心关注风险、下一步重点核验、免责声明。
- 后端 `ai_research_memo` 增加确定性 `metrics`（来自行情/估值/财务，缺失不编造）；AI 不可用时回退规则摘要（`engine=rule`），页面仍按同一格式展示。
- 版式（2026-11-04 调整）：AI 一页纸恢复为独立整行卡片，不再占用六维目录的 Tab；「证据与反证」不内联罗列，改为页头入口 + 弹窗查看。

### 10.6 验证

| 项 | 结果 |
|---|---|
| `pytest tests/test_inst_research_dimensions.py` | 5 passed：单维合并、逐维审核接口（可选）、单维追问、一页纸 metrics 与规则回退、量化推送契约 |
| `pytest tests/test_inst_*.py` | 48 passed（svquant_test） |
| `tsc --noEmit` | 通过 |
| e2e-09 只读 | 3 passed / 1 skipped |
| Playwright 走查 | 目录切换、单维正文、单独分析按钮、追问框、一键审核、结构化一页纸均可见；一页纸为独立整行卡片 |

## 11. 机会发现三 Tab、研究页 Tab 化与证据可读性（2026-11-03）

### 11.1 机会发现

`/inst/ideas` 从「全市场列表」改为三个 Tab：

| Tab | 数据 | 说明 |
|---|---|---|
| 量化策略推送 | `GET /api/inst/ideas/push` | A 股机构公司池，按近 2-20 个交易日动量 + 估值初筛；只推动量为正、PE TTM 0-100、PB 为正的标的 |
| 关注与自选 | `GET /api/inst/companies?pool_status=watch` | 观察池；立项评估后进入研究，或取消关注 |
| 当前持仓 | `GET /api/inst/portfolio` | 组合持仓、成本、市值、权重；复核立项或跳投后 |

量化推送规则写在接口返回的 `strategy.note` 与页面底部：窗口自动缩短（测试库只有最近几天数据时会用 3 日）、收盘后计算、不是实时信号、不构成投资建议。推送卡片展示参考价、动量、PE TTM、PB MRQ、筛选理由与标签；`industry` 为指数代码（如 `801120.SI`）时显示「行业待补充」。

**立项三问与决策门（2026-11-04）**

- 三个入口统一走「立项评估」弹窗：为什么现在、能力圈、资料齐备；数据不足显示「核心缺失」并禁止立项。
- 投资经理三选一：立项并进入研究 / 加入观察 / 放弃；三种决策都必须填写理由。
- `POST /api/inst/ideas/{company_id}/decision` 记录 `inst_idea_decision`（source/action/reason/circle_confirmed/data_sufficiency/actor/time）；立项额外创建研究案，放弃写 `drop_reason`，并写审计。
- 能力圈由投资经理勾选确认，不由规则或 AI 代替；规则建议明确标注「不是 AI 结论」。

### 11.2 研究页

- 「巴菲特六维分析」更名为「六维分析」。
- 「证据与反证」改为可读内容：类型图例（行情/财务/事实/公告/新闻/研究/反证）、来源中文说明、数据日期、原文摘录块与「这条证据说明什么」提示。
- 证据类型来自 `inst_evidence.evidence_type`；来源 `ifind:*` 显示为「iFinD 行情/财务库」，`eastmoney` 显示为「东方财富」，`agent` 显示为「AI Agent」。
- 2026-11-04 再次调整：一页纸恢复为独立整行卡片，证据改为页头入口 + 弹窗，详见 11.4。

### 11.3 验证

| 项 | 结果 |
|---|---|
| `pytest tests/test_inst_*.py` | 48 passed（svquant_test） |
| `tsc --noEmit` | 通过 |
| `npm run test:inst` | 5 passed |
| e2e-09 只读 | 3 passed / 1 skipped（新增机会发现页可达） |
| Playwright 走查 | 三个 Tab 计数 12/1/1；关注/取消关注可用；持仓卡片可见；研究页 6 个维度 Tab、独立一页纸卡片、证据弹窗均可见 |

### 11.4 研究页布局复核（2026-11-04）

按用户复核意见调整研究页信息层级：

| 项 | 调整 |
|---|---|
| 公司信息 | 从右侧栏移到页面最上方，横向展示代码、市场、行业、数据状态、参考价；研究案号放在卡片右上角 |
| 研究任务 | 删除右侧「研究任务」列表；生成过程中的「6 个 Agent 实时进度」保留，只在生成中展示 |
| AI 一页纸 | 从七维 Tab 中移出，恢复为六维分析下方独立整行卡片；自动生成与「重新生成一页纸」逻辑不变 |
| 证据与反证 | 不再在页面底部内联罗列；页头增加「证据与反证（N）」入口，点击打开弹窗查看类型图例、来源、数据日期、原文摘录与解释；支持遮罩/关闭按钮/Esc 关闭 |
| 五年 DCF | 按用户要求暂时移除计算器（研究页与辩论页均不再展示）；估值维度仍保留 DCF 假设的讨论与数据缺口提示，后续需要时再恢复 |
| 页面排版 | 主区域改为六维分析（左）+ 版本与审核（右）两栏，AI 一页纸在下方整行；1024 窄屏自动堆叠，无横向溢出 |

### 11.5 机会发现立项三问（2026-11-04）

按《11.4 白欣宜主观机构端产品方案（开发版）》先落地立项决策门：

| 项 | 实现 |
|---|---|
| 三问 | 为什么现在 / 能力圈 / 资料齐备；资料状态按 `data_status` + 市场判断，美股/港股标 `missing` |
| 决策 | 立项并进入研究 / 加入观察 / 放弃；三种决策均必须填写理由 |
| 约束 | 资料 `missing` 禁止立项；立项必须勾选能力圈确认；决策人必须是投资经理 |
| 留痕 | 新表 `inst_idea_decision` 记录来源、动作、理由、能力圈确认、资料状态、操作人与时间；写 `idea.decision` 审计 |
| 接口 | `POST /api/inst/ideas/{company_id}/decision` |
| 前端 | 三个入口卡片统一「立项评估」弹窗；卡片显示资料齐备度；不直接跳研究 |

验证：`pytest tests/test_inst_*.py` 54 passed；`e2e-10` 8 passed（新增立项三问弹窗用例）；`tsc` 与 `npm run test:inst` 通过。

### 11.6 六维提示词与 CIO 一页纸（2026-11-04）

按白欣宜产品方案的提示词和 CIO 合成口径升级：

| 项 | 实现 |
|---|---|
| 六维提示词 | `inst-dim-v2`：产业/商业模式/护城河/财务/治理/估值补充数据纪律、分析框架、结论先行、区分事实/推断/不知道、每条结论附证伪条件；基准日使用输入 `as_of`，不再硬编码日期 |
| 一页纸 | `inst.research_memo` 增加 `decision`（proceed/watch/avoid）、`six_dim_scores`、`conflicts`、`key_variables`；提示词加入否决/降级规则与冲突裁决 |
| 校验 | `validate_research_memo`：decision 非法回落 watch；六维 key 与 1-5 分校验，非法项丢弃 |
| 规则兜底 | AI 不可用时 `decision=watch`，不伪造评分/矛盾；页面显示“研究建议：观察” |
| 前端 | 一页纸展示研究建议、六维评分、未解决分歧、关键变量；仍不给目标价或买卖指令 |

验证：`pytest tests/test_inst_*.py` 56 passed；`e2e-10` 8 passed；`tsc`、`npm run test:inst` 通过。

### 11.7 证据可信层与 hash 绑定（2026-11-04，B2）

| 项 | 实现 |
|---|---|
| 证据分级 | `inst_evidence.grade` A-D：A 公告/年报、B 交易所/数据平台、C 第三方/媒体、D AI/推断；旧证据按来源幂等回填 |
| PIT | `event_time` / `available_time` / `cutoff`；行情用交易日，财务用公告日；缺失日期以生成日兜底并标注 |
| 原文锚点 | `document_id` / `page_ref` / `source_uri` 字段已建，当前数据源未提供时为空，不编造 |
| 版本 hash | `inst_research_version.content_hash` + `cutoff`；生成时计算，旧版本在审核/辩论/议案前补齐 |
| 议案绑定 | `inst_proposal_version.snapshot` 绑 `research_content_hash`、`research_cutoff`、`evidence_hash` |
| 授权绑定 | 授权快照绑 `proposal_hash`、`research_content_hash`、`evidence_hash` |
| 风控 | `hash_binding` 硬检查：研究内容/证据 hash 与快照不一致直接 block |
| 辩论核验 | `inst_evidence_check` 记录 claim/证据核验状态；D 级不能单独支撑结论，无有效证据的论点 `valid=false` |
| 前端 | 证据弹窗展示等级、可用时间、原文锚点；版本卡展示截止日、内容 hash、冻结时间；辩论页展示核验汇总与逐条证据状态 |

验证（svquant_test，-28，dataDate 2026-11-03）：

| 项 | 结果 |
|---|---|
| `pytest tests/test_inst_*.py` | 66 passed（新增 B2 证据/ hash 2 条，线性流程补 hash 断言） |
| `tsc --noEmit` | 通过 |
| `npm run test:inst` | 5 passed |
| `e2e-09/10/11` | 13 passed |
| 控制台错误 / 接口 5xx / 横向溢出 | 0 |

### 11.8 AI 自动运行、50 字摘要与结果落盘（2026-11-05，PR A）

| 项 | 实现 |
|---|---|
| 自动运行 | 研究一页纸、审批 AI 风控/Chairman 进入页面自动加载；有缓存直接展示，无缓存且有写权限才生成；按钮改为「重新生成」`refresh=true` |
| 50 字摘要 | 六维 summary、一页纸 summary、审批/岗位 summary 及列表项均截 50 字；评分、证据、风险结构保留；辩论 claim 前端显示 50 字摘要，完整原文悬浮 |
| 落库 | 新增 `ai_agent_output` 缓存（task + org + 对象 + 输入 hash + 提示词版本）；一页纸/审批 AI 命中缓存不重复调用模型；规则兜底不缓存，保留重试 AI 的机会 |
| 追问落库 | 新增 `inst_ai_chat_message`，单维追问按用户持久化；进入维度加载历史，发送带 `client_message_id` |
| 提示词覆盖 | 新增 `ai_agent_prompt` + `services/institution/prompts.py` 默认提示词；`_ai_task`、六维、辩论调用前解析全局覆盖，版本 +1 后缓存自动失效 |
| 安全 | 生成仍受机构工作区权限约束；AI 只读，不改审批/授权/持仓状态 |

验证：`pytest tests/test_inst_*.py` 69 passed；新增 AI cache/prompt test；`tsc` 通过。Agent 管理 UI 在 PR B。

### 11.9 机构端 Agent 管理（2026-11-05，PR B）

| 项 | 实现 |
|---|---|
| 入口 | `/inst/about`，原「Agent能力」页改为「Agent 管理」；侧栏名称同步 |
| 目录 | 展示 51 个 Agent：机构 15 个（含独立行业分析）、平台 TaskSpec 28 个、Agent 技能 8 个；支持分组、搜索 |
| 可编辑 | 投资经理可改机构 Agent 提示词；平台/技能本批只读，标注「只读」；H5/invest Agent 由 #95 的 H5 页面管理 |
| 版本 | 保存写入 `ai_agent_prompt` 新版本、旧版本归档；可查看历史、恢复默认；提示词版本变化自动失效 AI 结果缓存 |
| 权限 | 机构角色登录可看；保存/重置/历史仅 `manager`；其他角色看不到提示词正文 |
| 安全 | 系统仍强制 JSON 校验、50 字摘要、证据引用与风控约束；提示词不能关闭这些规则 |
| 审计 | `ai_agent_prompt` 保留版本/操作人/时间；保存/重置同时写系统审计 |

验证：`pytest tests/test_inst_*.py` 70 passed（含 Agent 目录/权限/版本/重置）；`e2e-09/10/11` 14 passed；`tsc`、`npm run test:inst` 通过。

### 11.10 价值分析页：独立行业分析、K 线与研究区间（2026-11-05，11.5 文档第一批）

按《11.5 主观机构使用说明》先落地价值分析页：

| 项 | 实现 |
|---|---|
| 独立行业分析 | 新增 `inst.industry` Agent 与 `inst_research_version.industry_analysis`；与六维并行生成，独立卡片展示空间/周期/产业链/竞争/政策摘要、反证与数据缺口 |
| K 线 | 新增 `GET /api/inst/companies/{id}/bars`（未复权日线，最近 120 日）；研究页右上 K 线卡，测试库数据不足时显示实际可用根数 |
| 一页纸 | 增加 `price_range`（low/base/high，注明“研究区间，不是目标价”）与 `holding_period`（条件性期限）；规则兜底从版本估值区间生成 |
| 页面顺序 | 公司信息 → 行业分析 + K 线 → 六维/版本 → 一页纸，符合 11.5 文档的“第二行”结构；1024 自动堆叠 |
| 自动保存 | 行业分析随版本落库并纳入 content_hash；一页纸缓存/重生成沿用现有机制 |

验证：pytest 71 passed、e2e-09/10/11 14 passed、tsc/unit 通过。

后续批次（未在本 PR）：退回勾选行业/维度并重跑、辩论页投资意见与可编辑议案、合伙人→风控→Chairman 多人审批、组合/投后逐持仓状态与退出备忘录。

### 11.11 退回勾选与按板块重跑（2026-11-05，11.5 文档第二批）

按《11.5 主观机构使用说明（欣宜2）》补齐价值分析页的退回闭环：

- 研究页「退回」改为弹窗：勾选「行业分析」和/或六个维度，填写退回原因；至少选一项。
- `POST /api/inst/research/{version_id}/review` 支持 `targets`；退回后自动重跑所选板块/维度并生成新版本（版本 +1），未选内容保留。
- 行业分析与六维均可单独重跑；旧版本置为 `changed`，新版本回到 `pending_review`。
- 重跑复用现有 AI Agent、提示词覆盖、证据 hash 与 50 字摘要规则。

验证：pytest 72 passed、e2e-09/10/11 14 passed、tsc/unit 通过。

### 11.12 辩论后投资意见与可编辑议案（2026-11-05，11.5 欣宜2 第三批）

按新文档补齐第③步：

- 辩论完成后不再自动建案跳转；页面展示议案骨架（方向、目标仓位、价格上下限、资金来源、有效期、监控/退出条件），由投资经理确认/修改。
- 新增「投资意见」独立输入区，生成议案时一并写入议案快照并送审批；审批页展示。
- 价格上下限默认取研究估值区间，可收窄/放宽；注明“研究区间，不是目标价”。
- 后端 `POST /cases/{id}/proposals` 显式接收并校验方向、仓位、价格、资金来源、有效期、监控条件、投资意见；不再允许 config 任意覆盖锁定的研究/辩论绑定字段。
- 退出研究案仍强制 exit/0，不可建买入议案。

验证：pytest 72 passed、e2e-09/10/11 14 passed、tsc/unit 通过。

### 11.13 投委会审批顺序、多人审批与六项风控（2026-11-05，11.5 欣宜2 第四批）

按新文档补齐第④步：

- 审批顺序固定为 合伙人 → 独立风控 → Chairman，不能跳级；风控未放行不能进 Chairman。
- 同角色支持多人：审批记录按人留痕，附意见与条件；提案人不得审批自己的议案。
- 风控任一审批人否决即终局（`frozen`），Chairman 不能批准；风控通过后、Chairman 批准前仍可追加否决。
- 六项风控检查：集中度（同发行人 ≤15%、同行业 ≤30%，含跨市场同公司）、交易后现金 ≥10%、研究/辩论/证据版本一致、有效期与价格、交易资格（停牌/涨跌停/ST/资金或持仓）、重复与冲突。
- 合伙人/风控/Chairman 均支持「附条件」；条件写入审批记录并进入授权快照，执行前需执行人确认条件已满足（`conditions_met=true`）。
- 审批页按角色展示可执行动作、多人审批链与六项检查结果。

验证：pytest 75 passed、e2e-09/10/11 14 passed、tsc/unit 通过。

### 11.14 投资管理合并、单票盘中管理与 K 线升级（2026-11-05，11.5 欣宜2 第五批）

按新文档补齐第⑥步与行情图：

- 「投资组合」更名为「投资管理」；「投后管理」不再作为独立菜单，旧 `/inst/monitor` 重定向到 `/inst/portfolio`，接口权限保留。
- 投资管理主页保留组合总览、持仓明细、组合约束、行业敞口、执行异常，并新增「在途退出审理」回链。
- 持仓行新增「查看详情（盘中管理）」→ `/inst/portfolio/:symbol` 单票页：持股信息、买入论点台账、监控事件与论点核对、投资经理意见。
- 论点台账从最近买入议案/研究版本重新生成，旧台账保留；仅在用户点「重新生成台账」时写入，不自动覆盖。
- 自动监控扫描：复核到期与价格较成本下跌超 10% 自动登记事件（7 天内去重），由有写权限用户点「重新扫描」触发。
- 经理意见可「记录并继续持有」或「提交减仓/清仓审理」，退出仍走研究 → 辩论 → 审批全流程。
- K 线支持日/周/月切换（周月由日线聚合）、MA5/10/20/60 勾选、30 秒轮询；分时/1/5/15/60 分钟按钮保留，但当前行情源只有日线，明确返回「未接入」而不是伪造数据。

验证：pytest 78 passed、e2e-09/10/11 15 passed、tsc/unit 通过。

### 11.15 机会发现移除立项三问（2026-11-05）

- 候选卡移除「立项评估」入口和三问弹窗（为什么现在 / 能力圈 / 资料齐备）。
- 每个公司卡直接展示「进入研究」「放弃」两个动作；持仓卡同样可重新立项或放弃。
- 进入研究直接创建研究案并进入价值分析；核心资料缺失或美股/港股无数据源的标的禁用立项并说明原因。
- 放弃时要求填写理由，写入 `inst_idea_decision`、公司池 `drop_reason` 与审计。

验证：e2e-09/10/11 15 passed、tsc/unit 通过。

### 11.16 Agent 提示词按 11.5 全集更新，移除 50 字限制（2026-11-05）

- 机构端所有 Agent 默认提示词改为「§0 通用底座 + 对应 Agent 段落」：行业 A03、六维 A04–A09、一页纸 A10、辩论 A11/A12/A15/A16、风控 A19、Chairman A20、岗位 A07/A13、A08/A09、A23/A24。
- 六个维度使用 A04–A09 共用的「六维统一输出契约」；一页纸使用 A10 的 dimension_scores / price_band / memo_md 等字段；风控与 Chairman 使用 A19/A20 的 checks / verdict / conditions / proposed_authorization 字段。
- validator 兼容新契约并归一化为平台字段（summary / checks / counter / evidence / risks / open_questions / six_dim_scores / price_range），旧缓存与旧调用不受影响。
- 移除 50 字摘要限制：后端不再截断 summary/checks/counter/risks 等；前端去掉 `clipBrief` 截断与「50 字摘要」文案。
- 研究页新增「完整分析 / 完整行业分析 / 完整一页纸与六张表」折叠区，展示 analysis_md / memo_md 全文；六维显示评级与 gate。
- Agent 管理中已保存的自定义提示词仍优先于默认值；需要采用新默认值时在 Agent 管理里「恢复默认」。

验证：pytest 81 passed、e2e-09/10/11 15 passed、tsc/unit 通过。

### 11.17 行业 Agent 空内容根因修复（2026-11-05）

**根因**：LLM 网关当前模型是推理模型。`inst.industry` 的 `max_tokens=3000` 全部被推理 token 消耗（`reasoning_tokens=3000`、`finish_reason=length`），正式 `content` 为空；网关 `_normalize` 只看到空 content，丢弃了 `finish_reason` 与 reasoning 用量，直接抛 `AiBadOutput`，且空内容不触发重试/兜底，最终变成研究 500。

**修复**：
- 提高机构端任务输出预算：行业/一页纸/辩论 16000，六维/岗位 12000，风控/Chairman 8000，单维追问 4000；超时同步放宽。
- 网关保留 `finish_reason`、`reasoning_tokens`、`reasoning_chars` 并记录日志；`finish_reason=length` 抛新的 `AiOutputTruncated`。
- `complete` 遇到截断自动把 `max_tokens` 翻倍重试（上限 `LLM_MAX_OUTPUT_TOKENS`，默认 32000），再切换兜底模型；`content_filter` 不重试。
- `.env.example` 增加 `LLM_MAX_OUTPUT_TOKENS` 说明。

**实测**：同一行业 Prompt 走后端真实网关——
- `max_tokens=3000`：reasoning 3000、content 0、finish_reason=length（复现空内容）；
- `max_tokens=12000`：reasoning 6092、content 9943、finish_reason=stop；
- `max_tokens=16000`：reasoning 8230、tokens_out 15087、JSON 通过 validator。
- 不再依赖 #104 的“失败即降级”兜底；正常路径即可产出完整行业分析。

验证：`pytest tests/test_inst_*.py tests/test_llm_fallback.py tests/test_ai_router.py tests/test_ai_layer_boundary.py` 114 passed。

### 11.18 Agent 管理只展示机构端 Agent（2026-11-05）

- `GET /api/inst/agents` 只返回 `source=institution` 的主观机构端 Agent，不再混入平台 Agent 与 Agent 技能。
- 页面移除「机构/平台/技能/全部」筛选，只保留搜索；卡片去掉来源徽标，描述改为「只展示主观机构端自己的 Agent」。
- 平台/个人中心的 Agent 目录接口不受影响。

验证：pytest `test_inst_agent_prompt_api.py` 通过；e2e-10 Agent 管理用例通过；tsc 通过。

### 11.19 AI 一页纸持久化（2026-11-05）

**问题**：进入已有研究案仍显示「AI 一页纸生成中」。原因是只按 `input_hash + prompt_version` 精确命中缓存；提示词/输入变化（包括本次 11.5 提示词升级）后，已有 AI 输出无法命中，页面每次进入都重新调用模型；规则兜底结果又因为 `engine=rule` 不落盘，导致每次进入都重算。

**修复**：
- `GET /cases/{id}/ai/memo` 改为只读 peek：命中已持久化结果直接返回，未命中返回 `missing`，不触发生成。
- `POST /cases/{id}/ai/memo` 仅在用户进入页面且确实没有结果时生成；生成后无论 AI 还是规则兜底都写入 `ai_agent_output`，提示词变化不再让旧结论消失。
- 精确缓存未命中时按 `scope_key`（研究案 + 版本）读取最近一次结果，返回 `cached=true` / `stale=true`；用户点「重新生成一页纸」才覆盖。
- 前端进入页面先 GET；已持久化时直接展示，只有写角色且无结果才 POST 生成；显示「已持久化 · 可重新生成」提示。
- 风控/Chairman AI 摘要同样增加 scope 最近结果回退，提示词变化不会导致页面反复重新生成。

**实测**：已有研究案首次 POST 生成规则/AI 结论并落盘；随后 GET 直接返回同一 `summary`（`cached=true`），再次 POST 不再调用模型；E2E 用例覆盖。

验证：`pytest tests/test_inst_*.py tests/test_llm_fallback.py` 91 passed；e2e-10 一页纸持久化用例通过；tsc 通过。

### 11.20 投委会审批四套角色页面（2026-11-05，11.5 欣宜3）

按新文档把审批台改为「一个入口、四套角色页面」，权限由服务端强制：

- **投资经理**：只读「我的议案」，只看自己提交的议案与三关进度；无审批按钮、无风控逐项核查、无任何 Agent 建议。
- **合伙人**：待审/已审；详情为议案 + 投资意见 + 研究与辩论摘要 + 操作区；右侧只放「合伙人 Agent · 审批建议」（新增 A18 Agent）。
- **独立风控**：待审/已审；详情为议案 + 投资意见 + 六项硬约束 + 交易资格 + 合伙人结论 + 操作区；右侧只放风控 Agent；不展示研究与辩论全文。
- **Chairman**：待审/已审；详情为议案 + 完整审批链 + 风控结论 + 研究与辩论裁决 + 操作区；右侧只放 Chairman Agent；不展示六项逐条明细。
- 页面骨架统一为左侧单列主工作区（约 72%）+ 右侧固定辅助区（约 28%）；顶部吸顶摘要条显示标的、版本、当前关卡、总体状态与角色。
- 列表按角色过滤：只显示轮到你这一关且你本人尚未给意见的议案；已审进入「已审」，进度显示「已审 x / 共 n」。
- 跨角色直接打开议案返回 403「该议案不在你当前角色的审批范围」，不会退化成只读完整审批页。
- 同角色多人改为**全部给出意见才推进下一关**；任一风控否决仍立即冻结终局；附条件随议案传递。
- 新增 `inst.partner_memo`（A18 合伙人 Agent）及 `/proposals/{id}/ai/partner-memo`，结果按议案版本落盘。

验证：pytest 92 passed、e2e-09/10/11/12 共 17 passed、tsc/unit 通过。

### 11.21 公司研究页：六维全宽与底部进入辩论（2026-11-06）

- 去掉右侧「版本与审核」卡片；版本号、状态、hash、冻结时间不再单独展示。
- 六维分析占满整行：左侧垂直维度目录，右侧显示所选维度的结论、证据、完整分析与单维追问。
- 页面最下方新增「进入投资辩论」按钮：
  - 版本已通过：直接进入辩论。
  - 版本未通过：点击后先冻结当前研究版本（审核通过），再进入辩论。
- 原「审核通过 / 退回并重跑」按钮随版本与审核卡片一起从页面移除；退回重跑接口仍保留，后续可放到独立入口。

验证：tsc 通过；e2e-10 公司研究详情用例通过（断言无「版本与审核」、底部有「进入投资辩论」）。

### 11.22 六维数据第一批：10 年财务、同业、净债务与数据闸门（2026-11-06）

按六维数据评审的第一批落地，不依赖新数据源：

- **10 年财务**：六维 Agent 财务输入从 8 个季度扩到 40 个季度（约 10 年），新增 `history_summary`（营收 CAGR、毛利率/ROE 中位数、OCF/净利、FCF 为正比例）。
- **同业中位数**：按申万一级行业取最多 40 家同业，计算营收增速、毛利率、净利率、ROE、PE、PB 中位数，写入 `peer_summary`；仅作对照，不当作公司自身数据。
- **估值**：新增同业估值中位数、股息率、股本变动、分红历史；演示估值加入净债务近似（总负债−现金），输出 `enterprise_value` / `equity_value` / `net_debt_proxy`，并明确标注“近似、未拆分有息负债”。
- **数据完备性**：每个维度输出 `data_completeness`（level/have/missing）；`level=partial` 时 gate 最高 watch，`level=missing` 时 gate 必须 fail；治理缺核心字段直接 fail（不可买入）。
- **一页纸闸门**：任一维 gate 非 pass 时，研究建议 `proceed` 自动降为 `watch`；治理 fail 时明确写“不可买入”。
- **提示词**：六维/行业/一页纸提示词追加“平台数据边界与闸门”，禁止用财务结果反推行业规模/份额、分部/客户、治理事实或审计结论。
- **页面**：六维与行业卡片显示数据完备性（缺失项可展开）；一页纸显示数据闸门说明。
- **数据需求文档**：第二批数据需求已整理到 `docs/数据需求/机构六维数据需求-第二批.md`，供数据业务排期。

验证：pytest 94 passed；tsc 通过；真实案例 `mode=full` 返回治理 gate=fail、其余 watch，一页纸 decision=watch。

### 11.23 数据业务 A 组接入（2026-11-06）

接入数据业务 A 组四张表（schema `svquant`）：

- `holder_top10` / `holder_float_top10`：最新报告期前十大股东/流通股东、持股比例、变动；只作为治理可见性，`ratio` 是报告期前十大合计、未认定一致行动人，不当作控制权集中度。
- `segment_revenue`：最近年报产品/地区/行业分部收入、占比、毛利率；与同一报告期合并营收做对账。
- `audit_opinion`：最新年报审计意见类型；非标准意见会把财务维度 gate 直接降为 fail。
- 新增 `services/institution/data_platform.py`：按 `available_time`/`report_date` 做 PIT，表未加载时返回 None，不影响研究生成。
- 数据完备性更新：治理 level=partial 但 `gate_cap=fail`（A 组只有股东/审计，仍不可买入）；商业模式补分部收入；财务补审计意见；一页纸仍最高 watch。
- 提示词 payload 增加 `holder_summary` / `float_holder_summary` / `segment_summary` / `audit_summary`，并明确股东比例口径。
- 三只样例（600519/000858/300750）已载入 `svquant_test` 验证；全市场由数据业务 loader 写入，DSN 由运维注入。

验证：pytest 96 passed（含 A 组数据接入测试）；tsc、e2e-09/10/11/12 17 passed。

### 11.24 数据业务有息负债/净债务接入（2026-11-06）

接入数据业务 `svquant.interest_debt`（有息负债、净债务、预收款、合同负债）：

- `data_platform.interest_debt_summary`：按 `report_date <= as_of` 且 `available_time::date <= as_of` 做 PIT（available_time 为公告/可见时点 m_anntime）；返回短期借款、一年内到期非流动负债、长期借款、应付债券、租赁负债、有息负债合计、现金、受限现金、净债务、预收款/合同负债、母公司/少数股东权益、`is_financial`。
- 口径以数据业务 2026-11-06 确认为准：
  - `interest_debt_total` = 短借 + 一年内到期非流动负债 + 长借 + 应付债券，**不含租赁负债**（源三表无该字段，固定 NULL，也未计入合计）；payload 用 `lease_in_total=false` 明示。
  - `net_debt = interest_debt_total − cash`，**cash 未扣受限资金**（`restricted_cash` 源缺失）；我们直接采用，不二次调整，展示标注“未扣受限资金”。
  - 金融企业 `interest_debt_total` 与 `net_debt` 均为 NULL，`is_financial=true` 是主判断；NULL 不得当 0，也不得用总负债−现金替代。
  - `advance_receipts` 是预收款项；`contract_liabilities` 源未单列（NULL），两者不可相加，也不参与 Gate。`advance_receipts > 0` 才算“有预收余额”的正面证据，`=0` 只表示该期期末无余额或源未列示，NULL 表示缺失（全市场非空 191,484 行中 0 有 95,602 行）。
  - 2011–2015 归母权益已回补，但 `available_time` 取原表 `m_anntime`，不是 F10 `NOTICE_DATE`。
- 净债务优先使用数据业务口径，原先的“有息负债代理 + 现金”只在表未加载时兜底，估值桥注明来源。
- 金融企业（`is_financial=true`）不适用净债务桥：演示估值降为 `relative_only` 并写明原因，不拿 NULL 当 0。
- 数据完备性：财务维度补充有息负债/净债务；商业模式补充预收款项（非合同负债）；估值维度注明净债务口径。
- 提示词 payload 增加 `interest_debt_summary` 与上述口径说明。

验证：pytest 98 passed（含 `test_interest_debt_summary_and_financial_null` 的 PIT 当天/前一天边界、`test_build_research_uses_data_business_net_debt`）；tsc 通过；e2e-09/10/11/12 17 passed。


### 11.25 主观机构端 v3 全量切换（2026-11-09）

按 `白欣宜11.6产品原型全流程.pdf` 与 `白欣宜11.6旸谷主观投研平台.html` 完成一次性切换，`/inst` 不再提供 v2 工作区。

**路由与壳**

- `/inst` 单一 v3 路由树：投资工作台、项目流水线、只读结果页、02 价值分析、03 多空辩论、04 投委会审批、05 执行成交、06 投资管理、流程与权限。
- 旧入口重定向：`overview → /inst`、`ideas → /inst/pipeline`、`portfolio|monitor → /inst/manage`、`execution → /inst/execute`、`about|audit → /inst/playbook`；旧预览 `/inst-v3/* → /inst`。
- v2 页面与 `InstLayout` 已删除；`instUi.tsx` / `instLocale.tsx` 因量化机构端仍在引用而保留。
- 生产按登录身份裁剪菜单，不提供前端角色切换。

**服务端状态机与门禁**

- 六阶段：0 机会发现 → 1 价值分析 → 2 多空辩论 → 3 投委会审批 → 4 执行成交 → 5 投资管理；`inst_case_transition` / `inst_gate_run` 记录迁移与门禁。
- 三次锁定：研究定稿 R3（六维 6/6、低置信处理、数据门禁、证据/hash）、议案 P3（研究已锁定、辩论完成、方向/仓位/价格带/资金/有效期/监控/意见齐全）、授权 AUTH（不可变快照）。
- 审批顺序合伙人 → 风控 → Chairman；同角色多人必须全部表态；提案人回避；风控否决终局；未锁定议案不能进入三关。
- 新增只读 read model：`/api/inst/pipeline`、`/projects/{key}`、`/holdings/{symbol}`、`/playbook`。

**验证**

- `pytest tests/test_inst_*.py`：103 passed，8 subtests passed。
- `npm run test:inst`：11 passed；`tsc --noEmit`、`npm run build` 通过。
- Playwright `e2e-09..12`：13 passed（写库闸门仅 `svquant_test`），覆盖六阶段入口、旧入口重定向、六角色菜单、研究 R3/P3 锁定、三关审批与跨关拒绝、AUTH 执行、结果页、1440/1024/400 无横向溢出。

**边界**

- 真实券商、多租户、SSO、WORM 审计仍未接入；执行仍为 SimBroker 纸面撮合。
- 部分 v2 遗留接口仍保留兼容（如 `research/{id}/review`），v3 页面统一走 `research/{id}/lock` 与 `proposals/{id}/lock`。


### 11.26 研究定稿门禁可视化与低置信复核（2026-11-09）

补齐 v3 价值分析最后一步，避免用户只能看到“研究门禁未通过”而无处处理。

- 新增 `GET /api/inst/research/{version_id}/gate`：返回六维 6/6、低置信、数据门禁、证据包、版本校验码五项检查与 `pass/warn/block`。
- 定稿页展示门禁明细；低置信维度（评级 <3.3 或置信度 <0.66）列出待复核项，可逐维调用 `POST /research/{version_id}/dimensions/{key}/review` 复核通过，复核说明写入审计。
- 正常门禁通过时使用「锁定研究定稿 R3」；仍有阻断项时，必须勾选“我已确认数据缺口”后才能「带缺口锁定」，服务端记录 `allow_gaps` 与原因。
- 锁定后仍由服务端再次执行门禁，页面不能绕过。

验证：pytest 104 passed；`tsc --noEmit`、`npm run build` 通过；Playwright `e2e-09..13` 共 14 passed（仅写 `svquant_test`）。


### 11.27 审批页研究与辩论摘要、Chairman 风控结论（2026-11-09）

补齐审批角色的决策材料；仍严格遵守“只看本关该看的字段”。

- 合伙人：在复核对前展示只读「研究与辩论摘要」——研究版本、行业底图、六维 gate/评级/摘要、一页纸结论、辩论结论与多空要点；不展示风控六项明细。
- Chairman：展示同一份研究与辩论摘要 + 「风控结论」（结论、意见、附加条件、表决进度）+ 完整审批链；仍不回传风控逐项核查值。
- 风控：只看六项硬约束与合伙人结论，不展示研究与辩论全文。
- 三张摘要卡在 400px 宽度下改为自适应网格；e2e-09 的窄屏检查扩展到 v3 全部八个入口。

验证：pytest 104 passed；`tsc --noEmit`、`npm run build` 通过；Playwright `e2e-09..13` 14 passed。


### 11.28 审批页 Agent 建议（2026-11-09）

把原型里的合伙人 / 风控 / Chairman Agent 建议接入 v3 审批页右侧栏。

- 右侧栏按登录角色显示对应 Agent：合伙人「审批建议」、风控「审批建议」、Chairman「决策建议」；投资经理仍为提案人只读。
- 进入议案时只用 `GET ...?cached_only=true` 读取已有建议，不自动调用模型；点击「生成审批建议 / 重新生成建议」才走 POST。
- 建议展示摘要、结论、主要风险、待确认问题、引用证据数，并标注引擎、缓存与上游变更；建议只读，不改变审批状态。
- AI 不可用时页面显示错误，审批按钮仍由服务端门禁控制。

验证：pytest 105 passed（新增 cached_only 不调用 AI 测试）；`tsc --noEmit`、`npm run build` 通过；Playwright `e2e-09..13` 14 passed。e2e-12 改用已持仓标的的卖出议案、e2e-11 目标仓位降到 1%，避免在途买入额度随重复运行累积。


### 11.29 执行成交与投资管理 UI 走查修复（2026-11-09）

补上 05/06 两个工作台的浏览器级验证，并修复走查发现的问题。

- **执行成交**：新增 Playwright 覆盖授权核对 → 下单成交 → 对账 → 持仓更新；执行成功后授权卡片立即显示 `filled`，不再停留在旧的 `qualified`。
- **投资管理**：监控事件 `detail` 可能是对象（如 `{text: ...}`），原页面直接渲染对象会触发 React 崩溃；统一用 `textOf` 归一化为字符串，覆盖事件、论点、KPI、推翻条件与退出意见。
- **退出入口**：创建退出案后自动进入 02 价值分析，按钮改为“创建退出研究案并进入研究”；不再让用户停在“提交投委会复核”的旧文案上。
- **一页纸空态**：没有研究版本时，`GET /cases/{id}/ai/memo` 返回 200 `missing`，不再 404 污染控制台；e2e-10 的控制台错误检查恢复全绿。
- 新增 `e2e-14`：卖出议案 → AUTH → 执行 UI → 对账 → 记录预警 → 创建退出研究案。

验证：pytest 105 passed；`tsc --noEmit`、`npm run build` 通过；Playwright `e2e-09..14` 15 passed。


### 11.30 v3 内容区取消 1180px 窄版居中（2026-11-09）

宽屏下 `.v3-main` 同时设置 `max-width:1180px` 与 `margin:0 auto`，在 1920 屏幕上左右各留出约 230px 空白，工作台被挤在中间。

- 去掉 `max-width` 与居中 margin，内容区按 `width:100%` + 左右 28px 内边距铺满；侧栏与内容区仍各自独立。
- 页面标题、流水线、结果页与工作台网格随宽度扩展；400/1024 断点和横向溢出规则不变。
- e2e-09 新增 1920 宽屏断言：`.v3-main` 宽度 >1500px 且无横向滚动，防止重新引入窄版上限。

验证：`tsc --noEmit`、`npm run build`、`npm run test:inst` 通过；Playwright `e2e-09..14` 16 passed。


### 11.31 v3 字号上调、工作台三栏对齐与流水线横向卡片（2026-11-09）

- **字号**：导航、页面标题、卡片标题、表格、表单、Agent 右栏与 chip 整体上调一档；正文 13px、表格 12.5px、表单 12.5px，最小标签不低于 10px。
- **三栏高度**：桌面端（>1100px）左项目列表、中栏工作区、右 Agent 栏统一为 `calc(100vh - 320px)`，各自内部滚动；中栏最后一张卡片铺满剩余高度，空态内容垂直居中，不再出现“中栏 300px、下面空一大片”。1440×900 下三栏均为 580px，页面无纵向/横向溢出。
- **项目流水线**：选择单个环节时，看板切为单列，项目卡片用 `auto-fill minmax(240px,1fr)` 横向铺开；「全流程」仍保留六列看板。
- e2e-09 新增单流程横向排列断言；1440/1024/400 溢出检查保持通过。

验证：`tsc --noEmit`、`npm run build`、`npm run test:inst` 通过；Playwright `e2e-09..14` **17 passed**。


### 11.32 右侧 Agent 面板与角色切换（2026-11-09）

按原型补上“右侧 Agent 面板”，不再只显示一个静态 CURRENT AGENT。

- 新增 `InstV3AgentRail`：角色卡网格 + 当前 Agent 详情（模型 / 状态 / 工具 / 产出）+ 本步上下文；多角色时明确显示“可切换”。
- **02 价值分析**：六位研究员各一张角色卡，点击任一维会同时切换主区六维分析页；行业/一页纸/定稿步骤显示单角色（定稿含研究经理与研究归档）。
- **03 多空辩论**：多空立论步骤显示多头/空头两张角色卡，点击切换主区多头或空头分析页；交叉质询/估值/议案步骤显示单角色（估值标注确定性服务）。
- **06 投资管理**：组合总览/单票盘中显示组合经理或监控 Agent；退出步骤显示组合经理 + 风控两张卡。
- **05 执行成交**：显示确定性执行引擎卡，明确“非 Agent · 确定性”。
- 右侧栏沿用工作台统一高度并内部滚动。

验证：`tsc --noEmit`、`npm run build`、`npm run test:inst` 通过；Playwright `e2e-09..14` **17 passed**，e2e-11/13/14 增加 Agent 切换断言。


### 11.33 多空立论：分段切换与一句话论点（2026-11-09）

- 主区增加明显的多头 / 空头分段切换（显示各自条数），与右侧 Agent 面板双向同步；切换后只显示当前一方的论点。
- 每条论点改为一句可扫读的 headline（≤40 字），完整原文保留在 title 悬停中；证据条数与置信度单独成 chip，证伪条件保留在下方。
- 规则兜底辩论改为短句；AI 多空提示词增加硬要求：claim 陈述 ≤40 个汉字，数字、口径与计算过程放进证据、量化影响与证伪条件。
- e2e-11 增加分段切换、Agent 面板同步与 headline 长度断言。

验证：pytest 105 passed；`tsc --noEmit`、`npm run build`、`npm run test:inst` 通过；Playwright `e2e-09..14` 17 passed。


### 11.34 演示项目精简为每环节 3 个（2026-11-09）

- 项目流水线新增 `INST_PIPELINE_PER_STAGE`（默认 3，0=不限制）：每个环节只返回并展示最多 3 个项目，`count` 与 `total` 同步为展示数，避免演示时一眼看到几百个项目。
- 当前演示库 `svquant_test` 已清理：六个环节各保留 3 个研究案（阶段 1–5 共 15 个），删除多余测试项目及其订单/退出案；公司池与持仓数据不动。
- 注意：清理是测试库操作，不在代码提交内；后续 E2E 新增项目会被流水线上限隐藏，但如需彻底精简可再次按 3 个/环节清理。
- 新增测试 `test_pipeline_per_stage_limit`，确保环节条数与返回卡片一致。

验证：pytest 106 passed；Playwright `e2e-09..14` 17 passed；流水线 API/UI 均为 6 环节 × 3 个，共 18 个。


### 11.35 Agent Prompt 对齐 11.9 v2.1 规格（2026-11-09）

按 `11.9欣宜Agent_Prompt_v3_呈现版.md` 重写机构端 Agent Prompt。

- **通用底座**：换成规格 §2 的 v2 底座：唯一事实源、证据分级、数字四件套、字段字数预算、gate/confidence/rating 锚点、输出前 8 条自检。
- **逐 Agent**：
  - P02 行业、P03–P08 六维、P09 一页纸；
  - P11 多头、P12 空头、P13 主持；
  - P15 合伙人、P16 风控、P17 Chairman；
  - P19 监控台账、P20 退出研究。
- **字段契约**：六维强制 `rating / gate / confidence / summary / checks / counter`；行业 `checks` 禁止为空；审批建议统一 `verdict / summary / risks[3] / open_questions[3] / evidence[]`；辩论 claim 28–42 字、falsifier 12–22 字。
- **落库链路**：
  - 六维/行业保留 `headline / kpis / direct evidence_ids`，不再被合并层丢掉；
  - 一页纸生成后把 `conclusion` 写回研究版本（未锁定时），并清空旧 `content_hash` 等下次门禁重算；
  - 辩论采用 P13 的 `conclusion`（无 `chair` 时由校验器合成，兼容旧契约）。
- **P01 机会发现**：`data_sufficiency` 对外改为 `insufficient`，数据库约束兼容旧 `missing`；台账兜底不再把“有条件通过”当买入论点，并从 monitoring 生成 KPI/证伪。
- **版本**：`PROMPT_VERSION` / `DIM_PROMPT_VERSION` 升到 `inst-v3.2` / `inst-dim-v3.2`，避免旧缓存继续命中。
- **边界**：P01 立项、P10 定稿复核、P14 议案、P18 组合总览、P21 退出风控当前仍是规则/人工/确定性步骤，没有独立 LLM Task；其字段契约已在对应代码中体现。若线上 Agent 管理里保存过全局 Prompt 覆盖，需重置为代码默认值后才会生效。

验证：pytest 107 passed；`tsc --noEmit`、`npm run build`、`npm run test:inst` 通过；Playwright `e2e-09..14` 17 passed。


### 11.36 机构端生产版 UI 收口（2026-11-09）

- **生产版标识**：移除顶栏 v3 标识、侧栏演示环境说明与静态数量、原型/角色切换说明；业务版本号只保留接口返回的研究/议案版本。
- **字体**：按反馈保留原有字体：正文 `Inter`、标题 `DM Sans`、数字 `JetBrains Mono`；数字全站 `tabular-nums`。
- **估值复核**：字段标签与内容全部中文化，隐藏 `is_demo`、内部 error 与原始 JSON；净债务桥/关键假设/每股价值/企业价值等按可读格式展示，并清理演示口径文案。
- **交叉质询**：按 claim 分组显示对应论点，核验状态翻译为已核验/部分核验/未核验/证据不足/证据矛盾，并显示证据编号与问题说明。
- **页面标题**：除首页外移除大标题下的解释性小字。
- **数字与列表**：删除静态计数与常数占位；数值来自接口。新增 `dedupeBy`，项目/研究案/论点/议案/授权/持仓/台账按唯一业务主键去重，并补单测。
- **三态**：页面级加载/错误态 + 列表/详情空态；无数据时显示明确空态，不渲染空容器。
- **验收截图**：`docs/测试设计/evidence/inst-ui-production-20261109/`（1280/1440/1920、空态、超长文本、交叉质询、估值复核）及 `README.md` 清单。

验证：pytest 107 passed；`tsc --noEmit`、`npm run build`、`npm run test:inst` 13 passed；Playwright `e2e-09..14` 17 passed。


### 11.37 研究版本提示（2026-11-09）

- 项目流水线卡片、项目结果页、价值分析/多空辩论/投委会审批/执行成交/投资管理的页面标题均显示当前研究/议案版本。
- 各工作台左侧切换列表（研究案、辩论案、议案、授权）同步显示“版本 N”；同一股票的不同研究版本不再只靠名称区分。
- 持仓详情按最近议案版本回填版本号；无版本时显示“—”，不编造。


### 11.38 同股单流程与 Logo 修复（2026-11-09）

- 项目流水线按公司聚合，只保留最近更新的研究案；同一股票不会再同时出现在价值分析/多空辩论/审批等多个环节。
- 价值分析、多空辩论、投委会审批、执行成交的左侧切换列表同样按股票保留最新一条，版本提示继续显示当前版本。
- 修复左上角印章：品牌副标题的 `span` 样式不再作用到 Logo，`旸` 字恢复 22px 居中显示，不裁切。
- 三档与极端态截图已重新拍摄。

验证：pytest 107 passed；前端 13 passed；Playwright `e2e-09..14` 17 passed。


### 11.39 全局股票搜索与自选进入研究（2026-11-09）

- 顶栏搜索改为全市场股票搜索：按代码/名称/行业检索 `inst_company`，显示行业、数据状态、当前流程与版本。
- 无当前研究案时显示「进入研究」，点击创建研究案并进入 02 价值分析；已有当前案时显示所在环节与版本，点击进入当前工作台/结果页。
- 同一股票复用当前案，不重复建案，继续满足“一股一流程”。
- 搜索支持加载中、无结果、错误三种状态；仅投资经理可新建研究，其他角色可查看已有流程。
- 新增 `test_search_and_start_research_reuses_current_case` 与 e2e-09 搜索用例。

验证：pytest 108 passed；前端 13 passed；Playwright `e2e-09..14` 18 passed。


### 11.40 生产隐患修复（2026-11-09）

按前后端审计结果修复以下生产隐患：

- **流水线不再截断**：`INST_PIPELINE_PER_STAGE` 默认 0（不限制），演示环境才显式设 3；接口新增 `total_count`/`truncated`，前端显示“展示数 / 总数”。
- **一股一流程落到数据层**：`create_case`/`start_research`/退出研究对同一公司复用当前研究案，并加事务级 advisory lock 防止并发双击建重案；退出研究不再新建同公司第二个案。
- **阶段与失效语义**：重开研究把旧版本置为 `changed` 并作废在途议案；合伙人/风控/Chairman/授权入口硬校验 `stale_at`；P3 门禁要求研究未 superseded；研究生成只允许在阶段 ≤1，禁止绕过重开直接改研究。
- **研究门禁**：`review` 审核复用 R3 门禁；证据包为空、维度 Agent 失败改为阻断，只能显式“带缺口锁定”；旧 `review` 不再能无门禁通过。
- **授权与执行**：授权仅 Chairman/风控可签发，禁止自批；同一议案版本只生成一份有效授权，重复调用幂等；执行前必须预检通过且只能顺序进入成交步骤。
- **持仓读取**：组合、集中度、监控扫描改为按 symbol 取各自最新快照，跨日新增持仓不会让旧持仓消失；NAV 按现金 + 最新市值计算。
- **审批边界**：合伙人只能修改意见/监控/资金/有效期/价格带/目标仓位白名单字段，修改后重跑 P3 门禁；同一研究案同时只允许一份在途议案。
- **权限与隔离**：写接口要求 workspace `write`；研究/辩论写操作收紧到 manager；摘要角色不能读取研究全文/导出报告；监控事件校验公司归属，监控 join 带 org 条件；AI 返回的证据 ID 仅接受本机构本案证据。
- **演示与文案**：演示账号种子默认关闭（测试/本地显式开启）；`POLICY_VERSION` 改为 `inst-policy-v1`；估值与报告移除“演示”措辞但保留“简易测算/不构成目标价”限制；前端不再把“演示口径”改写为“研究口径”。
- **前端健壮性**：Agent 面板不再写死“已完成”；研究/辩论/审批/执行/投资管理加请求序号防止旧响应覆盖；全局搜索支持上下键/回车/Esc/ARIA 且创建中禁止重复提交；仪表盘待办按登录角色过滤；直接访问无权限工作区显示 403 空态；401 重登保留深链接；原型 HTML 移出 `frontend/public`。
- **样式维护**：移除 `* { font-size:12px !important }` 通配覆盖，改为 `.inst-v3` 基础字号 + `:where(*)` 继承 + 11/12/16/22 阶梯类，保留内联字号与可访问性。

验证：pytest 866 passed；`tsc --noEmit`、`npm run build`、`npm run test:inst` 15 passed；Playwright `e2e-09..14` 18 passed。


### 11.41 排版阶梯 v2（2026-11-10）

- 字号收敛为 5 档：**12 辅助 / 14 列表主文与正文 / 18 区块标题与口号 / 24 页面标题 / 32 KPI 数字**。
- 口号 `.v3-hero h2` 降为 18px、字重 400；KPI 数字保持等宽字体。
- 中文最小 12px：原先 11px 及以下的文本统一改为 12px，并使用更浅的辅助色。
- 字重仅 400/500/600：覆盖 `b/strong/h1-h4` 默认 700，表头 500，标题与 KPI 600。
- 移除 CSS 中所有 11/16/22px 字面量；基础字号 14px，`small`/表单继承不再缩小。
- 修复 400px 下组合概览双列 KPI 被长数字撑破导致的 21px 横向溢出（`minmax(0,1fr)`）。

自检：Playwright 采集 8 个页面共 **1167** 个文本节点，字号分布 `12px 595 / 14px 478 / 18px 53 / 24px 18 / 32px 23`，越界字号 0、越界字重 0。逐节点清单见 `docs/测试设计/evidence/inst-typography-20261110/font-nodes.csv`。

验证：`tsc --noEmit`、`npm run build`、`npm run test:inst` 15 passed；Playwright `e2e-09..14` 18 passed。


### 11.42 Agent 四行结论契约（2026-11-10）

- 所有机构端 Agent 输出改为四行：**判断 / 依据 / 影响 / 动作**。
  - 判断：一句有主语的完整句子。
  - 依据：证据 ID + 数据 + 日期。
  - 影响：对估值或仓位意味着什么。
  - 动作：继续 / 补数据 / 放弃；补数据写明补什么、从哪补、补齐前怎么做。
- 提示词底座、六维契约、行业/一页纸/风控/合伙人/Chairman 输出约束同步更新；新增 `judgment/basis/impact/action/rating_benchmark` 字段。
- 后端 `_four_line_output` 统一归一化：
  - 评分缺少基准（同业中位或历史分位）时，rating 置空并在界面提示“未采用”。
  - 空泛词（双轮、闭环、赋能、生态化反）替换为具体表达。
  - 常见缩写首次出现补中文解释（TAM/SAM/SOM、CR3/CR5、KAM、DCF、ROE、PE/PB、EV/EBITDA 等）。
  - “待补充”类占位不进入判断：规则兜底输出改为“关键数据尚未取得，当前不能形成可执行判断”，动作写明补数清单。
- 前端新增 `InstV3FourLine`：研究六维、行业分析、多空辩论论点、审批 Agent 建议均按四行展示；多空论点无数值依据时，动作改为“补数据”，不再给“继续”。

验证（隔离测试库 + 规则兜底数据）：
- 研究六维 6 个四行块、辩论 2 个四行块，全部 4 行，无 `—`/空占位、无空泛词。
- 后端 `pytest tests` 872 passed；`tsc --noEmit`、`npm run build`、`npm run test:inst` 15 passed；Playwright `e2e-09..14` 18 passed。


### 11.43 六维评分与总体得分（2026-11-10）

- 六维每维右上角新增 Agent 评分徽章：**满分 10 分、保留 1 位小数**，使用 32px 等宽数字；评分下方显示基准（同业中位/历史分位）；无基准时显示“未评分/缺少评分基准”。
- 后端输出新增 `score_10`（0–10，一位小数），由 Agent 直接给出或由 5 分制 rating×2 推导；rating_benchmark 仍为必填。
- 一页纸新增“六维总分”：六个维度评分的算术平均，保留 1 位小数；一页纸指标框去掉括号，只保留正文内容。
- 研究定稿：
  - 删除校验码行与门禁“版本校验码”检查；
  - 新增“总体得分”栏（32px 数字 + 六维平均说明）；
  - 总体得分随议案详情返回，合伙人/风控/Chairman 审批页头部与研究摘要均显示。
- 多空辩论论点若无证据 ID 或无数值型数据，动作判为“补数据”，不再给“继续”。
- 左侧流程工作台导航删除序号（01/02…），只保留名称与计数。

验证：后端 `pytest tests` 872 passed；`tsc --noEmit`、`npm run build`、`npm run test:inst` 15 passed；Playwright `e2e-09..14` 18 passed。


### 11.44 历史脏数据清理（2026-11-10）

- 新增 `scripts/ops/cleanup_inst_duplicates.py`：默认 dry-run，只允许 `*_test/*_dev/*_ci/*_e2e/*_local`，生产库名 `svquant` 硬性拒绝。
- 不删除业务记录：重复研究案归档为 `closed`，在途议案作废，重复 qualified 授权撤销；已成交订单/成交/持仓不动，只输出人工复核清单；所有写操作写 `cleanup.*` 审计。
- `repo.cases` 排除 `stage='closed'`：归档旧案不再进入流水线、仪表盘与工作台左列表，但仍可按 case key 访问详情。
- 在 `svquant_dev` 执行结果：9 组重复研究案、归档 178 个旧案（含 150 个测试/自检公司案）；0 重复授权、0 同案多议案；清理后开放重复组 0、开放测试案 0、审计 178 条。
- 在 `svquant` 生产库执行：dry-run 5 组重复、32 个旧案、2 份同案多议案；备份到仓库外 `/home/dev01/backups/inst-cleanup-20261110/` 后 apply；清理后开放重复组 0、同案多开放议案组 0、关闭案在途议案 0、审计 34 条。
- 生产 apply 需同时给 `--allow-production --confirm-production`；报告与清单：`docs/测试设计/evidence/inst-duplicate-cleanup-20261110/`。

验证：后端 `pytest tests` 874 passed；Playwright `e2e-09..14` 18 passed。


### 11.45 议案 Agent 建议（2026-11-10）

- 新增 `GET /api/inst/cases/{id}/proposal-advice`：汇总六维评分与多空辩论最终结论，输出：
  - 推荐结论：推荐买入 / 推荐卖出 / 建议持有 / 暂不买入；
  - 建议目标仓位；
  - 议案框架：方向、目标仓位、价格区间、资金来源、有效期、监控条件、投资意见。
- 规则：
  - 无持仓、六维平均 ≥7.0、辩论已完成且未给出“补充研究”、无 gate=fail → 推荐买入；仓位按 7/8/9 分对应 2%/3%/5%。
  - 已持仓：评分 <5.0 或存在阻断维度 → 推荐卖出；否则建议持有。
  - 辩论未完成、结论为“补充研究”或存在阻断维度 → 暂不买入。
  - 价格带优先使用研究估值区间，区间不可用时按现价 ±5%。
- 辩论页第 4 步新增“交易员 Agent · 议案建议”卡：展示六维评分、辩论结论、推荐结论、建议仓位与议案框架；可一键“采用建议填入议案”。
- 建议接口对已归档/不存在的案返回 `available=false`，不把辅助信息缺失当成 404。
- 新增 `test_proposal_advice_lists_scores_debate_and_framework` 回归。

验证：后端 `pytest tests` 875 passed；Playwright `e2e-09..14` 18 passed。


### 11.46 机会发现改为“机会来源”（2026-11-10）

- 移除机会发现的“立项三问”展示与阶段门禁文案，阶段 0 统一改为“机会来源”。
- 后端 `STAGE_DEFS`、阶段回填、流水线 stage 0 卡的 gate 全部改为“机会来源”。
- 新增 `_opportunity_source`：
  - 来源：量化策略推送 / 自选 / 持仓候选；
  - 来源说明：策略初筛理由、投资经理加入自选的原因或持仓复核说明；
  - 附带 pool_status、标签与发现时间。
- 项目结果页 stage 0 不再显示“为什么是现在/能力圈/资料齐备度/AI 建议”，改为“机会来源 / 来源说明 / 当前状态 / 标签”。
- 流水线 stage 0 卡片直接显示来源标签与来源说明。
- 立项决策接口与 `inst_idea_decision` 数据保留兼容，不再作为 stage 0 的展示门禁。

验证：后端 `pytest tests` 875 passed；前端 `tsc`/`build`/`test:inst` 15 passed；Playwright `e2e-09..14` 18 passed。


### 11.47 撤销四行结论，保留 10 分制评分（2026-11-10）

- 撤销 Agent 输出的“判断/依据/影响/动作”四行契约：
  - 提示词移除四行结论段落与字段；
  - 研究六维、行业分析、多空辩论、审批建议恢复 summary / checks / counter / data_gaps 展示；
  - 删除 `InstV3FourLine` 组件与相关样式。
- 保留 10 分制评分：
  - 旧 5 分制 rating 若没有 `rating_benchmark`，仍按 `rating×2` 显示 10 分制，并标注“基准待补”；
  - 规则兜底维度按 gate + confidence 生成 0–10 的“规则评分”，明确标注“规则兜底，非 AI 评分”，不再全部显示“未评分”；
  - 移除 Agent 面板中的 `x/5` 文案，面板只显示“结论已生成”；
  - 审批摘要改为显示 10 分制评分（基准缺失显示“待补”）。
- 评分基准提示保留，但不再因为旧数据缺基准而显示“未评分”。

验证：后端 `pytest tests` 876 passed；前端 `tsc`/`build`/`test:inst` 15 passed；Playwright `e2e-09..14` 18 passed。


### 11.48 doc_extract → 六维 FactPack 接入层（2026-11-10）

- 新增 `backend/services/institution/doc_layer.py`：
  - 固定五个 `field_key`：前五大客户、量价拆分、成本结构、合同负债、渠道数据；
  - 依次探测 `svquant.doc_extract` / `doc_extract` / `public.doc_extract`，缺表、缺关键列或读取异常时返回空覆盖，不阻断研究；
  - 按 `available_time::date <= as_of` 做 PIT，按字段取最新三条；
  - `approved/verified/reviewed` 视为已复核；`pending` 只作线索；
  - 每条结果保留 `page_no / quote / doc_id / pdf_sha256 / available_time`。
- 研究生成接入：
  - `facts` 新增 `document_extracts`、`document_coverage`、`document_extract_available/note`；
  - `_data_completeness` 把已复核字段从 `missing` 移入 `have`，待复核字段标注“抽取结果待复核”；
  - 合同负债已复核时，财务缺口改为“受限资金/租赁负债（B 组补）”；
  - Agent payload：商业模式维度注入五个字段，财务维度注入成本结构与合同负债；提示词要求引用带 `doc_id/page_no/quote/available_time`。
- 新增 `docs/数据需求/机构端-doc-extract接入契约.md`，固定 18 列表结构、复核状态机、PIT、责任边界与数据业务当前覆盖/排期。
- 数据业务 2026-11-10 确认：已有 CSI300 2025 年报 291 份；五个字段抽取器未建；批 1 近 5 年目录 + 2025 年报全文，批 2 2019–2024 全文 + 公告类；在研 20–50 只优先预取。
- 文档目录实际字段为 `announce_time / platform_available_time`；联调发现回采文档的 `platform_available_time` 是入库时间（2026-11-10），不能当 PIT；回采文档统一用 `announce_time + 1 个自然日` 作保守代理，有真实历史首次可得时间时优先用它。
- 五个字段由机构端按页文本自抽并产出回写 SQL，初始 `pending`，抽检 20–30 条后改 `approved`；平台不排抽取器。
- 新增 `scripts/ops/extract_inst_doc_fields.py`：按客户/量价/成本/合同负债/渠道五类模板抽 2025 年报，产出 CSV + `INSERT` SQL + 缺口报告；7 份年报抽出 24 条、明确缺口 11 条，全部 `pending`。
- 数据业务 2026-11-10 已将 24 行写入生产 `svquant.doc_extract`；机构端抽检后回写 20 条 `verified`（客户/量价/合同负债/渠道），4 条成本结构保持 `pending`。回读接入层：600519/001219 四类字段已转为 `have`。
- 首版结果：600519 客户 10.10%、销量 85,104.14 吨、合同负债 80.07 亿元；001219 客户 23.74%、合同负债 0.386 亿元；000625 客户 10.28%、销量 291.30 万辆、合同负债 69.09 亿元；000002 销售面积 1,025 万㎡、合同负债 930.57 亿元；000001 合同负债 24.24 百亿元。成本结构保留原文表，渠道按行业差异标注缺失/不适用。
- 回写 SQL 已在 `svquant_test` 临时 `svquant.doc_extract` 表执行通过：24 行、7 只标的、5 个字段、全部 pending；导入后 `load_doc_extracts` 验证 PIT：600519 在 2026-04-01 看不到 2025 年报，2026-04-19 起可见。
- 新增迁移 `backend/migrations/0036_inst_doc_extract.sql`：建 `svquant.doc_extract`（18 列，`PRIMARY KEY(doc_id, field_key)`、`available_time NOT NULL`）、两个索引，并给 `svquant_data_loader` 授予 `INSERT, SELECT`；测试库已应用并验证 24 行可插入。

验证：后端 `pytest tests/test_inst_*.py` 117 passed、8 subtests；新增 `test_inst_doc_layer.py` 5 passed（PIT、复核状态、缺表降级、维度裁剪、完整度联动）。


### 11.49 流水线阶段展示与研究案删除（2026-11-10）

- 修复机会发现卡片把 `idea` 字典直接转成字符串的问题：`_opportunity_source` 识别字典并只取 `why_now`；流水线卡片统一显示“当前阶段：…”，不再出现 `{'source': 'push', ...}` 原始 JSON。
- 新增 `DELETE /api/inst/cases/{case_id}` 归档研究案：
  - 仅 `manager` 且 research 工作区有写权限；
  - 执行/投后（stage≥4）、有持仓、有效授权、在途议案时拒绝，需先走退出/撤回；
  - 归档为 `stage='closed'`、`stage_state='closed'`、`terminal_reason='deleted_by_user'`，公司池置 `dropped`，写 `research.case.delete` 审计；
  - 不做物理删除，历史版本/证据/审计保留；
  - `_existing_case_id` 只匹配未关闭案，删除后可重新立案；`create_case` 同步把公司池置 `research`。
- UI：流水线 stage 1–3 卡片新增“删除研究案”，结果页 header 同步提供删除入口；删除成功刷新流水线或返回流水线。
- 生产已直接授权执行 `0036_inst_doc_extract`（建表/索引）与 `0037_inst_doc_extract_privileges`（收紧为仅 INSERT/SELECT）；迁移状态 `current=0037`、`pending=[]`。

验证：后端 `pytest tests` **888 passed、67 subtests**（新增删除归档/执行阶段拦截、机会来源字典清洗）；前端 `tsc`/`build`/`test:inst` 15 passed；Playwright 新用例 1 passed（卡片显示“当前阶段”、无原始 JSON、删除入口存在）。


### 11.50 股票总览（2026-11-10）

- 左侧“投资工作空间”新增“股票总览”，路由 `/inst/stocks`，所有拥有 `overview` 权限的角色可见。
- 新增只读接口：
  - `GET /api/inst/stocks?q=&limit=200`：机构公司池列表，`overview` 权限即可读；
  - `GET /api/inst/stocks/{company_id}/bars?period=day|week|month&limit=`：复用日线/周线/月线聚合，分钟线未接入时明确返回不可用。
- 前端页面：
  - 左侧股票列表（研究中/自选/已移出优先），支持服务端按代码/名称/行业搜索，展示当前条数与全量总数；
  - 右侧 K 线（A 股红涨绿跌、成交量副图、日/周/月切换），价格与涨跌幅、高低/成交量摘要；
  - 相关资讯按 `symbol` 调 `/api/news`，展示标题、来源、时间与摘要，原文新窗口打开。
- 修复拆分遗留：`company_service.list_companies` 延迟导入 `_idea_questions`，避免 `/companies`、`/stocks` 因未定义名称 500。
- 新增 `InstV3KlineChart`（`lightweight-charts`），数据只走机构端 `stocks/{id}/bars`，不绕过租户隔离。

验证：后端 `pytest tests` **888 passed、67 subtests**；前端 `tsc`/`build`/`test:inst` 15 passed；Playwright 股票总览用例 1 passed（列表、价格、K 线 canvas、资讯区）。


### 11.51 只分析已有数据、治理字段接入与估值空态（2026-11-10）

- 六维分析改为“只分析已有数据”：
  - `data_completeness.level=missing` 的维度不再调用 Agent，状态为 `skipped`，summary 固定“数据未接入，暂不分析”，不评分，gate=fail；行业分析同样处理；
  - `level=partial` 时必须基于已提供字段给出结论，不得因缺口拒绝分析；缺失项只进 data_gaps；
  - Prompt 与 Agent payload 增加 `available_data_only` 规则；研究页数据缺口只展示前 3 项，完整列表放 title。
- 治理字段接入 `doc_layer`：新增 `controller_profile / board_structure / pledge_freeze / related_party / guarantee / litigation_penalty / commitment_history / dividend_financing / mgmt_change`；核心 6 项全部 verified 后治理维度从 fail 解锁为 sufficient，否则按核心覆盖数保持 fail/watch。
- 估值空态修复：`_build_research` 无法估值时返回 `method=unavailable + reason`，不再返回 `null`；辩论页“估值复核”展示不可用原因，并给出“去价值分析重跑估值”入口。常见原因：自由现金流/净利为负、缺少总股本或行情价格。
- 数据业务已确认批 1 范围：7 只在研标的治理 6 项 + 财务附注 + 000001 银行专项；行业研究型数据不采购、缺失维度保持“待补数据”。
- 一页纸指标改为确定性覆盖：价值区间取研究版本估值，有效维按“有评分且 gate≠fail”计数，低置信维单列；不再采用 AI 文案里的“不可用 / 0/6”。

验证：后端 `test_inst_six_agents` 10 passed、`test_inst_doc_layer` 6 passed、`test_inst_v3_flow` 16 passed；前端 `tsc` 通过；评分块改为紧凑横排并移除基准小字。


### 11.52 估值重跑与 PR（2026-11-10）

- 重跑 3 只旧版本无估值的在研案：
  - 000002 万科A：重开研究 → 跑估值维；结果 `unavailable`，原因“自由现金流为负（-0.16 亿元）”，不再空白；
  - 000625 长安汽车：同上，原因“自由现金流为负（-135.07 亿元）”；
  - 000006 深振业A：直接重跑，估值区间 2.69–4.48 元，基准 3.59 元。
- 000002/000625 重开研究后阶段回到 1（returned），需重新锁定研究定稿；无在途议案/授权被误伤。
- 一页纸指标改为确定性覆盖：有效维按“有评分且 gate≠fail”计数，价值区间取研究估值；001233 类场景由 0/6 修正为 5/6（治理 fail 剔除），价值区间显示 43.43–72.38 元。
- PR：https://gitee.com/yanggu-yuanqi-intelligence/SVQuant/pulls/200 （dev-lsb → master，含 0036/0037 生产已应用说明）。
