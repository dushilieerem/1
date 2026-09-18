# -*- coding: utf-8 -*-
"""KnowledgeHub 已就绪接口冒烟（写后清理）。"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8766"
USER = "admin"
PASS = "admin123"


def req(method: str, path: str, token: str | None = None, body: dict | None = None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(
        BASE + path, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw}
        return e.code, payload


def ok(name: str, status: int, expect: int | tuple = 200) -> bool:
    allowed = expect if isinstance(expect, tuple) else (expect,)
    passed = status in allowed
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {name}  HTTP {status}")
    return passed


def main() -> int:
    results: list[bool] = []
    print("=== KnowledgeHub API smoke ===")

      # 公开文档
    st, spec = req("GET", "/api/kh/openapi.json")
    results.append(ok("GET /openapi.json (public)", st) and bool(spec.get("paths")))

    try:
        with urllib.request.urlopen(BASE + "/api/kh/docs", timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            results.append(
                ok(
                    "GET /docs Swagger HTML",
                    200 if ("swagger" in html.lower() and resp.status == 200) else 500,
                )
            )
    except Exception as exc:
        print(f"  [FAIL] GET /docs Swagger HTML  {exc}")
        results.append(False)

    st, login = req("POST", "/api/auth/login", body={"username": USER, "password": PASS})
    results.append(ok("login", st))
    token = login.get("token")
    if not token:
        print("NO TOKEN", login)
        return 1

    st, meta = req("GET", "/api/kh/meta", token)
    results.append(ok("GET /meta", st) and bool(meta.get("pipelines")))

    st, cols = req("GET", "/api/kh/collections", token)
    results.append(ok("GET /collections", st))

    st, created = req(
        "POST",
        "/api/kh/collections",
        token,
        {
            "name": f"_smoke_{__import__('time').time_ns() % 100000}",
            "pipeline": "general",
            "chunkStrategy": "markdown_heading",
        },
    )
    results.append(ok("POST /collections", st))
    cid = (created.get("collection") or {}).get("id")
    if not cid:
        print("no collection id", created)
        return 1

    st, renamed = req("PUT", f"/api/kh/collections/{cid}", token, {"name": f"smoke_renamed_{cid}"})
    results.append(ok("PUT /collections/{id}", st) and (renamed.get("collection") or {}).get("name", "").startswith("smoke_"))

    st, doc = req(
        "POST",
        "/api/kh/documents",
        token,
        {
            "collectionId": cid,
            "title": "smoke_doc",
            "body": "# smoke\n\n### alpha_smoke\n\nmomentum factor hello\n",
            "fileName": "smoke.md",
            "ingest": True,
        },
    )
    results.append(ok("POST /documents (ingest)", st))
    did = (doc.get("document") or {}).get("id")
    chunk_n = (doc.get("document") or {}).get("chunkCount") or 0

    st, docs = req("GET", f"/api/kh/collections/{cid}/documents", token)
    results.append(ok("GET /collections/{id}/documents", st) and len(docs.get("documents") or []) >= 1)

    st, got = req("GET", f"/api/kh/documents/{did}", token)
    results.append(ok("GET /documents/{id}", st) and bool((got.get("document") or {}).get("body")))

    st, chunks = req("GET", f"/api/kh/documents/{did}/chunks", token)
    results.append(ok("GET /documents/{id}/chunks", st) and len(chunks.get("chunks") or []) >= 1)

    st, renamed_doc = req("PUT", f"/api/kh/documents/{did}", token, {"title": "smoke_doc_renamed"})
    results.append(
        ok("PUT /documents/{id}", st)
        and (renamed_doc.get("document") or {}).get("title") == "smoke_doc_renamed"
    )

    st, ing = req("POST", f"/api/kh/documents/{did}/ingest", token, {})
    results.append(ok("POST /documents/{id}/ingest", st) and ing.get("status") == "ready")

    st, search = req(
        "POST",
        "/api/kh/search",
        token,
        {"query": "alpha_smoke", "collectionId": cid, "topK": 5},
    )
    hits = search.get("hits") or []
    results.append(ok("POST /search", st) and len(hits) >= 1)

    st, outline = req("GET", "/api/kh/docs/outline", token)
    results.append(ok("GET /docs/outline", st) and len(outline.get("endpoints") or []) >= 10)

    # ask 应未实现 → 404 not found
    st, _ = req("POST", "/api/kh/ask", token, {"query": "x", "collectionIds": [cid]})
    results.append(ok("POST /ask (expect 404 planned)", st, 404))

    st, _ = req("DELETE", f"/api/kh/documents/{did}", token)
    results.append(ok("DELETE /documents/{id}", st))

    st, _ = req("DELETE", f"/api/kh/collections/{cid}", token)
    results.append(ok("DELETE /collections/{id}", st))

    passed = sum(1 for x in results if x)
    total = len(results)
    print(f"\n=== {passed}/{total} passed ===")
    print(f"(smoke doc chunks after create≈{chunk_n})")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
