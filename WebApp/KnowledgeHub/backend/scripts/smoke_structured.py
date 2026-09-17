#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""KnowledgeHub 结构化入库冒烟测试（需 PostgreSQL + 可选后端）。"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

# WebApp/backend 为 cwd 或 PYTHONPATH
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend"))
KH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in (ROOT, KH):
    if p not in sys.path:
        sys.path.insert(0, p)


def test_payload_utils() -> None:
    from knowledge_hub.payload_utils import iter_structured_field_chunks, render_payload_preview

    payload = {
        "document": {
            "title": "测试论文",
            "authors": [],
            "organization": [],
            "publish_date": "",
            "url": "",
            "doc_type": "paper",
            "language": "zh",
            "tags": [],
        },
        "research_note": {
            "summary": "这是一段用于检索的摘要。",
            "background": "",
            "motivation": "",
            "what_it_does": "",
            "key_idea": ["idea A"],
            "ml_tech": [],
            "qf_tech": [],
            "data": [],
            "result": "",
            "limitation": "",
            "conclusion": "",
        },
        "schema_version": "1.0",
    }
    chunks = iter_structured_field_chunks(payload)
    assert len(chunks) >= 2, chunks
    preview = render_payload_preview(payload)
    assert "测试论文" in preview
    print("[OK] payload_utils chunks=", len(chunks))


def test_schema() -> None:
    from knowledge_hub.schemas.knowledge_unit import parse_knowledge_unit_payload

    ku = parse_knowledge_unit_payload(
        {
            "document": {"title": "T", "doc_type": "blog"},
            "research_note": {},
        }
    )
    assert ku.document.doc_type == "blog"
    print("[OK] schema doc_type=", ku.document.doc_type)


def test_store_integration() -> None:
    from knowledge_hub.store import (
        create_collection,
        create_structured_document,
        delete_collection,
        delete_document,
        ensure_kh_schema,
        list_chunks,
        search_chunks,
    )

    ensure_kh_schema()
    coll = create_collection(
        name="__smoke_structured__",
        description="auto test",
        pipeline="paper",
    )
    doc = None
    try:
        doc = create_structured_document(
            collection_id=int(coll["id"]),
            domain="paper",
            payload={
                "document": {
                    "title": "Smoke Structured Doc",
                    "authors": ["Alice"],
                    "organization": [],
                    "publish_date": "2026",
                    "url": "",
                    "doc_type": "paper",
                    "language": "zh",
                    "tags": ["test"],
                },
                "research_note": {
                    "summary": "Transformer 架构用于序列建模。",
                    "background": "",
                    "motivation": "",
                    "what_it_does": "",
                    "key_idea": [],
                    "ml_tech": ["attention"],
                    "qf_tech": [],
                    "data": [],
                    "result": "",
                    "limitation": "",
                    "conclusion": "",
                },
                "schema_version": "1.0",
            },
            ingest=True,
        )
        assert doc["status"] == "ready", doc
        assert doc["ingestMode"] == "structured"
        chunks = list_chunks(int(doc["id"]))
        assert len(chunks) >= 2, len(chunks)
        res = search_chunks(
            query="Transformer",
            collection_ids=[int(coll["id"])],
            top_k=3,
        )
        assert res["hits"], res
        assert res.get("referencedDocuments"), res
        print("[OK] store integration chunks=", len(chunks), "hits=", len(res["hits"]))
    finally:
        if doc:
            delete_document(int(doc["id"]))
        delete_collection(int(coll["id"]))


def test_http(base: str = "http://127.0.0.1:8766") -> None:
    req = urllib.request.Request(f"{base}/api/kh/meta")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode())
    ids = [s.get("id") for s in data.get("chunkStrategies", [])]
    if "structured_fields" not in ids:
        print("[WARN] http meta 未含 structured_fields（需重启 backend 加载新代码）:", ids[:6])
        return
    print("[OK] http meta structured_fields present")


def main() -> None:
    test_payload_utils()
    test_schema()
    test_store_integration()
    try:
        test_http()
    except (urllib.error.URLError, TimeoutError) as e:
        print("[SKIP] http:", e)
    print("ALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
