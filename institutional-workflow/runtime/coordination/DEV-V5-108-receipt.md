# DEV-V5-108 回执

日期：2026-11-11
分支：`dev-zxd`
HEAD：`b96e36e` → `98b26ef`（代码 + 规格；本回执随后单独 docs 提交）
BFF `18799`：旧 PID **1761723**（2026-11-10 18:37:05）→ 新 PID **1884973**（2026-11-11 14:16:55）
前端 `19536` PID 3553141 未重启；私有 RE `18804`、共享 `9527`/`18803` 未动。

## 一、改了哪些文件、为什么

本批把 107 选择 (b) 时挂起的 UX106 正式交付，恢复并提交了前端 WIP，补齐后端 reports 与规格：

**后端（5）**
- `backend/app/routers/quant_factor_workflow.py`：新增 `GET /imports/{id}/reports` 与 `GET /assets/{id}/reports/{phase}` 两个只读路由（本次 diff 仅这 13 行；autonomy 路由是上一批已提交的 `ce186f7`）。
- `backend/services/quant_factor/library_reports.py`：因子库历史摘要/本人已保存报告索引；只投影白名单字段，不返回 `result` 正文，不做缓存读取或重算。
- `backend/services/quant_factor/asset_reports.py`：同机构已批准资产的研发/封存报告只读投影；校验注册快照、研发/查重/封存指纹与报告身份。
- `backend/services/quant_factor/assets.py`：增加 `full_report` 转调包装。
- `backend/tests/test_quant_factor_library_reports.py`：11 项隔离测试（库、资产、路由）。

**前端（11）**
- `frontend/src/pages/institutional-workflow/FactorLibraryDetailDrawer.tsx`：第三页签「验证记录」→「回测报告」，引用 `FactorLibraryReports`。
- `frontend/src/pages/institutional-workflow/FactorLibraryReports.tsx`（新）：平台历史回测摘要、完整报告列表、分页、服务错误重试、迟到响应保护。
- `frontend/src/lib/factorLibraryReports.ts`（新）：只读报告读取与身份/URL 校验。
- `frontend/src/pages/institutional-workflow/FactorResearchAssetDetails.tsx`：增加「查看研发报告」「查看独立验证报告」入口。
- `frontend/src/pages/institutional-workflow/QuantFactorReportPage.tsx`：支持 `/quant/factor/assets/:assetId/report/:phase` 只读资产报告模式；缺失日期显示「未记录」而不是推算。
- `frontend/src/App.tsx`：增加资产报告路由。
- `frontend/src/lib/researchClient.ts`：报告读取仅允许 GET，路径白名单。
- `frontend/src/pages/institutional-workflow/quantWorkspace.css`：UX106 样式。
- `frontend/tests/factorLibrarySource.test.tsx`：页签与空态断言更新。
- `frontend/tests/factorAssetReport.test.tsx`（新）：资产双报告、完整性拒绝、阶段切换迟到响应。
- `frontend/tests/factorLibraryReports.test.tsx`（新）：历史摘要/单位/0/null、服务错误重试、分页、迟到响应、身份拒绝。

**规格（1）**
- `docs/模块设计/量化机构端/因子工厂V5-因子回测报告.md`：PM 的 UX106 规格，本批一并提交。

**运行/证据（未提交，ignored）**
- `institutional-workflow/runtime/verification/dev-v5-108/*.png`：真实浏览器截图。
- `institutional-workflow/runtime/quant-bff-process.json`：更新为新 PID/18804 RE，供后续重载使用。
- 未改、未提交 `frontend/public/quant-delivery/v5/factor-factory.{html,css,js}`（PM 原型基线）与 `backend/factor/.custom_lib.lock`。

## 二、6 项验收逐项

| # | 验收项 | 结论 | 证据 |
|---|---|---|---|
| 1 | 331 条因子的指标组合与真实平台记录一致；检查三类因子、不同参数、0/null 和异常值口径 | **通过（真实数据 + 真实页面）** | 真实只读查询：`factor_dashboard_metrics` 3972 行 = 331 因子 × 12 组合；org 261 导入 331 条 / 12 类。真实 API：`/imports/8142a8e5…/reports` 鉴权后 **200**，12 条历史摘要、0 份已保存报告。页面 SV01_0001 默认「沪深300 · 近3年 · 过滤涨停」，显示 Rank IC 0.0010、Pearson IC 0.0085、ICIR 0.049、年化 4.34%、最大回撤 -24.19%、夏普 0.340；历史记录明确说明未保存净值/基准曲线，报告区 0 个 svg/canvas。SV13_0049 的 4 个 null rank_ic 在服务层保留为 null。截图 `03-report-empty-1366.png`。 |
| 2 | 已保存报告的详情入口、曲线/基准、返回导航真实可用；不读其他用户或机构的私有正文 | **通过（真实页面；无可读私有正文）** | SV06_0010 页面列出 **9 份**已保存报告，首条实际区间 2022-01-05 — 2024-12-31；点击「查看报告」进入 `/quant/factor/report/qf_0015b292…`，报告页有 3 个真实 svg 图表与研发门槛/指标；点击「实验记录」返回项目报告页（显示「1 份已保存报告」），再点「因子库」回到因子库。列表接口不返回 `result` 正文；跨机构 org=999 → 404。截图 `04-report-saved-1366.png`、`05-report-detail-1366.png`、`10-report-back-1366.png`。 |
| 3 | 已批准资产双报告的完整性/阶段/跨机构/未批准拒绝，用隔离固定证据测试；当前没有真实合格入库资产时不得伪称真实入库验收完成 | **通过（隔离单测）；真实入库未发生** | `pytest tests/test_quant_factor_library_reports.py` → 11 passed（研发/封存阶段、注册快照/研发/查重/封存指纹、跨机构、未批准拒绝、私有字段剔除）。DB 中 `archive->>'approved'='true'` = **0**，不声称真实入库验收完成；资产报告真实页面未做（无真实资产）。 |
| 4 | API 401/404、摘要缺失/服务错误、乱序响应与重复切换；原源码/复制/分类搜索不回归 | **通过（真实 API + 真实页面 + 隔离单测）** | 真实 API：未登录 `/reports` **401**，登录后 **200**。页面真实 404（请求不存在的 imported_id）显示「因子不存在或无权访问」+「重试读取报告」，截图 `02c-report-service-error-real404-1366.png`；注入 503 显示「报告服务暂时不可用」+ 重试并恢复，截图 `02b-report-service-error-503-1366.png`。迟到响应：延迟 SV01_0001 响应 2.5s 后切到 SV08_0060，最终抽屉为「Alpha#040 高价波动×量价相关」、SV01 抽屉 0 个、已保存报告 1 条、空态 0 次，截图 `06-late-response-1366.png`。隔离单测：后端 31 passed / 17 subtests；前端 UX106 16/16；回退前 factor 回归 50/50。 |
| 5 | 1366/1024/760 实页检查、页签键盘与滚动；不出现整页横溢出 | **通过（真实浏览器）** | 1366×768：`scrollWidth=1366`，无横溢出；1024×768：`scrollWidth=1024`，无横溢出，抽屉 `scrollWidth<=clientWidth`；760×900：`scrollWidth=760`，无横溢出，抽屉无横溢出。键盘：聚焦「回测报告」按 Enter，`aria-selected=true` 且面板可见。截图 `03`、`07-report-empty-1024.png`、`08-report-empty-760.png`、`09-keyboard-tab-1366.png`。 |
| 6 | 先适当专项测试和串行构建，再核零在途后只加载自有 BFF；不启动研究或新回测，不动共享服务，不应用 CR102 迁移 | **通过** | 测试：后端 31 passed/17 subtests；前端 UX106 16/16；`npx tsc` exit 0；`npm run build` exit 0。五类在途全 0（见第三节）后只重载 18799。浏览器请求审计：唯一 POST 是登录，无回测/计算/研究 POST；报告页仅 GET 已保存 run。未应用 CR102 迁移；autonomy `available=false/enabled=false`（见第四节）；未动 9527/18803/19536/18804。 |

## 三、重载前后 PID、health、五类在途

**重载前后**

| 项 | 前 | 后 |
|---|---|---|
| PID | 1761723 | 1884973 |
| 启动时间 | 2026-11-10 18:37:05 | 2026-11-11 14:16:55 |
| `ok` / `db` | true / ok | true / ok |
| schema | 0041_quant_model_capacity | 0041_quant_model_capacity |
| pending | [] | [] |
| queue.done | 845 | 845 |

重载方式：读取旧进程的 `QUANT_*` 环境（`QUANT_FACTOR_RE_BASE=http://127.0.0.1:18804`、`QUANT_NOVELTY_RE_BASE=http://127.0.0.1:18804`、`QUANT_RESEARCH_DURABLE_QUEUE=1`，token 不落盘），SIGTERM 旧 PID 后用同一 `start_quant_bff.py` 启动；未动 18804/19536/9527/18803。

**五类在途（只读查询 `svquant_dev`）**

| 类别 | 状态分布 | 在途 |
|---|---|---|
| F0 | completed 2、failed 2、stopped 43 | 0 |
| 候选 | development_error 3、development_failed 44、development_passed 7、validation_failed 2、validation_passed 1 | 0 |
| 封存 | failed 3、passed 3 | 0 |
| Agent jobs | failed 22、ready 61（ready 全部有 output） | 0 |
| 迭代 | failed 4、limit_reached 3、paused 1、review_pending 1 | 0 |
| 队列（附） | completed：agent 3、development 2、f0 2 | 0 |

重载后复核：`f0_active=0, cand_other=0, sealed_other=0, jobs_other=0, iter_other=0, queue_other=0`。

## 四、加载后复验

- `GET /api/inst/quant/factor-workflow/imports/8142a8e5-7b86-41b4-b8b1-66807fe19dfd/reports`：未登录 **401**；登录后 **200**，`history_summaries=12`、`saved_reports=0`、`private_reports_allowed=true`。
- `SV06_0010`：200，`saved_reports=9`。
- 页面三态：有报告（SV06_0010）、明确空态（SV01_0001）、明确服务错误（真实 404 中文提示 / 注入 503 重试）均正常；无白屏、无 404 裸错、无伪造曲线。
- **autonomy 状态（重要）**：重载后已在 HEAD `ce186f7` 的 autonomy 路由随进程注册，`/autonomy` 未登录从此前 404 变为 **401**（已加载）；登录后 200，但 `available=false`、`enabled=false`、`state=not_enabled`，7 张 CR102 表全部不存在，`QUANT_AUTONOMOUS_RESEARCH_ENABLED` 未设置。**未应用迁移、未启用、未启动任何研究**。

## 五、浏览器截图清单与视口

目录：`institutional-workflow/runtime/verification/dev-v5-108/`

| 文件 | 视口 | 内容 |
|---|---|---|
| `01-library-1366.png` | 1366×768 | 因子库加载完成，331 条、12 类 |
| `00-preload-404-halfstate-1366.png` | 1366×768 | 重载前半状态（真实 404，`Not Found`），仅作 107 半状态留证 |
| `02c-report-service-error-real404-1366.png` | 1366×768 | 交付后真实 404 中文服务错误 + 重试 |
| `02b-report-service-error-503-1366.png` | 1366×768 | 注入 503 的明确服务错误 + 重试恢复 |
| `03-report-empty-1366.png` | 1366×768 | SV01_0001 平台历史摘要 + 明确空态，无曲线 |
| `04-report-saved-1366.png` | 1366×768 | SV06_0010 的 9 份完整报告列表 |
| `05-report-detail-1366.png` | 1366×768 | 已保存完整报告页（真实图表/门槛/指标） |
| `06-late-response-1366.png` | 1366×768 | 迟到响应后仍为 SV08_0060，不覆盖当前因子 |
| `07-report-empty-1024.png` | 1024×768 | 1024 宽度，无横溢出 |
| `08-report-empty-760.png` | 760×900 | 760 宽度，无横溢出 |
| `09-keyboard-tab-1366.png` | 1366×768 | 键盘 Enter 激活「回测报告」页签 |
| `10-report-back-1366.png` | 1366×768 | 报告页「实验记录」返回项目报告页 |

浏览器：Playwright-core 1.64.1 + 缓存 Chromium headless shell 1248（真实浏览器，headless）；登录账号 `test`（user 2527，org 261，quant write）。

## 六、遗留问题与需 PM 决策

1. **autonomy 路由已随 BFF 重载注册**（HEAD `ce186f7` 已提交），`/autonomy` 从 404 变 401；功能仍 `available=false/enabled=false`，迁移未应用、flag 未设置。若 PM 要求运行进程也不得注册该路由，需要后续单独处理；本批未改 CR102 代码或迁移。
2. **stash 保留**：`85e9fda` 未删除（工作单要求保留至验收通过）。PM 验收后可 `git stash drop`。
3. **原型未提交**：`frontend/public/quant-delivery/v5/factor-factory.{html,css,js}` 仍是工作树修改（PM 的 UX106 原型基线），本批未改、未提交。
4. **锁文件未动**：`backend/factor/.custom_lib.lock` 仍为未跟踪，未提交。
5. **真实资产报告未验**：DB 中已批准资产 = 0，第 3 项仅隔离测试通过，未声称真实入库验收完成。
6. **运行记录**：`quant-bff-process.json` 已更新为新 PID 1884973 / RE 18804（ignored，不提交）；此前记录的 PID 是过期的。
7. **截图未入 Git**：位于 ignored 的 `institutional-workflow/runtime/verification/dev-v5-108/`，按工作单「只提交前端 UX106 全套 + 后端 reports 全部 + 规格文档」未提交；如需随代码入库请 PM 明确。
