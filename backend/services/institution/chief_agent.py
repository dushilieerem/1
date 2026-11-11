# -*- coding: utf-8 -*-
"""机构端 Chief Agent：带只读工具的 bounded agent。

模型负责决定“先看什么、查哪条证据、采信哪个专业输出、结论是什么”；
工具只返回事实/证据/既有专业输出，不替模型下结论。
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from ai.router import available_task, run_task
from ai.router.specs import TaskRequest
from ai.router.tasks.institution import validate_research_memo
from services.core.db import get_conn
from services.institution import doc_layer
from services.institution.research_service import (
    PROFESSIONAL_ROLE_TITLES,
    SIX_DIM_DEFS,
    _peer_summary,
)
from services.marketdata import store as md

MAX_TOOL_ROUNDS = 6
MAX_TOOL_CALLS = 12


def _spec(name: str, description: str, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "additionalProperties": False,
            },
        },
    }


TOOLS_SPEC = [
    _spec("list_specialists", "列出可用的专业 Agent 输出及其门禁/置信度", {}),
    _spec("get_data_profile", "查看当前研究版本的数据完备性、门禁和缺口", {}),
    _spec(
        "get_specialist_output",
        "读取某个专业 Agent 的完整输出（summary/checks/counter/gate/evidence_ids）",
        {"key": {"type": "string", "description": "专业 Agent key"}},
    ),
    _spec(
        "get_financials",
        "读取公司财务序列（营收/利润/现金流/ROE/毛利率等）",
        {"limit": {"type": "integer", "minimum": 1, "maximum": 40}},
    ),
    _spec("get_valuation", "读取当前估值、历史分位和估值模型输出", {}),
    _spec(
        "search_evidence",
        "按关键词检索本案例证据库，返回 evidence id/title/quote/source/grade",
        {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 12},
        },
    ),
    _spec(
        "get_document_extract",
        "读取已复核的文档抽取字段（如 top5_customers/guarantee/pledge_freeze）",
        {"field_key": {"type": "string"}},
    ),
    _spec("get_peer_summary", "读取同业中位数摘要", {}),
]


class ResearchToolContext:
    def __init__(self, case: dict[str, Any], version: dict[str, Any]):
        self.case = case
        self.version = version
        self.symbol = str(case.get("symbol") or "")

    def _specialist(self, key: str) -> dict[str, Any] | None:
        if key == "industry":
            block = self.version.get("industry_analysis")
            return block if isinstance(block, dict) else None
        for dim in self.version.get("six_dim") or []:
            if isinstance(dim, dict) and str(dim.get("key")) == key:
                return dim
        return None

    def list_specialists(self) -> dict[str, Any]:
        rows = []
        industry = self.version.get("industry_analysis")
        if isinstance(industry, dict) and industry:
            rows.append(
                {
                    "key": "industry_overview",
                    "name": "行业分析",
                    "role_title": PROFESSIONAL_ROLE_TITLES["industry_overview"],
                    "gate": industry.get("gate"),
                    "confidence": industry.get("confidence"),
                    "status": industry.get("status"),
                }
            )
        for key, title, _ in SIX_DIM_DEFS:
            dim = self._specialist(key) or {}
            rows.append(
                {
                    "key": key,
                    "name": title,
                    "role_title": PROFESSIONAL_ROLE_TITLES.get(key),
                    "gate": dim.get("gate"),
                    "confidence": dim.get("confidence"),
                    "status": dim.get("status"),
                }
            )
        return {"ok": True, "items": rows}

    def get_data_profile(self) -> dict[str, Any]:
        rows = []
        industry = self.version.get("industry_analysis")
        if isinstance(industry, dict) and industry:
            rows.append(
                {
                    "key": "industry_overview",
                    "gate": industry.get("gate"),
                    "data_completeness": industry.get("data_completeness"),
                    "data_gaps": industry.get("data_gaps"),
                }
            )
        for key, title, _ in SIX_DIM_DEFS:
            dim = self._specialist(key) or {}
            rows.append(
                {
                    "key": key,
                    "name": title,
                    "gate": dim.get("gate"),
                    "confidence": dim.get("confidence"),
                    "data_completeness": dim.get("data_completeness"),
                    "data_gaps": dim.get("data_gaps"),
                }
            )
        return {
            "ok": True,
            "version_no": self.version.get("version_no"),
            "conclusion": self.version.get("conclusion"),
            "items": rows,
        }

    def get_specialist_output(self, key: str) -> dict[str, Any]:
        dim = self._specialist(key)
        if not dim:
            return {"ok": False, "error": f"没有专业输出：{key}"}
        return {
            "ok": True,
            "key": key,
            "summary": dim.get("summary"),
            "checks": dim.get("checks"),
            "counter": dim.get("counter"),
            "impact": dim.get("impact"),
            "data_used": dim.get("data_used"),
            "gate": dim.get("gate"),
            "confidence": dim.get("confidence"),
            "evidence_ids": dim.get("evidence_ids") or dim.get("direct_evidence_ids"),
            "rating_benchmark": dim.get("rating_benchmark"),
            "data_completeness": dim.get("data_completeness"),
            "data_gaps": dim.get("data_gaps"),
        }

    def get_financials(self, limit: int = 8) -> dict[str, Any]:
        rows = md.financials(self.symbol, limit=max(1, min(int(limit or 8), 40)))
        return {"ok": True, "items": rows}

    def get_valuation(self) -> dict[str, Any]:
        return {
            "ok": True,
            "market": md.valuation_latest(self.symbol),
            "percentile": md.valuation_percentile(self.symbol, years=3),
            "model": self.version.get("valuation"),
        }

    def search_evidence(self, query: str, limit: int = 8) -> dict[str, Any]:
        text = str(query or "").strip().lower()
        evidence = [e for e in (self.case.get("evidence") or []) if isinstance(e, dict)]
        if text:
            evidence = [
                e
                for e in evidence
                if text in str(e.get("title") or "").lower()
                or text in str(e.get("quote") or "").lower()
                or text in str(e.get("source") or "").lower()
            ]
        return {
            "ok": True,
            "items": [
                {
                    "id": e.get("id"),
                    "title": e.get("title"),
                    "quote": str(e.get("quote") or "")[:300],
                    "source": e.get("source"),
                    "grade": e.get("grade"),
                    "as_of": e.get("as_of"),
                }
                for e in evidence[: max(1, min(int(limit or 8), 12))]
            ],
        }

    def get_document_extract(self, field_key: str) -> dict[str, Any]:
        as_of = self.version.get("cutoff") or date.today().isoformat()
        with get_conn() as conn:
            data = doc_layer.load_doc_extracts(conn, self.symbol, as_of)
        fields = data.get("fields") or {}
        key = str(field_key or "").strip()
        if key:
            return {"ok": True, "field": key, "value": fields.get(key)}
        return {"ok": True, "fields": fields}

    def get_peer_summary(self) -> dict[str, Any]:
        industry = md.industry_latest(self.symbol) or {}
        peers = md.industry_peers(self.symbol, industry.get("industry_code")) if industry else []
        return {"ok": True, "summary": _peer_summary(peers)}

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "list_specialists":
                return self.list_specialists()
            if name == "get_data_profile":
                return self.get_data_profile()
            if name == "get_specialist_output":
                return self.get_specialist_output(str(args.get("key") or ""))
            if name == "get_financials":
                return self.get_financials(int(args.get("limit") or 8))
            if name == "get_valuation":
                return self.get_valuation()
            if name == "search_evidence":
                return self.search_evidence(str(args.get("query") or ""), int(args.get("limit") or 8))
            if name == "get_document_extract":
                return self.get_document_extract(str(args.get("field_key") or ""))
            if name == "get_peer_summary":
                return self.get_peer_summary()
            return {"ok": False, "error": f"未知工具：{name}"}
        except Exception as exc:  # noqa: BLE001 - 工具失败返回给模型，不打断研究
            return {"ok": False, "error": str(exc)[:300]}


def _tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for item in message.get("tool_calls") or []:
        fn = item.get("function") or {}
        raw = fn.get("arguments")
        if isinstance(raw, dict):
            args = raw
        else:
            try:
                args = json.loads(str(raw or "{}"))
            except json.JSONDecodeError:
                args = {}
        out.append(
            {
                "id": str(item.get("id") or f"call_{len(out)}"),
                "name": str(fn.get("name") or ""),
                "args": args,
            }
        )
    return out


def run_chief_agent(
    case: dict[str, Any],
    version: dict[str, Any],
    payload: dict[str, Any],
    prompt: str,
) -> dict[str, Any] | None:
    """运行带工具的 Chief Agent；失败返回 None，由调用方回退旧链路。"""
    if not available_task("inst.chief.agent"):
        return None
    context = ResearchToolContext(case, version)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
    ]
    trace: list[dict[str, Any]] = []
    calls_used = 0

    for _round in range(MAX_TOOL_ROUNDS + 1):
        try:
            resp = run_task("inst.chief.agent", messages=messages, tools=TOOLS_SPEC)
        except Exception:  # noqa: BLE001 - Agent 失败回退旧链路
            return None
        calls = _tool_calls(resp.get("message") or {})
        if not calls:
            content = str(resp.get("content") or "").strip()
            if not content:
                return None
            data = validate_research_memo(content, TaskRequest())
            data["agent_trace"] = trace
            return data
        if calls_used + len(calls) > MAX_TOOL_CALLS:
            return None
        messages.append(resp.get("message") or {})
        for call in calls:
            calls_used += 1
            result = context.execute(call["name"], call["args"])
            trace.append(
                {
                    "tool": call["name"],
                    "args": call["args"],
                    "ok": bool(result.get("ok")),
                    "summary": (
                        f"{len(result.get('items') or [])} 条"
                        if isinstance(result.get("items"), list)
                        else str(result.get("error") or "ok")[:120]
                    ),
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str)[:12000],
                }
            )
    return None
