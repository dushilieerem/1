# -*- coding: utf-8 -*-
"""Agent A · 信息搜集 I/O 契约（与设计文档对齐）。"""
from __future__ import annotations

from typing import Any, Literal, TypedDict


class TimeWindow(TypedDict, total=False):
    preset: str  # 7d | 30d | 90d
    start: str
    end: str


class GatherSources(TypedDict, total=False):
    news: bool
    report: bool
    paper: bool
    post: bool
    sv_news: bool  # 兼容旧客户端
    web_public: bool


class EvidenceItem(TypedDict, total=False):
    id: str
    source_type: str  # news | report | paper | post
    title: str
    snippet: str
    published_at: str
    url: str | None
    sv_news_id: int | None
    source_label: str
    category: str
    themes: list[str]
    symbols: list[str]
    relevance: float


class GatherRequest(TypedDict, total=False):
    topic: str
    themes: list[str]
    symbols: list[str]
    time_window: TimeWindow
    sources: GatherSources
    max_items: int
    prefer_flash: bool
    language: str
    user_id: int


class DigestBullet(TypedDict):
    text: str
    item_ids: list[str]


class Citation(TypedDict, total=False):
    id: str
    label: str
    url: str | None


class GatherStats(TypedDict, total=False):
    retrieved: int
    after_dedupe: int
    returned: int
    elapsed_ms: int
    source_counts: dict[str, int]


class EvidencePack(TypedDict, total=False):
    ok: bool
    pack_id: str
    query: dict[str, Any]
    items: list[EvidenceItem]
    digest: str
    digest_bullets: list[DigestBullet]
    citations: list[Citation]
    gaps: list[str]
    stats: GatherStats
    warnings: list[str]
    error: str


# ── Agent B · Idea ──────────────────────────────────────────────


class IdeaPreference(TypedDict, total=False):
    focus: Literal["theme", "factor", "risk", "mixed"]
    horizon: Literal["short", "medium"]
    note: str


class IdeaRequest(TypedDict, total=False):
    pack: EvidencePack
    pack_id: str
    preference: IdeaPreference
    max_ideas: int
    user_id: int


class IdeaValidity(TypedDict, total=False):
    regime: Literal["persistent", "event", "structural"]
    suggested_start: str
    suggested_end: str
    why_window: str
    oos_split: str
    decay_notes: str


class FactorSpec(TypedDict, total=False):
    universe: str
    frequency: str
    used_fields: list[str]
    preferred_factor_name: str
    direction: str


class Idea(TypedDict, total=False):
    id: str
    title: str
    thesis: str
    citation_ids: list[str]
    suggested_next: str
    risk_notes: list[str]
    confidence: Literal["low", "mid", "high"]
    convertible: bool
    factor_prompt: str
    factor_spec: FactorSpec
    validity: IdeaValidity


class IdeaBundle(TypedDict, total=False):
    ok: bool
    bundle_id: str
    pack_id: str
    ideas: list[Idea]
    gaps: list[str]
    stats: dict[str, Any]
    warnings: list[str]
    error: str
