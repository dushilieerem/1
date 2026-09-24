# KnowledgeHub 测试用例（M11）

> 模块：KnowledgeHub 知识库（挂载于 `/api/kh`）。代码：`backend/app/routers/kh.py`、`KnowledgeHub/backend/knowledge_hub/*`。
> 关键代码事实：catch-all `ANY /api/kh/{path}` → `http_handlers`；认证门 `_require_admin`——登录非 admin 403、匿名默认以 `kh-anon/admin` 放行（`KH_REQUIRE_AUTH=1` 时 401）（**DCM-03，安全 P0 关注**）；`PermissionError→401`（KH 侧例外映射）；`POST /api/kh/model-providers/test` 为显式路由（optional_user）；子接口清单以 `GET /api/kh/openapi.json` 为准（本文步骤按功能族描述，不逐条手写路径）；表：kh_collections/documents/attachments/chunks/files/chats/conversations/chat_messages/model_providers/default_models；附件目录 `KnowledgeHub/data/`（默认不入 Git，需与元数据成对备份）。
> 状态：全部 NOT RUN。Req 基线：PRD §6.7。

## 覆盖概览

| 场景类别 | 用例数 | Case ID |
|---|---|---|
| 正常 | 9 | 001, 003–005, 011–012, 015, 017, 022 |
| 异常 | 5 | 002, 006, 009, 013, 018 |
| 边界 | 3 | 007, 014, 016 |
| 权限/安全 | 4 | 010, 019–021 |
| 一致性 | 3 | 008, 023–024 |

---

## 1. 入口与文档

### TC-KH-001 OpenAPI 文档入口
- **Req**: REQ-KH-006 ｜ **Pri**: P1 ｜ **Sev**: Minor ｜ **Type**: API
- **Steps**: 匿名 `GET /api/kh/docs` 与 `GET /api/kh/docs/`、`GET /api/kh/openapi.json`
- **Expected**: Swagger HTML 可加载；openapi.json 为合法 JSON spec；两路径等价（同函数）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-002 spec 与实现一致性抽查
- **Req**: REQ-KH-006 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: Contract
- **Steps**: 从 openapi.json 抽取 10 个子接口 → 逐个按 spec 发请求
- **Expected**: 实际响应与 spec 的方法/路径/状态码/必填字段一致（不一致记缺陷：KH spec 为手工维护，易漂移）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

## 2. 集合与文档

### TC-KH-003 集合 CRUD
- **Req**: REQ-KH-001 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: API
- **Steps**: 创建 collection（名称/描述）→ 列表 → 更新 → 删除
- **Expected**: 全链路一致；空名/超长名按实现校验
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-004 结构化创建文档并摄取
- **Req**: REQ-KH-002 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: Integration
- **Steps**: 结构化创建文档 → 触发 ingest → 轮询 progress → 查 chunks
- **Expected**: 摄取异步推进；进度接口状态从 pending→完成；chunks 按分块策略生成（数量>1 可验证）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-005 文件上传（合法类型）
- **Req**: REQ-KH-002 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: Integration
- **Data**: 小型 md/pdf/docx 各一
- **Steps**: 上传 → 元数据与 kh_files 落库 → 附件下载
- **Expected**: 上传成功；下载内容与上传一致；附件文件存在于 `KnowledgeHub/data/`
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-006 非法/损坏文件
- **Req**: REQ-KH-002 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: API
- **Data**: 伪造扩展名的二进制、损坏 pdf、空文件（0 字节）
- **Steps**: 上传并摄取
- **Expected**: 解析失败原因明确；文件不进入"可检索成功态"；不 500
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-007 大文件与重复文件
- **Req**: REQ-KH-002 ｜ **Pri**: P2 ｜ **Sev**: Minor ｜ **Type**: API
- **Steps**: 超大文件（实现上限处）；同名文件重复上传
- **Expected**: 超限明确拒绝（或记录实际上限）；重复上传行为确定（去重/允许并存），不产生孤儿附件
- **Auto**: MIXED ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-008 删除文档与附件清理
- **Req**: REQ-KH-003 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: Integration
- **Steps**: 删除已摄取文档（含附件）→ 查 chunks/attachments 元数据与磁盘文件
- **Expected**: 级联清理与 DB 设计一致（SET NULL/删除语义）；**元数据与磁盘文件不残留孤儿**（不成对删除记缺陷）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-009 附件缺失降级
- **Req**: REQ-KH-003 ｜ **Pri**: P2 ｜ **Sev**: Minor ｜ **Type**: Integration
- **Steps**: 手工删除磁盘附件后下载
- **Expected**: 明确报错"附件缺失"（PRD §6.7 异常表），不 500
- **Auto**: MANUAL ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-010 附件路径穿越
- **Req**: REQ-KH-006 ｜ **Pri**: P0 ｜ **Sev**: Critical ｜ **Type**: Security
- **Steps**: 下载请求路径含 `../`、绝对路径、URL 编码穿越（%2e%2e%2f）
- **Expected**: 全部拒绝；不能读出仓库任意文件（与 TC-SEC-022 联动）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

## 3. 检索与问答

### TC-KH-011 关键词检索有结果
- **Req**: REQ-KH-004 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: Integration
- **Pre**: 已摄取含特定关键词的文档
- **Steps**: 检索该关键词 → 检索无关联词
- **Expected**: 前者返回相关片段与出处；后者明确空态；检索结果带来源引用
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-012 问答带引用
- **Req**: REQ-KH-004 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: Integration
- **Steps**: 就已上传文档提问（ask）
- **Expected**: 返回答案 + 引用来源（文档/分块可定位）；多轮会话消息落 kh_chat_messages
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-013 供应商未配置/不可用
- **Req**: REQ-KH-005 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: Integration
- **Steps**: 移除/填错 embedding 或 LLM 供应商配置 → 检索、问答
- **Expected**: 明确错误；检索可降级为非向量方式（以实现为准，记录行为）；问答不静默空答
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-014 检索/问答参数边界
- **Req**: REQ-KH-004 ｜ **Pri**: P2 ｜ **Sev**: Minor ｜ **Type**: API
- **Steps**: 空查询串、超长查询、不存在的 collection/document 范围、top_k 极值
- **Expected**: 400/404 或明确空态；不 500
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

## 4. 对话会话

### TC-KH-015 会话生命周期
- **Req**: REQ-KH-005 ｜ **Pri**: P2 ｜ **Sev**: Minor ｜ **Type**: API
- **Steps**: 建 chat → 建 conversation → 发消息 → 读历史 → 删除
- **Expected**: 消息顺序正确；删除级联符合 DB 设计
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-016 消息边界
- **Req**: REQ-KH-005 ｜ **Pri**: P2 ｜ **Sev**: Minor ｜ **Type**: API
- **Steps**: 空消息、超长消息、非法 role、向不存在 conversation 发消息
- **Expected**: 校验明确（400/404）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

## 5. 模型供应商

### TC-KH-017 供应商配置 CRUD 与默认模型
- **Req**: REQ-KH-005 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: API
- **Steps**: 创建 provider（base_url/model）→ 列表 → 设 default-model → 删除
- **Expected**: CRUD 生效；**读取接口不回显 api_key 明文**（脱敏或掩码，若回显记 Critical）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-018 供应商连通性测试
- **Req**: REQ-KH-005 ｜ **Pri**: P1 ｜ **Sev**: Minor ｜ **Type**: Integration
- **Steps**: `POST /api/kh/model-providers/test`：可达供应商 / 不可达地址 / 坏 key / 非法 JSON body
- **Expected**: 分别返回成功/失败原因/400；测试**不写库、不残留凭据副本**；结果不含密钥
- **Auto**: MIXED ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

## 6. 权限（DCM-03 重点）

### TC-KH-019 匿名默认放行（现状记录）
- **Req**: REQ-KH-007 ｜ **Pri**: P0 ｜ **Sev**: Critical ｜ **Type**: Security
- **Steps**: `KH_REQUIRE_AUTH` 未开启时匿名调用只读与写接口各一
- **Expected**: 默认以 kh-anon/admin 放行（现状）；**该行为作为安全评审项留档**，生产是否可接受待确认（与 TC-SEC-014 同源）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-020 KH_REQUIRE_AUTH=1 时匿名 401
- **Req**: REQ-KH-007 ｜ **Pri**: P0 ｜ **Sev**: Major ｜ **Type**: Security
- **Pre**: 环境变量 `KH_REQUIRE_AUTH=1` 重启
- **Steps**: 匿名调用任意 /api/kh 子接口
- **Expected**: 401
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-021 登录非 admin 用户 403
- **Req**: REQ-KH-007 ｜ **Pri**: P0 ｜ **Sev**: Major ｜ **Type**: Security
- **Steps**: TEST_USER_A（role=user）调用 /api/kh 子接口
- **Expected**: 403（"仅管理员可进入知识库平台"）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-022 admin 用户正常访问
- **Req**: REQ-KH-007 ｜ **Pri**: P1 ｜ **Sev**: Minor ｜ **Type**: API
- **Steps**: TEST_ADMIN 走完集合→文档→检索链路
- **Expected**: 全部 200；功能正常（管理员非匿名身份）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

## 7. 一致性

### TC-KH-023 文档全生命周期
- **Req**: REQ-KH-001/002/003 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: Integration
- **Steps**: 建集合→传文档→摄取→检索到→删除文档→删除集合→逐层验证消失
- **Expected**: 元数据/分块/附件/磁盘文件四方一致；删除后检索不再命中
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-KH-024 摄取失败可重试
- **Req**: REQ-KH-002 ｜ **Pri**: P2 ｜ **Sev**: Minor ｜ **Type**: Integration
- **Steps**: 制造摄取失败（供应商断开）→ 恢复 → 重新摄取
- **Expected**: 进度接口显示失败原因；重试后成功且 chunks 不重复
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

---

## 统计

TC-KH 共 **24** 条：P0×4、P1×14、P2×6；AUTO 21 / MIXED 2 / MANUAL 1。状态全部 NOT RUN。
