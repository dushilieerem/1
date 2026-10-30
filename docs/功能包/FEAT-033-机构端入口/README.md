# FEAT-033 机构端登录入口与机构壳

| 项 | 内容 |
|---|---|
| 状态 | 已交付（第一刀：入口 + 登录 + 机构壳 + 驾驶舱） |
| 日期 | 2026-10-30 |
| 前置 | [主观机构端需求评估](../../产品与需求/主观机构端需求评估.md) |
| 分支 | `feat/inst-entry` |

## 1. 目标与范围

在 SVQuant 登录页新增机构端入口，并让机构角色进入独立的机构工作区。本轮只做"能登录、能分权、能看到骨架"，不实现研究/审批/执行业务。

**做**：

- 登录页「个人版 / 机构版」切换；机构版走独立接口签发机构令牌。
- 机构、成员、六角色落库；角色 × 九工作区权限由服务端计算。
- 机构壳：侧边栏九个工作区按权限显隐、只读/仅摘要标识、无权限门禁。
- 投资驾驶舱静态页（演示数据、演示标识）。
- 其余八个工作区为占位页，明确"下一阶段开放"，无死链。

**不做**：研究、辩论、议案、审批、风控、执行、投后业务；真实身份（SSO）；双语；真实数据。

## 2. 关键决策

| 决策 | 选择 | 原因 |
|---|---|---|
| 入口形态 | 登录卡片顶部 Tab | 同页切换，改动最小，后续可替换为 SSO |
| 账号模型 | 复用 `users` + `inst_orgs` / `inst_members` | 不破坏 `users.role` 的 `user/admin` CHECK；身份统一、会话分离 |
| 会话 | 机构登录签发 `scope=inst` 令牌 | 个人版令牌不能访问 `/api/inst/*`，机构令牌也不能替代个人版 |
| 权限 | 服务端矩阵 | 前端菜单显隐只是展示，不是安全边界 |
| 品牌 | 界面「旸谷资本」，产品名「SVQuant 机构端 · 主观价值投资」 | 与原型一致，保留 SVQuant 归属 |

## 3. 实现

### 3.1 后端

| 文件 | 内容 |
|---|---|
| `backend/services/institution/inst_store.py` | 机构/成员表、演示种子、六角色 × 九工作区矩阵、机构令牌签发与解析 |
| `backend/app/routers/inst.py` | `POST /api/inst/auth/login`、`GET /api/inst/me`；登录限流与审计 |
| `backend/app/deps.py` | `require_inst_user`：校验 `scope=inst` 与成员状态 |
| `backend/services/auth/auth_store.py` | 抽出 `authenticate_user`；`issue_token` 支持附加 claims |
| `backend/app/main.py` | 注册路由；机构登录由路由写审计，避免中间件重复 |
| `backend/app/bootstrap.py` | 启动时建表并幂等写入演示机构/账号 |

角色以数据库为准：令牌中的 `inst_role` 只是签发快照，权限每次都按当前成员表计算，改角色立即生效、无需重新登录。

### 3.2 权限矩阵

与需求文档 §2.2 一致，代码在 `inst_store.ROLE_WORKSPACE_ACCESS`：

| 工作区 | 经理 | 合伙人 | Chairman | 风控 | 执行 | 监控 |
|---|---|---|---|---|---|---|
| 驾驶舱 | 读 | 读 | 读 | 读 | 读 | 读 |
| 机会发现 | 写 | 读 | — | — | — | — |
| 公司研究 | 写 | 读 | 摘要 | 读 | — | 摘要 |
| 辩论室 | 写 | 读 | 摘要 | 读 | — | — |
| 组合 | 读 | 写 | 读 | 写 | 读 | 写 |
| 审批 | 写 | 写 | 写 | 写 | 读 | 摘要 |
| 执行 | 读 | 读 | 摘要 | 写 | 写 | 读 |
| 投后 | 写 | 写 | 读 | 写 | 读 | 写 |
| 关于我们 | 读 | 读 | 读 | 读 | 读 | 读 |

### 3.3 前端

| 文件 | 内容 |
|---|---|
| `frontend/src/lib/instAuth.ts` | 机构会话（独立 storage key）、登录、`/api/inst/me` |
| `frontend/src/data/instNav.ts` | 菜单排序/过滤、访问标识、路径匹配、占位内容 |
| `frontend/src/components/institution/InstLayout.tsx` | 机构壳：侧边栏、顶栏、权限门禁、会话校验 |
| `frontend/src/pages/institution/InstOverviewPage.tsx` | 投资驾驶舱（演示指标与待办） |
| `frontend/src/pages/institution/InstPlaceholderPage.tsx` | 八个占位工作区 |
| `frontend/src/pages/LoginPage.tsx` | 个人版/机构版 Tab、机构登录、开发环境演示账号 |
| `frontend/src/App.tsx` | `/inst/*` 独立路由树（不套个人版 Layout） |

## 4. 演示账号

启动时写入，密码由 `INST_DEMO_PASSWORD` 控制（默认 `inst123456`）：

| 用户名 | 角色 |
|---|---|
| `inst_manager` | 投资经理 |
| `inst_partner` | 合伙人 |
| `inst_chairman` | Chairman |
| `inst_risk` | 独立风控 |
| `inst_execution` | 交易执行 |
| `inst_monitoring` | 组合监控 |

登录页在开发环境（`import.meta.env.DEV`）展示快捷填充按钮；生产构建不显示。生产/试点必须设 `INST_SEED_DEMO=0`。

## 5. 验收

| 项 | 结果 |
|---|---|
| 登录页可切换个人版/机构版 | 代码完成；未跑浏览器 |
| 六角色登录进入各自可见菜单 | 权限矩阵单测覆盖；UI 未跑浏览器 |
| 直接访问无权限工作区被拒绝 | 服务端矩阵 + 前端门禁；未跑浏览器 |
| 个人版令牌不能访问 `/api/inst/me` | 单测覆盖（`test_personal_token_is_rejected_by_inst_session`） |
| 机构会话失效自动回登录 | 代码完成；未跑浏览器 |
| 驾驶舱为演示数据且带标识 | 代码完成 |

## 6. 测试

- `backend/tests/test_inst_auth.py`：8 条，覆盖六角色矩阵、未知角色 fail-closed、令牌 claims、个人版令牌拒绝。已通过。
- `frontend/tests/instNav.test.ts`：5 条，覆盖菜单过滤/排序去重、访问标识、最长前缀匹配。已通过。
- `frontend` `tsc --noEmit`：通过。

**未跑**：真实 PostgreSQL 建表与种子、后端启动、浏览器端登录与路由。原因：本机无 `backend/.env`（Vite 与后端均要求 `YG_RE_BASE`）、5432 未监听、`svquant` conda 环境缺依赖（用 base 环境验证）。

## 7. 下一阶段

1. 真实环境联调：建表、种子、登录、角色菜单、越权门禁。
2. 机构会话的登出/过期与个人版会话互不影响（当前 logout 只清机构 key）。
3. 研究页（六维、资料包、版本）第一刀。
4. SSO / 多机构 / 成员管理后台。

## 8. 风险与后续

- 演示账号默认密码是已知风险：生产关闭种子或强制改密。
- 权限矩阵目前硬编码在 Python：后续应改为可配置策略并版本化（审批/授权需要政策版本）。
- 本轮未做审计查询页，机构登录审计已写入 `app_audit_logs`（`action=inst.login`）。
