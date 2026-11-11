# DEV-V5-107 回执

日期：2026-11-11
分支：`dev-zxd`
HEAD：`bdef138` → `ce186f7`（代码提交：`ae527f3` P0-2、`ce186f7` P1-2；本回执随后单独 docs 提交）
运行基线：BFF `18799` PID 1761723（2026-11-10 18:37:05 启动，未重载）；前端 `19536` PID 3553141；私有 RE `18804`；共享 `9527`/`18803` 未动。

## P0-1

**选择：(b) 暂不交付 UX106。**

为什么：

1. 保守选项：不重载共享开发 BFF `18799`，不把未验收的 UX106 暴露给页面。
2. P1-2 明确要求 CR-102「未加载、未启用」；当前工作树的 router 同时含 UX106 reports 路由和 CR-102 autonomy 路由，若重载同一进程会把 autonomy 路由一并注册，与 P1-2 冲突。拆分后重载需要改 WIP，风险更大。
3. 本批没有真实浏览器登录会话，无法完成规格第 6 节第 5 条的 1366/1024/760 实页验收；只有替身单测不能写「已完成」。
4. 因此按 (b) 把前端回退到不引用未加载接口的状态（旧「验证记录」），WIP 完整保存。

改了哪些文件：

- 前端回退到 HEAD，改动保存在 `git stash`（`85e9fda`，含 7 个 tracked + 4 个 untracked）：
  - `frontend/src/App.tsx`
  - `frontend/src/lib/researchClient.ts`
  - `frontend/src/lib/factorLibraryReports.ts`（untracked）
  - `frontend/src/pages/institutional-workflow/FactorLibraryDetailDrawer.tsx`
  - `frontend/src/pages/institutional-workflow/FactorResearchAssetDetails.tsx`
  - `frontend/src/pages/institutional-workflow/QuantFactorReportPage.tsx`
  - `frontend/src/pages/institutional-workflow/quantWorkspace.css`
  - `frontend/src/pages/institutional-workflow/FactorLibraryReports.tsx`（untracked）
  - `frontend/tests/factorLibrarySource.test.tsx`
  - `frontend/tests/factorAssetReport.test.tsx`（untracked）
  - `frontend/tests/factorLibraryReports.test.tsx`（untracked）
- 后端 UX106 未进入本批提交（仍在工作树）：
  - `backend/services/quant_factor/asset_reports.py`（untracked）
  - `backend/services/quant_factor/library_reports.py`（untracked）
  - `backend/tests/test_quant_factor_library_reports.py`（untracked）
  - `backend/services/quant_factor/assets.py`（`full_report` 包装，未提交）
  - `backend/app/routers/quant_factor_workflow.py` 的 reports 两路由 hunk（未提交）
- 工作单点名的 4 个文件（`asset_reports.py` / `library_reports.py` / `FactorLibraryReports.tsx` / `factorLibraryReports.ts`）均不在本次提交中。
- `frontend/public/quant-delivery/v5/factor-factory.{html,css,js}` 是既有 UX106 原型改动，未由开发修改或提交。

证据：

- 运行中 BFF（未重载）：
  - `GET /api/inst/quant/factor-workflow/imports/8142a8e5-7b86-41b4-b8b1-66807fe19dfd/reports` → **404** `{"detail":"Not Found"}`
  - `GET …/source` → **401**（UX105 路由存在，需登录）
  - `GET …/autonomy` → **404**（CR-102 未加载）
  - 404 是路由未注册，不是鉴权问题。
- 前端 19536（Vite dev，未重启）：`/quant` → **200**；`curl /src/pages/institutional-workflow/FactorLibraryDetailDrawer.tsx` 的转译结果只含「验证记录」3 处，**无**「回测报告」、**无** `FactorLibraryReports`。
- 前端静态检查：`frontend/src`、`frontend/tests` 中 `factorLibraryReports` / `FactorLibraryReports` / `imports/*/reports` / `assets/*/reports` **0 处**；`App.tsx` 的 asset report 路由已移除。
- 测试/构建：factor 前端回归 **50/50 通过**；`npx tsc` **exit 0**；`npm run build` **exit 0**（1.85s，仅有既有 chunk size 警告）。
- **未做真实浏览器操作**（无登录会话）。

P0-1 四条验收：

1. `/reports` 返回 200/401：**未满足（仍 404）**。这是 (b) 的必然结果；前端不再引用，用户不可见。若 PM 要求线上非 404，必须改选 (a) 并安排零在途重载。
2. 页面三态：**源码层面回退为旧「验证记录」；无白屏、无 404 裸错、无伪造曲线。未做真实浏览器复核。**
3. 迟到响应不覆盖：**不适用**（回测报告未交付）；旧源码/复制页的迟到响应保护由 50 项 factor 测试覆盖。
4. 不触发回测/重导入/改审批：**通过（未触发）**。

## P0-2

改了哪些行：

- `frontend/src/pages/institutional-workflow/QuantFactorHomePage.tsx:337`、`:362`
- `frontend/src/pages/institutional-workflow/FactorWorkflowPage.tsx:37`（工作单只点名前两处；第三处同样是因子模块的同一文案，为满足「因子模块 grep=0」一并改）
- `'人工建立课题'` → `'人工建立分支'`，共 **3 处**。
- 选「人工建立分支」：与同一行的「人工接手」/「研究系统修订」并列自然；6 个汉字与原文等长，不改变该行宽度。

grep 结果：

- 因子模块前端源码（`QuantFactor*.tsx`、`Factor*.tsx`、`lib/factor*`）：`课题` = **0**。
- 原型 `factor-factory.html/js/css`：`课题` = **0**。
- `StrategyResearchPage.tsx` 未改（本批不动；仍有 23 处）；本批提交中该文件 diff = 0。
- 其他 v5 原型/设计文档仍有「课题」，但不在本次因子工厂原型范围。
- 1366/1024 实页：**未做浏览器检查**；字符数相同，理论上该行不换行错位。

## P1-1

| # | 验收项 | 结论 | 证据 |
|---|---|---|---|
| 1 | 331 条因子的指标组合与真实平台记录一致；检查三类因子、不同参数、0/null 和异常值口径 | **部分通过（真实数据 + 服务层；线上未加载）** | 真实只读查询 `svquant_dev`：`factor_dashboard_metrics` 3972 行、331 个因子、每因子 12 个组合（min=max=12）、2 股票池 × 3 区间 × 2 涨停过滤 × 1 停牌过滤；`error` 0 行；`rank_ic` null 232 行、0 值 0 行。org 261 导入因子 331 条、12 类，分类计数与规格一致（量价 88 / 波动 53 / 技术复合 50 / 动量 34 / 日内 31 / 反转 28 / 资金流 18 / 流动性 13 / 区间 8 / Beta 4 / 风险分布 3 / 估值 1）。真实服务函数只读调用 `imported_reports(2527,261,id,True)`：SV01_0001（动量）/SV06_0010（流动性）/SV08_0060（量价）/SV13_0049（技术复合）均返回 12 条历史摘要；SV13_0049 的 4 个 null rank_ic 保留为 null；单位映射 correlation/ratio/number 正确；跨机构 org=999 → 404。端点未加载，页面未验收。 |
| 2 | 已保存报告的详情入口、曲线/基准、返回导航真实可用；不读其他用户或机构的私有正文 | **未做（UX106 未交付）** | 服务层真实数据：用户 2527 有 11 份可对应报告（SV06_0010 9、SV08_0060 1、SV13_0049 1），列表返回 `report_url`、实际起止、版本指纹，且不返回 `result` 正文；跨机构 404。详情入口/曲线/导航未在真实页面验收。 |
| 3 | 已批准资产双报告的完整性/阶段/跨机构/未批准拒绝，用隔离固定证据测试；当前没有真实合格入库资产时不得伪称真实入库验收完成 | **通过（隔离固定证据单测）** | `pytest tests/test_quant_factor_library_reports.py` → 11 passed；覆盖研发/封存阶段、快照/研发/查重/封存指纹、跨机构、未批准拒绝、项目私有字段剔除。DB 中 `archive->>'approved'='true'` = **0**，因此**不声称真实入库验收完成**。 |
| 4 | API 401/404、摘要缺失/服务错误、乱序响应与重复切换；原源码/复制/分类搜索不回归 | **部分通过（隔离单测；线上 API 未加载）** | 后端：`pytest tests/test_quant_factor_library_reports.py tests/test_quant_autonomy_api.py tests/test_quant_autonomy_contract.py` → **31 passed, 17 subtests passed**；RouteTests 覆盖 401/403/404/409/503，摘要缺失/服务错误分开。前端：UX106 专项 16/16 通过（回退前、WIP 状态，现已 stash）；回退后 factor 回归 **50/50 通过**（源码/复制/筛选/导航）。运行中 BFF 未加载 reports，未在线上复核 401/404。 |
| 5 | 1366/1024/760 实页检查、页签键盘与滚动；不出现整页横溢出 | **未做** | 无真实浏览器会话；UX106 未交付。 |
| 6 | 先适当专项测试和串行构建，再核零在途后只加载自有 BFF；不启动研究或新回测，不动共享服务，不应用 CR102 迁移 | **未做加载（选择 b）** | 前置条件已核：五类在途均为 0；`npx tsc` exit 0、`npm run build` exit 0；未启动模型/RE/回测；未动 9527/18803/19536/18804；未应用 CR102 迁移。 |

## P1-2

5 个 WIP 文件完成度（均已在 `ce186f7` 提交；**未加载、未启用**）：

| 文件 | 完成度 | 说明 |
|---|---|---|
| `backend/services/quant_factor/autonomy.py` | **可用** | 授权开启/暂停/恢复、状态查询、幂等 request_key、advisory lock、事务回滚；隔离 PG 6/6 通过。**未接线**到 planner/family 执行适配器。 |
| `backend/services/quant_factor/autonomy_authorization.py` | **可用** | `prepare` / `original_receipt` / `control` / `may_plan`；权限、范围、CAS 冲突测试通过。 |
| `backend/services/quant_factor/autonomy_contract.py` | **可用** | family 身份、proposal 白名单、试验额度、K 计数、迟到应用校验；契约测试通过。 |
| `backend/services/quant_factor/research_experience.py` | **可用** | 仅 owner 私有研发证据、白名单 checks、指纹、`bounded_context`；契约测试通过。 |
| `backend/app/routers/quant_factor_workflow.py`（仅 autonomy 路由 hunk） | **可用** | GET `/autonomy`、POST `/autonomy/authorizations`、POST `/autonomy/authorizations/{id}/control`；API 测试 5 passed。同一文件的 reports 两路由 hunk **未提交**。 |

补充测试/脚本（同提交）：

- `backend/tests/test_quant_autonomy_api.py` → 5 passed, 4 subtests（用「HEAD + 仅 autonomy 路由」的临时文件跑过）。
- `backend/tests/test_quant_autonomy_contract.py` → 15 tests（包含在 31 passed 中）。
- `backend/scripts/run_quant_autonomy_pg_tests.py` → 6/6 OK；输出 `public_migration_applied=false`、`public_rows_and_constraints_unchanged=true`、`schema_cleaned=true`、`models_or_market_calls=0`。

哪些测试真跑过：

- `pytest -q tests/test_quant_autonomy_api.py` → 5 passed, 4 subtests。
- `pytest -q tests/test_quant_autonomy_contract.py`（在 31 passed 中）。
- `python backend/scripts/run_quant_autonomy_pg_tests.py --allow-owned-temporary-schema` → 6 tests OK。
- 只写了没跑：无（本批提交的测试都跑了）。明确非目标、未跑：真实自动立项、真实模型、真实 RE、CR102 迁移应用。

未加载/未启用证据：

- 运行中 BFF `GET /api/inst/quant/factor-workflow/autonomy` → **404**（未加载）。
- `svquant_dev` 中 7 张 CR102 表 `to_regclass` 全部为 NULL；`QUANT_AUTONOMOUS_RESEARCH_ENABLED` 未设置（默认 `0`）→ 未启用。
- `institutional-workflow/migrations/0048_quant_autonomous_research.sql` 存在但未被 git 跟踪（`institutional-workflow/` 整体 ignored）；本次未应用。

## 是否重载 BFF

**否。** `18799` 未重载；PID 1761723，启动时间 2026-11-10 18:37:05，前后一致。

五类在途（只读查询 `svquant_dev`）：

- F0：completed 2、failed 2、stopped 43；`queued/running` = 0。
- 候选：development_error 3、development_failed 44、development_passed 7、validation_failed 2、validation_passed 1；运行中 = 0。
- 封存：failed 3、passed 3；运行中 = 0。
- Agent jobs：failed 22、ready 61（ready 全部有 output）；`queued/running` = 0。
- 迭代：failed 4、limit_reached 3、paused 1、review_pending 1；running = 0。
- 附：`quant_research_queue_jobs` 全部 completed（agent 3、development 2、f0 2）；pending/running = 0。

Health 前后：

- 前：`ok=true`、`db=ok`、schema `0041_quant_model_capacity`、`pending=[]`、`queue.done=845`。
- 后：同上（未重载）。
- 前端 19536 PID 3553141 未变，`/quant` = 200；18804/9527/18803 未动。

## 未解决/需 PM 决策

1. **UX106 交付窗口**：下一批需在五类在途为 0 + 真实浏览器会话下验收 1366/1024/760，然后只重载 `18799`。恢复 WIP：`git stash apply 85e9fda`（会同时恢复 4 个 untracked 前端文件）；后端 UX106 文件仍在工作树。
2. **router 工作树半状态**：工作树 `quant_factor_workflow.py` 仍保留未提交的 reports 两路由（引用 untracked 的 `asset_reports.py`/`library_reports.py`）。当前运行进程未加载；若有人在此之前重载 `18799`，会意外暴露未验收的 UX106。PM 需安排 UX106 或明确要求开发移除该 hunk。
3. **原型/规格**：`factor-factory.{html,css,js}` 与 `docs/模块设计/量化机构端/因子工厂V5-因子回测报告.md` 仍是未提交 WIP；原型文件不是开发改的，本批未提交。
4. **P0-2 额外一处**：`FactorWorkflowPage.tsx:37` 的同一文案已改；工作单只点名 337/362，特此报告。
5. **策略「课题」**：`StrategyResearchPage.tsx` 仍有 23 处，按工作单本批不动，待 PM 统一。
6. **CR102 迁移**：0048 文件存在但未被跟踪；未应用。启用前需 PM 决定迁移入库/评审路径。
7. **P1-1 真实页面项**：第 2、5 项未做；第 1、4 项仅服务层/隔离单测；第 3 项隔离测试通过但真实入库资产为 0，不声称真实入库验收。
8. **BFF health 的 port 字段**显示 8766（环境元数据），实际监听 18799；这是既有现象，本批未改。
