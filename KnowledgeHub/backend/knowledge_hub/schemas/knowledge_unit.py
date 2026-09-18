# -*- coding: utf-8 -*-
"""KnowledgeUnit schema（对齐算法部 KnowledgeUnit.py，Pydantic v2）。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DOC_TYPE_OPTIONS = ("paper", "blog", "report", "code", "news", "others")
DOMAIN_OPTIONS = ("paper",)  # 第一期 UI 领域下拉

FIELD_LABELS_ZH: dict[str, str] = {
    "title": "标题",
    "authors": "作者",
    "organization": "机构",
    "publish_date": "发表日期",
    "url": "链接",
    "doc_type": "文档类型",
    "language": "语言",
    "tags": "标签",
    "summary": "摘要",
    "background": "背景",
    "motivation": "动机",
    "what_it_does": "方法概述",
    "key_idea": "核心思想",
    "ml_tech": "机器学习技术",
    "qf_tech": "量化金融模型",
    "data": "数据",
    "result": "结果",
    "limitation": "局限",
    "conclusion": "结论",
    "document_meta": "文献信息",
}


class Document(BaseModel):
    model_config = ConfigDict(extra="ignore")

    authors: list[str] = Field(default_factory=list, description="作者列表，可空")
    organization: list[str] = Field(default_factory=list, description="机构列表，可空")
    title: str = Field(description="标题")
    publish_date: str | None = None
    url: str | None = None
    doc_type: Literal["paper", "blog", "report", "code", "news", "others"] = "others"
    language: Literal["zh", "en", "other"] = "other"
    tags: list[str] = Field(default_factory=list)

    @field_validator("authors", "organization", "tags", mode="before")
    @classmethod
    def _coerce_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            s = v.strip()
            return [s] if s else []
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return []


class ResearchNote(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str | None = None
    background: str | None = None
    motivation: str | None = None
    what_it_does: str | None = None
    key_idea: list[str] = Field(default_factory=list)
    ml_tech: list[str] = Field(default_factory=list)
    qf_tech: list[str] = Field(default_factory=list)
    data: list[str] = Field(default_factory=list)
    result: str | None = None
    limitation: str | None = None
    conclusion: str | None = None

    @field_validator(
        "key_idea", "ml_tech", "qf_tech", "data", mode="before"
    )
    @classmethod
    def _coerce_note_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            s = v.strip()
            return [s] if s else []
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return []


class KnowledgeUnit(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    document: Document
    research_note: ResearchNote = Field(alias="researchNote")
    schema_version: str = "1.0"


def parse_knowledge_unit_payload(raw: dict[str, Any]) -> KnowledgeUnit:
    """兼容 research_note / researchNote 两种键名。"""
    data = dict(raw or {})
    if "researchNote" in data and "research_note" not in data:
        data["research_note"] = data["researchNote"]
    if "research_note" in data and "researchNote" not in data:
        data["researchNote"] = data["research_note"]
    if "research_note" not in data and "researchNote" not in data:
        data["research_note"] = {}
    if "document" not in data or not isinstance(data.get("document"), dict):
        raise ValueError("payload.document 必填")
    return KnowledgeUnit.model_validate(data)


def knowledge_unit_to_storage_dict(ku: KnowledgeUnit) -> dict[str, Any]:
    d = ku.model_dump(by_alias=False)
    d["research_note"] = d.pop("research_note", ku.research_note.model_dump())
    return d
