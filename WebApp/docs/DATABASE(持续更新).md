# SVQuant 数据库说明

> **最后刷新：** 2026-08-12 15:07（Asia/Shanghai）  
> **怎么更新：** 在 `WebApp/backend` 执行 `python scripts/refresh_database_docs.py`。脚本会重写本文件的表清单 / 字段 / 行数 / 样例；表用途与字段说明改脚本顶部的 `PURPOSES` / `FIELD_HINTS`。
> **边界：** SVQuant **不存行情 bars**；因子面板指标在本机 SQLite；账号 / 社区 / 检测 / 策略 / **官方因子目录缓存** （`re_factor_catalog_*`）/ **KnowledgeHub（`kh_*`）** 在 PostgreSQL。旧 `kb_*` 已删除，勿再建。

---

## 总览

| 库 | 引擎 | 连接 / 路径 | 表数量 | 用途 |
|----|------|-------------|--------|------|
| **主库** | PostgreSQL | `.env` → `DATABASE_URL`（`svquant`） | **33** | 用户、社区、Agent、检测/策略、KnowledgeHub |
| **因子面板缓存** | SQLite | `backend/output/factor_dashboard/metrics.sqlite` | **2** | 面板 IC/夏普等 + 跨平台校验状态 |

### PostgreSQL 表一览

| 表名 | 约行数 | 作用（一句话） |
|------|--------|----------------|
| `ai_usage` | 155 | Agent 调用流水（按 skill 一行）；日配额按当日行数计。 |
| `comment_votes` | 6 | 评论赞/踩（每用户每评论一票）。 |
| `community_reports` | 6 | 举报帖/评论；管理仓处理队列。 |
| `detect_projects` | 205 | 因子检测项目配置与归属。 |
| `detect_runs` | 216 | 因子检测一次运行结果摘要 / 状态。 |
| `kh_chat_messages` | 24 | KnowledgeHub 会话消息（role + content）；挂在 kh_conversations 下。 |
| `kh_chats` | 2 | KnowledgeHub 聊天应用配置（开场白、系统提示、关联知识库 ids）。 |
| `kh_chunks` | 180 | KnowledgeHub 文档切片（ordinal + text + meta JSONB）；检索读此表。 |
| `kh_collections` | 4 | KnowledgeHub 知识库集合（:9531；类型 pipeline + 分块策略）。 |
| `kh_conversations` | 8 | KnowledgeHub 用户会话线程（关联 chat / collection）。 |
| `kh_default_models` | 6 | 默认模型角色（llm / embedding / rerank …）。 |
| `kh_documents` | 6 | KnowledgeHub 文档（正文 / 分块策略 / status / enabled / parse_error）。 |
| `kh_files` | 0 | KnowledgeHub 文件管理页登记（可关联 collection）。 |
| `kh_model_providers` | 1 | 模型供应商（通义/OpenAI 兼容等；存 base_url / api_key）。 |
| `news_items` | 11779 | 资讯聚合条目（快讯/市场/公告/研报/政策/海外；真源 ingest upsert，含定时调度）。 |
| `notifications` | 54 | 站内通知（回复、@、系统等）。 |
| `post_comments` | 36 | 帖评论与楼中楼回复。 |
| `post_favorites` | 5 | 用户收藏帖。 |
| `post_votes` | 9 | 帖赞/踩（每用户每帖一票）。 |
| `posts` | 69 | 社区帖（正文 / 代码 / 分区 / 状态 / 置顶）。 |
| `re_factor_catalog_snapshot` | 1 | ResearchEngine 官方因子目录快照（库列表+因子清单 JSON）；页面读此表，不每次打 RE。 |
| `re_factor_catalog_sync_log` | 3 | 官方因子目录同步日志（定时/手动：有无变更、hash、条数）。 |
| `strategy_projects` | 80 | 策略研究项目配置与归属。 |
| `strategy_runs` | 74 | 策略回测一次运行结果摘要 / 状态。 |
| `user_custom_factors` | 0 | 用户自定义因子元数据（`.py` 另存磁盘；本表记归属与可见性）。 |
| `user_factor_libraries` | 7 | 用户自建因子库（文件夹）；与内置库同级，按 user 隔离。 |
| `user_follows` | 5 | 用户关注关系（关注者 → 被关注者）。 |
| `user_library_factors` | 13 | 用户因子库内的因子条目（含代码正文、分类、说明）。 |
| `user_library_strategies` | 3 | 用户策略库内入库快照（含策略说明、回测归档 JSON；与研究侧 run 脱钩）。 |
| `user_strategy_libraries` | 5 | 用户自建策略库（文件夹）；与内置库同级，按 user 隔离。 |
| `user_watchlist_symbols` | 41 | 自选组合内标的（symbol + 名称快照）；归属某 watchlist。 |
| `user_watchlists` | 6 | 用户自选股组合（文件夹）；按 user 隔离，前端 `/data/watchlist`。 |
| `users` | 9 | 账号与资料：登录、角色、AI 日配额、公开主页头像/封面/简介。 |

### SQLite 表一览

| 表名 | 约行数 | 作用（一句话） |
|------|--------|----------------|
| `factor_dashboard_metrics` | 15912 | 因子面板指标缓存（因子×池×周期×过滤规则）；RE 算完写入，非行情库。 |
| `factor_verify_status` | 2 | 因子跨平台对比校验状态（按因子名：pending/passed/failed），与指标行解耦。 |

---

## 怎么查

### PostgreSQL

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY 1;
```

```bash
cd WebApp/backend
python -c "from services.db import get_conn
with get_conn() as c:
  print([r['table_name'] for r in c.execute(\"SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1\").fetchall()])"
```

### 因子面板 SQLite

```bash
cd WebApp/backend
sqlite3 output/factor_dashboard/metrics.sqlite ".tables"
sqlite3 output/factor_dashboard/metrics.sqlite "SELECT COUNT(*) FROM factor_dashboard_metrics;"
```

代码入口：

- 连接：`services/db.py`
- 建表：`auth_store` / `profile_store` / `community_store` / `agent_store` / `detect_store` / `strategy_store` / `user_factor_store` / `user_library_store` / `user_strategy_library_store`
- 面板：`services/dashboard_store.py`

> **不在库内：** AI 因子/策略生成历史目前仅浏览器 `localStorage` （按 `userId` 隔离 key），未落 Postgres；后续计费对接服务端时再补表。

---

## A. PostgreSQL 表详解

### `ai_usage`

**作用：** Agent 调用流水（按 skill 一行）；日配额按当日行数计。

- 主键：`id`
- 当前行数：约 **155**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `user_id` | `bigint` | NO | 调用用户 |
| `run_id` | `text` | NO | 同一次 Agent run 的 UUID |
| `skill` | `text` | NO | 如 `polish_body` / `summarize_post` |
| `tokens_in` | `integer` | NO | 输入 token |
| `tokens_out` | `integer` | NO | 输出 token |
| `created_at` | `timestamp with time zone` | NO | 记账时间（按日计配额） |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 1,
    "user_id": 1,
    "skill": "polish_title",
    "tokens_in": 0,
    "tokens_out": 0,
    "created_at": "2026-07-24 13:42:20.406284+08:00"
  },
  {
    "id": 2,
    "user_id": 1,
    "skill": "polish_title",
    "tokens_in": 188,
    "tokens_out": 32,
    "created_at": "2026-07-24 13:55:20.169812+08:00"
  }
]
```

### `comment_votes`

**作用：** 评论赞/踩（每用户每评论一票）。

- 主键：`user_id`, `comment_id`
- 当前行数：约 **6**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `user_id` | `bigint` | NO | 投票用户 |
| `comment_id` | `bigint` | NO | 评论 |
| `value` | `smallint` | NO | 1 赞 / -1 踩 |
| `created_at` | `timestamp with time zone` | NO | 时间 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "user_id": 5,
    "comment_id": 5,
    "value": 1,
    "created_at": "2026-07-22 14:57:10.748818+08:00"
  },
  {
    "user_id": 4,
    "comment_id": 5,
    "value": 1,
    "created_at": "2026-07-23 17:48:28.809145+08:00"
  }
]
```

### `community_reports`

**作用：** 举报帖/评论；管理仓处理队列。

- 主键：`id`
- 当前行数：约 **6**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `reporter_id` | `bigint` | NO | 举报人 |
| `target_type` | `text` | NO | `post` / `comment` |
| `post_id` | `bigint` | NO | 关联帖 |
| `comment_id` | `bigint` | YES | 关联评论（可空） |
| `reason` | `text` | NO | 原因码 |
| `detail` | `text` | NO | 补充说明 |
| `status` | `text` | NO | `open` / `resolved` / `dismissed` |
| `created_at` | `timestamp with time zone` | NO | 举报时间 |
| `resolved_at` | `timestamp with time zone` | YES | 处理时间 |
| `resolver_id` | `bigint` | YES | 处理人 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 1,
    "reporter_id": 1,
    "target_type": "post",
    "post_id": 51,
    "reason": "spam",
    "status": "dismissed",
    "created_at": "2026-07-27 13:41:04.779079+08:00"
  },
  {
    "id": 2,
    "reporter_id": 5,
    "target_type": "post",
    "post_id": 33,
    "reason": "misinfo",
    "status": "resolved",
    "created_at": "2026-07-27 13:44:04.060039+08:00"
  }
]
```

### `detect_projects`

**作用：** 因子检测项目配置与归属。

- 主键：`user_id`, `id`
- 当前行数：约 **205**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `text` | NO | 项目 UUID/文本主键（与 user_id 复合） |
| `user_id` | `bigint` | NO | 所有者 |
| `name` | `text` | NO | 项目名 |
| `factor_name` | `text` | NO | 因子名 |
| `description` | `text` | NO | 说明 |
| `config` | `jsonb` | NO | 检测参数 JSON |
| `run_count` | `integer` | NO | 历史运行次数 |
| `is_sample` | `boolean` | NO | 是否示例项目 |
| `created_at` | `timestamp with time zone` | NO | 创建 |
| `updated_at` | `timestamp with time zone` | NO | 更新 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": "sample_momentum_5d",
    "user_id": 1,
    "name": "5日动量",
    "factor_name": "momentum_5d",
    "run_count": 1,
    "updated_at": "2026-07-21 12:14:04.475656+08:00"
  },
  {
    "id": "10aac563-4bf3-4380-9fea-4087dccd4b90",
    "user_id": 1,
    "name": "【因子检测】10日mom",
    "factor_name": "momentum_10d",
    "run_count": 0,
    "updated_at": "2026-07-23 11:05:55.464450+08:00"
  }
]
```

### `detect_runs`

**作用：** 因子检测一次运行结果摘要 / 状态。

- 主键：`user_id`, `id`
- 当前行数：约 **216**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `text` | NO | 运行 UUID/文本主键（与 user_id 复合） |
| `user_id` | `bigint` | NO | 所有者 |
| `project_id` | `text` | NO | 所属项目 id |
| `factor_name` | `text` | NO | 因子名 |
| `description` | `text` | NO | 说明 |
| `request` | `jsonb` | NO | 请求参数 JSON |
| `result` | `jsonb` | NO | 结果摘要 JSON |
| `finished_at` | `timestamp with time zone` | NO | 结束时间 |
| `elapsed_sec` | `double precision` | NO | 耗时秒 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": "test_run_1",
    "user_id": 1,
    "project_id": "sample_momentum_5d",
    "factor_name": "momentum_5d",
    "finished_at": "2026-07-21 12:14:04.475656+08:00",
    "elapsed_sec": 0.5
  },
  {
    "id": "test_run_3",
    "user_id": 3,
    "project_id": "sample_momentum_5d",
    "factor_name": "momentum_5d",
    "finished_at": "2026-07-21 12:14:05.279607+08:00",
    "elapsed_sec": 0.5
  }
]
```

### `kh_chat_messages`

**作用：** KnowledgeHub 会话消息（role + content）；挂在 kh_conversations 下。

- 主键：`id`
- 当前行数：约 **24**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO |  |
| `chat_id` | `bigint` | NO |  |
| `role` | `text` | NO |  |
| `content` | `text` | NO |  |
| `meta` | `jsonb` | NO |  |
| `created_at` | `timestamp with time zone` | NO |  |
| `conversation_id` | `bigint` | YES |  |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 9,
    "chat_id": 1,
    "role": "user",
    "content": "alpha 101",
    "meta": "{}",
    "created_at": "2026-08-04 10:27:19.896902+08:00",
    "conversation_id": 6
  },
  {
    "id": 26,
    "chat_id": 1,
    "role": "assistant",
    "content": "根据当前知识库内容无法确定。知识库中仅显示刘子铭在7.22会议上的汇报/负责模块为**“AI代理开发与数据源调研”**[2]，并未记录其具体的待办事项。如需准确信息，建议查阅完整的会议纪要原文。",
    "meta": "{\"hits\": [{\"meta\": {\"title\": \"导言\", \"embeddingDim\": 1024, \"embeddingModel\": \"qwen3.7-text-embedding\"}, \"text\": \"开发部7.22会议…",
    "created_at": "2026-08-05 15:02:42.003156+08:00",
    "conversation_id": 11
  }
]
```

### `kh_chats`

**作用：** KnowledgeHub 聊天应用配置（开场白、系统提示、关联知识库 ids）。

- 主键：`id`
- 当前行数：约 **2**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `name` | `text` | NO | 聊天应用名 |
| `description` | `text` | NO | 说明 |
| `opener` | `text` | NO | 开场白 |
| `system_prompt` | `text` | NO | 系统提示（可含 {knowledge}） |
| `empty_response` | `text` | NO | 无检索时回复 |
| `collection_ids` | `jsonb` | NO | 关联知识库 id 列表 JSONB |
| `model_name` | `text` | NO | 可选覆盖模型名 |
| `temperature` | `real` | YES | 采样温度 |
| `top_p` | `real` | YES | top_p |
| `max_tokens` | `integer` | YES | 最大 token |
| `created_by` | `bigint` | YES | 创建人 |
| `created_at` | `timestamp with time zone` | NO | 创建 |
| `updated_at` | `timestamp with time zone` | NO | 更新 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 1,
    "name": "1",
    "model_name": "",
    "updated_at": "2026-08-05 15:15:33.307199+08:00"
  },
  {
    "id": 2,
    "name": "2",
    "model_name": "",
    "updated_at": "2026-08-04 14:13:07.304183+08:00"
  }
]
```

### `kh_chunks`

**作用：** KnowledgeHub 文档切片（ordinal + text + meta JSONB）；检索读此表。

- 主键：`id`
- 当前行数：约 **180**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `document_id` | `bigint` | NO | kh_documents.id |
| `ordinal` | `integer` | NO | 片序 |
| `text` | `text` | NO | 切片正文 |
| `meta` | `jsonb` | NO | 如 title 等 JSONB |
| `created_at` | `timestamp with time zone` | NO | 创建 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 350,
    "document_id": 1,
    "ordinal": 0,
    "created_at": "2026-08-03 16:29:05.082891+08:00"
  },
  {
    "id": 351,
    "document_id": 3,
    "ordinal": 0,
    "created_at": "2026-08-03 16:35:26.658114+08:00"
  }
]
```

### `kh_collections`

**作用：** KnowledgeHub 知识库集合（:9531；类型 pipeline + 分块策略）。

- 主键：`id`
- 当前行数：约 **4**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `name` | `text` | NO | 知识库名（唯一） |
| `description` | `text` | NO | 说明 |
| `pipeline` | `text` | NO | 类型 general/qa/manual/… |
| `chunk_strategy` | `text` | NO | 分块策略 id |
| `status` | `text` | NO | active 等 |
| `created_by` | `bigint` | YES | 创建人 users.id（可空） |
| `created_at` | `timestamp with time zone` | NO | 创建 |
| `updated_at` | `timestamp with time zone` | NO | 更新 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 1,
    "name": "???-111539",
    "pipeline": "manual",
    "chunk_strategy": "markdown_heading",
    "status": "active",
    "updated_at": "2026-08-03 11:15:39.685452+08:00"
  },
  {
    "id": 9,
    "name": "因子手册v2",
    "pipeline": "general",
    "chunk_strategy": "markdown_heading",
    "status": "active",
    "updated_at": "2026-08-03 14:00:43.364442+08:00"
  }
]
```

### `kh_conversations`

**作用：** KnowledgeHub 用户会话线程（关联 chat / collection）。

- 主键：`id`
- 当前行数：约 **8**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO |  |
| `chat_id` | `bigint` | NO |  |
| `title` | `text` | NO |  |
| `created_at` | `timestamp with time zone` | NO |  |
| `updated_at` | `timestamp with time zone` | NO |  |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 5,
    "chat_id": 1,
    "title": "新会话",
    "created_at": "2026-08-04 10:24:49.663818+08:00",
    "updated_at": "2026-08-04 10:24:49.663818+08:00"
  },
  {
    "id": 6,
    "chat_id": 1,
    "title": "alpha 101",
    "created_at": "2026-08-04 10:27:07.975220+08:00",
    "updated_at": "2026-08-04 10:27:19.998867+08:00"
  }
]
```

### `kh_default_models`

**作用：** 默认模型角色（llm / embedding / rerank …）。

- 主键：`id`
- 当前行数：约 **6**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `role_key` | `text` | NO | llm / embedding / rerank … |
| `provider_key` | `text` | NO | 供应商 key |
| `model_name` | `text` | NO | 模型名 |
| `updated_at` | `timestamp with time zone` | NO | 更新 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 1,
    "role_key": "llm",
    "provider_key": "openai-compatible",
    "model_name": "qwen3.7-flash",
    "updated_at": "2026-08-03 15:30:44.695141+08:00"
  },
  {
    "id": 2,
    "role_key": "embedding",
    "provider_key": "openai-compatible",
    "model_name": "qwen3.7-text-embedding",
    "updated_at": "2026-08-03 15:30:44.695141+08:00"
  }
]
```

### `kh_documents`

**作用：** KnowledgeHub 文档（正文 / 分块策略 / status / enabled / parse_error）。

- 主键：`id`
- 当前行数：约 **6**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `collection_id` | `bigint` | NO | 所属 kh_collections.id |
| `title` | `text` | NO | 标题（可重命名） |
| `source_type` | `text` | NO | file / text |
| `body` | `text` | NO | 原文 |
| `file_name` | `text` | NO | 上传文件名 |
| `file_size` | `bigint` | NO | 字节 |
| `chunk_strategy` | `text` | NO | 分块策略 |
| `status` | `text` | NO | draft / parsing / ready / failed |
| `version` | `integer` | NO | ingest 版本 |
| `created_by` | `bigint` | YES | 上传人（可空） |
| `created_at` | `timestamp with time zone` | NO | 创建 |
| `updated_at` | `timestamp with time zone` | NO | 更新 |
| `enabled` | `boolean` | NO | 是否参与 search/ask（false=停用） |
| `parse_error` | `text` | NO | 最近一次解析失败原因 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 2,
    "collection_id": 4,
    "title": "因子库总览",
    "chunk_strategy": "markdown_heading",
    "status": "ready",
    "updated_at": "2026-08-03 16:22:39.600223+08:00"
  },
  {
    "id": 1,
    "collection_id": 1,
    "title": "????",
    "chunk_strategy": "markdown_heading",
    "status": "ready",
    "updated_at": "2026-08-03 16:29:05.082891+08:00"
  }
]
```

### `kh_files`

**作用：** KnowledgeHub 文件管理页登记（可关联 collection）。

- 主键：`id`
- 当前行数：约 **0**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `title` | `text` | NO | 标题 |
| `file_name` | `text` | NO | 文件名 |
| `file_size` | `bigint` | NO | 字节 |
| `body` | `text` | NO | 文本内容 |
| `collection_id` | `bigint` | YES | 可选关联知识库 |
| `created_by` | `bigint` | YES | 上传人 |
| `created_at` | `timestamp with time zone` | NO | 创建 |
| `updated_at` | `timestamp with time zone` | NO | 更新 |

### `kh_model_providers`

**作用：** 模型供应商（通义/OpenAI 兼容等；存 base_url / api_key）。

- 主键：`id`
- 当前行数：约 **1**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `provider_key` | `text` | NO | 供应商 key（唯一） |
| `display_name` | `text` | NO | 显示名 |
| `base_url` | `text` | NO | API Base URL |
| `api_key` | `text` | NO | 密钥（勿导出明文到文档样例） |
| `models` | `jsonb` | NO | 模型列表 JSONB |
| `created_at` | `timestamp with time zone` | NO | 创建 |
| `updated_at` | `timestamp with time zone` | NO | 更新 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 1,
    "provider_key": "openai-compatible",
    "display_name": "OpenAI 兼容 / 通义",
    "updated_at": "2026-08-03 15:26:32.407079+08:00"
  }
]
```

### `news_items`

**作用：** 资讯聚合条目（快讯/市场/公告/研报/政策/海外；真源 ingest upsert，含定时调度）。

- 主键：`id`
- 当前行数：约 **11779**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `title` | `text` | NO | 标题 |
| `summary` | `text` | NO | 摘要 |
| `body` | `text` | NO | 正文（电报多为全文；东财市场/政策可抓 HTML；研报为投资要点+#ctx-content，附 PDF 链；巨潮多为 PDF 说明） |
| `published_at` | `timestamp with time zone` | NO | 发布时间（巨潮常为披露日 00:00） |
| `source` | `text` | NO | `cls` / `eastmoney` / `cninfo` / `10jqka` / `wallstreetcn` / `bloomberg`（研报·政策调度键 em_research/em_policy，入库仍记 eastmoney） |
| `category` | `text` | NO | `flash` / `market` / `announce` / `research` / `policy` / `global` |
| `url` | `text` | NO | 源站、研报详情或 PDF 链接 |
| `symbols` | `jsonb` | NO | 关联代码 JSONB 数组 |
| `themes` | `jsonb` | NO | 题材标签 JSONB 数组（字典 + 源站） |
| `industries` | `jsonb` | NO | 行业标签 JSONB 数组（字典命中） |
| `raw_hash` | `text` | NO | 去重键（同源同条唯一） |
| `is_flash` | `boolean` | NO | 是否进电报流 |
| `is_featured` | `boolean` | NO | 是否头条卡 |
| `created_at` | `timestamp with time zone` | NO | 入库时间 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 617,
    "source": "cls",
    "category": "flash",
    "title": "财联社8月4日电，奥本海默将沃尔玛股票调降至“跑赢大盘”评级。",
    "published_at": "2026-08-04 20:23:05+08:00",
    "is_flash": true,
    "is_featured": false
  },
  {
    "id": 619,
    "source": "cls",
    "category": "flash",
    "title": "财联社8月4日电，沃尔玛公司表示，沃尔玛完成对Vibe.co的收购。",
    "published_at": "2026-08-04 20:17:02+08:00",
    "is_flash": true,
    "is_featured": false
  }
]
```

### `notifications`

**作用：** 站内通知（回复、@、系统等）。

- 主键：`id`
- 当前行数：约 **54**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `user_id` | `bigint` | NO | 接收者 |
| `actor_id` | `bigint` | NO | 触发者 |
| `type` | `text` | NO | 类型（回复 / @ / 系统等） |
| `post_id` | `bigint` | NO | 关联帖 |
| `comment_id` | `bigint` | YES | 关联评论 |
| `created_at` | `timestamp with time zone` | NO | 时间 |
| `read_at` | `timestamp with time zone` | YES | 已读时间 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 1,
    "user_id": 4,
    "actor_id": 5,
    "type": "reply",
    "post_id": 16,
    "read_at": "2026-07-22 14:57:43.271289+08:00",
    "created_at": "2026-07-22 14:57:28.693132+08:00"
  },
  {
    "id": 3,
    "user_id": 5,
    "actor_id": 4,
    "type": "reply",
    "post_id": 16,
    "read_at": "2026-07-22 14:58:29.088373+08:00",
    "created_at": "2026-07-22 14:58:18.865304+08:00"
  }
]
```

### `post_comments`

**作用：** 帖评论与楼中楼回复。

- 主键：`id`
- 当前行数：约 **36**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `post_id` | `bigint` | NO | 所属帖 |
| `author_id` | `bigint` | NO | 评论者 |
| `body` | `text` | NO | 评论正文 |
| `status` | `text` | NO | 状态 |
| `created_at` | `timestamp with time zone` | NO | 时间 |
| `parent_id` | `bigint` | YES | 父评论（楼中楼） |
| `images` | `jsonb` | YES | 图片 JSON |
| `reply_to_comment_id` | `bigint` | YES | 回复目标评论 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 1,
    "post_id": 1,
    "author_id": 1,
    "parent_id": null,
    "created_at": "2026-07-20 18:58:53.017425+08:00"
  },
  {
    "id": 2,
    "post_id": 7,
    "author_id": 4,
    "parent_id": null,
    "created_at": "2026-07-20 19:00:59.050369+08:00"
  }
]
```

### `post_favorites`

**作用：** 用户收藏帖。

- 主键：`user_id`, `post_id`
- 当前行数：约 **5**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `user_id` | `bigint` | NO | 收藏用户 |
| `post_id` | `bigint` | NO | 帖 |
| `created_at` | `timestamp with time zone` | NO | 时间 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "user_id": 4,
    "post_id": 7,
    "created_at": "2026-07-20 19:02:49.827969+08:00"
  },
  {
    "user_id": 5,
    "post_id": 11,
    "created_at": "2026-07-22 13:44:00.035929+08:00"
  }
]
```

### `post_votes`

**作用：** 帖赞/踩（每用户每帖一票）。

- 主键：`user_id`, `post_id`
- 当前行数：约 **9**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `user_id` | `bigint` | NO | 投票用户 |
| `post_id` | `bigint` | NO | 帖 |
| `value` | `smallint` | NO | 1 赞 / -1 踩 |
| `created_at` | `timestamp with time zone` | NO | 时间 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "user_id": 1,
    "post_id": 30,
    "value": 1,
    "created_at": "2026-07-30 10:40:34.142635+08:00"
  },
  {
    "user_id": 1,
    "post_id": 64,
    "value": 1,
    "created_at": "2026-07-30 10:39:07.921225+08:00"
  }
]
```

### `posts`

**作用：** 社区帖（正文 / 代码 / 分区 / 状态 / 置顶）。

- 主键：`id`
- 当前行数：约 **69**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `author_id` | `bigint` | NO | 作者 |
| `section` | `text` | NO | `strategy` / `factor` / `qa` / `hotspot` / `official` |
| `title` | `text` | NO | 标题 |
| `body` | `text` | NO | 正文（Markdown/HTML） |
| `code_snippet` | `text` | YES | 可克隆代码 |
| `view_count` | `integer` | NO | 浏览次数 |
| `status` | `text` | NO | `published` / `draft` / `hidden` 等 |
| `created_at` | `timestamp with time zone` | NO | 创建 |
| `updated_at` | `timestamp with time zone` | NO | 更新 |
| `is_pinned` | `boolean` | NO | 是否置顶 |
| `pinned_at` | `timestamp with time zone` | YES | 置顶时间 |
| `platform_ref` | `jsonb` | YES | 平台引用 JSON（面板指标 / 回测引用，供读帖 TL;DR 校验） |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 20,
    "author_id": 1,
    "section": "hotspot",
    "title": "证监会座谈会释三大信号：稳市场 · 建制度 · 以投资者为本",
    "status": "published",
    "view_count": 0,
    "is_pinned": false,
    "created_at": "2026-07-23 11:43:01.351571+08:00"
  },
  {
    "id": 35,
    "author_id": 4,
    "section": "strategy",
    "title": "真他妈沙比",
    "status": "published",
    "view_count": 5,
    "is_pinned": false,
    "created_at": "2026-07-24 10:27:48.419935+08:00"
  }
]
```

### `re_factor_catalog_snapshot`

**作用：** ResearchEngine 官方因子目录快照（库列表+因子清单 JSON）；页面读此表，不每次打 RE。

- 主键：`scope`
- 当前行数：约 **1**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `scope` | `text` | NO | `primary`（默认十库）或 `all` |
| `content_hash` | `text` | NO | 库+因子清单 SHA256，用于判断 RE 是否有更新 |
| `payload` | `jsonb` | NO | 完整目录 JSON（libraries + factors） |
| `fetched_at` | `timestamp with time zone` | NO | 最近一次从 RE 拉到内容的时间 |
| `fetched_at_unix` | `double precision` | NO | 同上，unix 秒 |
| `factor_count` | `integer` | NO | 因子条数 |
| `library_count` | `integer` | NO | 库个数 |
| `updated_at` | `timestamp with time zone` | NO | 最近检查/写入时间（无变更也会刷新） |

**样例（脱敏 / 截断）：**

```json
[
  {
    "scope": "primary",
    "content_hash": "8745c1093bef5d1dda6505d2f033821c2165266664c72be292799dbae95d62ca",
    "factor_count": 734,
    "library_count": 10,
    "fetched_at": "2026-08-12 14:53:56.752604+08:00",
    "updated_at": "2026-08-12 15:02:14.523718+08:00"
  }
]
```

### `re_factor_catalog_sync_log`

**作用：** 官方因子目录同步日志（定时/手动：有无变更、hash、条数）。

- 主键：`id`
- 当前行数：约 **3**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 自增主键 |
| `scope` | `text` | NO | 同步范围 |
| `changed` | `boolean` | NO | 本次是否写了新快照 |
| `content_hash` | `text` | YES | 当时 hash |
| `factor_count` | `integer` | YES | 因子条数 |
| `message` | `text` | YES | 人读摘要 |
| `created_at` | `timestamp with time zone` | NO | 日志时间 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 1,
    "scope": "primary",
    "changed": true,
    "factor_count": 734,
    "message": "首次写入 734 个因子",
    "created_at": "2026-08-12 14:53:56.976688+08:00"
  },
  {
    "id": 2,
    "scope": "primary",
    "changed": false,
    "factor_count": 734,
    "message": "无变更（hash=8745c1093bef…，734 个）",
    "created_at": "2026-08-12 14:54:03.055837+08:00"
  }
]
```

### `strategy_projects`

**作用：** 策略研究项目配置与归属。

- 主键：`user_id`, `id`
- 当前行数：约 **80**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `text` | NO | 项目 UUID/文本主键（与 user_id 复合） |
| `user_id` | `bigint` | NO | 所有者 |
| `name` | `text` | NO | 项目名 |
| `description` | `text` | NO | 说明 |
| `config` | `jsonb` | NO | 策略配置 JSON |
| `run_count` | `integer` | NO | 历史运行次数 |
| `created_at` | `timestamp with time zone` | NO | 创建 |
| `updated_at` | `timestamp with time zone` | NO | 更新 |
| `is_sample` | `boolean` | NO |  |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": "sample_momentum_20d",
    "user_id": 1,
    "name": "多因子合成 样例",
    "run_count": 0,
    "updated_at": "2026-07-29 14:53:21.322136+08:00"
  },
  {
    "id": "8af672d6-26fd-4aba-9c2b-60d18a71eec5",
    "user_id": 4,
    "name": "2",
    "run_count": 5,
    "updated_at": "2026-07-24 16:42:32.766831+08:00"
  }
]
```

### `strategy_runs`

**作用：** 策略回测一次运行结果摘要 / 状态。

- 主键：`user_id`, `id`
- 当前行数：约 **74**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `text` | NO | 运行 UUID/文本主键（与 user_id 复合） |
| `user_id` | `bigint` | NO | 所有者 |
| `project_id` | `text` | NO | 所属项目 id |
| `name` | `text` | NO | 运行名 / 策略名 |
| `description` | `text` | NO | 说明 |
| `request` | `jsonb` | NO | 请求参数 JSON |
| `result` | `jsonb` | NO | 结果摘要 JSON |
| `finished_at` | `timestamp with time zone` | NO | 结束时间 |
| `elapsed_sec` | `double precision` | NO | 耗时秒 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": "80091ed8-3ac2-419a-910e-64176cb2df21",
    "user_id": 4,
    "project_id": "16ae0be4-49f9-4265-8b98-9a075b1292bd",
    "name": "test",
    "finished_at": "2026-07-22 17:11:10.704535+08:00",
    "elapsed_sec": 2.0
  },
  {
    "id": "a6152768-3a07-4962-8ed3-f8e9560a75c8",
    "user_id": 4,
    "project_id": "88b8f5f2-bb2c-4121-bc82-56d55c256b49",
    "name": "wa",
    "finished_at": "2026-07-22 17:48:20.905557+08:00",
    "elapsed_sec": 2.0
  }
]
```

### `user_custom_factors`

**作用：** 用户自定义因子元数据（`.py` 另存磁盘；本表记归属与可见性）。

- 主键：`id`
- 当前行数：约 **0**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `user_id` | `bigint` | NO | 所有者 |
| `name` | `text` | NO | 因子标识名 |
| `method_name` | `text` | NO | Python 方法名 `def xxx(self)` |
| `body` | `text` | NO | 因子代码正文 |
| `description` | `text` | NO | 说明 |
| `created_at` | `timestamp with time zone` | NO | 创建 |
| `updated_at` | `timestamp with time zone` | NO | 更新 |

### `user_factor_libraries`

**作用：** 用户自建因子库（文件夹）；与内置库同级，按 user 隔离。

- 主键：`id`
- 当前行数：约 **7**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `user_id` | `bigint` | NO | 所有者 |
| `name` | `text` | NO | 库名（同用户唯一） |
| `created_at` | `timestamp with time zone` | NO | 创建 |
| `updated_at` | `timestamp with time zone` | NO | 更新 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 1,
    "user_id": 5,
    "name": "Test",
    "updated_at": "2026-07-29 18:29:04.218170+08:00"
  },
  {
    "id": 2,
    "user_id": 5,
    "name": "A",
    "updated_at": "2026-07-31 09:48:01.304364+08:00"
  }
]
```

### `user_follows`

**作用：** 用户关注关系（关注者 → 被关注者）。

- 主键：`follower_id`, `following_id`
- 当前行数：约 **5**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `follower_id` | `bigint` | NO | 关注者 `users.id` |
| `following_id` | `bigint` | NO | 被关注者 `users.id` |
| `created_at` | `timestamp with time zone` | NO | 关注时间 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "follower_id": 4,
    "following_id": 5,
    "created_at": "2026-07-27 16:07:53.443186+08:00"
  },
  {
    "follower_id": 5,
    "following_id": 4,
    "created_at": "2026-07-27 16:09:35.047406+08:00"
  }
]
```

### `user_library_factors`

**作用：** 用户因子库内的因子条目（含代码正文、分类、说明）。

- 主键：`id`
- 当前行数：约 **13**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `library_id` | `bigint` | NO | 所属 `user_factor_libraries.id` |
| `user_id` | `bigint` | NO | 所有者（冗余，便于按用户唯一名） |
| `name` | `text` | NO | 因子标识名（同用户唯一） |
| `method_name` | `text` | NO | Python 方法名 |
| `body` | `text` | NO | 因子源码 |
| `description` | `text` | NO | 中文说明 |
| `category_label` | `text` | NO | 分类标签 |
| `created_at` | `timestamp with time zone` | NO | 创建 |
| `updated_at` | `timestamp with time zone` | NO | 更新 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 1,
    "user_id": 5,
    "library_id": 2,
    "name": "mom_7d",
    "category_label": "动量/趋势",
    "updated_at": "2026-07-29 18:58:22.116226+08:00"
  },
  {
    "id": 2,
    "user_id": 5,
    "library_id": 2,
    "name": "realized_vol_20d",
    "category_label": "波动/风险",
    "updated_at": "2026-07-30 09:05:17.776041+08:00"
  }
]
```

### `user_library_strategies`

**作用：** 用户策略库内入库快照（含策略说明、回测归档 JSON；与研究侧 run 脱钩）。

- 主键：`id`
- 当前行数：约 **3**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `library_id` | `bigint` | NO | 所属 `user_strategy_libraries.id` |
| `user_id` | `bigint` | NO | 所有者 |
| `name` | `text` | NO | 策略名（同用户唯一） |
| `code_id` | `text` | NO | 关联代码标识（若有） |
| `body` | `text` | NO | 策略源码快照 |
| `description` | `text` | NO | 策略说明（入库时填写，列表副标题） |
| `category_label` | `text` | NO | 分类标签 |
| `created_at` | `timestamp with time zone` | NO | 创建 |
| `updated_at` | `timestamp with time zone` | NO | 更新 |
| `source_run_id` | `text` | NO | 来源研究 run id（仅溯源，不随研究侧变更） |
| `archive_request` | `jsonb` | YES | 入库时回测请求快照 JSON |
| `archive_result` | `jsonb` | YES | 入库时回测结果快照 JSON |
| `archive_elapsed_sec` | `double precision` | YES | 入库快照耗时秒 |
| `archive_finished_at` | `timestamp with time zone` | YES | 入库快照完成时间 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 8,
    "user_id": 5,
    "library_id": 5,
    "name": "唐奇安",
    "description": "1年回测",
    "source_run_id": "745f28a6-0ca2-4a4a-9a63-d12e456d3b21",
    "archive_finished_at": "2026-07-30 17:29:19.006383+08:00"
  },
  {
    "id": 9,
    "user_id": 5,
    "library_id": 5,
    "name": "LowVol20",
    "description": "稳定策略",
    "source_run_id": "7569b165-aaee-434a-b006-cc577132f5a2",
    "archive_finished_at": "2026-07-31 15:33:13.183918+08:00"
  }
]
```

### `user_strategy_libraries`

**作用：** 用户自建策略库（文件夹）；与内置库同级，按 user 隔离。

- 主键：`id`
- 当前行数：约 **5**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `user_id` | `bigint` | NO | 所有者 |
| `name` | `text` | NO | 库名（同用户唯一） |
| `created_at` | `timestamp with time zone` | NO | 创建 |
| `updated_at` | `timestamp with time zone` | NO | 更新 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 4,
    "user_id": 1,
    "name": "AA",
    "updated_at": "2026-07-30 12:28:56.456727+08:00"
  },
  {
    "id": 3,
    "user_id": 4,
    "name": "演示库",
    "updated_at": "2026-07-30 17:51:10.395436+08:00"
  }
]
```

### `user_watchlist_symbols`

**作用：** 自选组合内标的（symbol + 名称快照）；归属某 watchlist。

- 主键：`id`
- 当前行数：约 **41**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO |  |
| `watchlist_id` | `bigint` | NO |  |
| `user_id` | `bigint` | NO |  |
| `symbol` | `text` | NO |  |
| `name` | `text` | NO |  |
| `created_at` | `timestamp with time zone` | NO |  |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 1,
    "watchlist_id": 1,
    "user_id": 5,
    "symbol": "600001.SH",
    "name": "邯郸钢铁",
    "created_at": "2026-07-31 15:57:19.046989+08:00"
  },
  {
    "id": 2,
    "watchlist_id": 1,
    "user_id": 5,
    "symbol": "600002.SH",
    "name": "齐鲁石化",
    "created_at": "2026-07-31 15:57:24.008089+08:00"
  }
]
```

### `user_watchlists`

**作用：** 用户自选股组合（文件夹）；按 user 隔离，前端 `/data/watchlist`。

- 主键：`id`
- 当前行数：约 **6**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO |  |
| `user_id` | `bigint` | NO |  |
| `name` | `text` | NO |  |
| `created_at` | `timestamp with time zone` | NO |  |
| `updated_at` | `timestamp with time zone` | NO |  |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 3,
    "user_id": 5,
    "name": "11",
    "created_at": "2026-07-31 15:58:01.405674+08:00",
    "updated_at": "2026-07-31 15:58:01.405674+08:00"
  },
  {
    "id": 5,
    "user_id": 1,
    "name": "11",
    "created_at": "2026-07-31 16:08:30.309083+08:00",
    "updated_at": "2026-07-31 16:08:50.895115+08:00"
  }
]
```

### `users`

**作用：** 账号与资料：登录、角色、AI 日配额、公开主页头像/封面/简介。

- 主键：`id`
- 当前行数：约 **9**

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | `bigint` | NO | 主键 |
| `username` | `text` | NO | 登录名；公开主页 `/u/{username}` |
| `email` | `text` | YES | 邮箱（可空） |
| `password_hash` | `text` | NO | 密码哈希（禁止明文） |
| `role` | `text` | NO | `user` / `admin` |
| `status` | `text` | NO | `active` / `disabled` |
| `display_name` | `text` | YES | 展示昵称 |
| `ai_quota_daily` | `integer` | NO | 每日 Agent 调用上限（按次，非按 token） |
| `created_at` | `timestamp with time zone` | NO | 注册时间 |
| `updated_at` | `timestamp with time zone` | NO | 资料更新 |
| `avatar_url` | `text` | YES | 头像 URL / dataURL |
| `cover_url` | `text` | YES | 主页封面 |
| `headline` | `text` | YES | 一句话简介 |
| `bio` | `text` | YES | 关于我 |

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 2,
    "username": "smoke_user_1784571206",
    "display_name": "smoke_user_1784571206",
    "role": "user",
    "status": "active",
    "ai_quota_daily": 200,
    "created_at": "2026-07-20 18:13:26.563906+08:00"
  },
  {
    "id": 6,
    "username": "zwb",
    "display_name": "zwb",
    "role": "user",
    "status": "active",
    "ai_quota_daily": 200,
    "created_at": "2026-07-21 19:02:56.349391+08:00"
  }
]
```

---

## B. SQLite · 因子面板

路径：`E:/quant-lab/SV/SVQuant/WebApp/backend/output/factor_dashboard/metrics.sqlite`

**注意：** 仅面板**指标缓存**，无日线/分钟行情。行情在 YGQuant / bars-only；SVQuant 本机不落 bars。

### `factor_dashboard_metrics`

**作用：** 因子面板指标缓存（因子×池×周期×过滤规则）；RE 算完写入，非行情库。

- 当前行数：约 **15912**
- 主键：`(factor_name, universe, period, filter_limit_up, filter_suspended, rules_version)`

| 字段 | 类型 | NOT NULL | 说明 |
|------|------|----------|------|
| `factor_name` | `TEXT` | YES | 因子名 |
| `universe` | `TEXT` | YES | 股票池，如 CSI300 |
| `period` | `TEXT` | YES | 周期，如 3y |
| `filter_limit_up` | `INTEGER` | YES | 过滤涨停 0/1 |
| `filter_suspended` | `INTEGER` | YES | 过滤停牌 0/1 |
| `rules_version` | `TEXT` | YES | 口径版本 |
| `name_cn` | `TEXT` |  | 中文名 |
| `library` | `TEXT` |  | 所属库 |
| `ic_mean` | `REAL` |  | IC 均值 |
| `ic_std` | `REAL` |  | IC 标准差 |
| `ir` | `REAL` |  | 信息比率 |
| `q1_return` | `REAL` |  | Q1 收益 |
| `q5_return` | `REAL` |  | Q5 收益 |
| `long_short_spread` | `REAL` |  | 多空差 |
| `q1_turnover` | `REAL` |  | Q1 换手 |
| `q5_turnover` | `REAL` |  | Q5 换手 |
| `coverage_pool` | `REAL` |  | 池内覆盖率 |
| `coverage_total` | `REAL` |  | 总覆盖率 |
| `sharpe` | `REAL` |  | 夏普 |
| `annual_return` | `REAL` |  | 年化 |
| `max_drawdown` | `REAL` |  | 最大回撤 |
| `error` | `TEXT` |  | 失败原因；成功为空 |
| `computed_at` | `TEXT` | YES | 写入时间 |
| `rank_ic` | `REAL` |  | Rank IC |
| `win_rate` | `REAL` |  | 胜率 |
| `volatility` | `REAL` |  | 波动 |

**样例：**

```json
[
  {
    "factor_name": "momentum_5d",
    "universe": "CSI300",
    "period": "3y",
    "library": "momentum_lib",
    "ic_mean": 0.4313,
    "sharpe": -0.11810528636291907,
    "error": null,
    "computed_at": "2026-07-24T12:24:09.328588+00:00"
  },
  {
    "factor_name": "momentum_10d",
    "universe": "CSI300",
    "period": "3y",
    "library": "momentum_lib",
    "ic_mean": 0.6246,
    "sharpe": 0.04953668463786644,
    "error": null,
    "computed_at": "2026-07-24T12:24:15.112907+00:00"
  }
]
```

### `factor_verify_status`

**作用：** 因子跨平台对比校验状态（按因子名：pending/passed/failed），与指标行解耦。

- 当前行数：约 **2**
- 主键：`factor_name`

| 字段 | 类型 | NOT NULL | 说明 |
|------|------|----------|------|
| `factor_name` | `TEXT` |  | 因子名（主键） |
| `status` | `TEXT` | YES | `pending` 待验证 / `passed` 已通过 / `failed` 未通过 |
| `note` | `TEXT` | YES | 备注（可选） |
| `updated_at` | `TEXT` | YES | 最近更新时间 |
| `updated_by` | `TEXT` | YES | 更新人用户名 |

**样例：**

```json
[
  {
    "factor_name": "momentum_5d",
    "status": "pending",
    "note": "",
    "updated_at": "2026-07-28T10:36:27+08:00",
    "updated_by": "smoke"
  },
  {
    "factor_name": "earnings_yield",
    "status": "failed",
    "note": "",
    "updated_at": "2026-07-28T10:44:35+08:00",
    "updated_by": "admin"
  }
]
```

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-08-12 | 刷新行数/样例；`news_items` 说明补研报·政策（em_research/em_policy→source=eastmoney）；Postgres **33** 表 + SQLite **2** 表 |
| 2026-08-05 | 刷新：补全用户因子/策略库 4 表 + `user_library_strategies` 入库快照列；`posts.platform_ref`；注明 AI 生成历史暂未落库 |
| 2026-07-30 | 策略库入库快照列：`source_run_id` / `archive_*`；策略说明 `description` |
| 2026-07-28 | 初版：Postgres + 面板 SQLite；含 `factor_verify_status` / `post_votes` |
