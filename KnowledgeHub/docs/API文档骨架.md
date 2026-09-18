# KnowledgeHub API 文档

> **权威目录：** 前端 `/settings/api`（数据源 `store.api_catalog()`）  
> **Swagger：** `/api/kh/docs`
> 完成接口后务必在 `api_catalog()` 追加一条，本页与 Swagger 同步出现。

## 鉴权

```
Authorization: Bearer <SVQuant admin JWT>
```

非 admin → `403`。

前端：`http://127.0.0.1:9531/`（端口可按部署调整）
API：由 SVQuant backend 提供（或经前端代理 `/api`）

## 基础

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/kh/meta` | pipelines + chunkStrategies |
| GET | `/api/kh/collections` | 知识库列表 |
| POST | `/api/kh/collections` | 创建知识库 |
| PUT | `/api/kh/collections/{id}` | 重命名 / 更新 |
| DELETE | `/api/kh/collections/{id}` | 删除（级联） |
| GET | `/api/kh/collections/{id}/documents` | 文档列表 |
| POST | `/api/kh/documents` | 创建文档并可选 ingest；docx/pdf 传 `contentBase64` |
| GET | `/api/kh/documents/{id}` | 文档详情 |
| PUT | `/api/kh/documents/{id}` | 改标题 / `enabled` 等 |
| DELETE | `/api/kh/documents/{id}` | 删除文档及切片 |
| GET | `/api/kh/documents/{id}/chunks` | 切片列表 |
| POST | `/api/kh/documents/{id}/ingest` | 重新分块解析 |
| GET/POST | `/api/kh/chats` | 聊天应用 |
| GET/POST | `/api/kh/files` | 文件管理 |
| GET/POST | `/api/kh/model-providers` | 模型供应商 |
| GET/POST | `/api/kh/default-models` | 默认 LLM/Embedding/Rerank |

## 检索 / 问答（已就绪）

| 方法 | 路径 | 约定 |
|------|------|------|
| POST | `/api/kh/search` | 只返回命中片段；有 Embedding 时 hybrid，否则关键词 |
| POST | `/api/kh/ask` | 回答必须引用片段；无命中则明确「知识库未找到」，不调 LLM |

### `POST /api/kh/search`

```json
{
  "query": "alpha101",
  "collectionId": 4,
  "topK": 8
}
```

也可传 `collectionIds: [4, 5]`。仅检索 `ready` 且 `enabled=true` 的文档。

返回示例字段：`mode`、`totalCandidates`、`hits[]`（含 `chunkId`、`documentTitle`、`score`、`text`）。

### `POST /api/kh/ask`

```json
{
  "query": "alpha101 是什么",
  "chatId": 1,
  "collectionIds": [4],
  "topK": 5
}
```

返回：`answer`、`grounded`、`mode`、`hits`。`grounded=false` 表示知识库未找到依据。

## 会话（聊天应用）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/kh/chats/{id}/conversations` | 会话列表 |
| POST | `/api/kh/chats/{id}/conversations` | 新建会话 |
| GET/POST/DELETE | `/api/kh/conversations/{id}/messages` | 消息读写 / 清空 |
