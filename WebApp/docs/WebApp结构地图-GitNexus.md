# SVQuant WebApp · 结构地图（GitNexus + 代码核对）

> **用途：** 改 bug / 加功能时先看本页，再按「定位表」跳文件。  
> **范围：** `E:\quant-lab\SV\SVQuant\WebApp\`（frontend + backend + KnowledgeHub 挂载）。  
> **索引：** GitNexus 仓名 `SVQuant`（整仓含 ResearchEngine/QuantCore；本图只讲 WebApp 与同事接口）。  
> **刷新：** 在 `E:\quant-lab\SV\SVQuant` 执行 `npx gitnexus analyze`（大改后）。FTS 需网络装扩展时：`$env:GITNEXUS_LBUG_EXTENSION_INSTALL="auto"; npx gitnexus analyze --repair-fts`。  
> **看图（GitNexus Web UI）：** 见下文「§9 页面怎么打开」。  
> **可测步骤（检测回测）：** [`可测步骤-因子检测回测.md`](./可测步骤-因子检测回测.md)  
> **日期：** 2026-08-19

---

## 0. 一句话总览

```
浏览器 (:9530)
  ├─ /api/*     → Vite 代理 → 本机 SVQuant 薄后端 (:8766)  → SQLite/PG / factor源码 / 再 BFF 打 RE
  └─ /yg-api/*  → Vite 代理 → 同事 ResearchEngine (192.168.3.64:9527)  （去掉 /yg-api 前缀）
```

- **本机不存 bars / panel 原始行情**；算因子、策略回测、日线读数都在 **YGQuant ResearchEngine**。  
- WebApp 后端是 **ThreadingHTTPServer 薄 BFF**：路由全在 `backend/api_server.py` 的 `Handler` 里按 path 顺序匹配。  
- 长耗时因子回测：**不要**让 Vite 线程同步干等 RE → 走 `/api/factor/re-backtest` **异步队列**（`re_backtest_jobs`）。

---

## 1. 进程与端口

| 角色 | 地址 | 代码入口 |
|------|------|----------|
| 前端开发 | `http://127.0.0.1:9530` | `frontend/` · `npm run dev` |
| 前端试用预览 | `:9532` | `npm run preview:stable` |
| SVQuant API | `:8766` | `backend/api_server.py` |
| 同事 RE | `192.168.3.64:9527` | 仓外同事机；本仓有 `ResearchEngine/` 源码对照 |
| Postgres | `:5432` | 账号/社区/检测策略项目等 |
| 面板缓存 | SQLite 文件 | `backend/output/factor_dashboard/metrics.sqlite` |

代理配置：`frontend/vite.config.ts`（`/api`→8766，`/yg-api`→9527，强制绕过 Clash 对本机/局域网的拐弯）。

---

## 2. 模块地图（改哪里）

### 2.1 前端 `frontend/src/`

| 目录 | 职责 |
|------|------|
| `App.tsx` | 全部路由；`Authed` = 需登录 |
| `pages/` | 页面（因子/策略/检测/社区/数据/AI/帮助…） |
| `components/` | Layout、Navbar、RequireAuth；`community/` `factor/` `data/` |
| `lib/` | `auth.ts`、`*Api.ts`、`detectStore.ts`、`strategyStore.ts`、`ygApi.ts` |
| `content/help/` | 帮助目录；正文从 `docs/help/` 以 `?raw` 引入 |

### 2.2 后端 `backend/`

| 路径 | 职责 |
|------|------|
| `api_server.py` | **唯一 HTTP 路由表**（GET/POST/PUT/DELETE） |
| `services/auth/` | 注册登录 JWT、资料关注 |
| `services/factor/` | 因子库、检测、RE 目录、回测 BFF/队列、面板、试算 |
| `services/strategy/` | 策略项目/runs、官方/用户策略库 |
| `services/community/` | 帖子评论赞踩收藏通知 |
| `services/news/` | 资讯入库与列表 |
| `services/data/` | 自选股；日线 BFF |
| `services/core/` | PG、`lan_http`、env、回测区间 |
| `factor/` | 本机托管的自定义因子 `.py` + `index.yaml` |
| `ai/gateway/` | 方舟/硅基对话、语音 |
| `ai/runtime/` | Agent 配额与编排壳 |
| `ai/crews/gather_idea/` | A→B→C→D→E 因子灵感流水线 |
| `scripts/` | 面板批跑、目录同步、冒烟 |

### 2.3 KnowledgeHub

- `api_server` 把 `WebApp/KnowledgeHub/backend` 插入 `sys.path`。  
- 对外：`/api/kh*`（文档/OpenAPI 等）。与主站社区分离。

---

## 3. 两条出站通道（同事接口怎么走）

### A. 浏览器 → `/yg-api` → RE（无本站 JWT）

典型前端：`src/lib/ygApi.ts`、`aiFactorApi.ts`、`aiStrategyApi.ts`…

| 用途 | RE 路径（经 `/yg-api`） |
|------|-------------------------|
| 策略回测 | `POST /api/backtest/strategy` |
| 标的/指数列表等 | `GET /api/market-data/...` |
| RE 侧 AI 生成/解读 | `/api/ai/factor-generations` 等 |

### B. 浏览器 → `/api` → 本机 BFF → `lan_http` 直连 RE

| 本机 API | 实现 | 上游 RE |
|----------|------|---------|
| `POST /api/factor/re-backtest` + `GET .../{job_id}` | `re_backtest_jobs` → `forward_factor_backtest` | `POST /api/backtest/factor` |
| `POST /api/factor/custom/trial` | `factor_trial.py` | 同上（同步，超时更短） |
| `GET /api/market-data/daily/{code}` | `market_data_bff.py` | `GET /api/market-data/daily/{code}` |
| `GET/POST /api/factor/re-catalog*` | `re_factor_catalog.py` | 因子库列表/明细 |
| 面板 refresh | `dashboard_store.py` | 批跑官方库 `POST /api/backtest/factor` |
| `POST /api/agent/factor-backtest` | `backtest_agent` → `forward_factor_backtest` | **同步干等**（不走 job 队列） |

**GitNexus 调用边（核对）：**

- `api_server.do_POST` → `submit_factor_backtest`
- `_run_job` / `run_backtest_report` → `forward_factor_backtest`

`lan_http.py`：进程内 `NO_PROXY` + 无代理 opener，避免 Clash 把 `192.168.3.64` 打成 **502**。

---

## 4. 主流程（排错按这条链）

### 4.1 登录

```
LoginPage → POST /api/auth/login → auth_store
→ JWT + user 写入 sessionStorage（svquant_token / svquant_user）
→ 受保护页 RequireAuth；新标签 prepareAuthHandoff（localStorage 60s）→ consumeAuthHandoff
```

关键：`frontend/src/lib/auth.ts` · `backend/services/auth/auth_store.py`

### 4.2 因子检测回测（最易 502 的那条）

```
FactorDetectPage
  → detectStore 建项目/落 run（/api/detect/... · PG）
  → ygBacktestFactor → POST /api/factor/re-backtest   ← 立刻返回 job_id
  → 轮询 GET /api/factor/re-backtest/{id}
  → 池内 forward_factor_backtest → RE POST /api/backtest/factor
  → 成功后再写 detect run 结果
```

- 限流：`MAX_INFLIGHT` 默认 **8**（`SVQUANT_RE_BACKTEST_INFLIGHT`）。  
- **成功口径：** HTTP 200 且业务 `error == null`（帮助 FAQ 已写）。

### 4.3 策略研究回测

```
StrategyBacktestPage
  → /api/strategy/projects|runs 落库
  → ygBacktestStrategy → /yg-api/api/backtest/strategy  （直连 RE，不经本机队列）
  → 结果回写本机 runs / blob gzip
```

### 4.4 因子库 / 面板

- 官方目录：PG 快照权威，`re-catalog` 可 `fresh` 拉 RE。  
- 自定义：PG + 同步 `factor/custom_lib.py`。  
- 面板：只批跑官方公开库；指标进 SQLite，**不算** `custom_lib` / 带 `owner_id` 的他人因子。

### 4.5 行情 K 线

```
日线：/api/market-data/daily/:code → market_data_bff（内存 TTL）→ RE
码表等：/yg-api/api/market-data/...
自选：/api/watchlists*（只存关系，主数据在 RE）
```

### 4.6 社区 / 资讯

- 全走本机 `/api/community/*`、`/api/news*`（PG）；**不打 RE**。  
- 社区 AI 润色：`/api/agent/runs`（runtime orchestrator）。

### 4.7 Agent 搜集灵感 A→E

```
A gather → EvidencePack
B idea   → IdeaBundle（focus 写死偏因子）
C factor → 草稿代码
D backtest → forward_factor_backtest（同步）
E eval   → 是否建议入库（不自动写库）
```

端点：`/api/agent/gather|idea|factor|factor-backtest|factor-eval`；配额 `/api/agent/usage*`。

### 4.8 帮助

- 纯前端 Markdown：`/help/:docId` ← `docs/help/07-factor-strategy-guide/*.md`  
- **无后端。**

---

## 5. 数据边界（别踩）

| 存本机 | 不存本机 |
|--------|----------|
| 用户 JWT 业务数据（PG） | bars / 原始 panel |
| `factor/*.py` + `index.yaml`（自定义） | NBQuant 东财主库（别混 baostock） |
| 面板聚合指标 SQLite | RE 上的行情计算中间态 |
| 策略 run 的 gzip blob | — |
| 日线 BFF 进程内存短缓存 | — |

---

## 6. Bug 定位速查

| 现象 | 先查 |
|------|------|
| 整站 `/api` 全挂、短请求也 502 | `:8766` 是否被同步回测占满？是否误走了旧「同步打 RE」路径？看 `re_backtest_jobs` |
| 只有打 RE 失败 / 超时 | `192.168.3.64:9527` 可达？Clash？`lan_http` / Vite `NO_PROXY` |
| 检测白屏 / about:blank | 预览 iframe 与 loading HTML；报告页数据是否空 |
| 登录丢了 / 新标签未登录 | `sessionStorage` vs `prepareAuthHandoff` |
| 因子库列表空 | `re_factor_catalog` 快照；`POST .../re-catalog/sync` |
| 策略 OK、因子回测挂 | 因子走 BFF 队列；策略走 `/yg-api` — **两条链分开查** |
| Agent D 很慢卡住 | `backtest_agent` **同步**等 RE，不占 job 池但仍占 HTTP 线程 |
| 社区问题 | 只查 `community_store` + PG，别怀疑 RE |

**GitNexus 日常用法：**

```text
context({ name: "submit_factor_backtest", repo: "SVQuant" })
query({ search_query: "factor backtest" })   # FTS 修好后可用
cypher: MATCH (a)-[:CodeRelation {type:'CALLS'}]->(b:Function {name:'...'}) RETURN a.name, a.filePath
```

---

## 7. 前端路由速览（需登录用 Authed）

公开：`/` `/login` `/register` `/community*`（读） `/news*` `/help*` `/search`  
登录后：`/factor/*` `/strategy/*` `/data/*` `/ai/*` `/community/new|me|...`

完整表以 `frontend/src/App.tsx` 为准。

---

## 8. 后续（可选）

1. 大改代码后：`npx gitnexus analyze`；FTS 异常再 `$env:GITNEXUS_LBUG_EXTENSION_INSTALL="auto"; npx gitnexus analyze --repair-fts`  
2. 大改前：`impact` / `detect_changes` 看爆炸半径  
3. 本地图与 `webapp-architecture.html` 有出入时，以 **代码 + 本 md** 为准  
4. 按模块补「可测步骤表」（检测回测已有）

---

## 9. GitNexus 页面怎么打开（看调用图）

### 9.1 官方 UI（图谱）

1. `npx gitnexus serve -p 4747 --host 127.0.0.1`
2. 浏览器打开 **http://127.0.0.1:4747/**
3. 选仓库 **SVQuant**

> `--force` 重建后，流程步骤节点 id 已能从 cypher 读出；若「查看」仍不亮左边，硬刷新官方页再试灯泡。  
> **不要点「完整流程图」（300 条合并）**。

### 9.2 本地流程查看页（推荐读步骤）

**http://127.0.0.1:8765/gitnexus-flows.html**

需：`cd WebApp/docs && python -m http.server 8765 --bind 127.0.0.1`，且 4747 serve 在跑。

### 9.3 「300 个流程」≠ 全部产品功能

GitNexus 流程是自动挖的调用链（大量 `Page → AuthStore`），不是业务测单。  
测功能用 `可测步骤-*.md`。详见 [`GitNexus本机打开说明.md`](./GitNexus本机打开说明.md)。
