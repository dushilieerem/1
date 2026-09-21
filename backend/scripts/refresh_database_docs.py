# -*- coding: utf-8 -*-
"""刷新 docs/04-项目管理/数据库持续更新.md（表清单 / 字段 / 脱敏样例）。

用法（在 backend 目录）::

    python scripts/refresh_database_docs.py

只改「行数、字段类型、样例」；表用途与字段说明见下方 PURPOSES / FIELD_HINTS。
敏感字段会打码；长文本截断。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parent / "docs" / "04-项目管理"
OUT = DOCS / "数据库持续更新.md"
MAX_STR = 120
SAMPLE_N = 2
REDACT_KEYS = {
    "password_hash",
    "password",
    "token",
    "secret",
    "avatar_url",
    "cover_url",
}

# 样例只保留这些列（未列出则取前若干非大字段）
SAMPLE_COLS: dict[str, tuple[str, ...]] = {
    "users": ("id", "username", "display_name", "role", "status", "ai_quota_daily", "created_at"),
    "posts": ("id", "author_id", "section", "title", "status", "view_count", "is_pinned", "created_at"),
    "post_comments": ("id", "post_id", "author_id", "parent_id", "created_at"),
    "detect_projects": ("id", "user_id", "name", "factor_name", "run_count", "updated_at"),
    "detect_runs": ("id", "user_id", "project_id", "factor_name", "finished_at", "elapsed_sec"),
    "strategy_projects": ("id", "user_id", "name", "run_count", "updated_at"),
    "strategy_runs": ("id", "user_id", "project_id", "name", "remark", "flagged", "finished_at", "elapsed_sec"),
    "news_items": (
        "id",
        "source",
        "category",
        "title",
        "published_at",
        "is_flash",
        "is_featured",
    ),
    "user_custom_factors": ("id", "user_id", "name", "method_name", "created_at"),
    "user_factor_libraries": ("id", "user_id", "name", "updated_at"),
    "user_library_factors": ("id", "user_id", "library_id", "name", "category_label", "updated_at"),
    "user_strategy_libraries": ("id", "user_id", "name", "updated_at"),
    "builtin_strategies": (
        "id",
        "name",
        "strategy_type",
        "execution_mode",
        "entrypoint",
        "current_version",
        "source",
        "updated_at",
    ),
    "user_library_strategies": (
        "id",
        "user_id",
        "library_id",
        "name",
        "description",
        "source_run_id",
        "archive_finished_at",
    ),
    "kh_collections": ("id", "name", "pipeline", "chunk_strategy", "status", "updated_at"),
    "kh_documents": ("id", "collection_id", "title", "chunk_strategy", "status", "updated_at"),
    "kh_chunks": ("id", "document_id", "ordinal", "created_at"),
    "kh_files": ("id", "title", "file_name", "collection_id", "created_at"),
    "kh_chats": ("id", "name", "model_name", "updated_at"),
    "kh_model_providers": ("id", "provider_key", "display_name", "updated_at"),
    "kh_default_models": ("id", "role_key", "provider_key", "model_name", "updated_at"),
    "notifications": ("id", "user_id", "actor_id", "type", "post_id", "read_at", "created_at"),
    "community_reports": ("id", "reporter_id", "target_type", "post_id", "reason", "status", "created_at"),
    "ai_usage": ("id", "user_id", "skill", "tokens_in", "tokens_out", "created_at"),
    "app_audit_logs": (
        "id",
        "created_at",
        "username",
        "action",
        "module",
        "method",
        "path",
        "status_code",
        "duration_ms",
    ),
    "re_factor_catalog_snapshot": (
        "scope",
        "content_hash",
        "factor_count",
        "library_count",
        "fetched_at",
        "updated_at",
    ),
    "re_factor_catalog_sync_log": (
        "id",
        "scope",
        "changed",
        "factor_count",
        "message",
        "created_at",
    ),
    "factor_dashboard_metrics": (
        "factor_name",
        "universe",
        "period",
        "library",
        "ic_mean",
        "sharpe",
        "error",
        "computed_at",
    ),
    "factor_dashboard_verifications": (
        "library_name",
        "factor_name",
        "status",
        "updated_at",
        "updated_by",
    ),
    "factor_dashboard_legacy_imports": (
        "migration_key",
        "source_rows",
        "imported_rows",
        "skipped_rows",
        "completed_at",
    ),
}

PURPOSES: dict[str, str] = {
    "users": "账号与资料：登录、角色、AI 日配额、公开主页头像/封面/简介。",
    "user_follows": "用户关注关系（关注者 → 被关注者）。",
    "user_custom_factors": "用户自定义因子元数据（`.py` 另存磁盘；本表记归属与可见性）。",
    "user_factor_libraries": "用户自建因子库（文件夹）；与内置库同级，按 user 隔离。",
    "user_library_factors": "用户因子库内的因子条目（含代码正文、分类、说明）。",
    "user_strategy_libraries": "用户自建策略库（文件夹）；与内置库同级，按 user 隔离。",
    "builtin_strategies": "ResearchEngine 策略目录在 SVQuant 的全量镜像：id/名称/类型/执行模式/当前版本/入口/标签；source 仅保留过渡期回测源码快照，目录由管理员从 RE 同步。",
    "user_library_strategies": "用户策略库内入库快照（含策略说明、回测归档 JSON；与研究侧 run 脱钩）。",
    "kh_collections": "KnowledgeHub 知识库集合（:9531；类型 pipeline + 分块策略）。",
    "kh_documents": "KnowledgeHub 文档（正文 / 分块策略 / status / enabled / parse_error）。",
    "kh_chunks": "KnowledgeHub 文档切片（ordinal + text + meta JSONB）；检索读此表。",
    "kh_files": "KnowledgeHub 文件管理页登记（可关联 collection）。",
    "kh_chats": "KnowledgeHub 聊天应用配置（开场白、系统提示、关联知识库 ids）。",
    "kh_model_providers": "模型供应商（通义/OpenAI 兼容等；存 base_url / api_key）。",
    "kh_default_models": "默认模型角色（llm / embedding / rerank …）。",
    "posts": "社区帖（正文 / 代码 / 分区 / 状态 / 置顶）。",
    "post_comments": "帖评论与楼中楼回复。",
    "comment_votes": "评论赞/踩（每用户每评论一票）。",
    "post_votes": "帖赞/踩（每用户每帖一票）。",
    "post_favorites": "用户收藏帖。",
    "notifications": "站内通知（回复、@、系统等）。",
    "community_reports": "举报帖/评论；管理仓处理队列。",
    "ai_usage": "Agent 调用流水（按 skill 一行）；日配额按当日行数计。",
    "app_audit_logs": "系统审计日志（写操作 / 登录注册 / 4xx·5xx）；管理仓「系统日志」页查询；成功 GET 不记。",
    "detect_projects": "因子检测项目配置与归属。",
    "detect_runs": "因子检测一次运行结果摘要 / 状态。",
    "strategy_projects": "策略研究项目配置与归属。",
    "strategy_runs": "策略回测一次运行结果（检测报告列表按此表；含备注/标记；按 user 隔离）。",
    "news_items": "资讯聚合条目（快讯/市场/公告/研报/政策/海外；真源 ingest upsert，含定时调度）。",
    "user_watchlists": "用户自选股组合（文件夹）；按 user 隔离，前端 `/data/watchlist`。",
    "user_watchlist_symbols": "自选组合内标的（symbol + 名称快照）；归属某 watchlist。",
    "kh_chat_messages": "KnowledgeHub 会话消息（role + content）；挂在 kh_conversations 下。",
    "kh_conversations": "KnowledgeHub 用户会话线程（关联 chat / collection）。",
    "re_factor_catalog_snapshot": "ResearchEngine 官方因子目录快照（库列表+因子清单 JSON）；页面读此表，不每次打 RE。",
    "re_factor_catalog_sync_log": "官方因子目录同步日志（定时/手动：有无变更、hash、条数）。",
    "factor_dashboard_metrics": "SVQuant 因子面板指标缓存（因子×库×池×周期×过滤规则）；ResearchEngine 计算后写入 PostgreSQL。",
    "factor_dashboard_verifications": "因子跨平台对比校验状态（按因子库+因子名），SVQuant 产品数据。",
    "factor_dashboard_legacy_imports": "旧因子面板 SQLite 指标与校验记录的一次性导入标记，不承载面板业务数据。",
}

FIELD_HINTS: dict[str, dict[str, str]] = {
    "users": {
        "id": "主键",
        "username": "登录名；公开主页 `/u/{username}`",
        "email": "邮箱（可空）",
        "password_hash": "密码哈希（禁止明文）",
        "display_name": "展示昵称",
        "role": "`user` / `admin`",
        "status": "`active` / `disabled`",
        "ai_quota_daily": "每日 Agent 调用上限（按次，非按 token）",
        "avatar_url": "头像 URL / dataURL",
        "cover_url": "主页封面",
        "headline": "一句话简介",
        "bio": "关于我",
        "created_at": "注册时间",
        "updated_at": "资料更新",
    },
    "user_follows": {
        "follower_id": "关注者 `users.id`",
        "following_id": "被关注者 `users.id`",
        "created_at": "关注时间",
    },
    "user_custom_factors": {
        "id": "主键",
        "user_id": "所有者",
        "name": "因子标识名",
        "method_name": "Python 方法名 `def xxx(self)`",
        "body": "因子代码正文",
        "description": "说明",
        "visibility": "可见性",
        "created_at": "创建",
        "updated_at": "更新",
    },
    "user_factor_libraries": {
        "id": "主键",
        "user_id": "所有者",
        "name": "库名（同用户唯一）",
        "created_at": "创建",
        "updated_at": "更新",
    },
    "user_library_factors": {
        "id": "主键",
        "library_id": "所属 `user_factor_libraries.id`",
        "user_id": "所有者（冗余，便于按用户唯一名）",
        "name": "因子标识名（同用户唯一）",
        "method_name": "Python 方法名",
        "body": "因子源码",
        "description": "中文说明",
        "category_label": "分类标签",
        "created_at": "创建",
        "updated_at": "更新",
    },
    "user_strategy_libraries": {
        "id": "主键",
        "user_id": "所有者",
        "name": "库名（同用户唯一）",
        "created_at": "创建",
        "updated_at": "更新",
    },
    "builtin_strategies": {
        "id": "策略 id（主键；回测可作 strategy_id）",
        "name": "展示名",
        "strategy_type": "分类：trend/momentum/reversal/…",
        "execution_mode": "`vectorized` / `event`",
        "entrypoint": "入口类名",
        "tags": "标签 JSON 数组",
        "current_version": "RE 当前目录版本（仅镜像，不随回测请求发送）",
        "source": "过渡期完整 Python 源码快照；不用于内置策略执行",
        "updated_at": "更新时间",
    },
    "user_library_strategies": {
        "id": "主键",
        "library_id": "所属 `user_strategy_libraries.id`",
        "user_id": "所有者",
        "name": "策略名（同用户唯一）",
        "code_id": "关联代码标识（若有）",
        "body": "策略源码快照",
        "description": "策略说明（入库时填写，列表副标题）",
        "category_label": "分类标签",
        "source_run_id": "来源研究 run id（仅溯源，不随研究侧变更）",
        "archive_request": "入库时回测请求快照 JSON",
        "archive_result": "入库时回测结果快照 JSON",
        "archive_elapsed_sec": "入库快照耗时秒",
        "archive_finished_at": "入库快照完成时间",
        "created_at": "创建",
        "updated_at": "更新",
    },
    "kh_collections": {
        "id": "主键",
        "name": "知识库名（唯一）",
        "description": "说明",
        "pipeline": "类型 general/qa/manual/…",
        "chunk_strategy": "分块策略 id",
        "status": "active 等",
        "created_by": "创建人 users.id（可空）",
        "created_at": "创建",
        "updated_at": "更新",
    },
    "kh_documents": {
        "id": "主键",
        "collection_id": "所属 kh_collections.id",
        "title": "标题（可重命名）",
        "source_type": "file / text",
        "body": "原文",
        "file_name": "上传文件名",
        "file_size": "字节",
        "chunk_strategy": "分块策略",
        "status": "draft / parsing / ready / failed",
        "enabled": "是否参与 search/ask（false=停用）",
        "parse_error": "最近一次解析失败原因",
        "version": "ingest 版本",
        "created_by": "上传人（可空）",
        "created_at": "创建",
        "updated_at": "更新",
    },
    "kh_chunks": {
        "id": "主键",
        "document_id": "kh_documents.id",
        "ordinal": "片序",
        "text": "切片正文",
        "meta": "如 title 等 JSONB",
        "created_at": "创建",
    },
    "kh_files": {
        "id": "主键",
        "title": "标题",
        "file_name": "文件名",
        "file_size": "字节",
        "body": "文本内容",
        "collection_id": "可选关联知识库",
        "created_by": "上传人",
        "created_at": "创建",
        "updated_at": "更新",
    },
    "kh_chats": {
        "id": "主键",
        "name": "聊天应用名",
        "description": "说明",
        "opener": "开场白",
        "system_prompt": "系统提示（可含 {knowledge}）",
        "empty_response": "无检索时回复",
        "collection_ids": "关联知识库 id 列表 JSONB",
        "model_name": "可选覆盖模型名",
        "temperature": "采样温度",
        "top_p": "top_p",
        "max_tokens": "最大 token",
        "created_by": "创建人",
        "created_at": "创建",
        "updated_at": "更新",
    },
    "kh_model_providers": {
        "id": "主键",
        "provider_key": "供应商 key（唯一）",
        "display_name": "显示名",
        "base_url": "API Base URL",
        "api_key": "密钥（勿导出明文到文档样例）",
        "models": "模型列表 JSONB",
        "created_at": "创建",
        "updated_at": "更新",
    },
    "kh_default_models": {
        "id": "主键",
        "role_key": "llm / embedding / rerank …",
        "provider_key": "供应商 key",
        "model_name": "模型名",
        "updated_at": "更新",
    },
    "posts": {
        "id": "主键",
        "author_id": "作者",
        "section": "`strategy` / `factor` / `qa` / `hotspot` / `official`",
        "title": "标题",
        "body": "正文（Markdown/HTML）",
        "code_snippet": "可克隆代码",
        "status": "`published` / `draft` / `hidden` 等",
        "view_count": "浏览次数",
        "is_pinned": "是否置顶",
        "pinned_at": "置顶时间",
        "platform_ref": "平台引用 JSON（面板指标 / 回测引用，供读帖 TL;DR 校验）",
        "created_at": "创建",
        "updated_at": "更新",
    },
    "post_comments": {
        "id": "主键",
        "post_id": "所属帖",
        "author_id": "评论者",
        "user_id": "评论者（若有）",
        "parent_id": "父评论（楼中楼）",
        "reply_to_comment_id": "回复目标评论",
        "body": "评论正文",
        "status": "状态",
        "images": "图片 JSON",
        "created_at": "时间",
        "updated_at": "更新",
    },
    "comment_votes": {
        "user_id": "投票用户",
        "comment_id": "评论",
        "value": "1 赞 / -1 踩",
        "created_at": "时间",
    },
    "post_votes": {
        "user_id": "投票用户",
        "post_id": "帖",
        "value": "1 赞 / -1 踩",
        "created_at": "时间",
    },
    "post_favorites": {
        "user_id": "收藏用户",
        "post_id": "帖",
        "created_at": "时间",
    },
    "notifications": {
        "id": "主键",
        "user_id": "接收者",
        "actor_id": "触发者",
        "type": "类型（回复 / @ / 系统等）",
        "kind": "类型别名（若有）",
        "post_id": "关联帖",
        "comment_id": "关联评论",
        "payload": "内容 JSON",
        "is_read": "是否已读",
        "read_at": "已读时间",
        "created_at": "时间",
    },
    "community_reports": {
        "id": "主键",
        "reporter_id": "举报人",
        "target_type": "`post` / `comment`",
        "post_id": "关联帖",
        "comment_id": "关联评论（可空）",
        "reason": "原因码",
        "detail": "补充说明",
        "status": "`open` / `resolved` / `dismissed`",
        "resolver_id": "处理人",
        "resolved_by": "处理人（若有）",
        "resolved_at": "处理时间",
        "created_at": "举报时间",
    },
    "ai_usage": {
        "id": "主键",
        "user_id": "调用用户",
        "run_id": "同一次 Agent run 的 UUID",
        "skill": "如 `polish_body` / `summarize_post`",
        "tokens_in": "输入 token",
        "tokens_out": "输出 token",
        "created_at": "记账时间（按日计配额）",
    },
    "app_audit_logs": {
        "id": "主键",
        "created_at": "事件时间",
        "user_id": "操作用户 id（未登录可空）",
        "username": "用户名快照",
        "role": "角色快照 user/admin",
        "action": "动作：auth.login / http.post 等",
        "module": "模块：auth/community/detect/…（由路径前缀推断）",
        "resource": "资源标识（可空）",
        "method": "HTTP 方法",
        "path": "接口路径（去 query）",
        "status_code": "HTTP 状态码",
        "duration_ms": "耗时毫秒",
        "ip": "客户端 IP",
        "user_agent": "UA（截断）",
        "detail": "补充说明（如登录成功、HTTP 502）",
        "request_id": "请求关联 id（可空）",
    },
    "re_factor_catalog_snapshot": {
        "scope": "`primary`（默认十库）或 `all`",
        "content_hash": "库+因子清单 SHA256，用于判断 RE 是否有更新",
        "payload": "完整目录 JSON（libraries + factors）",
        "fetched_at": "最近一次从 RE 拉到内容的时间",
        "fetched_at_unix": "同上，unix 秒",
        "factor_count": "因子条数",
        "library_count": "库个数",
        "updated_at": "最近检查/写入时间（无变更也会刷新）",
    },
    "re_factor_catalog_sync_log": {
        "id": "自增主键",
        "scope": "同步范围",
        "changed": "本次是否写了新快照",
        "content_hash": "当时 hash",
        "factor_count": "因子条数",
        "message": "人读摘要",
        "created_at": "日志时间",
    },
    "detect_projects": {
        "id": "项目 UUID/文本主键（与 user_id 复合）",
        "user_id": "所有者",
        "name": "项目名",
        "factor_name": "因子名",
        "description": "说明",
        "config": "检测参数 JSON",
        "run_count": "历史运行次数",
        "is_sample": "是否示例项目",
        "created_at": "创建",
        "updated_at": "更新",
    },
    "detect_runs": {
        "id": "运行 UUID/文本主键（与 user_id 复合）",
        "user_id": "所有者",
        "project_id": "所属项目 id",
        "factor_name": "因子名",
        "description": "说明",
        "request": "请求参数 JSON",
        "result": "结果摘要 JSON",
        "status": "运行状态（若有）",
        "finished_at": "结束时间",
        "elapsed_sec": "耗时秒",
        "created_at": "时间",
    },
    "strategy_projects": {
        "id": "项目 UUID/文本主键（与 user_id 复合）",
        "user_id": "所有者",
        "name": "项目名",
        "description": "说明",
        "config": "策略配置 JSON",
        "run_count": "历史运行次数",
        "created_at": "创建",
        "updated_at": "更新",
    },
    "strategy_runs": {
        "id": "运行 UUID/文本主键（与 user_id 复合）",
        "user_id": "所有者",
        "project_id": "所属项目 id",
        "name": "运行名 / 策略名",
        "description": "说明",
        "remark": "用户备注（检测报告可编辑）",
        "flagged": "是否标记",
        "request": "请求参数 JSON",
        "result": "结果摘要 JSON",
        "status": "运行状态（若有）",
        "finished_at": "结束时间",
        "elapsed_sec": "耗时秒",
        "created_at": "时间",
    },
    "news_items": {
        "id": "主键",
        "title": "标题",
        "summary": "摘要",
        "body": "正文（电报多为全文；东财市场/政策可抓 HTML；研报为投资要点+#ctx-content，附 PDF 链；巨潮多为 PDF 说明）",
        "published_at": "发布时间（巨潮常为披露日 00:00）",
        "source": "`cls` / `eastmoney` / `cninfo` / `10jqka` / `wallstreetcn` / `bloomberg`（研报·政策调度键 em_research/em_policy，入库仍记 eastmoney）",
        "category": "`flash` / `market` / `announce` / `research` / `policy` / `global`",
        "url": "源站、研报详情或 PDF 链接",
        "symbols": "关联代码 JSONB 数组",
        "themes": "题材标签 JSONB 数组（字典 + 源站）",
        "industries": "行业标签 JSONB 数组（字典命中）",
        "raw_hash": "去重键（同源同条唯一）",
        "is_flash": "是否进电报流",
        "is_featured": "是否头条卡",
        "created_at": "入库时间",
    },
    "factor_dashboard_metrics": {
        "factor_name": "因子名",
        "universe": "股票池，如 CSI300",
        "period": "周期，如 3y",
        "filter_limit_up": "过滤涨停 0/1",
        "filter_suspended": "过滤停牌 0/1",
        "rules_version": "口径版本",
        "name_cn": "中文名",
        "library": "所属库",
        "ic_mean": "IC 均值",
        "ic_std": "IC 标准差",
        "ir": "信息比率",
        "rank_ic": "Rank IC",
        "q1_return": "Q1 收益",
        "q5_return": "Q5 收益",
        "long_short_spread": "多空差",
        "q1_turnover": "Q1 换手",
        "q5_turnover": "Q5 换手",
        "coverage_pool": "池内覆盖率",
        "coverage_total": "总覆盖率",
        "win_rate": "胜率",
        "volatility": "波动",
        "sharpe": "夏普",
        "annual_return": "年化",
        "max_drawdown": "最大回撤",
        "error": "失败原因；成功为空",
        "computed_at": "写入时间",
    },
    "factor_dashboard_verifications": {
        "library_name": "因子库名；`*` 表示从旧 SQLite 导入的全局同名状态",
        "factor_name": "因子名；与 library_name 组成主键",
        "status": "`pending` 待验证 / `passed` 已通过 / `failed` 未通过",
        "note": "备注（可选）",
        "updated_at": "最近更新时间",
        "updated_by": "更新人用户名",
    },
    "factor_dashboard_legacy_imports": {
        "migration_key": "一次性迁移名称（主键）",
        "source_rows": "旧 SQLite 源表行数",
        "imported_rows": "导入 PostgreSQL 的行数",
        "skipped_rows": "因关键字段无效而跳过的行数",
        "completed_at": "迁移完成时间",
    },
}


def _short(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (bytes, memoryview)):
        return f"<bytes {len(v)}>"
    if isinstance(v, (dict, list)):
        s = json.dumps(v, ensure_ascii=False, default=str)
        return s[:MAX_STR] + ("…" if len(s) > MAX_STR else "")
    if not isinstance(v, (str, int, float, bool)):
        s = str(v)
        return s[:MAX_STR] + ("…" if len(s) > MAX_STR else "")
    if isinstance(v, str) and len(v) > MAX_STR:
        return v[:MAX_STR] + "…"
    return v


def _pick_sample(row: dict[str, Any], table: str) -> dict[str, Any]:
    cols = SAMPLE_COLS.get(table)
    if cols:
        raw = {k: row.get(k) for k in cols if k in row}
    else:
        raw = dict(row)
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if k in REDACT_KEYS:
            out[k] = "***"
        else:
            out[k] = _short(v)
    return out


def _pg_dump() -> dict[str, Any]:
    from services.core.db import get_conn

    out: dict[str, Any] = {}
    with get_conn() as conn:
        tables = [
            r["table_name"]
            for r in conn.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = %s AND table_type = %s
                ORDER BY 1
                """,
                ("public", "BASE TABLE"),
            )
        ]
        for t in tables:
            cols = conn.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default,
                       character_maximum_length, udt_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                ("public", t),
            ).fetchall()
            pk = [
                r["column_name"]
                for r in conn.execute(
                    """
                    SELECT kcu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      ON tc.constraint_name = kcu.constraint_name
                     AND tc.table_schema = kcu.table_schema
                    WHERE tc.table_schema = %s AND tc.table_name = %s
                      AND tc.constraint_type = %s
                    ORDER BY kcu.ordinal_position
                    """,
                    ("public", t, "PRIMARY KEY"),
                )
            ]
            cnt = conn.execute(f'SELECT COUNT(*) AS c FROM "{t}"').fetchone()["c"]
            try:
                rows = conn.execute(f'SELECT * FROM "{t}" LIMIT {SAMPLE_N}').fetchall()
            except Exception as exc:  # noqa: BLE001
                rows = [{"_error": str(exc)}]
            out[t] = {
                "count": int(cnt),
                "pk": pk,
                "columns": [dict(c) for c in cols],
                "samples": [_pick_sample(dict(r), t) for r in rows],
            }
    return out


def _pg_type(c: dict[str, Any]) -> str:
    dt = c.get("data_type") or c.get("udt_name") or ""
    n = c.get("character_maximum_length")
    return f"{dt}({n})" if n else str(dt)


def render(pg: dict[str, Any]) -> str:
    now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    A: list[str] = []
    a = A.append

    a("# SVQuant 数据库说明")
    a("")
    a(f"> **最后刷新：** {now}（Asia/Shanghai）  ")
    a(
        "> **怎么更新：** 在 `backend` 执行 "
        "`python scripts/refresh_database_docs.py`。"
        "脚本会重写本文件的表清单 / 字段 / 行数 / 样例；"
        "表用途与字段说明改脚本顶部的 `PURPOSES` / `FIELD_HINTS`。"
    )
    a(
        "> **边界：** SVQuant **不存行情 bars**；"
        "因子面板指标与校验状态均保存在 SVQuant PostgreSQL；"
        "账号 / 社区 / 检测 / 策略 / **官方因子目录缓存** "
        "（`re_factor_catalog_*`）/ **KnowledgeHub（`kh_*`）** 在 PostgreSQL。"
        "旧 `kb_*` 已删除，勿再建。"
    )
    a("")
    a("---")
    a("")
    a("## 总览")
    a("")
    a("| 库 | 引擎 | 连接 / 路径 | 表数量 | 用途 |")
    a("|----|------|-------------|--------|------|")
    a(
        f"| **主库** | PostgreSQL | `.env` → `DATABASE_URL`（`svquant`） | "
        f"**{len(pg)}** | 用户、社区、Agent、检测/策略、KnowledgeHub |"
    )
    a(
        "| **因子面板数据** | PostgreSQL | `.env` → `DATABASE_URL` | "
        "`factor_dashboard_metrics` / `factor_dashboard_verifications` / "
        "`factor_dashboard_legacy_imports` | 指标缓存、校验状态与迁移标记 |"
    )
    a("")
    a("### PostgreSQL 表一览")
    a("")
    a("| 表名 | 约行数 | 作用（一句话） |")
    a("|------|--------|----------------|")
    for t in sorted(pg):
        a(f"| `{t}` | {pg[t]['count']} | {PURPOSES.get(t, '—')} |")
    a("")
    a("---")
    a("")
    a("## 怎么查")
    a("")
    a("### PostgreSQL")
    a("")
    a("```sql")
    a("SELECT table_name")
    a("FROM information_schema.tables")
    a("WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")
    a("ORDER BY 1;")
    a("```")
    a("")
    a("```bash")
    a("cd backend")
    a('python -c "from services.core.db import get_conn')
    a("with get_conn() as c:")
    a(
        "  print([r['table_name'] for r in c.execute("
        "\\\"SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1\\\""
        ").fetchall()])\""
    )
    a("```")
    a("")
    a(
        "因子面板指标由 `factor_dashboard_metrics` 保存；旧 `metrics.sqlite` 仅在首次启动迁移时"
        "只读导入，迁移后不再作为运行时数据源。批任务进度仍暂存于 "
        "`backend/output/factor_dashboard/job.json`，待 RE 任务 API 接管后退役。"
    )
    a("")
    a("代码入口：")
    a("")
    a("- 连接：`services/core/db.py`")
    a(
        "- 建表：`auth_store` / `profile_store` / `community_store` / "
        "`agent_store` / `detect_store` / `strategy_store` / `user_factor_store` / "
        "`user_library_store` / `user_strategy_library_store` / "
        "`factor_verification_store` / `factor_dashboard_metrics_store`"
    )
    a("- 面板：`services/factor/dashboard_store.py`")
    a("")
    a(
        "> **不在库内：** AI 因子/策略生成历史目前仅浏览器 `localStorage` "
        "（按 `userId` 隔离 key），未落 Postgres；后续计费对接服务端时再补表。"
    )
    a("")
    a("---")
    a("")
    a("## A. PostgreSQL 表详解")
    a("")

    for t in sorted(pg):
        meta = pg[t]
        a(f"### `{t}`")
        a("")
        a(f"**作用：** {PURPOSES.get(t, '（待补）')}")
        a("")
        pk = ", ".join(f"`{x}`" for x in (meta.get("pk") or [])) or "—"
        a(f"- 主键：{pk}")
        a(f"- 当前行数：约 **{meta['count']}**")
        a("")
        a("| 字段 | 类型 | 可空 | 说明 |")
        a("|------|------|------|------|")
        hints = FIELD_HINTS.get(t, {})
        for c in meta["columns"]:
            name = c["column_name"]
            a(
                f"| `{name}` | `{_pg_type(c)}` | {c.get('is_nullable') or ''} | "
                f"{hints.get(name, '')} |"
            )
        a("")
        if meta.get("samples"):
            a("**样例（脱敏 / 截断）：**")
            a("")
            a("```json")
            a(json.dumps(meta["samples"], ensure_ascii=False, indent=2))
            a("```")
            a("")

    a("---")
    a("")
    a("## 变更记录")
    a("")
    a("| 日期 | 说明 |")
    a("|------|------|")
    a(
        f"| {now[:10]} | 刷新行数/样例；`news_items` 说明补研报·政策（em_research/em_policy→source=eastmoney）；"
        f"PostgreSQL **{len(pg)}** 表 |"
    )
    a(
        "| 2026-08-05 | 刷新：补全用户因子/策略库 4 表 + `user_library_strategies` "
        "入库快照列；`posts.platform_ref`；注明 AI 生成历史暂未落库 |"
    )
    a("| 2026-07-30 | 策略库入库快照列：`source_run_id` / `archive_*`；策略说明 `description` |")
    a("| 2026-09-21 | 因子面板指标与校验状态统一迁入 PostgreSQL；旧 SQLite 仅作一次性只读迁移来源 |")
    a("| 2026-07-28 | 初版：Postgres + 面板 SQLite；含 `factor_verify_status` / `post_votes` |")
    a("")
    return "\n".join(A)


def main() -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    pg = _pg_dump()
    text = render(pg)
    DOCS.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT} ({len(text)} chars, pg={len(pg)})")


if __name__ == "__main__":
    main()
