# -*- coding: utf-8 -*-
"""年报原文 → 治理字段抽取（LLM 读章节页文本）。

分工：数据平台只提供 doc_page_text / section_index（见 services/institution/doc_lake.py），
版式不固定的字段由本模块在分析时读原文抽取：

- 章节 → 字段的映射固定（SECTION_FIELDS），一次调用只抽一节；
- 每条事实必须带 page_no 与原文 quote，quote 在页文本里校验，校验不过只降置信度；
- 结果缓存在 ai_agent_output（scope_key=doc:<doc_id>:<section>），提示词版本变化自然失效；
- 写回 svquant.doc_extract 时默认 review_status=pending，且需显式开启（SVQUANT_DOC_LLM_PERSIST=1）；
- 平台文档层缺失时返回空，不阻断研究生成。
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Any

from ai.router import available_task, run_task
from ai.runtime.agent_store import (
    get_cached_output,
    get_effective_prompt,
    input_hash as agent_input_hash,
    save_output,
)
from services.core.db import get_conn
from services.institution import doc_lake
from services.institution.prompts import DOC_EXTRACT_PROMPT

TASK_ID = "inst.doc_extract"
EXTRACTOR_VERSION = "inst-llm-v1"
ORGANIZATION_ID = 1

SECTION_FIELDS: dict[str, tuple[str, ...]] = {
    "公司治理": ("controller_profile", "board_structure"),
    "股份质押冻结": ("pledge_freeze",),
    "承诺事项": ("commitment_history",),
    "关联交易": ("related_party",),
    "对外担保": ("guarantee",),
    "董监高变动": ("mgmt_change",),
}

FIELD_LABELS: dict[str, str] = {
    "controller_profile": "实控人/董事长履历",
    "board_structure": "董事会结构",
    "pledge_freeze": "质押冻结",
    "related_party": "关联交易与资金占用",
    "guarantee": "对外担保",
    "commitment_history": "承诺兑现记录",
    "mgmt_change": "高管变动",
}

SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "公司治理": ("控股股东", "实际控制人", "董事会", "独立董事", "一致行动"),
    "股份质押冻结": ("质押", "冻结", "解除质押"),
    "承诺事项": ("承诺", "履行"),
    "关联交易": ("关联方", "关联交易", "资金占用"),
    "对外担保": ("担保", "被担保"),
    "董监高变动": ("辞职", "离任", "聘任", "选举", "变动"),
}

MAX_CHARS = 10000


def enabled() -> bool:
    return available_task(TASK_ID) and doc_lake.available()


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _page_map(pages: list[dict[str, Any]]) -> dict[int, str]:
    return {int(p.get("page_no") or 0): _norm(p.get("text")) for p in pages}


def _clip(value: Any, limit: int = 600) -> Any:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, list):
        return [_clip(v, limit) for v in value[:12]]
    if isinstance(value, dict):
        return {k: _clip(v, limit) for k, v in value.items()}
    return value


def _validate(data: Any, section: str, pages: list[dict[str, Any]]) -> dict[str, Any]:
    """校验模型输出：字段白名单、页码存在、quote 能在原文找到。"""
    allowed = SECTION_FIELDS.get(section, ())
    page_text = _page_map(pages)
    out: dict[str, Any] = {"section": section, "found": False, "facts": [], "note": ""}
    if not isinstance(data, dict):
        return out
    out["found"] = bool(data.get("found"))
    out["note"] = str(data.get("note") or "")[:300]
    for item in data.get("facts") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("field_key") or "").strip()
        if key not in allowed:
            continue
        try:
            page_no = int(str(item.get("page_no") or 0))
        except (TypeError, ValueError):
            page_no = 0
        quote = str(item.get("quote") or "").strip()
        quote_ok = bool(page_no in page_text and quote and _norm(quote)[:80] in page_text[page_no])
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence") or 0)))
        except (TypeError, ValueError):
            confidence = 0.0
        if not quote_ok:
            confidence = min(confidence, 0.5)
        if page_no not in page_text:
            continue
        out["facts"].append(
            {
                "field_key": key,
                "value": _clip(item.get("value")),
                "quote": quote[:800],
                "page_no": page_no,
                "confidence": round(confidence, 2),
                "quote_verified": quote_ok,
            }
        )
    return out


def _call_section(payload: dict[str, Any], section: str, *, refresh: bool, org_id: int, actor_member_id: int | None) -> dict[str, Any]:
    system, prompt_version = get_effective_prompt(TASK_ID, DOC_EXTRACT_PROMPT)
    scope_key = f"doc:{payload['doc_id']}:{section}"
    cache_key = agent_input_hash(payload, system)
    if not refresh:
        hit = get_cached_output(TASK_ID, org_id=org_id, scope_key=scope_key, input_hash=cache_key, prompt_version=prompt_version)
        if hit:
            return {"data": hit.get("output") or {}, "cached": True, "engine": hit.get("engine")}
    out = run_task(
        TASK_ID,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ],
        variables={"section": section, "doc_id": payload["doc_id"]},
    )
    data = out.get("data")
    if not isinstance(data, dict):
        content = str(out.get("content") or "")
        try:
            data = json.loads(content) if content.strip().startswith("{") else {}
        except json.JSONDecodeError:
            data = {}
    engine = str(out.get("engine") or "agent")
    if data:
        save_output(
            TASK_ID,
            org_id=org_id,
            scope_key=scope_key,
            input_hash=cache_key,
            prompt_version=prompt_version,
            output=data,
            engine=engine,
            created_by=actor_member_id,
        )
    return {"data": data, "cached": False, "engine": engine}


def extract_section(
    symbol: str,
    section: str,
    *,
    as_of: str | None = None,
    refresh: bool = False,
    org_id: int = ORGANIZATION_ID,
    actor_member_id: int | None = None,
) -> dict[str, Any]:
    """抽一节；文档层没有该节时返回 {"available": False, "reason": ...}。"""
    as_of = (as_of or date.today().isoformat())[:10]
    block = doc_lake.section_text(
        symbol, section, as_of=as_of, max_chars=MAX_CHARS, keywords=SECTION_KEYWORDS.get(section, ())
    )
    if not block:
        return {"available": False, "section": section, "reason": "年报该章节页文本不可用", "facts": []}
    if not available_task(TASK_ID):
        return {"available": False, "section": section, "reason": "AI 未配置", "facts": []}
    payload = {
        "symbol": symbol,
        "section": section,
        "doc_id": block["doc_id"],
        "report_period": block["report_period"],
        "available_time": block["available_time"],
        "truncated": block["truncated"],
        "text": block["text"],
    }
    result = _call_section(payload, section, refresh=refresh, org_id=org_id, actor_member_id=actor_member_id)
    validated = _validate(result.get("data"), section, block["pages"])
    validated.update(
        {
            "available": True,
            "doc_id": block["doc_id"],
            "report_period": block["report_period"],
            "available_time": block["available_time"],
            "cached": result.get("cached"),
            "engine": result.get("engine"),
        }
    )
    return validated


def extract_company(
    symbol: str,
    name: str = "",
    *,
    as_of: str | None = None,
    sections: list[str] | None = None,
    refresh: bool = False,
    org_id: int = ORGANIZATION_ID,
    actor_member_id: int | None = None,
) -> dict[str, Any]:
    """按章节抽一家公司的治理字段；返回已校验事实列表。"""
    as_of = (as_of or date.today().isoformat())[:10]
    blocks = doc_lake.sections(symbol, as_of)
    if not blocks:
        return {"symbol": symbol, "name": name, "available": False, "reason": "文档层未覆盖该标的", "facts": [], "sections": {}}
    wanted = sections or [s for s in doc_lake.SECTIONS if s in blocks]
    facts: list[dict[str, Any]] = []
    out: dict[str, Any] = {}
    for section in wanted:
        if section not in blocks:
            continue
        result = extract_section(
            symbol, section, as_of=as_of, refresh=refresh, org_id=org_id, actor_member_id=actor_member_id
        )
        out[section] = {
            "found": result.get("found"),
            "note": result.get("note"),
            "available": result.get("available"),
            "cached": result.get("cached"),
        }
        for item in result.get("facts") or []:
            facts.append(
                {
                    **item,
                    "symbol": symbol,
                    "doc_id": result.get("doc_id"),
                    "report_period": result.get("report_period"),
                    "available_time": result.get("available_time"),
                    "section": section,
                }
            )
    return {
        "symbol": symbol,
        "name": name,
        "available": True,
        "doc_id": next((r.get("doc_id") for r in facts), (next(iter(blocks.values())).get("doc_id") if blocks else None)),
        "report_period": next((r.get("report_period") for r in facts), None),
        "facts": facts,
        "sections": out,
    }


def field_items(
    symbol: str,
    *,
    as_of: str | None = None,
    refresh: bool = False,
    org_id: int = ORGANIZATION_ID,
    actor_member_id: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """按 doc_layer 的 items 结构返回字段，供 FactPack 合并（review_status=pending）。"""
    result = extract_company(
        symbol, as_of=as_of, refresh=refresh, org_id=org_id, actor_member_id=actor_member_id
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in result.get("facts") or []:
        grouped.setdefault(str(item["field_key"]), []).append(
            {
                "value": item.get("value"),
                "unit": None,
                "report_period": item.get("report_period"),
                "page_no": item.get("page_no"),
                "quote": item.get("quote"),
                "doc_id": item.get("doc_id"),
                "pdf_sha256": None,
                "source_url": None,
                "available_time": item.get("available_time"),
                "confidence": item.get("confidence"),
                "review_status": "pending",
                "reviewed": False,
                "not_applicable": False,
                "extractor_version": EXTRACTOR_VERSION,
            }
        )
    return grouped


def persist_result(result: dict[str, Any], *, org_id: int = ORGANIZATION_ID) -> int:
    """把抽取结果写回 svquant.doc_extract（默认 pending）；需显式开启生产写入。"""
    if not (os.getenv("SVQUANT_DOC_LLM_PERSIST", "0").strip() in {"1", "true", "yes"}):
        return 0
    facts = result.get("facts") or []
    if not facts:
        return 0
    written = 0
    with get_conn() as conn:
        for item in facts:
            conn.execute(
                """
                INSERT INTO svquant.doc_extract
                  (symbol, field_key, field_label, value_text, value_num, unit, report_period,
                   page_no, quote, doc_id, pdf_sha256, source_url, available_time,
                   extractor_version, confidence, review_status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')
                """,
                (
                    item.get("symbol"),
                    item.get("field_key"),
                    FIELD_LABELS.get(str(item.get("field_key")), ""),
                    json.dumps(item.get("value"), ensure_ascii=False),
                    None,
                    None,
                    item.get("report_period"),
                    item.get("page_no"),
                    item.get("quote"),
                    item.get("doc_id"),
                    None,
                    None,
                    item.get("available_time"),
                    EXTRACTOR_VERSION,
                    item.get("confidence"),
                ),
            )
            written += 1
    return written


__all__ = [
    "EXTRACTOR_VERSION",
    "FIELD_LABELS",
    "SECTION_FIELDS",
    "enabled",
    "extract_company",
    "extract_section",
    "field_items",
    "persist_result",
]
