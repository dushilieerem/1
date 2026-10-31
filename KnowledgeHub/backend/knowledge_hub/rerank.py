# -*- coding: utf-8 -*-
"""检索结果重排（P1-K05）。

配置 `KH_RERANK_URL`（OpenAI 兼容 /rerank）与 `KH_RERANK_API_KEY` 时调用模型；
未配置或调用失败时用确定性关键词重排兜底，保证检索始终可用。
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

_WORD_RE = re.compile(r"[A-Za-z0-9_]{2,}")
_CJK_RE = re.compile(r"[一-鿿]+")


def _tokens(text: str) -> set[str]:
    """英文按词，中文按 bigram（无分词器时的稳定兜底）。"""
    raw = text or ""
    out = {m.group(0).lower() for m in _WORD_RE.finditer(raw)}
    for run in _CJK_RE.findall(raw):
        if len(run) == 1:
            out.add(run)
        for i in range(len(run) - 1):
            out.add(run[i : i + 2])
    return out


def rerank_hits(query: str, hits: list[dict[str, Any]], *, top_k: int = 8) -> list[dict[str, Any]]:
    url = (os.environ.get("KH_RERANK_URL", "") or "").strip()
    if url:
        try:
            return _remote_rerank(url, query, hits, top_k)
        except Exception:
            pass
    return _lexical_rerank(query, hits, top_k)


def _lexical_rerank(query: str, hits: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    q = _tokens(query)
    out: list[dict[str, Any]] = []
    for hit in hits:
        title = str(hit.get("documentTitle") or "")
        text = str(hit.get("text") or "")
        blob = f"{title}\n{text}".lower()
        overlap = sum(1 for t in q if t in blob)
        title_hits = sum(1 for t in q if t in title.lower())
        # 原分归一（0-1）+ 覆盖度 + 标题命中
        base = float(hit.get("score") or 0)
        combined = base * 0.5 + overlap * 2.0 + title_hits * 1.5
        out.append({**hit, "rerankScore": round(combined, 4), "rerankMode": "lexical"})
    out.sort(key=lambda h: (-float(h.get("rerankScore") or 0), h.get("chunkId") or 0))
    return out[:top_k]


def _remote_rerank(
    url: str, query: str, hits: list[dict[str, Any]], top_k: int
) -> list[dict[str, Any]]:
    api_key = (os.environ.get("KH_RERANK_API_KEY", "") or "").strip()
    payload = {
        "model": (os.environ.get("KH_RERANK_MODEL", "") or "bge-reranker-v2-m3").strip(),
        "query": query,
        "documents": [str(h.get("text") or "") for h in hits],
        "top_n": top_k,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    rows = data.get("results") or data.get("data") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        idx = int(row.get("index", -1))
        if 0 <= idx < len(hits):
            out.append(
                {
                    **hits[idx],
                    "rerankScore": round(float(row.get("relevance_score", 0.0)), 4),
                    "rerankMode": "model",
                }
            )
    if not out:
        raise ValueError("rerank 服务返回空结果")
    out.sort(key=lambda h: -float(h.get("rerankScore") or 0))
    return out[:top_k]
