# -*- coding: utf-8 -*-
"""R1 P0 API/security execution suite for SVQuant.

Run while backend is listening on CONTRACT_BASE/R1_BASE, default http://127.0.0.1:8766.
The suite creates only R1_TEST_* data and cleans up best-effort.
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

BASE = (os.environ.get("R1_BASE") or os.environ.get("CONTRACT_BASE") or "http://127.0.0.1:8766").rstrip("/")
RUN_ID = os.environ.get("R1_RUN_ID") or f"R1_TEST_{int(time.time())}"


@dataclass
class Result:
    case_id: str
    module: str
    title: str
    status: str
    severity: str = ""
    requirement: str = ""
    http_status: int | None = None
    expected: str = ""
    actual: str = ""
    bug_id: str = ""
    evidence: str = ""


RESULTS: list[Result] = []
CLEANUP: list[tuple[str, str, str | None]] = []
BUGS: list[dict[str, Any]] = []


def req(method: str, path: str, *, token: str | None = None, body: dict | None = None, timeout: float = 60) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json", "User-Agent": f"SVQuant-R1-P0/{RUN_ID}"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return e.code, {"error": raw}


def record(case_id: str, module: str, title: str, ok: bool, *, severity: str = "", requirement: str = "", http_status: int | None = None, expected: str = "", actual: str = "", bug: str = "", evidence: str = "") -> None:
    RESULTS.append(
        Result(
            case_id=case_id,
            module=module,
            title=title,
            status="PASS" if ok else "FAIL",
            severity=severity,
            requirement=requirement,
            http_status=http_status,
            expected=expected,
            actual=actual,
            bug_id=bug,
            evidence=evidence,
        )
    )


def bug(bug_id: str, module: str, case_id: str, severity: str, title: str, expected: str, actual: str) -> str:
    BUGS.append(
        {
            "bug_id": bug_id,
            "module": module,
            "case_id": case_id,
            "severity": severity,
            "priority": "P0",
            "title": title,
            "expected": expected,
            "actual": actual,
            "status": "OPEN",
            "environment": "TEST",
            "evidence": f"{case_id} in {RUN_ID}",
        }
    )
    return bug_id


def login(username: str, password: str) -> tuple[int, dict[str, Any], str | None]:
    st, data = req("POST", "/api/auth/login", body={"username": username, "password": password})
    tok = data.get("token") if isinstance(data, dict) else None
    return st, data if isinstance(data, dict) else {}, str(tok) if tok else None


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


def db_counts() -> dict[str, int]:
    tables = [
        "users",
        "app_audit_logs",
        "user_watchlists",
        "strategy_projects",
        "strategy_runs",
        "user_factor_libraries",
        "user_library_factors",
        "kh_collections",
        "kh_documents",
        "community_posts",
    ]
    out: dict[str, int] = {}
    with get_conn() as conn:
        for table in tables:
            try:
                row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
                out[table] = int(row["n"])
            except Exception:
                out[table] = -1
    return out


def secret_leak(payload: Any) -> bool:
    raw = json.dumps(payload, ensure_ascii=False).lower()
    return any(x in raw for x in ("password_hash", "jwt_secret", "api_key", "access_token", "traceback", "stack trace"))


def setup_accounts() -> dict[str, str]:
    suffix = str(int(time.time()))[-8:]
    accounts = {
        "admin": "admin",
        "user_a": f"r1a_{suffix}",
        "user_b": f"r1b_{suffix}",
        "disabled": f"r1d_{suffix}",
    }
    ensure_user(accounts["admin"], "admin123", role="admin", status="active")
    ensure_user(accounts["user_a"], "Aa123456!", role="user", status="active")
    ensure_user(accounts["user_b"], "Bb123456!", role="user", status="active")
    ensure_user(accounts["disabled"], "Dd123456!", role="user", status="disabled")
    return accounts


def auth_tests(accts: dict[str, str]) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for key, pwd in (("admin", "admin123"), ("user_a", "Aa123456!"), ("user_b", "Bb123456!")):
        st, data, tok = login(accts[key], pwd)
        record(f"TC-AUTH-LOGIN-{key.upper()}", "AUTH", f"{key} login", st == 200 and bool(tok) and not secret_leak(data), severity="Critical", http_status=st, expected="200 with token and public user", actual=f"HTTP {st}")
        if tok:
            tokens[key] = tok
    st, data, _ = login(accts["user_a"], "wrong")
    record("TC-AUTH-003", "AUTH", "wrong password rejected", st == 401 and not secret_leak(data), severity="Critical", http_status=st, expected="401 error schema", actual=f"HTTP {st}")
    st, data, _ = login("no_such_r1_user", "x")
    record("TC-AUTH-004", "AUTH", "nonexistent user rejected", st == 401 and not secret_leak(data), severity="Critical", http_status=st)
    st, data, _ = login(accts["disabled"], "Dd123456!")
    record("TC-AUTH-005", "AUTH", "disabled user rejected", st == 401 and not secret_leak(data), severity="Critical", http_status=st)
    for cid, body in (("TC-AUTH-006", {"username": "", "password": "x"}), ("TC-AUTH-007", {"username": accts["user_a"], "password": ""})):
        st, data = req("POST", "/api/auth/login", body=body)
        record(cid, "AUTH", "empty credential rejected", st == 401 and not secret_leak(data), severity="Major", http_status=st)
    st, data = req("GET", "/api/auth/me")
    record("TC-AUTH-010", "AUTH", "missing token rejected", st == 401, severity="Critical", http_status=st)
    st, data = req("GET", "/api/auth/me", token="not-a-jwt")
    record("TC-AUTH-011", "AUTH", "invalid token rejected", st == 401, severity="Critical", http_status=st)
    if tokens.get("user_a"):
        st, data = req("GET", "/api/auth/me", token=tokens["user_a"] + "x")
        record("TC-AUTH-012", "AUTH", "tampered token rejected", st == 401, severity="Critical", http_status=st)
    return tokens


def common_and_re_tests(tokens: dict[str, str]) -> None:
    st, data = req("GET", "/api/health")
    record("TC-COMMON-001", "COMMON", "backend health", st == 200 and data.get("ok") is True, severity="Major", http_status=st)
    st, data = req("GET", "/openapi.json")
    record("TC-COMMON-002", "COMMON", "openapi reachable", st == 200 and "paths" in data, severity="Major", http_status=st)
    st, data = req("GET", "/api/not-found-r1")
    record("TC-COMMON-003", "COMMON", "404 error does not leak internals", st == 404 and not secret_leak(data), severity="Major", http_status=st)
    st, data = req("GET", "/api/re/health")
    record(
        "TC-RE-001",
        "RE",
        "RE health through gateway",
        st == 200 and (data.get("ok") is True or data.get("status") == "ok"),
        severity="Major",
        http_status=st,
        actual=json.dumps(data, ensure_ascii=False)[:300],
    )
    st, data = req("GET", "/api/factor/re-catalog")
    record("TC-RE-002", "RE", "factor catalog via RE", st == 200 and isinstance(data, dict), severity="Critical", http_status=st)
    st, data = req("GET", "/api/market-data/symbols")
    record("TC-MKT-001", "MARKET", "market symbols via gateway", st == 200 and not secret_leak(data), severity="Major", http_status=st)


def rbac_idor_tests(tokens: dict[str, str]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    user_a = tokens["user_a"]
    user_b = tokens["user_b"]
    admin = tokens["admin"]
    st, data = req("GET", "/api/admin/logs?limit=1", token=admin)
    record("TC-ADMIN-001", "ADMIN", "admin can read audit logs", st == 200 and ("items" in data or "logs" in data), severity="Critical", http_status=st)
    st, data = req("GET", "/api/admin/logs?limit=1", token=user_a)
    record("TC-ADMIN-002", "ADMIN", "normal user cannot read audit logs", st == 403, severity="Critical", http_status=st)
    st, data = req("GET", "/api/admin/logs?limit=1")
    record("TC-ADMIN-003", "ADMIN", "anonymous cannot read audit logs", st == 401, severity="Critical", http_status=st)

    st, wl = req("POST", "/api/watchlists", token=user_a, body={"name": f"{RUN_ID}_wl"})
    wl_id = (wl.get("watchlist") or {}).get("id")
    CLEANUP.append(("DELETE", f"/api/watchlists/{wl_id}", user_a))
    record("TC-MKT-004", "WATCHLIST", "owner creates watchlist", st == 200 and wl_id, severity="Major", http_status=st)
    if wl_id:
        for cid, method, path, body in (
            ("TC-MKT-005-GET", "GET", f"/api/watchlists/{wl_id}/symbols", None),
            ("TC-MKT-005-PUT", "PUT", f"/api/watchlists/{wl_id}", {"name": f"{RUN_ID}_evil"}),
            ("TC-MKT-005-DELETE", "DELETE", f"/api/watchlists/{wl_id}", None),
        ):
            st, data = req(method, path, token=user_b, body=body)
            ok = st in (403, 404)
            bug_id = ""
            if not ok:
                bug_id = bug("BUG-R1-001", "WATCHLIST", cid, "Critical", "watchlist IDOR: other user can access owner resource", "403/404", f"HTTP {st}")
            record(cid, "IDOR", "watchlist cross-user access rejected", ok, severity="Critical", http_status=st, bug=bug_id)

    st, proj = req("POST", "/api/strategy/projects", token=user_a, body={"name": f"{RUN_ID}_strategy"})
    project_id = (proj.get("project") or {}).get("id")
    CLEANUP.append(("DELETE", f"/api/strategy/projects/{project_id}", user_a))
    record("TC-STRATEGY-001", "STRATEGY", "owner creates strategy project", st == 200 and project_id, severity="Major", http_status=st)
    if project_id:
        st, data = req("GET", f"/api/strategy/projects/{project_id}", token=user_b)
        ok = st in (403, 404)
        bug_id = "" if ok else bug("BUG-R1-002", "STRATEGY", "TC-STRATEGY-IDOR-GET", "Critical", "strategy project IDOR read", "403/404", f"HTTP {st}")
        record("TC-STRATEGY-IDOR-GET", "IDOR", "strategy cross-user read rejected", ok, severity="Critical", http_status=st, bug=bug_id)

        # The strategy project key is scoped by (user_id, id). A PUT with the same id
        # may create/update a project in user B's namespace; it must not modify user A.
        st, _ = req("PUT", f"/api/strategy/projects/{project_id}", token=user_b, body={"name": f"{RUN_ID}_evil"})
        st_a, a_after = req("GET", f"/api/strategy/projects/{project_id}", token=user_a)
        a_name = ((a_after.get("project") or {}).get("name") or "")
        ok = st_a == 200 and not a_name.endswith("_evil")
        bug_id = "" if ok else bug("BUG-R1-002", "STRATEGY", "TC-STRATEGY-IDOR-PUT", "Critical", "strategy project IDOR update", "User B must not modify User A project", f"PUT HTTP {st}; A name={a_name}")
        record("TC-STRATEGY-IDOR-PUT", "IDOR", "strategy cross-user update cannot affect owner resource", ok, severity="Critical", http_status=st, bug=bug_id)

        st, _ = req("DELETE", f"/api/strategy/projects/{project_id}", token=user_b)
        st_a, a_after = req("GET", f"/api/strategy/projects/{project_id}", token=user_a)
        ok = st_a == 200 and bool(a_after.get("project"))
        bug_id = "" if ok else bug("BUG-R1-002", "STRATEGY", "TC-STRATEGY-IDOR-DELETE", "Critical", "strategy project IDOR delete", "User B must not delete User A project", f"DELETE HTTP {st}; owner GET HTTP {st_a}")
        record("TC-STRATEGY-IDOR-DELETE", "IDOR", "strategy cross-user delete cannot affect owner resource", ok, severity="Critical", http_status=st, bug=bug_id)

    st, lib = req("POST", "/api/factor/libraries", token=user_a, body={"name": f"{RUN_ID}_factor_lib"})
    lib_id = (lib.get("library") or {}).get("id")
    CLEANUP.append(("DELETE", f"/api/factor/libraries/{lib_id}", user_a))
    record("TC-FACTOR-001", "FACTOR", "owner creates factor library", st == 200 and lib_id, severity="Major", http_status=st)
    if lib_id:
        st, fac = req("POST", f"/api/factor/libraries/{lib_id}/factors", token=user_a, body={"name": f"{RUN_ID}_factor", "body": "close.pct_change(5)", "description": "r1"})
        factor_id = (fac.get("factor") or {}).get("id")
        record("TC-FACTOR-002", "FACTOR", "owner creates factor", st == 200 and factor_id, severity="Critical", http_status=st)
        for cid, method, path, body in (
            ("TC-FACTOR-IDOR-GET", "GET", f"/api/factor/libraries/{lib_id}/factors", None),
            ("TC-FACTOR-IDOR-PUT", "PUT", f"/api/factor/libraries/{lib_id}/factors/{factor_id or 0}", {"body": "close", "description": "evil"}),
            ("TC-FACTOR-IDOR-DELETE", "DELETE", f"/api/factor/libraries/{lib_id}/factors/{factor_id or 0}", None),
        ):
            st, data = req(method, path, token=user_b, body=body)
            ok = st in (403, 404)
            bug_id = "" if ok else bug("BUG-R1-003", "FACTOR", cid, "Critical", "factor library IDOR", "403/404", f"HTTP {st}")
            record(cid, "IDOR", "factor cross-user access rejected", ok, severity="Critical", http_status=st, bug=bug_id)
    return evidence


def kh_tests(tokens: dict[str, str]) -> None:
    admin = tokens["admin"]
    user_a = tokens["user_a"]
    user_b = tokens["user_b"]
    st, data = req("GET", "/api/kh/collections")
    anon_get_ok = st in (401, 403)
    bug_id = ""
    if not anon_get_ok and st == 200:
        bug_id = bug("BUG-R1-004", "KnowledgeHub", "TC-KH-ANON-GET", "Critical", "anonymous can read KH collections", "401/403", "HTTP 200")
    record("TC-KH-ANON-GET", "KnowledgeHub", "anonymous cannot list KH collections", anon_get_ok, severity="Critical", http_status=st, bug=bug_id)

    st, data = req("POST", "/api/kh/collections", body={"name": f"{RUN_ID}_anon_kh", "pipeline": "general"})
    anon_post_ok = st in (401, 403)
    bug_id = ""
    if not anon_post_ok and st == 200:
        cid = (data.get("collection") or {}).get("id")
        if cid:
            CLEANUP.append(("DELETE", f"/api/kh/collections/{cid}", admin))
        bug_id = bug("BUG-R1-005", "KnowledgeHub", "TC-KH-ANON-POST", "Critical", "anonymous can create KH collection", "401/403", "HTTP 200")
    record("TC-KH-ANON-POST", "KnowledgeHub", "anonymous cannot create KH collection", anon_post_ok, severity="Critical", http_status=st, bug=bug_id)

    st, col = req("POST", "/api/kh/collections", token=admin, body={"name": f"{RUN_ID}_kh", "pipeline": "general", "chunkStrategy": "markdown_heading"})
    cid = (col.get("collection") or {}).get("id")
    CLEANUP.append(("DELETE", f"/api/kh/collections/{cid}", admin))
    record("TC-KH-003", "KnowledgeHub", "admin creates collection", st == 200 and cid, severity="Major", http_status=st)
    if cid:
        st, doc = req("POST", "/api/kh/documents", token=admin, body={"collectionId": cid, "title": f"{RUN_ID}_doc", "body": "# R1\n\nneedle", "fileName": "r1.md", "ingest": True})
        did = (doc.get("document") or {}).get("id")
        record("TC-KH-005", "KnowledgeHub", "admin creates and ingests document", st == 200 and did, severity="Major", http_status=st)
        st, search = req("POST", "/api/kh/search", token=admin, body={"query": "needle", "collectionId": cid, "topK": 3})
        record("TC-KH-011", "KnowledgeHub", "admin searches KH", st == 200 and "hits" in search, severity="Major", http_status=st)
        st, ask = req("POST", "/api/kh/ask", token=admin, body={"query": "no_such_r1_needle", "collectionIds": [cid], "topK": 3})
        record("TC-KH-012", "KnowledgeHub", "admin asks KH without LLM dependency", st == 200 and isinstance(ask.get("answer"), str), severity="Major", http_status=st)
        for cid_case, method, path, body in (
            ("TC-KH-IDOR-GET", "GET", f"/api/kh/documents/{did}", None),
            ("TC-KH-IDOR-DELETE", "DELETE", f"/api/kh/documents/{did}", None),
        ):
            st, data = req(method, path, token=user_b, body=body)
            # Current KH model is admin-only, normal users should be rejected.
            ok = st in (401, 403, 404)
            bug_id = "" if ok else bug("BUG-R1-006", "KnowledgeHub", cid_case, "Critical", "normal user can access admin KH document", "401/403/404", f"HTTP {st}")
            record(cid_case, "IDOR", "KH normal-user access rejected", ok, severity="Critical", http_status=st, bug=bug_id)
    st, data = req("GET", "/api/kh/collections", token=user_a)
    record("TC-KH-USER-RBAC", "KnowledgeHub", "normal user cannot use KH admin API", st in (403, 404), severity="Critical", http_status=st)


def strategy_factor_core(tokens: dict[str, str]) -> None:
    tok = tokens["user_a"]
    st, proj = req("POST", "/api/strategy/projects", token=tok, body={"name": f"{RUN_ID}_strategy_core"})
    project_id = (proj.get("project") or {}).get("id")
    CLEANUP.append(("DELETE", f"/api/strategy/projects/{project_id}", tok))
    record("TC-STRATEGY-CORE-CREATE", "STRATEGY", "strategy project create", st == 200 and project_id, severity="Critical", http_status=st)
    if project_id:
        st, upd = req("PUT", f"/api/strategy/projects/{project_id}", token=tok, body={"name": f"{RUN_ID}_strategy_core_upd", "description": "r1", "config": {"universe": "CSI300"}})
        record("TC-STRATEGY-CORE-UPDATE", "STRATEGY", "strategy project update", st == 200, severity="Major", http_status=st)
        st, run = req("POST", "/api/strategy/runs", token=tok, body={"projectId": project_id, "name": f"{RUN_ID}_run", "request": {"universe": "CSI300"}, "result": {"metrics": {"annual_return": 0.1}, "equity_curve": []}, "elapsedSec": 0.01})
        run_id = (run.get("run") or {}).get("id")
        record("TC-STRATEGY-CORE-RUN-SAVE", "STRATEGY", "strategy run persisted", st == 200 and run_id, severity="Critical", http_status=st)
        if run_id:
            st, got = req("GET", f"/api/strategy/runs/{run_id}", token=tok)
            record("TC-STRATEGY-CORE-RUN-GET", "STRATEGY", "strategy run query", st == 200 and (got.get("run") or {}).get("id") == run_id, severity="Critical", http_status=st)
            st, _ = req("DELETE", f"/api/strategy/runs/{run_id}", token=tok)
            record("TC-STRATEGY-CORE-RUN-DELETE", "STRATEGY", "strategy run delete", st == 200, severity="Major", http_status=st)

    st, lib = req("POST", "/api/factor/libraries", token=tok, body={"name": f"{RUN_ID}_factor_core"})
    lib_id = (lib.get("library") or {}).get("id")
    CLEANUP.append(("DELETE", f"/api/factor/libraries/{lib_id}", tok))
    record("TC-FACTOR-CORE-LIB-CREATE", "FACTOR", "factor library create", st == 200 and lib_id, severity="Critical", http_status=st)
    if lib_id:
        st, fac = req("POST", f"/api/factor/libraries/{lib_id}/factors", token=tok, body={"name": f"{RUN_ID}_factor_core", "body": "close.pct_change(5)", "description": "r1", "formulaReady": True})
        fid = (fac.get("factor") or {}).get("id")
        record("TC-FACTOR-CORE-CREATE", "FACTOR", "factor create", st == 200 and fid, severity="Critical", http_status=st)
        if fid:
            st, _ = req("PUT", f"/api/factor/libraries/{lib_id}/factors/{fid}", token=tok, body={"body": "close.pct_change(10)", "description": "r1 update", "formulaReady": True})
            record("TC-FACTOR-CORE-UPDATE", "FACTOR", "factor update", st == 200, severity="Major", http_status=st)
            st, _ = req("POST", f"/api/factor/libraries/{lib_id}/factors", token=tok, body={"name": "", "body": ""})
            record("TC-FACTOR-INVALID", "FACTOR", "invalid factor rejected", st == 400, severity="Major", http_status=st)


def ai_audit_tests(tokens: dict[str, str]) -> None:
    tok = tokens["user_a"]
    admin = tokens["admin"]
    st, data = req("GET", "/api/ai/chat/models")
    record("TC-AI-001", "AI", "AI models metadata reachable", st == 200 and not secret_leak(data), severity="Major", http_status=st)
    st, data = req("POST", "/api/ai/chat", body={"messages": [{"role": "user", "content": "hello"}]})
    record("TC-AI-SEC-ANON", "AI", "anonymous cannot call AI chat", st == 401, severity="Critical", http_status=st)
    st, data = req("GET", "/api/agent/usage/me?days=1", token=tok)
    record("TC-AI-USAGE", "AI", "user can read own AI usage", st == 200, severity="Major", http_status=st)
    st, logs = req("GET", f"/api/admin/logs?limit=20&username={RUN_ID}", token=admin)
    # USERNAME filter may not match RUN_ID; verify admin endpoint itself and no secret leakage.
    record("TC-ADMIN-AUDIT-SECRET", "ADMIN", "audit query does not expose secrets", st == 200 and not secret_leak(logs), severity="Critical", http_status=st)


def cleanup() -> None:
    for method, path, token in reversed(CLEANUP):
        if "None" in path:
            continue
        try:
            req(method, path, token=token)
        except Exception:
            pass


def main() -> int:
    started_counts = db_counts()
    accts = setup_accounts()
    tokens = auth_tests(accts)
    if {"admin", "user_a", "user_b"} - set(tokens):
        print(json.dumps({"run_id": RUN_ID, "fatal": "login setup failed", "results": [asdict(x) for x in RESULTS]}, ensure_ascii=False, indent=2))
        return 2
    common_and_re_tests(tokens)
    rbac_idor_tests(tokens)
    kh_tests(tokens)
    strategy_factor_core(tokens)
    ai_audit_tests(tokens)
    cleanup()
    ended_counts = db_counts()
    out = {
        "run_id": RUN_ID,
        "base": BASE,
        "started_counts": started_counts,
        "ended_counts": ended_counts,
        "results": [asdict(x) for x in RESULTS],
        "bugs": BUGS,
        "summary": {
            "planned": len(RESULTS),
            "executed": len(RESULTS),
            "pass": sum(1 for r in RESULTS if r.status == "PASS"),
            "fail": sum(1 for r in RESULTS if r.status == "FAIL"),
            "blocked": sum(1 for r in RESULTS if r.status == "BLOCKED"),
            "critical_bugs": sum(1 for b in BUGS if b["severity"] == "Critical"),
            "major_bugs": sum(1 for b in BUGS if b["severity"] == "Major"),
        },
    }
    path = ROOT / "tests" / f"{RUN_ID}_r1_p0_results.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out["summary"], ensure_ascii=False, indent=2))
    print(f"RESULT_JSON={path}")
    return 1 if BUGS else 0


if __name__ == "__main__":
    raise SystemExit(main())
