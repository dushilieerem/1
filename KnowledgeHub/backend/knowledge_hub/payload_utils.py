# -*- coding: utf-8 -*-
"""KnowledgeUnit 渲染预览与结构化分块。"""
from __future__ import annotations

from typing import Any

from knowledge_hub.schemas.knowledge_unit import (
    FIELD_LABELS_ZH,
    KnowledgeUnit,
    knowledge_unit_to_storage_dict,
    parse_knowledge_unit_payload,
)


def _is_nonempty_scalar(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    return True


def _format_list(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items if str(x).strip())


def render_payload_preview(payload: dict[str, Any] | KnowledgeUnit) -> str:
    ku = payload if isinstance(payload, KnowledgeUnit) else parse_knowledge_unit_payload(payload)
    doc = ku.document
    note = ku.research_note
    lines: list[str] = [f"# {doc.title.strip()}", ""]
    if doc.authors:
        lines += ["## 作者", ", ".join(doc.authors), ""]
    if doc.organization:
        lines += ["## 机构", ", ".join(doc.organization), ""]
    if doc.publish_date:
        lines += ["## 发表日期", doc.publish_date, ""]
    if doc.url:
        lines += ["## 链接", doc.url, ""]
    lines += [f"## 文档类型", doc.doc_type, ""]
    if doc.tags:
        lines += ["## 标签", ", ".join(doc.tags), ""]

    def add_section(key: str, label: str, value: Any) -> None:
        if isinstance(value, list):
            if not value:
                return
            lines.extend([f"## {label}", _format_list(value), ""])
        elif _is_nonempty_scalar(value):
            lines.extend([f"## {label}", str(value).strip(), ""])

    add_section("summary", FIELD_LABELS_ZH["summary"], note.summary)
    add_section("background", FIELD_LABELS_ZH["background"], note.background)
    add_section("motivation", FIELD_LABELS_ZH["motivation"], note.motivation)
    add_section("what_it_does", FIELD_LABELS_ZH["what_it_does"], note.what_it_does)
    add_section("key_idea", FIELD_LABELS_ZH["key_idea"], note.key_idea)
    add_section("ml_tech", FIELD_LABELS_ZH["ml_tech"], note.ml_tech)
    add_section("qf_tech", FIELD_LABELS_ZH["qf_tech"], note.qf_tech)
    add_section("data", FIELD_LABELS_ZH["data"], note.data)
    add_section("result", FIELD_LABELS_ZH["result"], note.result)
    add_section("limitation", FIELD_LABELS_ZH["limitation"], note.limitation)
    add_section("conclusion", FIELD_LABELS_ZH["conclusion"], note.conclusion)
    return "\n".join(lines).strip()


def iter_structured_field_chunks(
    payload: dict[str, Any] | KnowledgeUnit,
) -> list[dict[str, Any]]:
    """每个非空字段 → 一条 chunk 描述。"""
    ku = payload if isinstance(payload, KnowledgeUnit) else parse_knowledge_unit_payload(payload)
    title = ku.document.title.strip()
    doc_type = ku.document.doc_type
    doc = ku.document.model_dump()
    note = ku.research_note.model_dump()
    chunks: list[dict[str, Any]] = []
    ordinal = 0

    def append(field: str, body: str, *, section: str) -> None:
        nonlocal ordinal
        text = f"【{title}】\n【字段】{FIELD_LABELS_ZH.get(field, field)}\n{body.strip()}"
        chunks.append(
            {
                "ordinal": ordinal,
                "text": text,
                "meta": {
                    "kind": "structured_field",
                    "field": field,
                    "section": section,
                    "title": title,
                    "doc_type": doc_type,
                },
            }
        )
        ordinal += 1

    # Document 元数据：短字段合并为「文献信息」一块
    meta_lines: list[str] = []
    if doc.get("authors"):
        meta_lines.append(f"作者：{', '.join(doc['authors'])}")
    if doc.get("organization"):
        meta_lines.append(f"机构：{', '.join(doc['organization'])}")
    if doc.get("publish_date"):
        meta_lines.append(f"发表日期：{doc['publish_date']}")
    if doc.get("url"):
        meta_lines.append(f"链接：{doc['url']}")
    meta_lines.append(f"文档类型：{doc.get('doc_type') or 'others'}")
    if doc.get("language"):
        meta_lines.append(f"语言：{doc['language']}")
    if doc.get("tags"):
        meta_lines.append(f"标签：{', '.join(doc['tags'])}")
    if meta_lines:
        append("document_meta", "\n".join(meta_lines), section="document")

    scalar_note = {
        "summary": note.get("summary"),
        "background": note.get("background"),
        "motivation": note.get("motivation"),
        "what_it_does": note.get("what_it_does"),
        "result": note.get("result"),
        "limitation": note.get("limitation"),
        "conclusion": note.get("conclusion"),
    }
    for key, val in scalar_note.items():
        if _is_nonempty_scalar(val):
            append(key, str(val).strip(), section="research_note")

    list_note = {
        "key_idea": note.get("key_idea") or [],
        "ml_tech": note.get("ml_tech") or [],
        "qf_tech": note.get("qf_tech") or [],
        "data": note.get("data") or [],
    }
    for key, items in list_note.items():
        if items:
            append(key, _format_list(items), section="research_note")

    return chunks


def storage_payload_dict(payload: dict[str, Any] | KnowledgeUnit) -> dict[str, Any]:
    ku = payload if isinstance(payload, KnowledgeUnit) else parse_knowledge_unit_payload(payload)
    return knowledge_unit_to_storage_dict(ku)
