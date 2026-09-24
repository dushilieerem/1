# -*- coding: utf-8 -*-
"""R5 KnowledgeHub ask regression suite.

Run while backend is listening on R5_BASE/CONTRACT_BASE, default http://127.0.0.1:8766.
The suite creates only R5_KH_ASK_* data and restores the LLM default model setting.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.auth.auth_store import ensure_schema, hash_password  # noqa: E402
from services.core.db import get_conn  # noqa: E402

BASE = (os.environ.get("R5_BASE") or os.environ.get("CONTRACT_BASE") or "http://127.0.0.1:8766").rstrip("/")
RUN_ID = os.environ.get("R5_RUN_ID") or f"R5_KH_ASK_{int(time.time())}"
NEEDLE = f"{RUN_ID}_NEEDLE_knowledgehub_ask"
OUT = Path(__file__).with_name(f"{RUN_ID}_kh_ask_regression_results.json")


@dataclass
class Result:
    case_id: str
    title: str
    status: str
    http_status: int | None = None
    expected: str = ""
    actual: str = ""
    evidence: str = ""


RESULTS: list[Result] = []
CLEANUP: list[tuple[str, str, str | None]] = []


def req(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 60,
) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json", "User-Agent": f"SVQuant-R5-KH-Ask/{RUN_ID}"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, {"error": raw}


def record(
    case_id: str,
    title: str,
    ok: bool,
    *,
    http_status: int | None = None,
    expected: str = "",
    actual: str = "",
    evidence: str = "",
) -> None:
    RESULTS.append(
        Result(
            case_id=case_id,
            title=title,
            status="PASS" if ok else "FAIL",
            http_status=http_status,
            expected=expected,
            actual=actual,
            evidence=evidence,
        )
    )


def ensure_user(username: str, password: str, *, role: str = "user", status: str = "active") -> None:
    ensure_schema()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO users (username, email, password_hash, role, status, display_name)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (username) DO UPDATE SET
              password_hash = EXCLUDED.password_hash,
              role = EXCLUDED.role,
              status = EXCLUDED.status,
              display_name = EXCLUDED.display_name,
              updated_at = NOW()
            """,
            (username, None, hash_password(password), role, status, username),
        )


def login(username: str, password: str) -> str:
    status, data = req("POST", "/api/auth/login", body={"username": username, "password": password})
    if status != 200 or not isinstance(data, dict) or not data.get("token"):
        raise RuntimeError(f"login failed for {username}: HTTP {status}")
    return str(data["token"])


def backup_llm_default() -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT provider_key, model_name FROM kh_default_models WHERE role_key = 'llm'"
        ).fetchone()
    return dict(row) if row else {}


def clear_llm_default() -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM kh_default_models WHERE role_key = 'llm'")


def set_bad_llm_default(provider_key: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO kh_model_providers (provider_key, display_name, base_url, api_key, models)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (provider_key) DO UPDATE SET
              display_name = EXCLUDED.display_name,
              base_url = EXCLUDED.base_url,
              api_key = EXCLUDED.api_key,
              models = EXCLUDED.models,
              updated_at = NOW()
            """,
            (provider_key, provider_key, "http://127.0.0.1:9/v1", "R5_DUMMY_KEY", json.dumps(["bad-model"])),
        )
        conn.execute(
            """
            INSERT INTO kh_default_models (role_key, provider_key, model_name)
            VALUES ('llm', %s, 'bad-model')
            ON CONFLICT (role_key) DO UPDATE SET
              provider_key = EXCLUDED.provider_key,
              model_name = EXCLUDED.model_name,
              updated_at = NOW()
            """,
            (provider_key,),
        )


def restore_llm_default(original: dict[str, Any], bad_provider_key: str) -> None:
    with get_conn() as conn:
        if original:
            conn.execute(
                """
                INSERT INTO kh_default_models (role_key, provider_key, model_name)
                VALUES ('llm', %s, %s)
                ON CONFLICT (role_key) DO UPDATE SET
                  provider_key = EXCLUDED.provider_key,
                  model_name = EXCLUDED.model_name,
                  updated_at = NOW()
                """,
                (original.get("provider_key") or "", original.get("model_name") or ""),
            )
        else:
            conn.execute("DELETE FROM kh_default_models WHERE role_key = 'llm'")
        conn.execute("DELETE FROM kh_model_providers WHERE provider_key = %s", (bad_provider_key,))


def setup_data(admin_token: str) -> int:
    status, data = req(
        "POST",
        "/api/kh/collections",
        token=admin_token,
        body={"name": f"{RUN_ID}_collection", "pipeline": "general", "chunkStrategy": "markdown_heading"},
    )
    cid = (data.get("collection") or {}).get("id") if isinstance(data, dict) else None
    if status != 200 or not cid:
        raise RuntimeError(f"create collection failed: HTTP {status} {str(data)[:200]}")
    CLEANUP.append(("DELETE", f"/api/kh/collections/{cid}", admin_token))

    status, data = req(
        "POST",
        "/api/kh/documents",
        token=admin_token,
        body={
            "collectionId": cid,
            "title": f"{RUN_ID}_doc",
            "fileName": "r5-kh-ask.md",
            "body": f"# R5 Ask Regression\n\nThe answer needle is {NEEDLE}. KnowledgeHub ask must return grounded content.",
            "ingest": True,
        },
    )
    did = (data.get("document") or {}).get("id") if isinstance(data, dict) else None
    if status != 200 or not did:
        raise RuntimeError(f"create document failed: HTTP {status} {str(data)[:200]}")

    for _ in range(20):
        status, data = req("POST", "/api/kh/search", token=admin_token, body={"query": NEEDLE, "collectionId": cid, "topK": 3})
        if status == 200 and (data.get("hits") or []):
            return int(cid)
        time.sleep(0.5)
    raise RuntimeError(f"search readiness timeout: HTTP {status} {str(data)[:200]}")


def cleanup() -> None:
    for method, path, token in reversed(CLEANUP):
        try:
            req(method, path, token=token, timeout=10)
        except Exception:
            pass
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE username LIKE %s", (f"{RUN_ID}%",))


def main() -> int:
    original_llm = backup_llm_default()
    bad_provider = f"{RUN_ID}_bad_llm"
    exit_code = 0
    try:
        admin_password = "R5AskAdmin123!"
        user_password = "R5AskUser123!"
        admin_name = f"{RUN_ID}_admin"
        user_name = f"{RUN_ID}_user"
        ensure_user(admin_name, admin_password, role="admin")
        ensure_user(user_name, user_password, role="user")
        admin_token = login(admin_name, admin_password)
        user_token = login(user_name, user_password)
        collection_id = setup_data(admin_token)

        clear_llm_default()
        status, data = req(
            "POST",
            "/api/kh/ask",
            token=admin_token,
            body={"query": f"what is {NEEDLE}?", "collectionIds": [collection_id], "topK": 3},
        )
        record(
            "TC-KH-ASK-REGRESSION-001",
            "合法用户 Ask 成功（无 LLM 降级答案）",
            status == 200 and isinstance(data.get("answer"), str) and bool(data.get("hits")),
            http_status=status,
            expected="HTTP 200 with answer and hits",
            actual=f"HTTP {status}",
            evidence=str({"grounded": data.get("grounded"), "llmConfigured": data.get("llmConfigured"), "degraded": data.get("degraded")}),
        )

        status, data = req(
            "POST",
            "/api/kh/ask",
            token=user_token,
            body={"query": f"what is {NEEDLE}?", "collectionIds": [collection_id], "topK": 3},
        )
        record(
            "TC-KH-ASK-REGRESSION-002",
            "无权限用户 Ask 失败",
            status in (401, 403),
            http_status=status,
            expected="HTTP 401/403",
            actual=f"HTTP {status}",
        )

        status, data = req(
            "POST",
            "/api/kh/ask",
            token=admin_token,
            body={"query": f"what is {NEEDLE}?", "collectionIds": [999999999], "topK": 3},
        )
        record(
            "TC-KH-ASK-REGRESSION-003",
            "非法 Collection 返回 404",
            status == 404,
            http_status=status,
            expected="HTTP 404",
            actual=f"HTTP {status}",
            evidence=str(data)[:200],
        )

        status, data = req(
            "POST",
            "/api/kh/ask",
            token=admin_token,
            body={"query": "", "collectionIds": [collection_id], "topK": 3},
        )
        record(
            "TC-KH-ASK-REGRESSION-004",
            "空问题返回 400",
            status == 400,
            http_status=status,
            expected="HTTP 400",
            actual=f"HTTP {status}",
            evidence=str(data)[:200],
        )

        set_bad_llm_default(bad_provider)
        status, data = req(
            "POST",
            "/api/kh/ask",
            token=admin_token,
            body={"query": f"what is {NEEDLE}?", "collectionIds": [collection_id], "topK": 3},
            timeout=20,
        )
        record(
            "TC-KH-ASK-REGRESSION-005",
            "LLM 异常返回明确错误且不 500",
            status == 502 and isinstance(data.get("error"), str) and data.get("code") == "llm_unavailable",
            http_status=status,
            expected="HTTP 502 with llm_unavailable",
            actual=f"HTTP {status}",
            evidence=str({"code": data.get("code"), "hasError": bool(data.get("error"))}),
        )
    except Exception as exc:
        exit_code = 1
        record(
            "TC-KH-ASK-REGRESSION-SETUP",
            "回归测试准备或执行异常",
            False,
            expected="suite completes",
            actual=str(exc)[:300],
        )
    finally:
        try:
            restore_llm_default(original_llm, bad_provider)
        finally:
            cleanup()

    if any(r.status == "FAIL" for r in RESULTS):
        exit_code = 1
    payload = {
        "runId": RUN_ID,
        "base": BASE,
        "total": len(RESULTS),
        "pass": sum(1 for r in RESULTS if r.status == "PASS"),
        "fail": sum(1 for r in RESULTS if r.status == "FAIL"),
        "results": [asdict(r) for r in RESULTS],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
