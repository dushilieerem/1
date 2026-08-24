# SVQuant 本机 API 说明（:8766）

本文描述 **WebApp 本机后端**（FastAPI，`http://127.0.0.1:8766`）的接口：做什么、发什么、收什么。

## `/docs` 是不是全部？

[http://127.0.0.1:8766/docs](http://127.0.0.1:8766/docs) 会列出本机 **约 91 条路径**，和当前路由表一致，但有三点要注意：

1. **请求/响应字段几乎没写细**：路由用的是未建模的 JSON `dict`，Swagger 里多半只有「随便一个 object」，**不能当字段手册**。字段以本文为准。
2. **知识库 `/api/kh/*` 在 `/docs` 里是一条通配** `/api/kh/{path}`。明细在 [http://127.0.0.1:8766/api/kh/docs](http://127.0.0.1:8766/api/kh/docs)。
3. **不算本机 API、不在 `/docs`**：前端 `/yg-api/*` 由 Vite 转到同事 ResearchEngine `:9527`（因子/策略回测、行情、部分 AI）。检测台「进行检测」走的是这条，不是下面的 `/api/factor/re-backtest`。

前端开发时：`fetch('/api/...')` → Vite 代理到 `127.0.0.1:8766`。

---

## 通用约定

| 项 | 说明 |
|---|---|
| 协议 | JSON，`Content-Type: application/json`（少数返回 YAML/源码/SSE） |
| 鉴权 | 需要登录的接口：`Authorization: Bearer <token>`（登录/注册返回的 `token`） |
| 成功 | HTTP 200，业务体多为 `{ "ok": true, ... }` |
| 失败 | `{ "error": "说明文字" }`；常见 400 参数、401 未登录、403 无权限、404 不存在 |
| 可选登录 | 部分 GET 无 token 时返回空列表（如用户因子库、自选股列表），不是 401 |

`user` 对象常见字段：`id, username, email, role, status, display_name, ai_quota_daily, avatar_url, cover_url, headline, bio, created_at`。

---

## 健康检查

### `GET /api/health`（无需登录）

**收：** `{ ok, service, port, factor_dir, note }`  
例：`service=svquant`，`port=8766`。

---

## 登录 / 用户 / 资料

### `POST /api/auth/register`

**发：** `{ username, password, email?, display_name? }`  
**收：** `{ ok, user, token }`；校验失败 400。

### `POST /api/auth/login`

**发：** `{ username, password }`  
**收：** `{ ok, user, token }`；账密错误 401。

### `GET /api/auth/me`

**发：** Header Bearer  
**收：** `{ ok, user, dev_skip_auth }`；无效 token 401。

### `POST /api/profile/me`

**发：** 出现的字段才会改：`display_name, headline, bio, avatar_url, cover_url`  
**收：** `{ ok, profile }`。`profile` 含关注数、帖子数、`is_self`、`is_following` 等。

### `GET /api/users/{username}`

可选登录（影响 `is_following`）。  
**收：** `{ ok, profile }`；用户不存在 404。

### `GET /api/users/{username}/posts`

Query：`limit`（默认 20）、`offset`、`section`。  
**收：** `{ ok, total, section, section_counts, items }`。

### `GET /api/users/{username}/following` · `GET .../followers`

Query：`limit`（默认 30）、`offset`。可选登录。  
**收：** `{ ok, kind, total, items }`。

### `POST /api/users/{username}/follow` · `DELETE .../follow`

需登录。  
**收：** `{ ok, profile }`（对方资料）。不能关注自己 → 400。

---

## 因子检测（项目 / 记录）

回测计算 **不在本机**。本机只存项目配置和跑完后的报告。

### `GET /api/detect/projects`

需登录。Query：`visible`（`1/true` 时只显示样本或已有 run 的项目）。  
**收：** `{ ok, user_id, username, projects }`  
`project`：`id, name, factorName, description, createdAt, updatedAt, runCount, sample, config`。

### `POST /api/detect/projects`

需登录。

- 若带 `factorName`/`factor_name` 且 **没有** `id`、`config` → **新建**：`factorName`、`description`/`name`、可选 `name` 作显示名。  
- 否则 **upsert** 整份 body：`id, name, factorName, description, config, sample`。

**收：** `{ ok, user_id, project }`。

### `GET /api/detect/projects/{id}` · `PUT` · `DELETE`

需登录。PUT 的 body 会强制带上 path 里的 `id` 再 upsert。  
GET 收 `{ ok, user_id, project }`；DELETE 收 `{ ok, id }`（样本项目可能 `{ ok, skipped: "sample" }`）。

### `GET /api/detect/projects/{id}/runs`

需登录。  
**收：** `{ ok, user_id, runs }`（列表里的 `request`/`result` 为精简版）。

### `POST /api/detect/runs`

需登录。  
**发：** `projectId`（必填），可选 `id, factorName, description, request, result, finishedAt, elapsedSec`。  
**收：** `{ ok, user_id, run, project }`。缺项目 404。

### `GET /api/detect/runs/{id}` · `DELETE`

需登录。GET 收 `{ ok, run }`（完整 request/result）。跨用户读 → 404。

---

## 策略研究

形态与检测类似，需登录（用户策略库列表无 token 时返回空数组）。

| 方法 | 路径 | 发 | 收 |
|---|---|---|---|
| GET | `/api/strategy/projects` | Query `visible` | `{ ok, projects, ... }` |
| POST | `/api/strategy/projects` | 无 `id` 且无 `config` → 按 `name`/`description` 新建；否则 upsert | `{ ok, project }` |
| GET/PUT/DELETE | `/api/strategy/projects/{id}` | PUT：配置 JSON | 项目对象 / `{ ok, id }` |
| GET | `/api/strategy/projects/{id}/runs` | — | `{ ok, runs }` |
| POST | `/api/strategy/runs` | `projectId` + `request`/`result` 等 | `{ ok, run }` |
| GET/DELETE | `/api/strategy/runs/{id}` | — | run / `{ ok, id }` |
| GET | `/api/strategy/library` | — | 内置策略目录 |
| GET | `/api/strategy/library/{id}` | Query `version` | 策略源码 |
| GET/POST | `/api/strategy/libraries` | POST `{ name }` | `{ ok, libraries }` / `{ ok, library }` |
| DELETE | `/api/strategy/libraries/{libId}` | — | `{ ok, ... }` |
| GET/POST | `/api/strategy/libraries/{libId}/strategies` | POST：`name, body\|strategy_code, description, categoryLabel, codeId, sourceRunId, archive*` | `{ ok, strategies }` / `{ ok, strategy }` |
| DELETE | `/api/strategy/libraries/{libId}/strategies/{strategyId}` | — | `{ ok, ... }` |
| GET | `/api/strategy/library-strategies/{id}/archive` | — | 入库时冻结的回测包 |

真正跑策略回测：前端 `POST /yg-api/api/backtest/strategy`（不在本表）。

---

## 因子库 / 目录 / 面板 / 自定义

| 方法 | 路径 | 鉴权 | 发 | 收 |
|---|---|---|---|---|
| GET | `/api/factor/index` | 可选 | — | YAML 文本（按用户过滤后的 index） |
| GET | `/api/factor/re-catalog` | 无 | Query `fresh`,`all`（`1/true/yes`） | 内置因子目录 JSON；RE 不可达 **502** `{ ok:false, error }` |
| POST | `/api/factor/re-catalog/sync` | **管理员** | — | 全量同步结果；空目录 502 |
| GET/POST | `/api/factor/libraries` | GET 可选；POST 需登录 | POST `{ name }` | `{ ok, libraries }` / `{ ok, library }` |
| DELETE | `/api/factor/libraries/{id}` | 登录 | — | `{ ok, ... }` |
| GET | `/api/factor/libraries/factors` | 可选 | — | `{ ok, factors }` |
| GET/POST | `/api/factor/libraries/{id}/factors` | 登录 | POST `{ name, body\|expression, description, categoryLabel\|category }` | `{ ok, factors }` / `{ ok, factor }` |
| DELETE | `/api/factor/libraries/{libId}/factors/{factorId}` | 登录 | — | `{ ok, ... }` |
| GET | `/api/factor/file/{name}` | `custom_lib.py` 按用户过滤 | path 不能含 `..` `/` `\` | 源码或 YAML 字节；404 |
| GET | `/api/factor/dashboard` | 无 | Query `universe, period, filter_limit_up, filter_suspended, library` | 面板指标表 |
| GET | `/api/factor/dashboard/status` | 无 | — | 批跑 job 状态 |
| POST | `/api/factor/dashboard/refresh` | 无 | `{ universe, period, filter_limit_up, filter_suspended, limit? }` | 启动批跑 |
| POST | `/api/factor/dashboard/verify` | **管理员** | `{ factor_name, status, note }` | 校验状态 |
| POST | `/api/factor/custom` | 登录 | `{ name, body, description }` | 新增自定义因子 |
| PUT/DELETE | `/api/factor/custom/{name}` | 登录 | PUT `{ body, description }` | 更新/删除 |
| POST | `/api/factor/custom/trial` | 登录 | `{ body, name\|factor_name, universe, period }` | 试算（同步打 RE，可能较慢） |
| POST | `/api/factor/re-backtest` | 登录 | 与 RE 因子回测相近的 JSON | `{ job_id, ... }` 异步队列（**检测台已不用**；兼容旧客户端） |
| GET/DELETE | `/api/factor/re-backtest/{job_id}` | 登录 | — | 任务状态 / 取消。`missing`→404，`forbidden`→403 |

检测台当前回测：**`POST /yg-api/api/backtest/factor`**

**发（给 RE，不经本机队列）：**

```json
{
  "library_name": "momentum_lib",
  "factor_name": "momentum_20d",
  "universe": "CSI300",
  "start": "2016-08-19",
  "end": "2026-08-19",
  "filter_limit_up": true,
  "filter_suspended": true,
  "groups": 5,
  "rebalance_days": 5,
  "benchmark": "CSI300",
  "analysis_level": "core",
  "commission_rate": 0.0003,
  "stamp_tax": 0.001,
  "slippage_rate": 0.001
}
```

自定义代码时带 `factor_code`；纯内置因子不要传空 `factor_code`。  
**收：** 回测报告 JSON，或 `{ error }`；并发过多可能 **429**。

---

## 自选股

| 方法 | 路径 | 发 | 收 |
|---|---|---|---|
| GET | `/api/watchlists` | 无 token → 空列表 | `{ ok, watchlists }` |
| POST | `/api/watchlists` | `{ name }` | `{ ok, watchlist }` |
| PUT | `/api/watchlists/{id}` | `{ name }` | 改名后的列表项 |
| DELETE | `/api/watchlists/{id}` | — | `{ ok, ... }` |
| GET | `/api/watchlists/{id}/symbols` | 需登录 | `{ ok, symbols }` |
| POST | `/api/watchlists/{id}/symbols` | `{ symbol, name }` | 添加结果 |
| POST | `/api/watchlists/{id}/symbols/batch` | `{ items: [{symbol, name}, ...] }` | 批量添加 |
| DELETE | `/api/watchlists/{id}/symbols/{symbol}` | — | `{ ok, ... }` |

指数成分、代码搜索等走 `/yg-api/api/market-data/...`。

### `GET /api/market-data/daily/{code}`

Query：`start, end, fresh`（`1/true/yes` 绕缓存）。本机再转 RE。失败 400/502。

---

## 资讯

无需登录（ingest/enrich 也未强制登录）。

| 方法 | 路径 | 发 | 收 |
|---|---|---|---|
| GET | `/api/news` | Query：`category, source, q, mode, theme[], symbol[], industry[], limit, offset` | 列表页 JSON |
| GET | `/api/news/dict` | — | `{ ok, ...标签字典 }` |
| GET | `/api/news/{id}` | id 须为数字 | 单条 |
| POST | `/api/news/ingest` | `{ sources?: string[]\|逗号串, limit\|limit_per_source? }` | 抓取结果；非法源 400 并带回 supported |
| POST | `/api/news/{id}/enrich` | — | 补全文 |

---

## 社区

列表/热帖/帖详情/评论列表 **可不登录**。写操作、收藏、通知、审核 **需登录**。审核/举报处理/清空帖需相应角色（无权限 403）。

| 方法 | 路径 | Query / Body | 收（概要） |
|---|---|---|---|
| GET | `/api/community/posts` | `section, q, sort=views, limit=50, offset=0` | 帖子列表 |
| POST | `/api/community/posts` | `{ title, body, section, code_snippet?, status?, platform_ref? }` | 新帖 |
| GET | `/api/community/posts/{id}` | `bump` 默认计阅读；`0/false/no` 不计 | 帖详情 |
| PUT | `/api/community/posts/{id}` | 同创建字段 + `clear_platform_ref?` | 更新后的帖 |
| DELETE | `/api/community/posts/{id}` | — | `{ ok }` |
| GET | `/api/community/posts/{id}/comments` | — | 评论树 |
| POST | `/api/community/posts/{id}/comments` | `{ body, parent_id?, images? }` | 新评论 |
| POST | `/api/community/posts/{id}/vote` | `{ value }` | 投票后计数 |
| POST/DELETE | `/api/community/posts/{id}/favorite` | — | 收藏/取消 |
| POST | `/api/community/posts/{id}/moderate` | `{ pinned?, status? }` | 置顶/状态 |
| POST | `/api/community/posts/{id}/purge` | — | 管理删除 |
| POST | `/api/community/comments/{id}/vote` | `{ value }` | 评论投票 |
| GET | `/api/community/hot` | `limit, section` | 热帖 |
| GET | `/api/community/favorites` | `limit, offset` | 我的收藏 |
| GET | `/api/community/my-posts` | `status, limit, offset` | 我的帖 |
| GET | `/api/community/notifications` | `type, limit, offset` | 通知列表 |
| GET | `/api/community/notifications/unread-count` | — | 未读数 |
| POST | `/api/community/notifications/read` | `{ ids?, type?, all? }` | 已读 |
| GET/POST | `/api/community/reports` | POST `{ target_type, post_id, comment_id?, reason, detail }` | 列表 / 提交 |
| POST | `/api/community/reports/{id}/resolve` | `{ status? }` 默认 resolved | 处理举报 |
| GET | `/api/community/moderation` | `kind, limit, offset` | 审核队列 |
| GET | `/api/community/ops/summary` | `days` 默认 7 | 运营汇总 |

---

## Agent / AI 对话

均需登录（models/speech status 除外）。配额不足：`PermissionError` 且文案含「配额」→ **403**。

### `GET /api/agent/usage/me`

Query：`days` 默认 7。当前用户用量。

### `GET /api/agent/usage`

**管理员。** Query：`days`。全站用量。

### `POST /api/agent/usage/quota`

**管理员。** `{ user_id, quota_daily }`。

### `POST /api/agent/runs`

`{ goal, skills?: string[], context?: object, mode?, crew? }` → 一次 Agent 运行结果。

### 流水线（body 为 JSON 对象，字段随步骤变化）

| 路径 | 典型发送 | 接收 |
|---|---|---|
| `POST /api/agent/gather` | `{ topic, themes?, symbols?, time_window?, sources?, max_items? }` | 证据包 |
| `POST /api/agent/idea` | 搜集结果 + 约束 | Idea 包 |
| `POST /api/agent/factor` | Idea / 说明 | 因子草稿 |
| `POST /api/agent/factor-backtest` | 因子草稿 + 回测参数 | 回测报告（内部会打 RE） |
| `POST /api/agent/factor-eval` | 报告 | 评价 |

### `GET /api/ai/chat/models`

可用模型列表（无需登录）。

### `POST /api/ai/chat`

**发：** `{ messages: [{role, content}, ...], model?, temperature?, stream? }`

- `stream` 假：JSON `{ content, model, usage }`
- `stream` 真：`text/event-stream`  
  `data: {"status":"start"}` → 多条 `data: {"delta":"..."}` → `data: [DONE]`  
  出错：`data: {"error":"..."}` 再 `[DONE]`

上游未配置 → 503；其它网关错 → 502。

### `GET /api/ai/speech/status`

语音是否就绪。

### `POST /api/ai/speech/transcribe`

**发：** `{ audio_base64, mime? }`（可带 `data:...;base64,` 前缀）  
**收：** 转写文本 JSON。

---

## 知识库 `/api/kh`

本机 FastAPI 把非文档路径转给 KnowledgeHub。管理员界面；未登录时默认可进（环境变量 `KH_REQUIRE_AUTH=1` 则强制登录）。

交互文档：[http://127.0.0.1:8766/api/kh/docs](http://127.0.0.1:8766/api/kh/docs)

| 方法 | 路径 | 做什么 |
|---|---|---|
| GET | `/api/kh/docs` · `/api/kh/openapi.json` | Swagger / 规格 |
| GET | `/api/kh/meta` | 管线、切分策略 |
| GET/POST | `/api/kh/collections` | 列出 / 创建知识库 |
| PUT/DELETE | `/api/kh/collections/{id}` | 改名或删除（含文档、切片） |
| GET | `/api/kh/collections/{id}/documents` | 库内文档 |
| POST | `/api/kh/documents` | 上传/粘贴；Word/PDF 用 `contentBase64` + `fileName` |
| GET/PUT/DELETE | `/api/kh/documents/{id}` | 详情 / 启用停用 / 删除 |
| GET | `/api/kh/documents/{id}/chunks` | 切片 |
| POST | `/api/kh/documents/{id}/ingest` | 重新切片入库 |
| POST | `/api/kh/search` | 检索切片 `{ query, collection_ids?, top_k? }` |
| POST | `/api/kh/ask` | 检索 + LLM 回答 |
| GET/POST/DELETE | `/api/kh/chats/{id}/messages` | 默认会话消息 |
| GET/POST | `/api/kh/chats/{id}/conversations` | 会话列表 / 新建 |
| GET/POST/PUT/DELETE | `/api/kh/conversations/{id}` 及 `/messages` | 指定会话 CRUD、清空历史 |

另有文件、模型供应商、默认模型等，以 KH Swagger 为准。

---

## 和前端页面的对应（常用）

| 页面动作 | 本机 `/api` | 计算 `/yg-api` |
|---|---|---|
| 登录 | `POST /api/auth/login` | — |
| 因子库页头「检测」 | 无（只跳转列表） | — |
| 因子库行内红「检测」 | `GET/POST/PUT /api/detect/projects` | **不打** |
| 检测台「进行检测」 | 先 `PUT` 项目，成功后 `POST /api/detect/runs` | `POST /api/backtest/factor` |
| 策略回测 | 存 `strategy/runs` | `POST /api/backtest/strategy` |
| 社区发帖 | `POST /api/community/posts` | — |

---

## 怎么试

```bash
# 交互列表（字段不完整）
# http://127.0.0.1:8766/docs

curl http://127.0.0.1:8766/api/health
curl -s -X POST http://127.0.0.1:8766/api/auth/login ^
  -H "Content-Type: application/json" ^
  -d "{\"username\":\"max\",\"password\":\"123456\"}"
```

把返回的 `token` 放到后续请求的 `Authorization: Bearer ...`。
