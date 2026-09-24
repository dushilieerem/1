# -*- coding: utf-8 -*-
"""R2 P1 functional/integration execution suite for SVQuant.

Run while backend is listening on R2_BASE/CONTRACT_BASE, default http://127.0.0.1:8766.
The suite creates only R2_TEST_* business data and cleans it up best-effort.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.auth.auth_store import ensure_schema, hash_password  # noqa: E402
from services.core.db import database_url, get_conn  # noqa: E402

BASE = (os.environ.get("R2_BASE") or os.environ.get("CONTRACT_BASE") or "http://127.0.0.1:8766").rstrip("/")
RUN_ID = os.environ.get("R2_RUN_ID") or f"R2_TEST_{int(time.time())}"


@dataclass
class Result:
    case_id: str
    module: str
    title: str
    status: str
    priority: str = "P1"
    severity: str = ""
    requirement: str = ""
    http_status: int | None = None
    expected: str = ""
    actual: str = ""
    bug_id: str = ""
    evidence: str = ""


RESULTS: list[Result] = []
BUGS: list[dict[str, Any]] = []
ARTIFACTS: dict[str, Any] = {}


def req(method: str, path: str, *, token: str | None = None, body: dict | None = None, timeout: float = 60) -> tuple[int, Any, dict[str, str]]:
    data = None
    headers = {"Accept": "application/json", "User-Agent": f"SVQuant-R2-P1/{RUN_ID}"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed: Any
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"raw": raw}
            return resp.status, parsed, dict(resp.headers.items())
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return e.code, parsed, dict(e.headers.items())
    except Exception as exc:
        return 0, {"error": str(exc)}, {}


def record(case_id: str, module: str, title: str, ok: bool, *, severity: str = "", requirement: str = "", http_status: int | None = None, expected: str = "", actual: str = "", bug: str = "", evidence: str = "", priority: str = "P1") -> None:
    RESULTS.append(
        Result(
            case_id=case_id,
            module=module,
            title=title,
            status="PASS" if ok else "FAIL",
            priority=priority,
            severity=severity,
            requirement=requirement,
            http_status=http_status,
            expected=expected,
            actual=actual,
            bug_id=bug,
            evidence=evidence,
        )
    )


def add_bug(bug_id: str, module: str, case_id: str, severity: str, title: str, expected: str, actual: str) -> str:
    BUGS.append(
        {
            "bug_id": bug_id,
            "module": module,
            "case_id": case_id,
            "severity": severity,
            "priority": "P1",
            "title": title,
            "expected": expected,
            "actual": actual,
            "status": "OPEN",
            "environment": "TEST",
            "evidence": f"{case_id} in {RUN_ID}",
        }
    )
    return bug_id


def leak(payload: Any) -> bool:
    raw = json.dumps(payload, ensure_ascii=False).lower()
    return any(x in raw for x in ("password_hash", "jwt_secret", "traceback", "stack trace", "secret=", "apikey="))


def ok_shape(data: Any, key: str | None = None) -> bool:
    return isinstance(data, dict) and (key is None or key in data)


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


def db_user_id(username: str) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM users WHERE username=%s", (username,)).fetchone()
        if not row:
            raise RuntimeError(f"user missing: {username}")
        return int(row["id"])


def db_count(table: str, where: str = "", args: tuple[Any, ...] = ()) -> int:
    sql = f"SELECT COUNT(*) AS n FROM {table}"
    if where:
        sql += f" WHERE {where}"
    with get_conn() as conn:
        row = conn.execute(sql, args).fetchone()
        return int(row["n"]) if row else 0


def login(username: str, password: str) -> str | None:
    st, data, _ = req("POST", "/api/auth/login", body={"username": username, "password": password})
    return str(data.get("token")) if st == 200 and isinstance(data, dict) and data.get("token") else None


def setup_accounts() -> dict[str, Any]:
    suffix = str(int(time.time()))[-8:]
    accounts = {
        "admin": "admin",
        "user_a": f"r2a_{suffix}",
        "user_b": f"r2b_{suffix}",
        "password_a": "Aa123456!",
        "password_b": "Bb123456!",
        "admin_password": "admin123",
    }
    ensure_user(accounts["admin"], accounts["admin_password"], role="admin", status="active")
    ensure_user(accounts["user_a"], accounts["password_a"], role="user", status="active")
    ensure_user(accounts["user_b"], accounts["password_b"], role="user", status="active")
    accounts["admin_id"] = db_user_id(accounts["admin"])
    accounts["user_a_id"] = db_user_id(accounts["user_a"])
    accounts["user_b_id"] = db_user_id(accounts["user_b"])
    accounts["admin_token"] = login(accounts["admin"], accounts["admin_password"])
    accounts["user_a_token"] = login(accounts["user_a"], accounts["password_a"])
    accounts["user_b_token"] = login(accounts["user_b"], accounts["password_b"])
    return accounts


def baseline() -> dict[str, Any]:
    def cmd(args: list[str]) -> str:
        try:
            return subprocess.check_output(args, cwd=REPO, text=True, stderr=subprocess.STDOUT).strip()
        except Exception as exc:
            return f"ERROR: {exc}"

    return {
        "run_id": RUN_ID,
        "base": BASE,
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "branch": cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "commit": cmd(["git", "rev-parse", "--short", "HEAD"]),
        "python": sys.version.split()[0],
        "node": cmd(["node", "-v"]),
        "db": database_url().split("@")[-1],
    }


def cleanup_r2_data(accounts: dict[str, Any]) -> None:
    names = [accounts.get("user_a"), accounts.get("user_b")]
    ids = [accounts.get("user_a_id"), accounts.get("user_b_id")]
    with get_conn() as conn:
        for sql, args in [
            ("DELETE FROM post_favorites WHERE user_id = ANY(%s)", (ids,)),
            ("DELETE FROM post_votes WHERE user_id = ANY(%s)", (ids,)),
            ("DELETE FROM comment_votes WHERE user_id = ANY(%s)", (ids,)),
            ("DELETE FROM community_reports WHERE reporter_id = ANY(%s) OR resolver_id = ANY(%s)", (ids, ids)),
            ("DELETE FROM post_comments WHERE author_id = ANY(%s) OR body LIKE %s", (ids, f"{RUN_ID}%")),
            ("DELETE FROM posts WHERE author_id = ANY(%s) OR title LIKE %s", (ids, f"{RUN_ID}%")),
            ("DELETE FROM user_watchlist_symbols WHERE watchlist_id IN (SELECT id FROM user_watchlists WHERE user_id = ANY(%s) OR name LIKE %s)", (ids, f"{RUN_ID}%")),
            ("DELETE FROM user_watchlists WHERE user_id = ANY(%s) OR name LIKE %s", (ids, f"{RUN_ID}%")),
            ("DELETE FROM user_library_factors WHERE library_id IN (SELECT id FROM user_factor_libraries WHERE user_id = ANY(%s) OR name LIKE %s)", (ids, f"{RUN_ID}%")),
            ("DELETE FROM user_factor_libraries WHERE user_id = ANY(%s) OR name LIKE %s", (ids, f"{RUN_ID}%")),
            ("DELETE FROM user_library_strategies WHERE library_id IN (SELECT id FROM user_strategy_libraries WHERE user_id = ANY(%s) OR name LIKE %s)", (ids, f"{RUN_ID}%")),
            ("DELETE FROM user_strategy_libraries WHERE user_id = ANY(%s) OR name LIKE %s", (ids, f"{RUN_ID}%")),
            ("DELETE FROM strategy_plaza_items WHERE author_id = ANY(%s) OR title LIKE %s", (ids, f"{RUN_ID}%")),
            ("DELETE FROM strategy_runs WHERE user_id = ANY(%s) OR name LIKE %s", (ids, f"{RUN_ID}%")),
            ("DELETE FROM strategy_projects WHERE user_id = ANY(%s) OR name LIKE %s", (ids, f"{RUN_ID}%")),
            ("DELETE FROM kh_collections WHERE name LIKE %s", (f"{RUN_ID}%",)),
            ("DELETE FROM users WHERE username = ANY(%s)", (names,)),
        ]:
            try:
                conn.execute(sql, args)
            except Exception:
                pass


def entry_and_regression(tokens: dict[str, str]) -> None:
    st, data, _ = req("GET", "/api/health")
    record("TC-R2-ENTRY-001", "ENTRY", "backend health reachable", st == 200 and data.get("ok") is True, severity="Major", http_status=st)
    st, data, _ = req("GET", "/api/re/health")
    record("TC-R2-ENTRY-002", "ENTRY", "ResearchEngine gateway reachable", st == 200 and isinstance(data, dict), severity="Major", http_status=st, actual=json.dumps(data, ensure_ascii=False)[:300])
    st, data, _ = req("GET", "/api/kh/collections")
    record("TC-R2-REG-KH-001", "R1_REGRESSION", "KH anonymous read remains rejected", st == 401, severity="Critical", http_status=st, priority="P0")
    st, data, _ = req("POST", "/api/kh/collections", body={"name": RUN_ID})
    record("TC-R2-REG-KH-002", "R1_REGRESSION", "KH anonymous write remains rejected", st == 401, severity="Critical", http_status=st, priority="P0")
    st, data, _ = req("GET", "/api/kh/collections", token=tokens["user_a"])
    record("TC-R2-REG-KH-003", "R1_REGRESSION", "KH non-admin read remains forbidden", st == 403, severity="Critical", http_status=st, priority="P0")


def auth_profile_tests(accts: dict[str, Any]) -> None:
    token = accts["user_a_token"]
    st, data, _ = req("POST", "/api/auth/register", body={"username": accts["user_a"], "password": "Abc12345!"})
    record("TC-R2-AUTH-001", "AUTH", "duplicate username rejected", st in {400, 409}, severity="Major", http_status=st)
    st, data, _ = req("POST", "/api/auth/register", body={"username": "x", "password": "123"})
    record("TC-R2-AUTH-002", "AUTH", "invalid registration rejected", st == 400, severity="Major", http_status=st)
    st, data, _ = req("POST", "/api/profile/me", token=token, body={"display_name": f"{RUN_ID} 用户A", "bio": "R2 profile"})
    record("TC-R2-AUTH-003", "AUTH", "profile update persists", st == 200 and ok_shape(data, "profile") and not leak(data), severity="Major", http_status=st)
    st, data, _ = req("GET", f"/api/users/{urllib.parse.quote(accts['user_a'])}")
    record("TC-R2-AUTH-004", "AUTH", "public profile can be queried", st == 200 and ok_shape(data, "profile") and not leak(data), severity="Major", http_status=st)
    st, data, _ = req("POST", f"/api/users/{urllib.parse.quote(accts['user_b'])}/follow", token=token, body={})
    record("TC-R2-AUTH-005", "AUTH", "follow user works", st == 200 and ok_shape(data), severity="Minor", http_status=st)
    st, data, _ = req("GET", f"/api/users/{urllib.parse.quote(accts['user_a'])}/following", token=token)
    record("TC-R2-AUTH-006", "AUTH", "following list reflects relationship", st == 200 and ok_shape(data), severity="Minor", http_status=st)
    st, data, _ = req("DELETE", f"/api/users/{urllib.parse.quote(accts['user_b'])}/follow", token=token)
    record("TC-R2-AUTH-007", "AUTH", "unfollow user works", st == 200 and ok_shape(data), severity="Minor", http_status=st)
    st, data, _ = req("GET", f"/api/users/no_such_{RUN_ID}")
    record("TC-R2-AUTH-008", "AUTH", "missing public profile returns 404", st == 404, severity="Minor", http_status=st)


def market_watchlist_tests(tokens: dict[str, str]) -> None:
    token = tokens["user_a"]
    name = f"{RUN_ID}_watch"
    st, data, _ = req("GET", "/api/market-data/symbols?limit=5")
    record("TC-R2-MARKET-001", "MARKET", "market symbols pagination endpoint", st == 200 and isinstance(data, dict), severity="Major", http_status=st)
    st, data, _ = req("GET", "/api/market-data/indices")
    record("TC-R2-MARKET-002", "MARKET", "market indices endpoint", st == 200 and isinstance(data, dict), severity="Major", http_status=st)
    st, data, _ = req("GET", "/api/market-data/daily/INVALID_CODE")
    record("TC-R2-MARKET-003", "MARKET", "invalid daily quote handled", st in {400, 404, 502} or (st == 200 and isinstance(data.get("bars"), list)), severity="Minor", http_status=st)
    st, data, _ = req("POST", "/api/watchlists", token=token, body={"name": name})
    wl_id = (data.get("watchlist") or {}).get("id") if isinstance(data, dict) else None
    record("TC-R2-WATCH-001", "WATCHLIST", "create watchlist", st == 200 and wl_id, severity="Major", http_status=st)
    st, data, _ = req("POST", "/api/watchlists", token=token, body={"name": name})
    record("TC-R2-WATCH-002", "WATCHLIST", "duplicate watchlist rejected", st == 400, severity="Minor", http_status=st)
    st, data, _ = req("POST", "/api/watchlists", token=token, body={"name": ""})
    record("TC-R2-WATCH-003", "WATCHLIST", "empty watchlist name rejected", st == 400, severity="Minor", http_status=st)
    if wl_id:
        st, data, _ = req("POST", f"/api/watchlists/{wl_id}/symbols", token=token, body={"symbol": "000001.SZ", "name": "平安银行"})
        record("TC-R2-WATCH-004", "WATCHLIST", "add symbol to watchlist", st == 200 and ok_shape(data), severity="Major", http_status=st)
        st, data, _ = req("POST", f"/api/watchlists/{wl_id}/symbols/batch", token=token, body={"items": [{"symbol": "000001.SZ"}, {"symbol": "600000.SH", "name": "浦发银行"}]})
        record("TC-R2-WATCH-005", "WATCHLIST", "batch add supports duplicate skip", st == 200 and ok_shape(data), severity="Minor", http_status=st)
        st, data, _ = req("GET", f"/api/watchlists/{wl_id}/symbols", token=token)
        record("TC-R2-WATCH-006", "WATCHLIST", "list watchlist symbols after batch", st == 200 and isinstance(data.get("symbols"), list), severity="Major", http_status=st)
        st, data, _ = req("DELETE", f"/api/watchlists/{wl_id}/symbols/NO_SUCH", token=token)
        record("TC-R2-WATCH-007", "WATCHLIST", "delete missing watchlist symbol handled", st in {400, 404}, severity="Minor", http_status=st)
        st, data, _ = req("DELETE", f"/api/watchlists/{wl_id}", token=token)
        record("TC-R2-WATCH-008", "WATCHLIST", "delete watchlist", st == 200 and ok_shape(data), severity="Major", http_status=st)


def factor_tests(tokens: dict[str, str]) -> None:
    token = tokens["user_a"]
    st, data, headers = req("GET", "/api/factor/index", token=token)
    record("TC-R2-FACTOR-001", "FACTOR", "factor index returns content", st == 200 and (isinstance(data, dict) or isinstance(data, str) or "yaml" in str(headers).lower()), severity="Major", http_status=st)
    st, data, _ = req("GET", "/api/factor/libraries", token=token)
    record("TC-R2-FACTOR-002", "FACTOR", "factor libraries list", st == 200 and isinstance(data.get("libraries"), list), severity="Major", http_status=st)
    lib_name = f"{RUN_ID}_factor_lib"
    st, data, _ = req("POST", "/api/factor/libraries", token=token, body={"name": lib_name})
    lib_id = (data.get("library") or {}).get("id") if isinstance(data, dict) else None
    record("TC-R2-FACTOR-003", "FACTOR", "create factor library", st == 200 and lib_id, severity="Major", http_status=st)
    st, data, _ = req("POST", "/api/factor/libraries", token=token, body={"name": lib_name})
    record("TC-R2-FACTOR-004", "FACTOR", "duplicate factor library rejected", st == 400, severity="Minor", http_status=st)
    if lib_id:
        st, data, _ = req("POST", f"/api/factor/libraries/{lib_id}/factors", token=token, body={"name": f"{RUN_ID}_alpha", "body": "close / open - 1", "description": "r2", "categoryLabel": "动量", "formulaReady": True})
        factor_id = (data.get("factor") or {}).get("id") if isinstance(data, dict) else None
        record("TC-R2-FACTOR-005", "FACTOR", "add factor to user library", st == 200 and factor_id, severity="Major", http_status=st)
        st, data, _ = req("POST", f"/api/factor/libraries/{lib_id}/factors", token=token, body={"name": "", "body": ""})
        record("TC-R2-FACTOR-006", "FACTOR", "invalid factor rejected", st == 400, severity="Major", http_status=st)
        if factor_id:
            st, data, _ = req("PUT", f"/api/factor/libraries/{lib_id}/factors/{factor_id}", token=token, body={"description": "r2 updated", "formulaReady": False})
            record("TC-R2-FACTOR-007", "FACTOR", "update factor metadata", st == 200 and ok_shape(data, "factor"), severity="Major", http_status=st)
        st, data, _ = req("GET", f"/api/factor/libraries/{lib_id}/factors", token=token)
        record("TC-R2-FACTOR-008", "FACTOR", "list factors in user library", st == 200 and isinstance(data.get("factors"), list), severity="Major", http_status=st)
        st, data, _ = req("GET", "/api/factor/file/../secret.py", token=token)
        record("TC-R2-FACTOR-009", "FACTOR", "factor file path traversal rejected", st in {400, 404}, severity="Major", http_status=st)
        st, data, _ = req("DELETE", f"/api/factor/libraries/{lib_id}", token=token)
        record("TC-R2-FACTOR-010", "FACTOR", "delete factor library cascades factors", st == 200 and ok_shape(data), severity="Major", http_status=st)
    st, data, _ = req("GET", "/api/factor/dashboard/status")
    record("TC-R2-FACTOR-011", "FACTOR", "factor dashboard status endpoint", st == 200 and isinstance(data, dict), severity="Minor", http_status=st)
    st, data, _ = req("POST", "/api/factor/custom/trial", token=token, body={"name": f"{RUN_ID}_trial", "body": ""})
    record("TC-R2-FACTOR-012", "FACTOR", "invalid custom trial rejected", st == 400, severity="Minor", http_status=st)


def strategy_tests(tokens: dict[str, str]) -> None:
    token = tokens["user_a"]
    project_id = f"{RUN_ID}_strategy_project"
    st, data, _ = req("POST", "/api/strategy/projects", token=token, body={"id": project_id, "name": f"{RUN_ID} strategy", "config": {"universe": "CSI300", "period": "3m"}, "description": "R2"})
    record("TC-R2-STRATEGY-001", "STRATEGY", "upsert strategy project", st == 200 and ok_shape(data), severity="Major", http_status=st)
    st, data, _ = req("GET", f"/api/strategy/projects/{project_id}", token=token)
    record("TC-R2-STRATEGY-002", "STRATEGY", "get strategy project", st == 200 and ok_shape(data), severity="Major", http_status=st)
    st, data, _ = req("PUT", f"/api/strategy/projects/{project_id}", token=token, body={"name": f"{RUN_ID} strategy updated", "config": {"period": "6m"}})
    record("TC-R2-STRATEGY-003", "STRATEGY", "update strategy project", st == 200 and ok_shape(data), severity="Major", http_status=st)
    st, data, _ = req("POST", "/api/strategy/runs", token=token, body={"project_id": project_id, "name": f"{RUN_ID}_run", "params": {"x": 1}, "result": {"return": 0.12}, "status": "done"})
    run_id = (data.get("run") or data).get("id") if isinstance(data, dict) else None
    record("TC-R2-STRATEGY-004", "STRATEGY", "save strategy run", st == 200 and run_id, severity="Major", http_status=st, actual=json.dumps(data, ensure_ascii=False)[:200])
    if run_id:
        st, data, _ = req("GET", f"/api/strategy/runs/{run_id}", token=token)
        record("TC-R2-STRATEGY-005", "STRATEGY", "get strategy run", st == 200 and ok_shape(data), severity="Major", http_status=st)
        st, data, _ = req("PATCH", f"/api/strategy/runs/{run_id}", token=token, body={"remark": "R2 remark"})
        record("TC-R2-STRATEGY-006", "STRATEGY", "patch strategy run remark", st == 200 and ok_shape(data), severity="Minor", http_status=st)
        st, data, _ = req("PATCH", f"/api/strategy/runs/{run_id}", token=token, body={"flagged": True})
        record("TC-R2-STRATEGY-007", "STRATEGY", "patch strategy run flag", st == 200 and ok_shape(data), severity="Minor", http_status=st)
        st, data, _ = req("PATCH", f"/api/strategy/runs/{run_id}", token=token, body={})
        record("TC-R2-STRATEGY-008", "STRATEGY", "empty strategy run patch rejected", st == 400, severity="Minor", http_status=st)
    st, data, _ = req("GET", f"/api/strategy/projects/{project_id}/runs", token=token)
    record("TC-R2-STRATEGY-009", "STRATEGY", "list project runs", st == 200 and ok_shape(data), severity="Major", http_status=st)
    st, data, _ = req("POST", "/api/strategy/libraries", token=token, body={"name": f"{RUN_ID}_strategy_lib"})
    lib_id = (data.get("library") or {}).get("id") if isinstance(data, dict) else None
    record("TC-R2-STRATEGY-010", "STRATEGY", "create strategy library", st == 200 and lib_id, severity="Major", http_status=st)
    if lib_id:
        st, data, _ = req("POST", f"/api/strategy/libraries/{lib_id}/strategies", token=token, body={"name": f"{RUN_ID}_item", "body": "def run(): return {}", "description": "r2"})
        strat_id = (data.get("strategy") or {}).get("id") if isinstance(data, dict) else None
        record("TC-R2-STRATEGY-011", "STRATEGY", "add strategy to user library", st == 200 and strat_id, severity="Major", http_status=st)
        st, data, _ = req("GET", f"/api/strategy/libraries/{lib_id}/strategies", token=token)
        record("TC-R2-STRATEGY-012", "STRATEGY", "list user strategy library items", st == 200 and isinstance(data.get("strategies"), list), severity="Major", http_status=st)
        st, data, _ = req("DELETE", f"/api/strategy/libraries/{lib_id}", token=token)
        record("TC-R2-STRATEGY-013", "STRATEGY", "delete strategy library", st == 200 and ok_shape(data), severity="Major", http_status=st)
    st, data, _ = req("GET", "/api/strategy/plaza?limit=5")
    record("TC-R2-STRATEGY-014", "STRATEGY", "public strategy plaza list", st == 200 and ok_shape(data), severity="Minor", http_status=st)
    st, data, _ = req("POST", "/api/strategy/plaza", token=token, body={"title": f"{RUN_ID}_plaza", "body": "R2 public strategy", "snapshot": {"ret": 0.1}})
    item_id = (data.get("item") or {}).get("id") if isinstance(data, dict) else None
    record("TC-R2-STRATEGY-015", "STRATEGY", "create plaza item", st == 200 and item_id, severity="Major", http_status=st)
    if item_id:
        st, data, _ = req("DELETE", f"/api/strategy/plaza/{item_id}", token=tokens["user_b"])
        record("TC-R2-STRATEGY-016", "STRATEGY", "other user cannot hide plaza item", st in {403, 404}, severity="Major", http_status=st)
        st, data, _ = req("DELETE", f"/api/strategy/plaza/{item_id}", token=token)
        record("TC-R2-STRATEGY-017", "STRATEGY", "owner can hide plaza item", st == 200, severity="Major", http_status=st)
    if run_id:
        st, data, _ = req("DELETE", f"/api/strategy/runs/{run_id}", token=token)
        record("TC-R2-STRATEGY-018", "STRATEGY", "delete strategy run", st == 200, severity="Minor", http_status=st)
    st, data, _ = req("DELETE", f"/api/strategy/projects/{project_id}", token=token)
    record("TC-R2-STRATEGY-019", "STRATEGY", "delete strategy project", st == 200, severity="Major", http_status=st)


def kh_tests(tokens: dict[str, str]) -> None:
    admin = tokens["admin"]
    user = tokens["user_a"]
    st, data, _ = req("GET", "/api/kh/openapi.json")
    sec = json.dumps(data, ensure_ascii=False)
    record("TC-R2-KH-001", "KNOWLEDGE_HUB", "KH OpenAPI exposes auth security", st == 200 and "BearerAuth" in sec, severity="Major", http_status=st)
    st, data, _ = req("GET", "/api/kh/meta", token=admin)
    record("TC-R2-KH-002", "KNOWLEDGE_HUB", "KH meta admin read", st == 200 and ok_shape(data, "pipelines"), severity="Major", http_status=st)
    st, data, _ = req("POST", "/api/kh/collections", token=admin, body={"name": f"{RUN_ID}_kh", "description": "R2", "pipeline": "general"})
    coll_id = (data.get("collection") or {}).get("id") if isinstance(data, dict) else None
    record("TC-R2-KH-003", "KNOWLEDGE_HUB", "admin creates KH collection", st == 200 and coll_id, severity="Major", http_status=st)
    st, data, _ = req("POST", "/api/kh/collections", token=user, body={"name": f"{RUN_ID}_kh_user"})
    record("TC-R2-KH-004", "KNOWLEDGE_HUB", "normal user cannot create KH collection", st == 403, severity="Critical", http_status=st)
    if coll_id:
        st, data, _ = req("PUT", f"/api/kh/collections/{coll_id}", token=admin, body={"name": f"{RUN_ID}_kh_renamed", "description": "R2 updated"})
        record("TC-R2-KH-005", "KNOWLEDGE_HUB", "admin updates KH collection", st == 200 and ok_shape(data, "collection"), severity="Major", http_status=st)
        st, data, _ = req("POST", "/api/kh/documents", token=admin, body={"collectionId": coll_id, "title": f"{RUN_ID}_doc", "body": "SVQuant R2 knowledge hub content. factor strategy market.", "ingest": True})
        doc_id = (data.get("document") or {}).get("id") if isinstance(data, dict) else None
        record("TC-R2-KH-006", "KNOWLEDGE_HUB", "create and ingest KH document", st == 200 and doc_id, severity="Major", http_status=st)
        if doc_id:
            st, data, _ = req("GET", f"/api/kh/documents/{doc_id}/chunks", token=admin)
            record("TC-R2-KH-007", "KNOWLEDGE_HUB", "list document chunks", st == 200 and isinstance(data.get("chunks"), list), severity="Major", http_status=st)
            st, data, _ = req("POST", "/api/kh/search", token=admin, body={"query": "factor strategy", "collectionIds": [coll_id], "topK": 3})
            record("TC-R2-KH-008", "KNOWLEDGE_HUB", "KH search returns result schema", st == 200 and isinstance(data, dict), severity="Major", http_status=st)
            st, data, _ = req("POST", "/api/kh/search", token=admin, body={"query": "", "collectionIds": [coll_id]})
            record("TC-R2-KH-009", "KNOWLEDGE_HUB", "KH empty search rejected or empty-handled", st in {200, 400}, severity="Minor", http_status=st)
            st, data, _ = req("DELETE", f"/api/kh/documents/{doc_id}", token=admin)
            record("TC-R2-KH-010", "KNOWLEDGE_HUB", "delete KH document", st == 200 and ok_shape(data), severity="Major", http_status=st)
        st, data, _ = req("GET", "/api/kh/documents/not-number", token=admin)
        record("TC-R2-KH-011", "KNOWLEDGE_HUB", "invalid KH document id handled", st in {400, 404}, severity="Minor", http_status=st)
        st, data, _ = req("DELETE", f"/api/kh/collections/{coll_id}", token=admin)
        record("TC-R2-KH-012", "KNOWLEDGE_HUB", "delete KH collection", st == 200 and ok_shape(data), severity="Major", http_status=st)


def ai_agent_tests(accts: dict[str, Any]) -> None:
    admin = accts["admin_token"]
    user = accts["user_a_token"]
    st, data, _ = req("GET", "/api/ai/chat/models")
    record("TC-R2-AI-001", "AI_AGENT", "AI model list endpoint", st == 200 and isinstance(data, dict), severity="Minor", http_status=st)
    st, data, _ = req("GET", "/api/ai/speech/status")
    record("TC-R2-AI-002", "AI_AGENT", "speech status endpoint", st == 200 and isinstance(data, dict), severity="Minor", http_status=st)
    st, data, _ = req("POST", "/api/ai/chat", token=user, body={"content": "missing messages"})
    record("TC-R2-AI-003", "AI_AGENT", "AI chat missing messages rejected", st == 400, severity="Major", http_status=st)
    st, data, _ = req("POST", "/api/ai/speech/transcribe", token=user, body={})
    record("TC-R2-AI-004", "AI_AGENT", "speech missing audio rejected", st == 400, severity="Major", http_status=st)
    st, data, _ = req("GET", "/api/agent/usage/me?days=7", token=user)
    record("TC-R2-AGENT-001", "AI_AGENT", "agent usage me", st == 200 and isinstance(data, dict), severity="Major", http_status=st)
    st, data, _ = req("GET", "/api/agent/usage?days=7", token=user)
    record("TC-R2-AGENT-002", "AI_AGENT", "normal user cannot view admin usage", st == 403, severity="Major", http_status=st)
    st, data, _ = req("GET", "/api/agent/usage?days=7", token=admin)
    record("TC-R2-AGENT-003", "AI_AGENT", "admin usage summary", st == 200 and isinstance(data, dict), severity="Major", http_status=st)
    st, data, _ = req("POST", "/api/agent/usage/quota", token=admin, body={"user_id": accts["user_a_id"], "quota_daily": 20})
    record("TC-R2-AGENT-004", "AI_AGENT", "admin can set AI quota", st == 200 and isinstance(data, dict), severity="Major", http_status=st)
    st, data, _ = req("POST", "/api/agent/usage/quota", token=user, body={"user_id": accts["user_a_id"], "quota_daily": 20})
    record("TC-R2-AGENT-005", "AI_AGENT", "normal user cannot set AI quota", st == 403, severity="Major", http_status=st)
    st, data, _ = req("POST", "/api/agent/runs", token=user, body={"goal": f"{RUN_ID} invalid skills", "skills": "bad"})
    record("TC-R2-AGENT-006", "AI_AGENT", "agent run invalid skills rejected", st == 400, severity="Major", http_status=st)


def community_tests(tokens: dict[str, str]) -> None:
    user_a = tokens["user_a"]
    user_b = tokens["user_b"]
    admin = tokens["admin"]
    st, data, _ = req("POST", "/api/community/posts", token=user_a, body={"title": f"{RUN_ID}_post", "body": "R2 community post", "section": "strategy"})
    post_id = (data.get("post") or data).get("id") if isinstance(data, dict) else None
    record("TC-R2-COMM-001", "COMMUNITY", "create community post", st == 200 and post_id, severity="Major", http_status=st, actual=json.dumps(data, ensure_ascii=False)[:200])
    st, data, _ = req("POST", "/api/community/posts", token=user_a, body={"title": "", "body": "", "section": "bad"})
    record("TC-R2-COMM-002", "COMMUNITY", "invalid community post rejected", st == 400, severity="Major", http_status=st)
    if post_id:
        st, data, _ = req("GET", f"/api/community/posts/{post_id}")
        record("TC-R2-COMM-003", "COMMUNITY", "get community post", st == 200 and ok_shape(data), severity="Major", http_status=st)
        st, data, _ = req("GET", f"/api/community/posts?q={urllib.parse.quote(RUN_ID)}&sort=newest&limit=5")
        record("TC-R2-COMM-004", "COMMUNITY", "list/search community posts", st == 200 and ok_shape(data), severity="Minor", http_status=st)
        st, data, _ = req("POST", f"/api/community/posts/{post_id}/comments", token=user_b, body={"body": f"{RUN_ID} comment"})
        comment_id = (data.get("comment") or data).get("id") if isinstance(data, dict) else None
        record("TC-R2-COMM-005", "COMMUNITY", "create comment", st == 200 and comment_id, severity="Major", http_status=st)
        st, data, _ = req("GET", f"/api/community/posts/{post_id}/comments")
        record("TC-R2-COMM-006", "COMMUNITY", "list comments", st == 200 and ok_shape(data), severity="Major", http_status=st)
        st, data, _ = req("POST", f"/api/community/posts/{post_id}/vote", token=user_b, body={"value": 1})
        record("TC-R2-COMM-007", "COMMUNITY", "vote post", st == 200 and ok_shape(data), severity="Minor", http_status=st)
        if comment_id:
            st, data, _ = req("POST", f"/api/community/comments/{comment_id}/vote", token=user_a, body={"value": 1})
            record("TC-R2-COMM-008", "COMMUNITY", "vote comment", st == 200 and ok_shape(data), severity="Minor", http_status=st)
        st, data, _ = req("POST", f"/api/community/posts/{post_id}/favorite", token=user_b, body={})
        record("TC-R2-COMM-009", "COMMUNITY", "favorite post", st == 200 and ok_shape(data), severity="Minor", http_status=st)
        st, data, _ = req("POST", "/api/community/reports", token=user_b, body={"target_type": "post", "post_id": post_id, "reason": "spam", "detail": "R2"})
        report_id = (data.get("report") or data).get("id") if isinstance(data, dict) else None
        record("TC-R2-COMM-010", "COMMUNITY", "create report", st == 200 and report_id, severity="Major", http_status=st)
        if report_id:
            st, data, _ = req("POST", f"/api/community/reports/{report_id}/resolve", token=user_b, body={"status": "resolved"})
            record("TC-R2-COMM-011", "COMMUNITY", "normal user cannot resolve report", st == 403, severity="Major", http_status=st)
            st, data, _ = req("POST", f"/api/community/reports/{report_id}/resolve", token=admin, body={"status": "resolved"})
            record("TC-R2-COMM-012", "COMMUNITY", "admin resolves report", st == 200 and ok_shape(data), severity="Major", http_status=st)
        st, data, _ = req("PUT", f"/api/community/posts/{post_id}", token=user_b, body={"title": f"{RUN_ID}_hack", "body": "bad", "section": "strategy"})
        record("TC-R2-COMM-013", "COMMUNITY", "other user cannot update post", st == 403, severity="Major", http_status=st)
        st, data, _ = req("DELETE", f"/api/community/posts/{post_id}", token=user_a)
        record("TC-R2-COMM-014", "COMMUNITY", "owner deletes post", st == 200 and ok_shape(data), severity="Major", http_status=st)


def news_admin_tests(tokens: dict[str, str]) -> None:
    st, data, _ = req("GET", "/api/news?limit=5&offset=0")
    record("TC-R2-NEWS-001", "NEWS", "news list pagination", st == 200 and isinstance(data, dict), severity="Minor", http_status=st)
    st, data, _ = req("GET", "/api/news/dict")
    record("TC-R2-NEWS-002", "NEWS", "news dictionary endpoint", st == 200 and isinstance(data, dict), severity="Minor", http_status=st)
    st, data, _ = req("GET", "/api/news/not-a-number")
    record("TC-R2-NEWS-003", "NEWS", "invalid news id handled", st in {400, 404}, severity="Minor", http_status=st)
    st, data, _ = req("POST", "/api/news/ingest", body={"sources": ["unsupported-source"]})
    record("TC-R2-NEWS-004", "NEWS", "unsupported news source rejected", st == 400, severity="Minor", http_status=st)
    st, data, _ = req("GET", "/api/admin/logs?limit=5&writeOnly=true", token=tokens["admin"])
    record("TC-R2-ADMIN-001", "ADMIN_AUDIT", "admin audit write-only query", st == 200 and isinstance(data, dict) and not leak(data), severity="Major", http_status=st)
    st, data, _ = req("GET", "/api/admin/logs?limit=5", token=tokens["user_a"])
    record("TC-R2-ADMIN-002", "ADMIN_AUDIT", "normal user cannot query audit logs", st == 403, severity="Major", http_status=st)
    st, data, _ = req("GET", "/api/admin/logs?limit=500", token=tokens["admin"])
    record("TC-R2-ADMIN-003", "ADMIN_AUDIT", "audit limit upper bound enforced", st in {400, 422}, severity="Minor", http_status=st)


def db_integration_checks(accts: dict[str, Any]) -> None:
    checks = {
        "r2_users_removed_later": db_count("users", "username IN (%s,%s)", (accts["user_a"], accts["user_b"])),
        "kh_r2_collections": db_count("kh_collections", "name LIKE %s", (f"{RUN_ID}%",)),
        "watchlists_r2": db_count("user_watchlists", "name LIKE %s", (f"{RUN_ID}%",)),
        "strategy_projects_r2": db_count("strategy_projects", "name LIKE %s", (f"{RUN_ID}%",)),
        "community_posts_r2": db_count("posts", "title LIKE %s", (f"{RUN_ID}%",)),
    }
    ARTIFACTS["db_post_flow_counts"] = checks
    record("TC-R2-DB-001", "DB_INTEGRATION", "R2 users exist during run", checks["r2_users_removed_later"] == 2, severity="Major", actual=json.dumps(checks, ensure_ascii=False))
    record("TC-R2-DB-002", "DB_INTEGRATION", "owned durable business data cleaned before final cleanup point", checks["kh_r2_collections"] == 0 and checks["watchlists_r2"] == 0 and checks["strategy_projects_r2"] == 0, severity="Major", actual=json.dumps(checks, ensure_ascii=False))


def frontend_static_check() -> None:
    url = os.environ.get("R2_FRONTEND_BASE", "http://127.0.0.1:9530").rstrip("/")
    try:
        with urllib.request.urlopen(url + "/", timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            ok = resp.status == 200 and ("id=\"root\"" in raw or "id='root'" in raw)
            record("TC-R2-FE-001", "FRONTEND", "frontend root serves SPA shell", ok, severity="Major", http_status=resp.status, expected="200 with root node")
    except Exception as exc:
        record("TC-R2-FE-001", "FRONTEND", "frontend root serves SPA shell", False, severity="Major", expected="200 with root node", actual=str(exc), bug=add_bug("BUG-R2-FE-001", "FRONTEND", "TC-R2-FE-001", "Major", "Frontend dev server unavailable during R2 static check", "Frontend root should be reachable", str(exc)))


def classify_failures() -> None:
    n = 1
    existing = {b["case_id"] for b in BUGS}
    for r in RESULTS:
        if r.status != "FAIL" or r.case_id in existing:
            continue
        sev = r.severity or "Major"
        bid = f"BUG-R2-{n:03d}"
        n += 1
        r.bug_id = bid
        add_bug(
            bid,
            r.module,
            r.case_id,
            sev,
            r.title,
            r.expected or "expected condition should hold",
            r.actual or f"HTTP {r.http_status}",
        )


def main() -> int:
    ARTIFACTS["baseline"] = baseline()
    accts = setup_accounts()
    tokens = {
        "admin": accts["admin_token"],
        "user_a": accts["user_a_token"],
        "user_b": accts["user_b_token"],
    }
    missing = [k for k, v in tokens.items() if not v]
    if missing:
        record("TC-R2-ENTRY-000", "ENTRY", f"login tokens missing: {missing}", False, priority="P0", severity="Critical", expected="all test users can login")
    else:
        entry_and_regression(tokens)
        auth_profile_tests(accts)
        market_watchlist_tests(tokens)
        factor_tests(tokens)
        strategy_tests(tokens)
        kh_tests(tokens)
        ai_agent_tests(accts)
        community_tests(tokens)
        news_admin_tests(tokens)
        db_integration_checks(accts)
        frontend_static_check()
    classify_failures()
    cleanup_r2_data(accts)
    ARTIFACTS["cleanup_counts"] = {
        "r2_users": db_count("users", "username IN (%s,%s)", (accts["user_a"], accts["user_b"])),
        "kh_r2_collections": db_count("kh_collections", "name LIKE %s", (f"{RUN_ID}%",)),
        "watchlists_r2": db_count("user_watchlists", "name LIKE %s", (f"{RUN_ID}%",)),
        "strategy_projects_r2": db_count("strategy_projects", "name LIKE %s", (f"{RUN_ID}%",)),
        "community_posts_r2": db_count("posts", "title LIKE %s", (f"{RUN_ID}%",)),
    }
    out = {
        "run_id": RUN_ID,
        "summary": {
            "total": len(RESULTS),
            "passed": sum(1 for r in RESULTS if r.status == "PASS"),
            "failed": sum(1 for r in RESULTS if r.status == "FAIL"),
        },
        "results": [asdict(r) for r in RESULTS],
        "bugs": BUGS,
        "artifacts": ARTIFACTS,
    }
    path = Path(__file__).with_name(f"{RUN_ID}_r2_p1_results.json")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out["summary"], ensure_ascii=False))
    print(str(path))
    return 1 if BUGS else 0


if __name__ == "__main__":
    raise SystemExit(main())
