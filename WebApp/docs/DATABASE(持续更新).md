# SVQuant 数据库说明

> **最后刷新：** 2026-07-28 10:37
> **边界：** SVQuant **不存行情 bars**；因子面板指标在本机 SQLite；账号 / 社区 / 检测 / 策略在 PostgreSQL。

---

## 总览

| 库 | 引擎 | 连接 / 路径 | 表数量 | 用途 |
|----|------|-------------|--------|------|
| **主库** | PostgreSQL | `.env` → `DATABASE_URL`（`svquant`） | **14** | 用户、社区、Agent 用量、检测/策略 |
| **因子面板缓存** | SQLite | `backend/output/factor_dashboard/metrics.sqlite` | **2** | 面板 IC/夏普等 + 跨平台校验状态 |

### PostgreSQL 表一览

| 表名 | 约行数 | 作用（一句话） |
|------|--------|----------------|
| `ai_usage` | 102 | Agent 调用流水（按 skill 一行）；日配额按当日行数计。 |
| `comment_votes` | 5 | 评论赞/踩（每用户每评论一票）。 |
| `community_reports` | 6 | 举报帖/评论；管理仓处理队列。 |
| `detect_projects` | 79 | 因子检测项目配置与归属。 |
| `detect_runs` | 111 | 因子检测一次运行结果摘要 / 状态。 |
| `notifications` | 26 | 站内通知（回复、@、系统等）。 |
| `post_comments` | 34 | 帖评论与楼中楼回复。 |
| `post_favorites` | 5 | 用户收藏帖。 |
| `posts` | 53 | 社区帖（正文 / 代码 / 分区 / 状态 / 置顶）。 |
| `strategy_projects` | 17 | 策略研究项目配置与归属。 |
| `strategy_runs` | 20 | 策略回测一次运行结果摘要 / 状态。 |
| `user_custom_factors` | 14 | 用户自定义因子元数据（`.py` 另存磁盘；本表记归属与可见性）。 |
| `user_follows` | 3 | 用户关注关系（关注者 → 被关注者）。 |
| `users` | 6 | 账号与资料：登录、角色、AI 日配额、公开主页头像/封面/简介。 |

### SQLite 表一览

| 表名 | 约行数 | 作用（一句话） |
|------|--------|----------------|
| `factor_dashboard_metrics` | 15912 | 因子面板指标缓存（因子×池×周期×过滤规则）；RE 算完写入，非行情库。 |
| `factor_verify_status` | 1 | 因子跨平台对比校验状态（按因子名：pending/passed/failed），与指标行解耦。 |

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
- 建表：`auth_store` / `profile_store` / `community_store` / `agent_store` / `detect_store` / `strategy_store` / `user_factor_store`
- 面板：`services/dashboard_store.py`

---

## A. PostgreSQL 表详解

### `ai_usage`

**作用：** Agent 调用流水（按 skill 一行）；日配额按当日行数计。

- 主键：`id`
- 当前行数：约 **102**

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
- 当前行数：约 **5**

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
- 当前行数：约 **79**

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
- 当前行数：约 **111**

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

### `notifications`

**作用：** 站内通知（回复、@、系统等）。

- 主键：`id`
- 当前行数：约 **26**

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
- 当前行数：约 **34**

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

### `posts`

**作用：** 社区帖（正文 / 代码 / 分区 / 状态 / 置顶）。

- 主键：`id`
- 当前行数：约 **53**

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
    "id": 23,
    "author_id": 1,
    "section": "hotspot",
    "title": "两融降温超 2500 亿：杠杆回落，交易结构在变健康？",
    "status": "published",
    "view_count": 1,
    "is_pinned": false,
    "created_at": "2026-07-23 11:43:01.635413+08:00"
  }
]
```

### `strategy_projects`

**作用：** 策略研究项目配置与归属。

- 主键：`user_id`, `id`
- 当前行数：约 **17**

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

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": "8af672d6-26fd-4aba-9c2b-60d18a71eec5",
    "user_id": 4,
    "name": "2",
    "run_count": 5,
    "updated_at": "2026-07-24 16:42:32.766831+08:00"
  },
  {
    "id": "88b8f5f2-bb2c-4121-bc82-56d55c256b49",
    "user_id": 4,
    "name": "wa",
    "run_count": 2,
    "updated_at": "2026-07-22 17:52:37.935992+08:00"
  }
]
```

### `strategy_runs`

**作用：** 策略回测一次运行结果摘要 / 状态。

- 主键：`user_id`, `id`
- 当前行数：约 **20**

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
- 当前行数：约 **14**

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

**样例（脱敏 / 截断）：**

```json
[
  {
    "id": 1,
    "user_id": 1,
    "name": "EDIT_BEFORE",
    "method_name": "u1_EDIT_BEFORE",
    "created_at": "2026-07-21 10:24:35.222971+08:00"
  },
  {
    "id": 2,
    "user_id": 3,
    "name": "RISK_ADJ_MOM_20",
    "method_name": "u3_RISK_ADJ_MOM_20",
    "created_at": "2026-07-21 16:18:12.313811+08:00"
  }
]
```

### `user_follows`

**作用：** 用户关注关系（关注者 → 被关注者）。

- 主键：`follower_id`, `following_id`
- 当前行数：约 **3**

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

### `users`

**作用：** 账号与资料：登录、角色、AI 日配额、公开主页头像/封面/简介。

- 主键：`id`
- 当前行数：约 **6**

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
    "id": 3,
    "username": "maruixiang",
    "display_name": "maruixiang",
    "role": "user",
    "status": "active",
    "ai_quota_daily": 200,
    "created_at": "2026-07-20 18:20:23.457146+08:00"
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

- 当前行数：约 **1**
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
  }
]
```

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-28 | 初版 / 刷新：Postgres 14 表 + 面板 SQLite 2 表；含字段与脱敏样例 |
