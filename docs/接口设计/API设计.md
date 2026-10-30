# SVQuant API 设计

> 文档版本：v2.0（2026-09-23）。全量接口总览 + 核心接口详细定义。
> 接口清单来自对 `backend/app/routers/*.py` 与 `KnowledgeHub/backend/knowledge_hub/` 的路由声明扫描（156 处 `@router` 声明，155 个端点函数）；未展开接口以运行时 OpenAPI 为准。
> 关联文档：[PRD](../产品与需求/PRD.md)、[系统架构](../架构与技术/系统架构.md)、[数据库设计](../数据设计/数据库设计.md)、[因子面板-RE接口契约](RE契约/因子面板-RE接口契约.md)、[模块详细设计](../模块设计/SVQuant产品层/模块设计.md)。

---

## 1. API 约定

### 1.1 Base URL 与运行入口

| 项 | 值 |
|---|---|
| Base URL | `/api` |
| 本地开发地址 | `http://127.0.0.1:8766`（SVQuant 后端 FastAPI，`backend/app/main.py`） |
| OpenAPI（SVQuant） | `GET /openapi.json`、`GET /docs`（FastAPI 默认挂载） |
| KnowledgeHub OpenAPI | `GET /api/kh/openapi.json`、`GET /api/kh/docs`（Swagger 页，spec 由 `openapi_docs.py` 手工维护） |
| 前端地址（参考） | `:9530`；ResearchEngine 计算服务 `:9527`（前端不得直连，见 §7） |

### 1.2 请求格式

- `Content-Type: application/json`（绝大多数接口 body 为 `dict[str, Any]` 手工解析，非 Pydantic 模型）。
- 例外：`POST /api/ai/speech/transcribe` 传 JSON 内嵌 `audio_base64`（非 multipart）；文件上传能力以运行时 OpenAPI 为准。

### 1.3 认证方式（当前实现）

- `Authorization: Bearer <JWT>`；JWT 由 `POST /api/auth/login` / `register` 返回（`token` 字段），HS256，密钥 `JWT_SECRET_KEY`，有效期 `JWT_EXPIRE_DAYS`（默认 7 天）。`JWT_SECRET_KEY` 必须由环境变量提供，缺失或弱值会导致后端启动失败。
- 依赖分级（`backend/app/deps.py`）：

| 依赖 | 语义 | 未登录行为 |
|---|---|---|
| （无依赖） | 完全公开 | 放行 |
| `optional_user` | 尽力解析用户 | 放行，user=None |
| `soft_db_user_id` | 解析失败返回 None，接口返回空集 | 放行（空结果） |
| `require_user` / `require_db_user_id` | 必须登录且映射到数据库用户 | 401 |
| `require_admin` | 必须登录且 `role=admin` | 401（未登录）/ 403（非管理员） |

- 开发后门：`DEV_SKIP_AUTH` 开启时视为 id=0 的 admin 用户（仅开发环境）。
- JWT **无状态**：服务端不存 token 表；登出即前端丢弃，无服务端吊销（待确认）。

### 1.4 响应格式

- **当前没有统一响应 envelope**。多数接口返回业务对象；相当一部分带 `{"ok": true, ...}` 外层（watchlists / factor libraries / news dict 等），管理端点多为裸对象或 `{...统计}`。
- **实际以各路由实现与运行时 OpenAPI 为准**；本文响应示例为示意，不承诺字段全集。
- 是否引入统一 envelope 见 §12 待确认。

### 1.5 错误返回格式

- 没有统一业务错误码。三种形态并存：
  1. FastAPI `HTTPException` → `{"detail": "<中文/英文文案>"}`（绝大多数路由）；
  2. `app/errors.py` 统一处理器安装（`install_exception_handlers`）兜底；
  3. 个别 BFF 返回 `{"error": "<文案>"}` + 对应状态码（factor re-catalog、re 网关转发、market-data/daily）。
- 典型映射约定（路由层实现）：`ValueError → 400`、`KeyError → 404`、`PermissionError → 401/403`（含"配额"文案 → 403，KH 侧 → 401）、RE/外部服务不可达 → 502。

---

## 2. 状态码

| Code | 含义 | 典型场景（当前代码） |
|---|---|---|
| 200 | 成功 | 绝大多数查询与写操作（当前项目未显式返回 201，创建类也返回 200） |
| 201 | 创建成功 | **当前未使用**（预留；创建资源现状一律 200） |
| 400 | 参数错误 | `ValueError`（用户名不合法、板块非法、`missing remark`、`invalid JSON`、`unsupported sources`、试算失败等） |
| 401 | 未认证 | 未带/无效 Bearer token（require 类依赖）；登录失败（`/api/auth/login` 用 401 而非 400）；KH 匿名且 `KH_REQUIRE_AUTH=1`；KH 路由 `PermissionError` 映射 401 |
| 403 | 无权限 | 非 admin 调管理员端点（`require_admin`→403；社区管理端点 store 内 role 校验→403）；AI 配额不足（文案含"配额"→403）；非资源所有者（run job forbidden→403、自选股越权） |
| 404 | 资源不存在 | `KeyError`（帖子/项目/run/用户不存在）；factor 回测 job `missing`；路径前缀探测（`/api/users/{username}` 含 `/`） |
| 409 | 状态冲突或重复 | **当前未显式使用**——重复资源（如用户名已存在、重复收藏唯一键）现状以 400 返回；是否引入 409 见待确认 |
| 422 | 请求体验证失败 | FastAPI 自动校验（query/path 类型不匹配，如 `limit=abc`）；手工解析 body 的接口不产生 422 |
| 500 | 系统错误 | 未捕获异常兜底；面板刷新失败（`/api/factor/dashboard/refresh` 显式 500） |
| 502 | 外部服务不可用 | ResearchEngine 不可达/超时（`URLError → 502`，re 网关与 factor BFF）；LLM/方舟调用失败；目录同步结果为空 |
| 503 | 服务未配置 | AI/语音"未配置"密钥（文案含"未配置"→503） |

---

## 3. 全量接口总览

> 扫描命令：`rg -n "@router\.(get|post|put|delete|patch)\(" backend/app/routers KnowledgeHub/backend`
> 结果：**158 处声明 / 157 个端点**（`/api/kh/docs` 一个函数挂两个路径）。下表覆盖全部端点；`详细`列标注本文展开的 37 个核心接口，其余以运行时 OpenAPI 为准。

### 3.1 健康检查（health.py，1 个）

| 方法 | 路径 | 功能 | 权限 | 管理员 | 副作用 | 详细 |
|---|---|---|---|---|---|---|
| GET | `/api/health` | SVQuant 后端健康检查 | 匿名 | — | 无 | ✅ |

### 3.2 用户与权限（auth.py，10 个）

| 方法 | 路径 | 功能 | 权限 | 管理员 | 副作用 | 详细 |
|---|---|---|---|---|---|---|
| POST | `/api/auth/register` | 注册（写审计） | 匿名 | — | ✓ | ✅ |
| POST | `/api/auth/login` | 登录（写审计） | 匿名 | — | 无（写审计日志） | ✅ |
| GET | `/api/auth/me` | 当前用户信息 | Bearer | — | 无 | ✅ |
| POST | `/api/profile/me` | 更新个人资料 | 登录 | — | ✓ | ✅ |
| GET | `/api/users/{username}` | 公开主页（关注数/粉丝数/帖子数） | optional_user | — | 无 | — |
| GET | `/api/users/{username}/posts` | 用户公开帖子列表 | 匿名 | — | 无 | — |
| GET | `/api/users/{username}/following` | 关注列表 | optional_user | — | 无 | — |
| GET | `/api/users/{username}/followers` | 粉丝列表 | optional_user | — | 无 | — |
| POST | `/api/users/{username}/follow` | 关注 | 登录 | — | ✓ | — |
| DELETE | `/api/users/{username}/follow` | 取消关注 | 登录 | — | ✓ | — |

### 3.2b 机构端（inst.py，2 个）

| 方法 | 路径 | 功能 | 权限 | 管理员 | 副作用 | 详细 |
|---|---|---|---|---|---|---|
| POST | `/api/inst/auth/login` | 机构端登录：校验账号密码 + 机构成员身份，签发 `scope=inst` 令牌 | 匿名（限流 10 次/分/IP） | — | 写审计 | — |
| GET | `/api/inst/me` | 机构会话：用户、机构、角色、九工作区权限 | 机构令牌（`scope=inst`） | — | 无 | — |

> 机构令牌与个人版令牌互不通用：个人版令牌访问 `/api/inst/*` 返回 401；机构令牌也不能替代个人版会话。权限矩阵见实现 `backend/services/institution/inst_store.py`，以服务端为准。

### 3.3 自选股（watchlists.py，8 个）

| 方法 | 路径 | 功能 | 权限 | 管理员 | 副作用 | 详细 |
|---|---|---|---|---|---|---|
| GET | `/api/watchlists` | 我的分组列表（匿名返回空集） | soft_db_user_id | — | 无 | ✅ |
| POST | `/api/watchlists` | 创建分组 | 登录 | — | ✓ | ✅ |
| GET | `/api/watchlists/{wl_id}/symbols` | 组内标的 | 登录+归属 | — | 无 | — |
| POST | `/api/watchlists/{wl_id}/symbols` | 添加标的 | 登录+归属 | — | ✓ | — |
| POST | `/api/watchlists/{wl_id}/symbols/batch` | 批量添加 | 登录+归属 | — | ✓ | — |
| PUT | `/api/watchlists/{wl_id}` | 重命名分组 | 登录+归属 | — | ✓ | — |
| DELETE | `/api/watchlists/{wl_id}/symbols/{symbol}` | 移除标的 | 登录+归属 | — | ✓ | — |
| DELETE | `/api/watchlists/{wl_id}` | 删除分组 | 登录+归属 | — | ✓ | — |

### 3.4 因子研究（factor.py，26 个）

| 方法 | 路径 | 功能 | 权限 | 管理员 | 副作用 | 详细 |
|---|---|---|---|---|---|---|
| GET | `/api/factor/index` | 因子索引 YAML（内置+按用户过滤） | optional_user | — | 无 | — |
| GET | `/api/factor/re-catalog` | RE 官方因子目录（读快照；`fresh=1` 强制拉取） | 匿名 | — | fresh=1 时刷新缓存 | ✅ |
| POST | `/api/factor/re-catalog/sync` | 管理员同步目录快照 | 登录 | ✓ | ✓ | ✅ |
| POST | `/api/factor/re-backtest` | 提交因子回测任务（本站排队） | 登录 | — | ✓ | ✅ |
| GET | `/api/factor/re-backtest/{job_id}` | 轮询任务状态/结果 | 登录+归属 | — | 无 | ✅ |
| DELETE | `/api/factor/re-backtest/{job_id}` | 取消任务 | 登录+归属 | — | ✓ | — |
| POST | `/api/backtest/factor` | RE 异步因子回测薄转发（方案 A） | 登录 | — | ✓（RE 侧） | — |
| GET | `/api/backtest/factor/{run_id}` | RE 因子 run 轮询薄转发 | 登录 | — | 无 | — |
| DELETE | `/api/backtest/factor/{run_id}` | RE 因子 run 取消薄转发 | 登录 | — | ✓（RE 侧） | — |
| GET | `/api/factor/libraries` | 我的因子库列表 | soft_db_user_id | — | 无 | — |
| POST | `/api/factor/libraries` | 创建因子库 | 登录 | — | ✓ | — |
| DELETE | `/api/factor/libraries/{lib_id}` | 删除因子库 | 登录+归属 | — | ✓ | — |
| GET | `/api/factor/libraries/factors` | 全部库因子扁平列表 | soft_db_user_id | — | 无 | — |
| GET | `/api/factor/libraries/{lib_id}/factors` | 库内因子 | 登录+归属 | — | 无 | — |
| POST | `/api/factor/libraries/{lib_id}/factors` | 新增库内因子 | 登录+归属 | — | ✓ | — |
| PUT | `/api/factor/libraries/{lib_id}/factors/{factor_id}` | 更新库内因子 | 登录+归属 | — | ✓ | — |
| DELETE | `/api/factor/libraries/{lib_id}/factors/{factor_id}` | 删除库内因子 | 登录+归属 | — | ✓ | — |
| GET | `/api/factor/file/{name:path}` | 因子文件源码（含 custom_lib.py） | soft_db_user_id | — | 无 | — |
| GET | `/api/factor/dashboard` | 因子面板指标查询 | 匿名 | — | 无 | — |
| GET | `/api/factor/dashboard/status` | 面板批任务进度 | 匿名 | — | 无 | — |
| POST | `/api/factor/dashboard/refresh` | 触发面板刷新批任务 | **匿名**（待确认） | — | ✓ | — |
| POST | `/api/factor/dashboard/verify` | 设置校验状态 | 登录 | ✓ | ✓ | — |
| POST | `/api/factor/custom` | 新增自定义因子 | 登录 | — | ✓ | ✅ |
| PUT | `/api/factor/custom/{name}` | 更新自定义因子 | 登录+归属 | — | ✓ | — |
| DELETE | `/api/factor/custom/{name}` | 删除自定义因子 | 登录+归属 | — | ✓ | — |
| POST | `/api/factor/custom/trial` | 因子试算（经 RE） | 登录 | — | 无（RE 计算缓存） | ✅ |

### 3.5 因子检测（detect.py，11 个，全部登录+归属）

| 方法 | 路径 | 功能 | 副作用 | 详细 |
|---|---|---|---|---|
| GET | `/api/detect/projects` | 项目列表（`visible=1` 仅可见） | 无 | ✅ |
| POST | `/api/detect/projects` | 创建/更新项目（含 upsert 语义） | ✓ | ✅ |
| GET | `/api/detect/projects/{project_id}` | 项目详情 | 无 | — |
| PUT | `/api/detect/projects/{project_id}` | 更新项目 | ✓ | — |
| DELETE | `/api/detect/projects/{project_id}` | 删除项目（级联 runs） | ✓ | — |
| GET | `/api/detect/projects/{project_id}/runs` | 项目内运行 | 无 | — |
| POST | `/api/detect/runs` | 保存运行记录 | ✓ | ✅ |
| GET | `/api/detect/runs` | 全部运行（检测报告） | 无 | — |
| GET | `/api/detect/runs/{run_id}` | 运行详情 | 无 | — |
| PATCH | `/api/detect/runs/{run_id}` | 备注/标记 | ✓ | — |
| DELETE | `/api/detect/runs/{run_id}` | 删除运行 | ✓ | — |

### 3.6 策略研究（strategy.py，26 个）

| 方法 | 路径 | 功能 | 权限 | 管理员 | 副作用 | 详细 |
|---|---|---|---|---|---|---|
| GET | `/api/strategy/projects` | 策略项目列表 | 登录 | — | 无 | ✅ |
| POST | `/api/strategy/projects` | 创建/更新项目 | 登录 | — | ✓ | ✅ |
| GET | `/api/strategy/projects/{project_id}` | 项目详情 | 登录+归属 | — | 无 | — |
| PUT | `/api/strategy/projects/{project_id}` | 更新项目 | 登录+归属 | — | ✓ | — |
| DELETE | `/api/strategy/projects/{project_id}` | 删除项目 | 登录+归属 | — | ✓ | — |
| GET | `/api/strategy/projects/{project_id}/runs` | 项目内运行 | 登录+归属 | — | 无 | — |
| POST | `/api/strategy/runs` | 保存运行记录（摘要+blob） | 登录 | — | ✓ | ✅ |
| GET | `/api/strategy/runs` | 全部运行（回测报告） | 登录 | — | 无 | — |
| GET | `/api/strategy/runs/{run_id}` | 运行详情（blob 还原） | 登录+归属 | — | 无 | — |
| PATCH | `/api/strategy/runs/{run_id}` | 备注/标记 | 登录+归属 | — | ✓ | — |
| DELETE | `/api/strategy/runs/{run_id}` | 删除运行（含 blob） | 登录+归属 | — | ✓ | — |
| GET | `/api/strategy/library` | 内置策略目录镜像 | 登录 | — | 无 | ✅ |
| POST | `/api/strategy/library/sync` | 管理员从 RE 同步镜像 | 登录 | ✓ | ✓ | ✅ |
| GET | `/api/strategy/library/{strategy_id}` | 内置策略详情/源码快照 | 登录 | — | 无 | — |
| GET | `/api/strategy/libraries` | 用户策略库列表 | 登录 | — | 无 | — |
| POST | `/api/strategy/libraries` | 创建策略库 | 登录 | — | ✓ | — |
| DELETE | `/api/strategy/libraries/{lib_id}` | 删除策略库 | 登录+归属 | — | ✓ | — |
| GET | `/api/strategy/libraries/{lib_id}/strategies` | 库内策略 | 登录+归属 | — | 无 | — |
| POST | `/api/strategy/libraries/{lib_id}/strategies` | 入库策略快照 | 登录+归属 | — | ✓ | — |
| DELETE | `/api/strategy/libraries/{lib_id}/strategies/{strategy_id}` | 移除库内策略 | 登录+归属 | — | ✓ | — |
| POST | `/api/strategy/library-strategies/{strategy_id}/mark-detected` | 标记已检测 | 登录+归属 | — | ✓ | — |
| GET | `/api/strategy/library-strategies/{strategy_id}/archive` | 查看归档快照 | 登录+归属 | — | 无 | — |
| GET | `/api/strategy/plaza` | 策略广场列表 | **匿名** | — | 无 | ✅ |
| GET | `/api/strategy/plaza/{item_id}` | 广场详情（`bump=1` 计浏览） | **匿名** | — | bump=1 时 ✓ | — |
| POST | `/api/strategy/plaza` | 发布广场条目 | 登录 | — | ✓ | — |
| DELETE | `/api/strategy/plaza/{item_id}` | 隐藏/删除（作者或管理员） | 登录 | 作者或 admin | ✓ | — |

### 3.7 ResearchEngine 网关（re_gateway.py，10 个）

| 方法 | 路径 | 功能 | 权限 | 管理员 | 副作用 | 详细 |
|---|---|---|---|---|---|---|
| POST | `/api/backtest/strategy` | 策略回测提交（薄转发，1800s） | 登录 | — | ✓（RE 侧） | ✅ |
| GET | `/api/backtest/strategy/{run_id}` | 策略回测轮询（60s） | 登录 | — | 无 | ✅ |
| DELETE | `/api/backtest/strategy/{run_id}` | 策略回测取消（60s） | 登录 | — | ✓（RE 侧） | — |
| GET | `/api/re/health` | RE 健康代理（15s） | optional_user | — | 无 | ✅ |
| POST | `/api/ai/factor-generations` | RE AI 因子生成代理（600s） | 登录 | — | ✓（RE 侧） | — |
| POST | `/api/ai/strategy-generations` | RE AI 策略生成代理（600s） | 登录 | — | ✓（RE 侧） | — |
| POST | `/api/ai/strategy-transcriptions` | RE 聚宽策略转写代理（600s） | 登录 | — | ✓（RE 侧） | — |
| POST | `/api/ai/backtest-interpretations` | RE 回测解读代理（600s） | 登录 | — | ✓（RE 侧） | — |
| GET | `/api/market-data/symbols` | 证券列表转发 | **匿名** | — | 无 | — |
| GET | `/api/market-data/indices` | 指数列表转发 | **匿名** | — | 无 | — |
| GET | `/api/market-data/indices/{key}/constituents` | 指数成分转发 | **匿名** | — | 无 | — |

### 3.8 社区（community.py，24 个）

| 方法 | 路径 | 功能 | 权限 | 管理员 | 副作用 | 详细 |
|---|---|---|---|---|---|---|
| GET | `/api/community/posts` | 帖子列表 | **匿名** | — | 无 | ✅ |
| GET | `/api/community/hot` | 热门榜 | **匿名** | — | 无 | — |
| GET | `/api/community/posts/{post_id}` | 帖子详情 | optional_user | — | 浏览计数 ✓ | — |
| GET | `/api/community/posts/{post_id}/comments` | 评论列表 | optional_user | — | 无 | — |
| GET | `/api/community/my-posts` | 我的帖子 | 登录 | — | 无 | — |
| GET | `/api/community/favorites` | 我的收藏 | 登录 | — | 无 | — |
| GET | `/api/community/notifications` | 通知列表 | 登录 | — | 无 | — |
| GET | `/api/community/notifications/unread-count` | 未读数 | 登录 | — | 无 | — |
| POST | `/api/community/posts` | 发布帖子 | 登录 | — | ✓ | ✅ |
| PUT | `/api/community/posts/{post_id}` | 编辑帖子（作者） | 登录+归属 | — | ✓ | — |
| DELETE | `/api/community/posts/{post_id}` | 删除帖子（作者/admin） | 登录 | 作者或 admin | ✓ | — |
| POST | `/api/community/posts/{post_id}/comments` | 发表评论 | 登录 | — | ✓ | — |
| POST | `/api/community/posts/{post_id}/vote` | 帖投票 | 登录 | — | ✓ | — |
| POST | `/api/community/comments/{comment_id}/vote` | 评论投票 | 登录 | — | ✓ | — |
| POST | `/api/community/posts/{post_id}/favorite` | 收藏 | 登录 | — | ✓ | — |
| DELETE | `/api/community/posts/{post_id}/favorite` | 取消收藏 | 登录 | — | ✓ | — |
| POST | `/api/community/notifications/read` | 批量已读 | 登录 | — | ✓ | — |
| POST | `/api/community/reports` | 举报 | 登录 | — | ✓ | ✅ |
| POST | `/api/community/reports/{report_id}/resolve` | 处理举报 | 登录（store 校验 admin） | ✓ | ✓ | — |
| GET | `/api/community/moderation` | 待审/隐藏队列 | 登录（store 校验 admin） | ✓ | 无 | — |
| POST | `/api/community/posts/{post_id}/moderate` | 置顶/上下架 | 登录（store 校验 admin） | ✓ | ✓ | ✅ |
| POST | `/api/community/posts/{post_id}/purge` | 彻底清除 | 登录（store 校验 admin） | ✓ | ✓ | — |
| GET | `/api/community/reports` | 举报列表 | 登录（store 校验 admin） | ✓ | 无 | — |
| GET | `/api/community/ops/summary` | 运营摘要 | 登录（store 校验 admin） | ✓ | 无 | — |

### 3.9 新闻（news.py，6 个，均匿名）

| 方法 | 路径 | 功能 | 权限 | 管理员 | 副作用 | 详细 |
|---|---|---|---|---|---|---|
| GET | `/api/news` | 资讯列表（多条件过滤） | **匿名** | — | 无 | ✅ |
| GET | `/api/news/dict` | 标签词典快照 | **匿名** | — | 无 | — |
| GET | `/api/news/{news_id}` | 资讯详情 | **匿名** | — | 无 | — |
| POST | `/api/news/ingest` | 手动触发一轮采集 | **匿名**（待确认） | — | ✓ | ✅ |
| POST | `/api/news/{news_id}/enrich` | 单条正文增强 | **匿名**（待确认） | — | ✓ | — |
| GET | `/api/market-data/daily/{code}` | 展示日线（BFF 缓存；挂载于本路由） | **匿名** | — | 写缓存 | — |

### 3.10 AI（ai.py，4 个）

| 方法 | 路径 | 功能 | 权限 | 管理员 | 副作用 | 详细 |
|---|---|---|---|---|---|---|
| GET | `/api/ai/chat/models` | 模型列表 | 匿名 | — | 无 | — |
| GET | `/api/ai/speech/status` | 语音就绪状态 | 匿名 | — | 无 | — |
| POST | `/api/ai/chat` | 对话（SSE 流式 / JSON） | 登录 | — | 消耗模型调用 | ✅（含 §6 流式说明） |
| POST | `/api/ai/speech/transcribe` | 语音转写（base64） | 登录 | — | 消耗外部调用 | — |

### 3.11 Agent（agent.py，9 个）

| 方法 | 路径 | 功能 | 权限 | 管理员 | 副作用 | 详细 |
|---|---|---|---|---|---|---|
| GET | `/api/agent/usage/me` | 我的用量汇总 | 登录 | — | 无 | ✅ |
| GET | `/api/agent/usage` | 全局用量汇总 | 登录 | ✓ | 无 | — |
| POST | `/api/agent/usage/quota` | 设置用户日配额 | 登录（store 校验 admin） | ✓ | ✓ | — |
| POST | `/api/agent/runs` | 启动 Agent run（技能编排） | 登录 | — | ✓（消耗额度） | ✅ |
| POST | `/api/agent/gather` | 研究流水线·证据收集 | 登录 | — | ✓（消耗额度） | — |
| POST | `/api/agent/idea` | 研究流水线·因子构思 | 登录 | — | ✓ | — |
| POST | `/api/agent/factor` | 研究流水线·因子代码 | 登录 | — | ✓ | — |
| POST | `/api/agent/factor-backtest` | 研究流水线·回测报告 | 登录 | — | ✓ | — |
| POST | `/api/agent/factor-eval` | 研究流水线·评估 | 登录 | — | ✓ | — |

### 3.12 KnowledgeHub（kh.py，4 个端点函数 + catch-all）

| 方法 | 路径 | 功能 | 权限 | 管理员 | 副作用 | 详细 |
|---|---|---|---|---|---|---|
| GET | `/api/kh/docs`（+ `/api/kh/docs/`） | KH Swagger 页 | 匿名（页面门禁在前端） | — | 无 | ✅ |
| GET | `/api/kh/openapi.json` | KH OpenAPI spec | 匿名 | — | 无 | ✅ |
| POST | `/api/kh/model-providers/test` | 模型供应商连通性测试（显式路由） | optional_user（KH admin 门见 §8） | — | 消耗外部调用 | ✅ |
| ANY | `/api/kh/{path:path}` | catch-all → `handle_kh_get/post/put/delete` | 见 §8 | — | 视子接口 | 索引（引用 OpenAPI） |

> KH 子接口（collections/documents/ingest/search/ask/chats/conversations/messages/files/model-providers/default-models/progress/chunks/attachment 等 40 余条）**不在本文手写**，一律引用 `GET /api/kh/openapi.json`，见 §8。

### 3.12b 模拟盘（paper.py，15 个）

| 方法 | 路径 | 功能 | 权限 | 副作用 |
|---|---|---|---|---|
| GET | `/api/paper/accounts` | 模拟账户列表 | 登录 | 无 |
| POST | `/api/paper/accounts` | 创建账户（快照策略项目） | 登录 | ✓ |
| GET | `/api/paper/accounts/{id}` | 账户详情 + 持仓 | 登录+归属 | 无 |
| POST | `/api/paper/accounts/{id}/status` | 重命名/暂停/恢复/关闭 | 登录+归属 | ✓ |
| DELETE | `/api/paper/accounts/{id}` | 软关闭账户 | 登录+归属 | ✓ |
| GET | `/api/paper/accounts/{id}/positions` | 当前持仓 | 登录+归属 | 无 |
| GET | `/api/paper/accounts/{id}/orders` | 订单（可按日期过滤） | 登录+归属 | 无 |
| GET | `/api/paper/accounts/{id}/fills` | 成交（可按日期过滤） | 登录+归属 | 无 |
| GET | `/api/paper/accounts/{id}/equity` | 每日权益曲线 | 登录+归属 | 无 |
| GET | `/api/paper/accounts/{id}/settlements` | 结算记录 | 登录+归属 | 无 |
| GET | `/api/paper/accounts/{id}/settlement-attempts` | 结算尝试/失败原因 | 登录+归属 | 无 |
| POST | `/api/paper/accounts/{id}/settle` | 手动结算/补结算 | 登录+归属 | ✓ |
| POST | `/api/paper/accounts/{id}/replay` | 回滚并重算最新结算 | 登录+归属 | ✓ |
| POST | `/api/paper/accounts/{id}/sync-strategy` | 同步策略项目快照 | 登录+归属 | ✓ |
| GET | `/api/paper/status` | Feature Flag、RE 数据就绪与调度状态 | 登录 | 无 |

结算内部接口在 ResearchEngine，仅内网调用：
`GET /api/internal/paper-trading/status`、`GET /api/internal/paper-trading/trading-days`、
`POST /api/internal/paper-trading/settle`。

---

### 3.13 管理与审计（admin_logs.py，2 个）

| 方法 | 路径 | 功能 | 权限 | 管理员 | 副作用 | 详细 |
|---|---|---|---|---|---|---|
| GET | `/api/admin/logs` | 审计日志查询（多维过滤） | 登录 | ✓ | 无 | ✅ |
| POST | `/api/admin/logs/purge` | 清理 N 天前审计日志 | 登录 | ✓ | ✓ | ✅ |

---

## 4. 权限矩阵（按接口组）

| 接口组 | 匿名可访问 | 登录用户 | 资源所有者 | 管理员 |
|---|---|---|---|---|
| 健康检查 | GET /api/health、GET /api/re/health | — | — | — |
| 认证 | register / login | me / profile | — | — |
| 机构端 | — | 仅接受 `scope=inst` 机构令牌；个人版令牌返回 401 | 六角色 × 九工作区矩阵（服务端计算） | — |
| 用户主页 | 帖子列表、following/followers、主页 | follow/unfollow | — | — |
| 自选股 | —（匿名 GET 返回空集） | 全部读写 | 归属校验（`_require_watchlist`） | — |
| 因子研究 | re-catalog、dashboard、dashboard/status、**dashboard/refresh** | 其余全部 | 因子库/自定义因子按 user 隔离 | re-catalog/sync、dashboard/verify |
| 因子检测 | — | 全部 | 项目/run 按 (user_id,id) 隔离 | — |
| 策略研究 | plaza 列表/详情 | 其余全部 | 项目/run/库按 user 隔离 | library/sync、plaza 隐藏 |
| RE 网关 | market-data symbols/indices/constituents | 其余 | — | — |
| 社区 | 帖子列表/热门/详情/评论 | 发帖/评论/投票/收藏/举报 | 编辑/删除自己的帖子 | moderation/purge/resolve/reports/ops |
| 新闻 | 全部 6 个（含 ingest/enrich，**待确认是否收紧**） | — | — | — |
| AI | models、speech/status | chat、transcribe | — | — |
| Agent | — | 全部 | usage/me 仅本人 | usage、usage/quota |
| KnowledgeHub | docs/openapi；子接口默认匿名=admin（`KH_REQUIRE_AUTH` 关闭时） | 开启后需登录 | — | 登录用户须 role=admin（403 否则） |
| 管理与审计 | — | — | — | logs、logs/purge |

> 社区的"管理员"判定在 store 层按调用方传入的 role 参数执行（`moderate_post` 等 `author_role != "admin"` 抛 PermissionError → 403），路由层仅 `require_user`。

---

## 5. 幂等性与副作用

| 类别 | 规则（当前实现） |
|---|---|
| GET | 通常无副作用。例外：`GET /api/community/posts/{post_id}` 浏览计数+1；`GET /api/strategy/plaza/{item_id}?bump=1` 浏览计数+1 |
| POST 创建/提交 | 非幂等：发帖/评论/项目/库/广场发布/Agent run/回测提交，每次产生新行或新 run_id/job_id |
| POST 同步类 | 幂等（覆盖 upsert）：`re-catalog/sync`、`strategy/library/sync`、`news/ingest`（hash 去重）、`usage/quota`（覆盖设置）、`profile/me`、PUT 类更新 |
| DELETE | 删除/取消的幂等以实现为准：审计 purge/自选股删除重复调用安全；RE run 取消重复调用安全性由 RE 语义决定（待确认） |
| 副作用接口（非写库） | `POST /api/factor/dashboard/refresh`（启动批任务）、`POST /api/news/ingest`（外呼多源）、`POST /api/factor/dashboard/*` 缓存刷新 |
| AI / Agent | 每次调用消耗每日额度（`ai_usage` 记账）；`/api/ai/chat` 不记入 agent 额度（无记账，待确认是否应计入） |

---

## 6. 限流与额度

| 机制 | 现状 |
|---|---|
| AI / Agent 每日额度 | 有：`users.ai_quota_daily`（默认 200，按次计）。Agent run/流水线执行前 `assert_quota_available`，超限 403（文案含"配额"）；管理员可 `POST /api/agent/usage/quota` 调整 |
| `/api/ai/chat` | **不计入** agent 额度（无记账逻辑），仅受外部 LLM 供应商配额约束（待确认是否应计费） |
| RE 回测并发 | 因子回测本站队列 `SVQUANT_RE_BACKTEST_INFLIGHT=8`（超限排队/拒绝以实现为准）；策略回测为薄转发无自建队列，RE 侧并发上限待确认 |
| 登录限流 | **无**（现状仅审计记录失败；是否引入见待确认） |
| API 全局限流 | **无**（待确认） |
| 新闻/外部供应商限流 | 采集周期 `NEWS_INGEST_INTERVAL_SEC=900`、每源每次 `NEWS_INGEST_LIMIT=12`、单源超时约 20s；手动 ingest 无频控（待确认） |
| KH 供应商测试 | 无频控；每次调用打外部 API |

---

## 7. ResearchEngine 边界

### 7.1 接口归属

| 类别 | 接口 | 说明 |
|---|---|---|
| SVQuant 自有接口 | 健康检查、认证/主页、自选股、因子库/自定义因子/试算排队、检测项目/运行、策略项目/运行/库/广场、社区、新闻、AI 对话/语音、Agent、审计 | 数据与逻辑在 SVQuant（PostgreSQL / 磁盘 blob） |
| RE 网关/薄转发（无自建队列） | `/api/backtest/strategy*`、`/api/re/health`、`/api/ai/factor-generations`、`/api/ai/strategy-generations`、`/api/ai/strategy-transcriptions`、`/api/ai/backtest-interpretations`、`/api/market-data/symbols|indices|constituents` | 计算/数据在 RE，SVQuant 只做转发、超时与错误映射 |
| RE BFF（有本地适配） | `/api/factor/re-catalog*`（快照缓存）、`/api/backtest/factor*`（异步薄代理）、`/api/market-data/daily/{code}`（缓存）、`/api/factor/custom/trial`（经 RE 试算） | SVQuant 持有缓存/任务记录，但**不伪造结果** |
| 同步快照 | `POST /api/factor/re-catalog/sync`、`POST /api/strategy/library/sync` | RE 是事实来源，SVQuant 存只读镜像 |

### 7.2 硬性约束

1. **前端不得直连 RE**：浏览器只打本机 `/api`；所有 RE 访问经 SVQuant 网关/BFF。
2. **`YG_RE_BASE`（backend/.env）是唯一 RE 地址来源**（`services/core/re_config.py` 导入期校验，缺失即启动失败）。
3. **RE 不可用时返回 502**（`URLError → (502, {}, {"error": ...})`），SVQuant 不伪造研究结果、不返回假数据；目录同步结果为空时拒绝写入（502）。
4. RE 4xx/5xx **状态码与 body 透传**（业务语义保留），`Retry-After` 头透传；策略回测提交若返回 `run_id` 则改写 `poll_url` 为本站路径并附 `Location` 头。
5. 因子面板批任务契约（提交/轮询/结果查询、指标口径）详见 [因子面板-RE接口契约](RE契约/因子面板-RE接口契约.md)；RE 契约版本号与兼容窗口待确认。

---

## 8. KnowledgeHub 挂载边界

- KH 以**进程内挂载**方式并入 SVQuant 后端：`backend/app/routers/kh.py` 的 `@router.api_route("/api/kh/{path:path}", methods=[GET,POST,PUT,DELETE])` catch-all 分发到 `KnowledgeHub/backend/knowledge_hub/http_handlers.py` 的 `handle_kh_get/post/put/delete`。
- 入口：`GET /api/kh/docs`（Swagger HTML）、`GET /api/kh/openapi.json`（手工维护的 spec）。**子接口不逐条写入本文**，一律以 KH OpenAPI 为准。
- 认证约束（`_require_admin`）：
  - 登录用户：必须 `role=admin`，否则 403「仅管理员可进入知识库平台」；
  - 匿名请求：`KH_REQUIRE_AUTH` 未开启（**默认**）时以 `kh-anon/admin` 身份放行（内网调试便利）；`KH_REQUIRE_AUTH=1` 时返回 401；
  - 路由层 `except PermissionError → 401`。
- 显式端点：`POST /api/kh/model-providers/test`（绕过 catch-all 的连通性测试，body 为 `{provider_key|base_url, api_key, model}` 形态，字段以 KH OpenAPI 为准）。
- 已知子接口面（仅索引，不展开）：`/api/kh/meta`、`/api/kh/collections*`、`/api/kh/documents*`（含 `/{id}/ingest|chunks|progress|attachment`）、`/api/kh/documents/structured`、`/api/kh/search`、`/api/kh/ask`、`/api/kh/chats*`、`/api/kh/chats/{id}/conversations*`、`/api/kh/conversations/{id}/messages*`、`/api/kh/files*`、`/api/kh/model-providers*`、`/api/kh/default-models*`、`/api/kh/docs/outline`。

---

## 9. 核心接口详细定义

> 通用约定：body 均为 `dict[str, Any]` 手工解析（无 Pydantic 模型）；响应示例为示意，字段全集**以运行时 OpenAPI 为准**。关联模块文档见 [模块详细设计](../模块设计/SVQuant产品层/模块设计.md)。

### 9.1 GET /api/health

- **API 名称**：SVQuant 后端健康检查
- **方法和路径**：`GET /api/health`
- **来源文件**：`backend/app/routers/health.py`
- **权限要求**：匿名
- **路径/查询/Body 参数**：无
- **请求示例**：`curl http://127.0.0.1:8766/api/health`
- **返回示例**：

```json
{
  "ok": true,
  "service": "svquant",
  "port": 8766,
  "factor_dir": ".../backend/factor",
  "note": "no market data stored; compute via YGQuant RE"
}
```

- **错误情况**：无定义失败分支（中间件兜底 500）。
- **幂等性**：是。
- **限流/额度**：无。
- **关联数据表**：无。
- **关联模块文档**：[用户与权限模块/流程设计](../模块设计/用户与权限模块/流程设计.md)（bootstrap 时序）。
- **备注**：与 `GET /api/re/health`（RE 侧）区分；审计中间件跳过本路径。

### 9.2 POST /api/auth/register

- **API 名称**：用户注册
- **方法和路径**：`POST /api/auth/register`
- **来源文件**：`backend/app/routers/auth.py`（`auth_store.register_user`）
- **权限要求**：匿名
- **Body 参数**（手工解析，均可省略→校验失败）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| username | string | 是 | 3–32 位字母/数字/下划线 |
| password | string | 是 | ≥6 位 |
| email | string | 否 | 需含 `@`，≤120 字符，唯一 |
| display_name | string | 否 | 默认取 username |

- **请求示例**：

```json
{"username": "demo_user", "password": "******", "email": "demo@example.com"}
```

- **返回示例**（示意）：

```json
{"ok": true, "user": {"id": 2, "username": "demo_user", "role": "user", "status": "active", "ai_quota_daily": 200}, "token": "<JWT>"}
```

- **错误情况**：400（用户名/密码/邮箱不合法、用户名或邮箱已存在——**当前重复也返回 400 而非 409**）；注册成功/失败均写审计（`auth.register` / `auth.register_failed`）。
- **幂等性**：否（重复注册报错）。
- **限流/额度**：无（待确认是否加登录/注册限流）。
- **关联数据表**：users；app_audit_logs。
- **关联模块文档**：[用户与权限模块](../模块设计/用户与权限模块/模块设计.md)。

### 9.3 POST /api/auth/login

- **API 名称**：用户登录
- **方法和路径**：`POST /api/auth/login`
- **来源文件**：`backend/app/routers/auth.py`（`auth_store.login_user`）
- **权限要求**：匿名
- **Body 参数**：`username`（string，必填）、`password`（string，必填）
- **请求示例**：

```json
{"username": "demo_user", "password": "******"}
```

- **返回示例**（示意）：

```json
{"ok": true, "user": {"id": 2, "username": "demo_user", "role": "user"}, "token": "<JWT>"}
```

> 注意：旧版文档所写 `access_token`/`token_type` 字段**不存在**；实际为 `token` 字段。
- **错误情况**：401（用户名或密码错误、账号已停用）；失败写审计 `auth.login_failed`。
- **幂等性**：是（无状态 JWT，重复登录结果等价）。
- **限流/额度**：无登录限流（待确认）。
- **关联数据表**：users；app_audit_logs。
- **关联模块文档**：[用户与权限模块](../模块设计/用户与权限模块/模块设计.md)。

### 9.4 GET /api/auth/me

- **API 名称**：当前用户信息
- **方法和路径**：`GET /api/auth/me`
- **来源文件**：`backend/app/routers/auth.py`（`auth_store.me_response`）
- **权限要求**：Bearer token（无 Header → 401）
- **参数**：无
- **返回示例**（示意）：

```json
{"ok": true, "user": {"id": 2, "username": "demo_user", "role": "user", "ai_quota_daily": 200}, "dev_skip_auth": false}
```

- **错误情况**：401（未登录或 token 无效/过期/用户已停用）。
- **幂等性**：是。
- **限流/额度**：无。
- **关联数据表**：users（读）。
- **关联模块文档**：[用户与权限模块](../模块设计/用户与权限模块/模块设计.md)。
- **备注**：token 每次请求都回查 users 表（状态停用即失效）。

### 9.5 POST /api/profile/me

- **API 名称**：更新个人资料
- **方法和路径**：`POST /api/profile/me`
- **来源文件**：`backend/app/routers/auth.py`（`profile_store.update_my_profile`）
- **权限要求**：登录（require_user）
- **Body 参数**（全部可选，仅传即更新）：

| 字段 | 类型 | 说明 |
|---|---|---|
| display_name | string | 昵称 |
| headline | string | 一句话简介（限长以实现为准） |
| bio | string | 关于我 |
| avatar_url | string | 图片 dataURL/URL（须 `data:image/` 前缀，超限 400） |
| cover_url | string | 封面图，同上 |

- **返回示例**（示意）：`{"ok": true, "profile": {...}}`——以运行时 OpenAPI 为准。
- **错误情况**：400（图片格式/超限）；404（用户不存在）。
- **幂等性**：是（覆盖更新）。
- **关联数据表**：users。
- **关联模块文档**：[用户与权限模块](../模块设计/用户与权限模块/类设计.md)（`_normalize_image` 限长）。

### 9.6 GET /api/watchlists

- **API 名称**：我的自选股分组列表
- **方法和路径**：`GET /api/watchlists`
- **来源文件**：`backend/app/routers/watchlists.py`（`watchlist_store.list_watchlists`）
- **权限要求**：`soft_db_user_id`——匿名/无法映射 DB 用户时**返回空集而非 401**
- **参数**：无
- **返回示例**：

```json
{"ok": true, "watchlists": [{"id": 1, "name": "核心池", "symbol_count": 12}]}
```

（行字段示意，以运行时 OpenAPI 为准）
- **错误情况**：无显式错误分支。
- **幂等性**：是。
- **关联数据表**：user_watchlists（symbol_count 聚合）。
- **关联模块文档**：[ResearchEngine网关模块](../模块设计/ResearchEngine网关模块/模块设计.md)（自选股部分）。

### 9.7 POST /api/watchlists

- **API 名称**：创建自选股分组
- **方法和路径**：`POST /api/watchlists`
- **来源文件**：`backend/app/routers/watchlists.py`
- **权限要求**：登录（require_db_user_id）
- **Body 参数**：`name`（string，必填；空/重名 → 400，同用户内唯一）
- **请求示例**：`{"name": "核心池"}`
- **返回示例**：`{"ok": true, "watchlist": {...}}`
- **错误情况**：400（名称非法或重复）。
- **幂等性**：否（重名报错）。
- **关联数据表**：user_watchlists（`UNIQUE(user_id,name)`）。
- **关联模块文档**：[ResearchEngine网关模块/类设计](../模块设计/ResearchEngine网关模块/类设计.md)。

### 9.8 GET /api/factor/re-catalog

- **API 名称**：RE 官方因子目录（快照）
- **方法和路径**：`GET /api/factor/re-catalog`
- **来源文件**：`backend/app/routers/factor.py`（`re_factor_catalog.fetch_re_catalog`）
- **权限要求**：匿名（当前无依赖，待确认是否收紧）
- **查询参数**：

| 参数 | 默认 | 说明 |
|---|---|---|
| fresh | `0` | `1/true/yes` 强制打 RE 拉取并刷新缓存 |
| all | `0` | `1/true/yes` 返回全部库（默认 primary 十库） |

- **返回示例**（示意）：目录 JSON（库列表 + 因子清单 + 计数），读 `re_factor_catalog_snapshot` 快照；字段以运行时 OpenAPI 为准。
- **错误情况**：502（`{"ok": false, "error": ...}`，RE 不可达且无可用快照时）。
- **幂等性**：是（`fresh=1` 有副作用：覆盖快照缓存）。
- **限流/额度**：无。
- **关联数据表**：re_factor_catalog_snapshot。
- **关联模块文档**：[因子研究模块](../模块设计/因子研究模块/模块设计.md)、[因子面板-RE接口契约](RE契约/因子面板-RE接口契约.md)。

### 9.9 POST /api/factor/re-catalog/sync

- **API 名称**：同步 RE 因子目录快照（管理员）
- **方法和路径**：`POST /api/factor/re-catalog/sync`
- **来源文件**：`backend/app/routers/factor.py`（`re_factor_catalog.sync_from_re`）
- **权限要求**：require_admin（非管理员 403）
- **Body 参数**：无
- **返回示例**（示意）：

```json
{"ok": true, "factor_count": 120, "library_factor_counts": {"quality": 18}, "content_hash": "…"}
```

- **错误情况**：502（RE 不可达或同步结果为空——空结果不写入，保留旧快照）；403（非管理员）。
- **幂等性**：是（覆盖式 upsert + content_hash 变更判定）。
- **关联数据表**：re_factor_catalog_snapshot、re_factor_catalog_sync_log。
- **关联模块文档**：[因子研究模块/流程设计](../模块设计/因子研究模块/流程设计.md)（流程 C）。

### 9.10 POST /api/factor/re-backtest

- **API 名称**：提交因子回测任务（本站排队）
- **方法和路径**：`POST /api/factor/re-backtest`
- **来源文件**：`backend/app/routers/factor.py`（`re_backtest_jobs.submit_factor_backtest`）
- **权限要求**：登录（require_user）
- **Body 参数**：回测请求 dict（因子引用/代码、池、周期、过滤规则等），schema 由 RE 契约定义，**以运行时 OpenAPI 与 RE 契约为准**，本文不虚构字段。
- **返回示例**（示意）：`{"job_id": "<id>", "status": "queued"}`。
- **错误情况**：400（`ValueError`：参数/因子校验失败）；队列在 `SVQUANT_RE_BACKTEST_INFLIGHT=8` 满时的行为（排队或拒绝）以实现为准。
- **幂等性**：否（每次新 job_id）。
- **限流/额度**：并发上限 8（进程内 `_job_lock` + inflight 计数）；任务 TTL 3600s。
- **关联数据表**：detect_runs（任务与项目关联）、re_factor_catalog_snapshot（因子解析）；任务暂态在进程内存 + `backend/output/factor_dashboard/job.json`。
- **关联模块文档**：[因子研究模块/流程设计](../模块设计/因子研究模块/流程设计.md)（流程 B：异步回测时序）。

### 9.11 GET /api/factor/re-backtest/{job_id}

- **API 名称**：轮询因子回测任务
- **方法和路径**：`GET /api/factor/re-backtest/{job_id}`
- **来源文件**：`backend/app/routers/factor.py`（`re_backtest_jobs.get_factor_backtest_job`）
- **权限要求**：登录；任务归属校验（非本人 → 403）
- **路径参数**：`job_id`（string）
- **返回示例**（示意）：`{"job_id": "...", "status": "running|completed|failed", ...}`，completed 时含结果/指标；字段以 OpenAPI 为准。
- **错误情况**：404（status=missing，含 TTL 过期 3600s 后被清理）；403（status=forbidden）。
- **幂等性**：是。
- **关联数据表**：detect_runs（结果落库由任务完成回调写入）。
- **关联模块文档**：[因子研究模块/流程设计](../模块设计/因子研究模块/流程设计.md)（状态机 queued→running→completed/failed/canceled）。

### 9.12 POST /api/factor/custom

- **API 名称**：新增自定义因子
- **方法和路径**：`POST /api/factor/custom`
- **来源文件**：`backend/app/routers/factor.py`（`factor_store.add_custom_factor` 兼容层 → `user_factor_store`）
- **权限要求**：登录（require_db_user_id）
- **Body 参数**：`name`（因子名）、`body`（Python 源码）、`description`（可选）
- **返回示例**（示意）：`{"ok": true, "factor": {...}}`——以 OpenAPI 为准。
- **错误情况**：400（重名/名称非法/代码校验失败；`method_name` 全局唯一冲突）。
- **幂等性**：否。
- **关联数据表**：user_custom_factors（`UNIQUE(user_id,name)`、`UNIQUE(method_name)`）；启动时 `migrate_legacy_custom_to_admin` 迁移旧数据。
- **关联模块文档**：[因子研究模块/类设计](../模块设计/因子研究模块/类设计.md)。

### 9.13 POST /api/factor/custom/trial

- **API 名称**：因子试算（经 RE）
- **方法和路径**：`POST /api/factor/custom/trial`
- **来源文件**：`backend/app/routers/factor.py`（`factor_trial.trial_via_re`）
- **权限要求**：登录（require_user）
- **Body 参数**：

| 字段 | 默认 | 说明 |
|---|---|---|
| body | —（必填） | 因子 Python 源码 |
| name / factor_name | `trial_factor` | 因子名 |
| universe | `CSI300` | 股票池 |
| period | `3m` | 试算区间 |

- **返回示例**（示意）：试算结果对象；**成功判定 = 无 `error` 字段且含 `metrics`**（约定见因子模块），失败时含 `error` 文案。
- **错误情况**：400（`ValueError/RuntimeError`：代码不合法或 RE 拒绝）。
- **幂等性**：是（同输入结果等价；RE 侧可能有计算缓存）。
- **限流/额度**：无专门限流；受 RE 可用性约束（不可达时报错）。
- **关联数据表**：无（试算不落库，待确认）。
- **关联模块文档**：[因子研究模块/类设计](../模块设计/因子研究模块/类设计.md)（`trial_via_re`）。

### 9.14 GET /api/detect/projects

- **API 名称**：检测项目列表
- **方法和路径**：`GET /api/detect/projects`
- **来源文件**：`backend/app/routers/detect.py`（`detect_store.list_projects`）
- **权限要求**：登录（require_db_user_id）；仅返回本人项目
- **查询参数**：`visible`（默认 `0`；`1/false/no` 外的值表示仅显示可见项目）
- **返回示例**（示意）：`{"ok": true, "projects": [...]}`——以 OpenAPI 为准。
- **错误情况**：无显式分支。
- **幂等性**：是。
- **关联数据表**：detect_projects（示例项目 `SAMPLE_ID="sample_momentum_5d"` 由 `ensure_sample_projects` 种子）。
- **关联模块文档**：[因子研究模块](../模块设计/因子研究模块/模块设计.md)。

### 9.15 POST /api/detect/projects

- **API 名称**：创建/更新检测项目（upsert）
- **方法和路径**：`POST /api/detect/projects`
- **来源文件**：`backend/app/routers/detect.py`（`detect_store.create_project` / `upsert_project`）
- **权限要求**：登录
- **Body 参数**（双形态，代码事实）：

| 形态 | 条件 | 行为 |
|---|---|---|
| 简单创建 | body 含 `factorName`/`factor_name` 且无 `id`、无 `config` | `create_project`（默认名 `custom_combo`，`name` 作展示名/描述） |
| 完整 upsert | 其他情况 | `upsert_project(uid, body)`（body 含 `id` 即更新） |

- **返回示例**（示意）：项目对象——以 OpenAPI 为准。
- **错误情况**：400（`ValueError`）。
- **幂等性**：upsert 形态幂等；创建形态非幂等。
- **关联数据表**：detect_projects（PK `(user_id, id)`）。
- **关联模块文档**：[因子研究模块/流程设计](../模块设计/因子研究模块/流程设计.md)。

### 9.16 POST /api/detect/runs

- **API 名称**：保存检测运行记录
- **方法和路径**：`POST /api/detect/runs`
- **来源文件**：`backend/app/routers/detect.py`（`detect_store.save_run`）
- **权限要求**：登录
- **Body 参数**：运行记录 dict（项目 id、因子名、request/result 摘要等；字段以 OpenAPI 为准）
- **返回示例**（示意）：run 对象。
- **错误情况**：404（项目不存在 `KeyError`）；400（`ValueError`）。
- **幂等性**：同 run 重复保存的 upsert 语义以实现为准（待确认）。
- **关联数据表**：detect_runs（复合 FK → detect_projects）。
- **关联模块文档**：[因子研究模块](../模块设计/因子研究模块/模块设计.md)。

### 9.17 GET /api/strategy/projects

- **API 名称**：策略项目列表
- **方法和路径**：`GET /api/strategy/projects`
- **来源文件**：`backend/app/routers/strategy.py`（`strategy_store.list_projects`）
- **权限要求**：登录；仅本人
- **查询参数**：`visible`（同 detect）
- **返回示例**（示意）：项目列表（新用户自动种子示例项目 `sample_momentum_20d`）。
- **错误情况**：无显式分支。
- **幂等性**：是。
- **关联数据表**：strategy_projects。
- **关联模块文档**：[策略研究模块](../模块设计/策略研究模块/模块设计.md)。

### 9.18 POST /api/strategy/projects

- **API 名称**：创建/更新策略项目（upsert）
- **方法和路径**：`POST /api/strategy/projects`
- **来源文件**：`backend/app/routers/strategy.py`
- **权限要求**：登录
- **Body 参数**：项目 dict（`id` 存在即更新；`config` 含策略代码与 `SVQUANT_PARAMS` 参数区），字段以 OpenAPI 为准。
- **返回示例**（示意）：项目对象。
- **错误情况**：400（`ValueError`）。
- **幂等性**：upsert 幂等。
- **关联数据表**：strategy_projects。
- **关联模块文档**：[策略研究模块](../模块设计/策略研究模块/模块设计.md)。

### 9.19 POST /api/strategy/runs

- **API 名称**：保存策略运行记录
- **方法和路径**：`POST /api/strategy/runs`
- **来源文件**：`backend/app/routers/strategy.py`（`strategy_store.save_run`）
- **权限要求**：登录
- **Body 参数**：运行记录 dict（run_id、project_id、request/result 等）
- **处理规则**（代码事实）：`slim_strategy_result_for_db` 瘦身后入 `strategy_runs.result`；**完整结果 gzip 写磁盘** `backend/data/strategy_run_blobs/{user_id}/{run_id}.json.gz`（`write_run_blob`）。
- **返回示例**（示意）：run 摘要对象。
- **错误情况**：404（项目不存在）；400（`ValueError`）。
- **幂等性**：同 run 重复保存 upsert 语义待确认。
- **关联数据表**：strategy_runs；磁盘 blob。
- **关联模块文档**：[策略研究模块/流程设计](../模块设计/策略研究模块/流程设计.md)（流程 A）。

### 9.20 GET /api/strategy/library

- **API 名称**：内置策略目录（PG 镜像）
- **方法和路径**：`GET /api/strategy/library`
- **来源文件**：`backend/app/routers/strategy.py`（`builtin_strategies_store.list_builtin_strategies_from_db`）
- **权限要求**：登录（require_user）
- **返回示例**（示意）：`{"total": n, "items": [...]}`（id/名称/类型/执行模式/版本/标签）。
- **错误情况**：502（镜像读取失败）。
- **幂等性**：是。
- **关联数据表**：builtin_strategies（RE 同步快照，**非源码事实来源**）。
- **关联模块文档**：[策略研究模块/类设计](../模块设计/策略研究模块/类设计.md)。

### 9.21 POST /api/strategy/library/sync

- **API 名称**：从 RE 同步内置策略镜像（管理员）
- **方法和路径**：`POST /api/strategy/library/sync`
- **来源文件**：`backend/app/routers/strategy.py`（`sync_builtin_strategies_from_re`，RE `GET /api/strategies`）
- **权限要求**：require_admin
- **返回示例**（示意）：`{"ok": true, "upserted": n, ...}`。
- **错误情况**：502（RE 不可达或同步结果为空——`upserted<=0` 拒绝写入）；403。
- **幂等性**：是（覆盖 upsert）。
- **关联数据表**：builtin_strategies。
- **关联模块文档**：[策略研究模块/流程设计](../模块设计/策略研究模块/流程设计.md)（流程 B）。

### 9.22 GET /api/strategy/plaza

- **API 名称**：策略广场列表
- **方法和路径**：`GET /api/strategy/plaza`
- **来源文件**：`backend/app/routers/strategy.py`（`strategy_plaza_store.list_plaza_items`）
- **权限要求**：**匿名**（公开）
- **查询参数**：`limit`（默认 30，1–100）、`offset`（默认 0）、`q`（关键词）、`sort`（默认 `newest`）、`universe`
- **返回示例**（示意）：条目列表（snapshot 内含瘦身指标与 ≤360 点净值曲线；**不含代码**，代码在详情）。
- **错误情况**：422（limit 越界时由 FastAPI 校验返回）。
- **幂等性**：是。
- **关联数据表**：strategy_plaza_items（仅 `published` 对普通用户可见）。
- **关联模块文档**：[策略研究模块/流程设计](../模块设计/策略研究模块/流程设计.md)（流程 D）。

### 9.23 POST /api/backtest/strategy

- **API 名称**：策略回测提交（RE 薄转发）
- **方法和路径**：`POST /api/backtest/strategy`
- **来源文件**：`backend/app/routers/re_gateway.py`（`forward_re`，RE 路径同名）
- **权限要求**：登录
- **Body 参数**：原样转发 RE（strategy_id 或 code + 日期 + params），schema 由 RE 定义，**以运行时 OpenAPI 为准**。
- **处理规则**（代码事实）：转发超时 **1800s**；RE 返回含 `run_id` 时把 `poll_url` 改写为 `/api/backtest/strategy/{run_id}` 并附 `Location` 响应头；同步形态直接长等返回结果。
- **返回示例**（示意，202 异步形态）：`{"run_id": "...", "status": "submitted", "poll_url": "/api/backtest/strategy/..."}`。
- **错误情况**：502（RE 不可达）；RE 4xx/5xx 透传。
- **幂等性**：否（每次新 run_id；RE 侧去重契约待确认）。
- **限流/额度**：无自建队列（线程占用风险见架构文档）；RE 侧并发待确认。
- **关联数据表**：无（结果由前端回传 `POST /api/strategy/runs` 落库）。
- **关联模块文档**：[ResearchEngine网关模块/流程设计](../模块设计/ResearchEngine网关模块/流程设计.md)（流程 A）。

### 9.24 GET /api/backtest/strategy/{run_id}

- **API 名称**：策略回测轮询（RE 薄转发）
- **方法和路径**：`GET /api/backtest/strategy/{run_id}`
- **来源文件**：`backend/app/routers/re_gateway.py`
- **权限要求**：登录（**注意：当前不校验 run 归属，转发即查**，待确认是否补归属校验）
- **路径参数**：`run_id`（RE 侧运行 id）
- **处理规则**：转发超时 60s；状态/结果/失败原因原样透传。
- **返回示例**（示意）：`{"run_id": "...", "status": "running|completed|failed", ...}`（completed 含净值/指标/持仓，字段以 RE 契约为准）。
- **错误情况**：404（RE 侧未知 run 透传）；502（RE 不可达）。
- **幂等性**：是。
- **关联数据表**：无。
- **关联模块文档**：[ResearchEngine网关模块/流程设计](../模块设计/ResearchEngine网关模块/流程设计.md)。

### 9.25 GET /api/re/health

- **API 名称**：ResearchEngine 健康代理
- **方法和路径**：`GET /api/re/health`
- **来源文件**：`backend/app/routers/re_gateway.py`
- **权限要求**：optional_user（匿名可访问）
- **处理规则**：转发 RE `GET /api/health`，超时 15s。
- **返回示例**：RE 健康对象透传（示意）。
- **错误情况**：502（RE 不可达）。
- **幂等性**：是。
- **关联数据表**：无。
- **关联模块文档**：[系统架构 §失败与容错矩阵](../架构与技术/系统架构.md)。

### 9.26 GET /api/community/posts

- **API 名称**：社区帖子列表
- **方法和路径**：`GET /api/community/posts`
- **来源文件**：`backend/app/routers/community.py`（`community_store.list_posts`）
- **权限要求**：**匿名**
- **查询参数**：`section`（五板块之一，可选）、`q`、`sort`（默认 `views`）、`limit`（默认 50）、`offset`
- **返回示例**（示意）：帖子列表（含作者信息、互动计数；viewer 身份影响可见范围）。
- **错误情况**：400（非法 section/sort）。
- **幂等性**：是。
- **关联数据表**：posts（索引 `idx_posts_section_created` / `idx_posts_views`）。
- **关联模块文档**：[社区与新闻模块](../模块设计/社区与新闻模块/模块设计.md)。

### 9.27 POST /api/community/posts

- **API 名称**：发布社区帖子
- **方法和路径**：`POST /api/community/posts`
- **来源文件**：`backend/app/routers/community.py`（`community_store.create_post`）
- **权限要求**：登录
- **Body 参数**：

| 字段 | 必填 | 说明 |
|---|---|---|
| title | 是 | 标题 |
| body | 是 | 正文 |
| section | 是 | `strategy`/`factor`/`qa`/`hotspot`/`official` |
| code_snippet | 否 | 可克隆代码 |
| status | 否 | 默认 `published`（draft/hidden 受 CHECK 支持） |
| platform_ref | 否 | 平台引用 JSON（面板指标/回测引用，供读帖校验对账） |

- **处理规则**：解析正文 @提及 → 写 `notifications`（type=mention）。
- **返回示例**（示意）：帖子对象。
- **错误情况**：400（板块非法/标题空等 `ValueError`）。
- **幂等性**：否。
- **限流/额度**：无发帖频控（待确认）。
- **关联数据表**：posts、notifications。
- **关联模块文档**：[社区与新闻模块/流程设计](../模块设计/社区与新闻模块/流程设计.md)（流程 A）；[AI与Agent模块](../模块设计/AI与Agent模块/模块设计.md)（AI 生成草稿后经本接口落库）。

### 9.28 POST /api/community/reports

- **API 名称**：举报帖子/评论
- **方法和路径**：`POST /api/community/reports`
- **来源文件**：`backend/app/routers/community.py`（`community_store.create_report`）
- **权限要求**：登录
- **Body 参数**：`target_type`（`post`/`comment`）、`post_id`（必填 int）、`comment_id`（可选）、`reason`（`spam`/`abuse`/`illegal`/`misinfo`/`other`）、`detail`（可选）
- **返回示例**（示意）：举报对象（status=open）。
- **错误情况**：400（枚举非法/重复 open 举报受部分唯一索引约束——重复时行为以实现为准）；404（目标不存在）。
- **幂等性**：同一 (reporter, target, post, comment) 仅一条 open（部分唯一索引 `idx_reports_open_uniq`）。
- **关联数据表**：community_reports。
- **关联模块文档**：[社区与新闻模块/流程设计](../模块设计/社区与新闻模块/流程设计.md)（流程 B）。

### 9.29 POST /api/community/posts/{post_id}/moderate

- **API 名称**：帖子置顶/上下架（管理员）
- **方法和路径**：`POST /api/community/posts/{post_id}/moderate`
- **来源文件**：`backend/app/routers/community.py`（`community_store.moderate_post`）
- **权限要求**：登录；**store 内校验 `author_role == "admin"`**（非管理员 403）
- **路径参数**：`post_id`（int）
- **Body 参数**：`pinned`（bool，可选）、`status`（`published`/`hidden`，可选）——至少其一
- **返回示例**（示意）：更新后的帖子对象。
- **错误情况**：403（非管理员）；404；400（两者都缺或 status 非法）。
- **幂等性**：是（状态置位）。
- **关联数据表**：posts。
- **关联模块文档**：[社区与新闻模块/类设计](../模块设计/社区与新闻模块/类设计.md)。

### 9.30 GET /api/news

- **API 名称**：资讯列表
- **方法和路径**：`GET /api/news`
- **来源文件**：`backend/app/routers/news.py`（`news_store.list_news`）
- **权限要求**：**匿名**
- **查询参数**：`category`、`source`、`q`、`mode`、`theme`（数组）、`symbol`（数组）、`industry`（数组）、`limit`（默认 50）、`offset`
- **返回示例**（示意）：资讯条目列表（含标签/关联代码；字段以 OpenAPI 为准）。
- **错误情况**：400（过滤参数非法）。
- **幂等性**：是。
- **限流/额度**：无。
- **关联数据表**：news_items（GIN 索引支持 theme/symbol/industry 包含查询；FIFO 容量 15000/10000/2000）。
- **关联模块文档**：[社区与新闻模块](../模块设计/社区与新闻模块/模块设计.md)。

### 9.31 POST /api/news/ingest

- **API 名称**：手动触发资讯采集
- **方法和路径**：`POST /api/news/ingest`
- **来源文件**：`backend/app/routers/news.py`（`news_ingest.ingest_news`）
- **权限要求**：**匿名**（当前无依赖，**待确认是否收紧为管理员**）
- **Body 参数**（均可选）：`sources`（数组或逗号分隔串；非法源 → 400 并返回 supported/unsupported 清单）、`limit` / `limit_per_source`（默认 12）
- **处理规则**：遍历指定源（cls/eastmoney(_research/_policy)/cninfo/wallstreetcn/10jqka）拉取 → hash 去重 upsert → 标签回填 → 正文增强 → FIFO 裁剪；单源失败不阻塞其他源。
- **返回示例**（示意）：各源采集统计 JSON（新增/跳过/裁剪计数）。
- **错误情况**：400（unsupported sources）。
- **幂等性**：是（hash 去重，重复采集不产生重复行）。
- **限流/额度**：无频控（与后台 900s 调度线程可能并发，依赖 upsert 幂等）。
- **关联数据表**：news_items。
- **关联模块文档**：[社区与新闻模块/流程设计](../模块设计/社区与新闻模块/流程设计.md)（流程 C）。

### 9.32 POST /api/ai/chat

- **API 名称**：AI 对话（SSE 流式 / JSON 同步）
- **方法和路径**：`POST /api/ai/chat`
- **来源文件**：`backend/app/routers/ai.py`（`ai/gateway/ark_chat.py`）
- **权限要求**：登录（require_user；**当前不计入 agent 日额度**，待确认）
- **Body 参数**：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| messages | array | 是 | — | `[{role, content}]`；非数组 → 400 |
| model | string | 否 | 方舟默认模型 | 经 `resolve_provider` 路由方舟/硅基流动 |
| temperature | number | 否 | `0.7` | 解析失败回退 0.7 |
| stream | bool | 否 | `false` | `true` 走 SSE 流式 |

- **请求示例**：

```json
{"messages": [{"role": "user", "content": "你好"}], "model": "...", "stream": true}
```

- **返回示例（非流式，示意）**：模型响应对象（content 等，字段以 OpenAPI 为准）。
- **流式返回**：`text/event-stream; charset=utf-8`（`Cache-Control: no-cache, no-store`、`X-Accel-Buffering: no`），帧格式见 §10。
- **错误情况**：400（messages 非数组；流式过程中的模型错误以**错误帧**返回而非 HTTP 错误）；非流式时 503（文案含"未配置"）/502（调用失败）。
- **幂等性**：否（生成结果不保证一致）。
- **限流/额度**：无本站记账；受外部供应商配额约束。
- **关联数据表**：无（对话不落库）。
- **关联模块文档**：[AI与Agent模块](../模块设计/AI与Agent模块/模块设计.md)。

### 9.33 GET /api/agent/usage/me

- **API 名称**：我的 AI 用量汇总
- **方法和路径**：`GET /api/agent/usage/me`
- **来源文件**：`backend/app/routers/agent.py`（`ai/runtime/store.usage_summary_for_user`）
- **权限要求**：登录（仅本人数据）
- **查询参数**：`days`（默认 7）
- **返回示例**（示意）：按日/按 skill 的用量汇总与配额余量；字段以 OpenAPI 为准。
- **错误情况**：401。
- **幂等性**：是。
- **关联数据表**：ai_usage、users.ai_quota_daily。
- **关联模块文档**：[AI与Agent模块/类设计](../模块设计/AI与Agent模块/类设计.md)。

### 9.34 POST /api/agent/runs

- **API 名称**：启动 Agent run（技能编排）
- **方法和路径**：`POST /api/agent/runs`
- **来源文件**：`backend/app/routers/agent.py`（`ai/runtime/runtime.start_run`）
- **权限要求**：登录；消耗每日额度（`assert_quota_available`，超限 403 文案含"配额"）
- **Body 参数**：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| skills | array | 否 | 合法值限 `SINGLE_SKILLS`（polish_title/polish_body/summarize_post）；非数组 → 400 |
| goal | string | 否 | 关键词路由技能（读帖/tldr→summarize_post 等） |
| context | object | 否 | 上下文（帖子/面板数据）；非对象 → 400 |
| mode | string | 否 | 默认 `single` |
| crew | string | 否 | 指定 crew（如社区创作/读帖） |

- **处理规则**：`resolve_skills` 路由 → board 状态机逐步执行 → 每步 `record_usage` 记账；LLM 未配置时 mock 降级（board 带 mock 标记）。
- **返回示例**（示意）：board（steps、draft、审计与信任标记）。
- **错误情况**：403（配额不足）；400（`ValueError`/`LlmError`）；401。
- **幂等性**：否（每次新 run_id）。
- **限流/额度**：每日按次（默认 200）。
- **关联数据表**：ai_usage、users。
- **关联模块文档**：[AI与Agent模块/流程设计](../模块设计/AI与Agent模块/流程设计.md)（流程 B + 时序图）。

### 9.35 GET /api/admin/logs

- **API 名称**：审计日志查询（管理员）
- **方法和路径**：`GET /api/admin/logs`
- **来源文件**：`backend/app/routers/admin_logs.py`（`audit_log_store.list_audit_logs`）
- **权限要求**：require_admin
- **查询参数**：`limit`（默认 50，1–200）、`offset`、`module`、`username`、`action`、`statusCode`、`statusMin`、`statusMax`、`method`、`writeOnly`（bool，仅写操作）、`path`（包含匹配）、`since`、`until`
- **返回示例**（示意）：日志条目分页列表。
- **错误情况**：403（非管理员）；422（参数越界）。
- **幂等性**：是。本接口自身的成功 GET 不写审计（中间件跳过防刷屏）。
- **关联数据表**：app_audit_logs。
- **关联模块文档**：[用户与权限模块/类设计](../模块设计/用户与权限模块/类设计.md)。

### 9.36 POST /api/admin/logs/purge

- **API 名称**：清理审计日志（管理员）
- **方法和路径**：`POST /api/admin/logs/purge`
- **来源文件**：`backend/app/routers/admin_logs.py`（`audit_log_store.purge_audit_logs`）
- **权限要求**：require_admin
- **查询参数**：`days`（1–3650，可选；缺省读环境变量 `AUDIT_LOG_RETENTION_DAYS`，默认 **30** 天）
- **返回示例**：

```json
{"ok": true, "days": 30, "deleted": 1234}
```

- **错误情况**：403；422（days 越界）；`days<=0` 不清理（返回 deleted=0）。
- **幂等性**：是（重复执行删除 0 行）。
- **关联数据表**：app_audit_logs。
- **关联模块文档**：[数据库设计 §8 生命周期](../数据设计/数据库设计.md)。

### 9.37 KnowledgeHub 入口（3 个）

#### GET /api/kh/docs

- **API 名称**：KnowledgeHub Swagger 页
- **方法和路径**：`GET /api/kh/docs`（与 `/api/kh/docs/` 等价，同一函数挂两个路径）
- **来源文件**：`backend/app/routers/kh.py`（`openapi_docs.swagger_html`）
- **权限要求**：匿名（spec 页面本身不鉴权；子接口受 §8 认证约束）
- **返回**：`text/html` Swagger UI。
- **幂等性**：是。**关联数据表**：无。

#### GET /api/kh/openapi.json

- **API 名称**：KnowledgeHub OpenAPI spec
- **方法和路径**：`GET /api/kh/openapi.json`
- **来源文件**：`backend/app/routers/kh.py`（`openapi_docs.openapi_spec`，手工维护）
- **权限要求**：匿名
- **返回**：KH 全部子接口的 OpenAPI JSON（**KH 子接口的权威定义**）。
- **幂等性**：是。**关联数据表**：无。

#### POST /api/kh/model-providers/test

- **API 名称**：模型供应商连通性测试（显式路由，绕过 catch-all）
- **方法和路径**：`POST /api/kh/model-providers/test`
- **来源文件**：`backend/app/routers/kh.py` → `http_handlers.handle_kh_post`
- **权限要求**：optional_user → `_require_admin` 门（见 §8）
- **Body 参数**：供应商凭据（base_url / api_key / model 等），字段以 KH OpenAPI 为准；body 非法 JSON → 400。
- **处理规则**：用提交的凭据发起真实外部调用验证；**不经 store、不写库**。
- **返回示例**（示意）：测试结果 JSON（成功/失败原因）。
- **错误情况**：400（invalid JSON）；401/403（认证门）；外部调用失败以结果体返回。
- **幂等性**：是（探测无副作用，但消耗外部 API 调用）。
- **关联数据表**：无。
- **关联模块文档**：[KnowledgeHub模块](../模块设计/KnowledgeHub模块/模块设计.md)。

---

## 10. POST /api/ai/chat 流式专项说明

- **是否支持流式**：支持。body 传 `"stream": true` 时返回 `StreamingResponse`（SSE），否则为普通 JSON。
- **SSE 帧格式**（`_sse_chat_frames`，逐帧 `data: <JSON>\n\n`）：

```text
data: {"status":"start"}          ← 首帧，流开始
data: {"delta":"片段文本"}         ← 多帧增量（模型流式 piece，已做 strip_thinking）
data: {"error":"错误文案"}         ← 异常帧（ArkChatError 或其他异常）
data: [DONE]                      ← 终止帧（正常结束与异常结束都会发送）
```

- **错误处理方式**：流式过程中发生错误**不以 HTTP 状态码表达**（响应头已 200 发出），而是发 `{"error": ...}` 错误帧 + `[DONE]` 结束；非流式模式则以 HTTP 状态码表达（503/502）。
- **未配置模型密钥时**：
  - 非流式：`ArkChatError` 文案含"未配置" → **503**（引导配置 `ARK_API_KEY` 等）；其他错误 → 502。
  - 流式：帧内 `{"error": "未配置…"}` + `[DONE]`。
- **响应头**：`Cache-Control: no-cache, no-store`、`Connection: keep-alive`、`X-Accel-Buffering: no`（禁代理缓冲）。
- **思考链**：`strip_thinking` 剥离模型思考输出后再下发 delta。

---

## 11. 未展开接口清单（仅索引，103 个）

以下接口已在上文 §3 总览中列出（方法/路径/功能/权限/副作用/来源文件），但未按 §9 模板展开，**请求/响应字段一律以运行时 OpenAPI 为准**：

- 用户主页与关注 6 个：`GET /api/users/{username}`、`.../posts`、`.../following`、`.../followers`、`POST/DELETE .../follow`。
- 自选股 6 个：`GET .../symbols`、`POST .../symbols`、`POST .../symbols/batch`、`PUT /{wl_id}`、`DELETE .../symbols/{symbol}`、`DELETE /{wl_id}`。
- 因子研究 19 个：`GET /api/factor/index`、`DELETE /api/factor/re-backtest/{job_id}`、`/api/backtest/factor*` 3 个、因子库 CRUD 9 个、`GET /api/factor/file/{name:path}`、dashboard 3 个（dashboard/status、verify）、custom 更新/删除 2 个。
- 因子检测 8 个：项目详情/更新/删除/运行列表、runs 列表/详情/PATCH/DELETE。
- 策略研究 20 个：项目详情/更新/删除/项目运行、runs 列表/详情/PATCH/删除、library/{id}、用户库 6 个、mark-detected/archive、plaza 详情/发布/删除。
- RE 网关 7 个：`DELETE /api/backtest/strategy/{run_id}`、AI 生成代理 3 个、market-data 3 个。
- 社区 21 个：热门/详情/评论列表、我的帖子/收藏、通知 3 个、评论/投票/收藏 5 个、通知已读、举报处理、审核队列、purge、举报列表、运营摘要、编辑/删除帖子。
- 新闻 3 个：`/api/news/dict`、`/api/news/{news_id}`、`POST /api/news/{news_id}/enrich`、`GET /api/market-data/daily/{code}`（4 个）。
- AI 3 个：chat/models、speech/status、speech/transcribe。
- Agent 6 个：usage（admin）、usage/quota、流水线 4 个。
- KH catch-all 约 40 条子接口（§8 索引）——以 `/api/kh/openapi.json` 为准。

---

## 12. 待确认项

1. **是否需要统一响应 envelope**（`{code, data, message}`）：现状三种形态并存（`{ok,...}` / 裸对象 / `{"error":...}`）。
2. **是否需要版本化** `/api/v1`：现状无版本段，破坏性变更无退路。
3. **是否需要统一业务错误码**：现状仅 HTTP 状态码 + `detail` 文案；409 未使用（重复资源走 400）。
4. **是否需要登录/注册限流**（防爆破）：现状仅审计记录。
5. **是否需要 API 全局限流**（网关层/应用层）。
6. **是否需要自动导出 OpenAPI 到 docs**（CI 生成 `openapi.json` 快照，防文档漂移；KH 已有手工 spec，SVQuant 侧未导出）。
7. **ResearchEngine 契约版本号与兼容窗口**：RE API 无版本约定，锁步发布下的兼容策略待确认。
8. 资讯端点（含 ingest/enrich）与 `POST /api/factor/dashboard/refresh`、market-data 转发端点当前**匿名**，是否收紧。
9. `GET /api/backtest/strategy/{run_id}` 无 run 归属校验（任何登录用户可轮询他人 run），是否补齐。
10. `/api/ai/chat` 是否计入 agent 日额度并落 `ai_usage`。
11. JWT 无服务端吊销（登出/封禁即时性依赖每请求回查 users.status——已实现回查，但 token 本身到期前仍有效），是否需要黑名单。
12. 生产 CORS `allow_origins=["*"]` 是否收敛为白名单。

---

## 13. 文末统计

| 项 | 数值 |
|---|---|
| 实际扫描路由声明 | **156 处**（`rg` 扫描 `backend/app/routers` + KnowledgeHub；`/api/kh/docs` 一函数两路径） |
| 去重后端点数 | **140 个** |
| 文档总览覆盖 | **140 个**（§3 全量，含 KH catch-all 1 条 + 显式 3 条） |
| 详细展开核心接口 | **37 个**（§9，含 KH 入口 3 个） |
| 仅索引未展开 | **103 个**（§11 清单；KH 子接口约 40 条引至 KH OpenAPI） |
| 需运行服务后用 OpenAPI 校验 | 全部未展开接口；特别是： KH 子接口全集、因子库/检测/策略 CRUD 的字段级 schema、社区返回对象形状、Agent 流水线产物 schema |
