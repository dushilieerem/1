/**
 * 分块策略列表由后端 `GET /api/kh/meta` 提供，勿在此硬编码。
 * 新增策略见：WebApp/KnowledgeHub/docs/分块策略扩展.md
 * 实现位置：WebApp/KnowledgeHub/backend/knowledge_hub/chunking/strategies.py
 */
export type { ChunkStrategy } from "./api";
