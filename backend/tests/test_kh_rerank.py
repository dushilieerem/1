# -*- coding: utf-8 -*-
"""P1-K05：检索重排兜底与远程结果解析。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "KnowledgeHub" / "backend"))

from knowledge_hub.rerank import _lexical_rerank  # noqa: E402


def test_lexical_rerank_prefers_title_and_overlap() -> None:
    hits = [
        {"chunkId": 1, "documentTitle": "无关文档", "text": "天气 心情", "score": 9.0},
        {"chunkId": 2, "documentTitle": "动量因子研究", "text": "动量 因子 回测 说明", "score": 1.0},
    ]
    out = _lexical_rerank("动量因子怎么回测", hits, top_k=2)
    assert out[0]["chunkId"] == 2
    assert out[0]["rerankMode"] == "lexical"
    assert out[0]["rerankScore"] > out[1]["rerankScore"]


def test_lexical_rerank_respects_top_k() -> None:
    hits = [{"chunkId": i, "documentTitle": "", "text": "x", "score": i} for i in range(10)]
    assert len(_lexical_rerank("x", hits, top_k=3)) == 3
