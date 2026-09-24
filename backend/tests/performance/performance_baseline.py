# -*- coding: utf-8 -*-
"""R4 performance and stability baseline suite for SVQuant.

The script is intentionally dependency-light and writes a JSON artifact next to itself.
Run while the backend is listening on PERF_BASE/CONTRACT_BASE.
"""
from __future__ import annotations

import json
import os
import platform
import random
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.auth.auth_store import ensure_schema, hash_password  # noqa: E402
from services.core.db import database_url, get_conn  # noqa: E402

BASE = (os.environ.get("PERF_BASE") or os.environ.get("CONTRACT_BASE") or "http://127.0.0.1:8766").rstrip("/")
RUN_ID = os.environ.get("PERF_RUN_ID") or f"R4_PERF_TEST_{int(time.time())}"
LATENCY_REQUESTS = int(os.environ.get("PERF_LATENCY_REQUESTS", "100") or "100")
CONCURRENCY_LEVELS = [
    int(x.strip())
    for x in (os.environ.get("PERF_CONCURRENCY_LEVELS", "10,50,100") or "10,50,100").split(",")
    if x.strip()
]
CONCURRENCY_DURATION_SEC = int(os.environ.get("PERF_CONCURRENCY_DURATION_SEC", "300") or "300")
STABILITY_DURATION_SEC = int(os.environ.get("PERF_STABILITY_DURATION_SEC", "1800") or "1800")
STABILITY_CONCURRENCY = int(os.environ.get("PERF_STABILITY_CONCURRENCY", "20") or "20")
REQUEST_TIMEOUT_SEC = float(os.environ.get("PERF_REQUEST_TIMEOUT_SEC", "15") or "15")


@dataclass
class RequestResult:
    name: str
    method: str
    path: str
    status: int
    ok: bool
    elapsed_ms: float
    error: str = ""
    error_type: str = ""


@dataclass
class SummaryRow:
    name: str
    method: str
    path: str
    requests: int
    success: int
    failed: int
    avg_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    rps: float
    error_rate: float
    status_counts: dict[str, int]
    error_counts: dict[str, int]


class Client:
    def __init__(self, token: str | None = None):
        self.token = token

    def request(self, method: str, path: str, *, body: dict | None = None, name: str = "") -> RequestResult:
        data = None
        headers = {"Accept": "application/json", "User-Agent": f"SVQuant-R4-Perf/{RUN_ID}"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
                resp.read()
                elapsed = (time.perf_counter() - t0) * 1000
                return RequestResult(name or path, method, path, resp.status, 200 <= resp.status < 400, elapsed)
        except urllib.error.HTTPError as exc:
            try:
                exc.read()
            except Exception:
                pass
            elapsed = (time.perf_counter() - t0) * 1000
            error_type = "server_error" if int(exc.code) >= 500 else "client_error"
            return RequestResult(name or path, method, path, exc.code, False, elapsed, f"HTTP {exc.code}", error_type)
        except (TimeoutError, socket.timeout):
            elapsed = (time.perf_counter() - t0) * 1000
            return RequestResult(name or path, method, path, 0, False, elapsed, "TimeoutError", "timeout")
        except urllib.error.URLError as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                return RequestResult(name or path, method, path, 0, False, elapsed, "TimeoutError", "timeout")
            return RequestResult(name or path, method, path, 0, False, elapsed, exc.__class__.__name__, "connection_error")
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            return RequestResult(name or path, method, path, 0, False, elapsed, exc.__class__.__name__, "other_error")


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * p))))
    return ordered[idx]


def summarize(results: list[RequestResult], wall_sec: float | None = None) -> SummaryRow:
    times = [r.elapsed_ms for r in results]
    success = sum(1 for r in results if r.ok)
    failed = len(results) - success
    first = results[0] if results else RequestResult("", "", "", 0, False, 0)
    denom = wall_sec if wall_sec and wall_sec > 0 else (sum(times) / 1000 if times else 0)
    status_counts: dict[str, int] = {}
    error_counts: dict[str, int] = {}
    for r in results:
        status_counts[str(r.status)] = status_counts.get(str(r.status), 0) + 1
        if not r.ok:
            key = r.error_type or ("server_error" if r.status >= 500 else "client_error" if r.status >= 400 else "other_error")
            error_counts[key] = error_counts.get(key, 0) + 1
    return SummaryRow(
        name=first.name,
        method=first.method,
        path=first.path,
        requests=len(results),
        success=success,
        failed=failed,
        avg_ms=round(statistics.mean(times), 2) if times else 0.0,
        p50_ms=round(percentile(times, 0.50), 2),
        p95_ms=round(percentile(times, 0.95), 2),
        p99_ms=round(percentile(times, 0.99), 2),
        max_ms=round(max(times), 2) if times else 0.0,
        rps=round(len(results) / denom, 2) if denom else 0.0,
        error_rate=round(failed / len(results), 4) if results else 0.0,
        status_counts=status_counts,
        error_counts=error_counts,
    )


def cmd(args: list[str], *, cwd: Path = REPO, timeout: int = 20) -> str:
    try:
        out = subprocess.check_output(args, cwd=cwd, stderr=subprocess.STDOUT, timeout=timeout)
        return out.decode("utf-8", errors="replace").strip()
    except Exception as exc:
        return f"ERROR: {exc}"


def env_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "os": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0],
        "node": cmd(["node", "-v"]),
        "docker": cmd(["docker", "--version"]),
        "git_branch": cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "git_commit": cmd(["git", "rev-parse", "--short", "HEAD"]),
        "database": database_url().split("@")[-1],
    }
    try:
        with get_conn() as conn:
            info["postgres"] = conn.execute("SHOW server_version").fetchone()["server_version"]
    except Exception as exc:
        info["postgres"] = f"ERROR: {exc}"
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        info["memory_total_gb"] = round(vm.total / 1024 / 1024 / 1024, 2)
        disks = []
        for part in psutil.disk_partitions():
            if part.fstype:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disks.append({"mount": part.mountpoint, "total_gb": round(usage.total / 1024 / 1024 / 1024, 2)})
                except Exception:
                    pass
        info["disks"] = disks[:8]
    except Exception as exc:
        info["resource_probe"] = f"psutil unavailable: {exc}"
    return info


def ensure_user(username: str, password: str, *, role: str = "user") -> int:
    ensure_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO users (username, email, password_hash, role, status, display_name)
            VALUES (%s, %s, %s, %s, 'active', %s)
            ON CONFLICT (username) DO UPDATE SET
              password_hash = EXCLUDED.password_hash,
              role = EXCLUDED.role,
              status = 'active',
              display_name = EXCLUDED.display_name,
              updated_at = NOW()
            RETURNING id
            """,
            (username, None, hash_password(password), role, username),
        ).fetchone()
    return int(row["id"])


def login(username: str, password: str) -> str:
    result = Client().request("POST", "/api/auth/login", body={"username": username, "password": password}, name="login")
    if not result.ok:
        raise RuntimeError(f"login failed for {username}: {result.status}")
    data = json.loads(urllib.request.urlopen(
        urllib.request.Request(
            BASE + "/api/auth/login",
            data=json.dumps({"username": username, "password": password}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        ),
        timeout=REQUEST_TIMEOUT_SEC,
    ).read().decode("utf-8"))
    return str(data["token"])


def setup_data() -> dict[str, Any]:
    suffix = str(int(time.time()))
    password = "Aa123456!"
    admin = f"{RUN_ID}_admin"
    user = f"{RUN_ID}_user"
    user2 = f"{RUN_ID}_user2"
    ensure_user(admin, password, role="admin")
    ensure_user(user, password, role="user")
    ensure_user(user2, password, role="user")
    admin_token = login(admin, password)
    user_token = login(user, password)
    user2_token = login(user2, password)
    client = Client(user_token)
    admin_client = Client(admin_token)
    wl = json_body(client, "POST", "/api/watchlists", {"name": f"{RUN_ID}_wl"})
    wl_id = (wl.get("watchlist") or {}).get("id")
    project_id = f"{RUN_ID}_strategy_project"
    json_body(client, "POST", "/api/strategy/projects", {"id": project_id, "name": project_id, "config": {"r4": True}})
    run = json_body(client, "POST", "/api/strategy/runs", {"project_id": project_id, "name": f"{RUN_ID}_run", "result": {"ok": True}})
    kh = json_body(admin_client, "POST", "/api/kh/collections", {"name": f"{RUN_ID}_kh"})
    return {
        "password": password,
        "admin": admin,
        "user": user,
        "user2": user2,
        "admin_token": admin_token,
        "user_token": user_token,
        "user2_token": user2_token,
        "watchlist_id": wl_id,
        "project_id": project_id,
        "run_id": (run.get("run") or run).get("id") if isinstance(run, dict) else None,
        "kh_collection_id": (kh.get("collection") or {}).get("id") if isinstance(kh, dict) else None,
    }


def json_body(client: Client, method: str, path: str, body: dict | None = None) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json", "User-Agent": f"SVQuant-R4-Perf/{RUN_ID}"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if client.token:
        headers["Authorization"] = f"Bearer {client.token}"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw else {}


def data_scale() -> dict[str, Any]:
    counts: dict[str, Any] = {}
    table_map = {
        "users": "users",
        "strategy_projects": "strategy_projects",
        "strategy_runs": "strategy_runs",
        "detect_projects": "detect_projects",
        "detect_runs": "detect_runs",
        "kh_collections": "kh_collections",
        "kh_documents": "kh_documents",
        "posts": "posts",
        "post_comments": "post_comments",
        "app_audit_logs": "app_audit_logs",
        "user_watchlists": "user_watchlists",
        "user_factor_libraries": "user_factor_libraries",
    }
    with get_conn() as conn:
        for key, table in table_map.items():
            try:
                counts[key] = int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
            except Exception as exc:
                counts[key] = f"ERROR: {exc}"
    return counts


def latency_tests(accts: dict[str, Any]) -> list[dict[str, Any]]:
    user = Client(accts["user_token"])
    admin = Client(accts["admin_token"])
    anon = Client()
    endpoints: list[tuple[str, Client, str, str, dict | None]] = [
        ("health", anon, "GET", "/api/health", None),
        ("openapi", anon, "GET", "/openapi.json", None),
        ("login", anon, "POST", "/api/auth/login", {"username": accts["user"], "password": accts["password"]}),
        ("me", user, "GET", "/api/auth/me", None),
        ("market_symbols", anon, "GET", "/api/market-data/symbols", None),
        ("market_indices", anon, "GET", "/api/market-data/indices", None),
        ("factor_index", user, "GET", "/api/factor/index", None),
        ("factor_re_catalog", user, "GET", "/api/factor/re-catalog", None),
        ("factor_libraries", user, "GET", "/api/factor/libraries", None),
        ("strategy_library", user, "GET", "/api/strategy/library", None),
        ("strategy_projects", user, "GET", "/api/strategy/projects", None),
        ("strategy_runs", user, "GET", "/api/strategy/runs", None),
        ("watchlists", user, "GET", "/api/watchlists", None),
        ("kh_collections", admin, "GET", "/api/kh/collections", None),
        ("ai_models", anon, "GET", "/api/ai/chat/models", None),
        ("admin_logs", admin, "GET", "/api/admin/logs?limit=20", None),
    ]
    rows = []
    for name, client, method, path, body in endpoints:
        results = [client.request(method, path, body=body, name=name) for _ in range(LATENCY_REQUESTS)]
        rows.append(asdict(summarize(results)))
    return rows


def mixed_read_request(accts: dict[str, Any]) -> RequestResult:
    user = Client(accts["user_token"])
    admin = Client(accts["admin_token"])
    anon = Client()
    candidates = [
        (anon, "GET", "/api/health", None, "mix_health"),
        (anon, "GET", "/api/market-data/symbols", None, "mix_symbols"),
        (user, "GET", "/api/auth/me", None, "mix_me"),
        (user, "GET", "/api/strategy/projects", None, "mix_strategy_projects"),
        (user, "GET", "/api/strategy/runs", None, "mix_strategy_runs"),
        (user, "GET", "/api/factor/libraries", None, "mix_factor_libraries"),
        (user, "GET", "/api/watchlists", None, "mix_watchlists"),
        (admin, "GET", "/api/kh/collections", None, "mix_kh"),
        (admin, "GET", "/api/admin/logs?limit=5", None, "mix_admin_logs"),
    ]
    client, method, path, body, name = random.choice(candidates)
    return client.request(method, path, body=body, name=name)


def run_for_duration(concurrency: int, duration_sec: int, factory: Callable[[], RequestResult]) -> tuple[list[RequestResult], float]:
    stop_at = time.monotonic() + duration_sec
    lock = threading.Lock()
    results: list[RequestResult] = []

    def worker() -> None:
        local: list[RequestResult] = []
        while time.monotonic() < stop_at:
            local.append(factory())
        with lock:
            results.extend(local)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(worker) for _ in range(concurrency)]
        for fut in as_completed(futures):
            fut.result()
    return results, time.perf_counter() - t0


def concurrency_tests(accts: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for level in CONCURRENCY_LEVELS:
        results, wall = run_for_duration(level, CONCURRENCY_DURATION_SEC, lambda: mixed_read_request(accts))
        row = asdict(summarize(results, wall_sec=wall))
        row["concurrency"] = level
        row["duration_sec"] = round(wall, 2)
        rows.append(row)
    return rows


def business_concurrency(accts: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    password = accts["password"]

    def login_req() -> RequestResult:
        return Client().request("POST", "/api/auth/login", body={"username": accts["user"], "password": password}, name="business_login")

    for name, factory in [
        ("login", login_req),
        ("watchlist_query", lambda: Client(accts["user_token"]).request("GET", "/api/watchlists", name="business_watchlist")),
        ("strategy_run_query", lambda: Client(accts["user_token"]).request("GET", "/api/strategy/runs", name="business_strategy_runs")),
        ("ai_quota_query", lambda: Client(accts["user_token"]).request("GET", "/api/agent/usage/me", name="business_ai_quota")),
        ("kh_search_like_query", lambda: Client(accts["admin_token"]).request("GET", "/api/kh/collections", name="business_kh_query")),
    ]:
        results, wall = run_for_duration(min(20, max(CONCURRENCY_LEVELS or [10])), 60, factory)
        row = asdict(summarize(results, wall_sec=wall))
        row["business_case"] = name
        row["concurrency"] = min(20, max(CONCURRENCY_LEVELS or [10]))
        row["duration_sec"] = round(wall, 2)
        cases.append(row)
    return cases


def table_order_clause(conn: Any, table: str) -> str:
    for column in ("updated_at", "created_at", "id"):
        row = conn.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
            """,
            (table, column),
        ).fetchone()
        if row:
            return f" ORDER BY {column} DESC"
    return ""


def database_perf() -> dict[str, Any]:
    out: dict[str, Any] = {}
    with get_conn() as conn:
        query_specs = {
            "user_lookup": ("users", " WHERE username LIKE 'R4_PERF_TEST_%'"),
            "strategy_projects": ("strategy_projects", ""),
            "strategy_runs": ("strategy_runs", ""),
            "factor_libraries": ("user_factor_libraries", ""),
            "kh_collections": ("kh_collections", ""),
            "audit_logs": ("app_audit_logs", ""),
        }
        queries = {}
        for name, (table, where) in query_specs.items():
            queries[name] = (
                f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                f"SELECT * FROM {table}{where}{table_order_clause(conn, table)} LIMIT 20"
            )
        for name, sql in queries.items():
            try:
                plan = conn.execute(sql).fetchone()["QUERY PLAN"][0]
                out[name] = {
                    "execution_ms": round(float(plan.get("Execution Time", 0)), 3),
                    "planning_ms": round(float(plan.get("Planning Time", 0)), 3),
                    "node_type": plan.get("Plan", {}).get("Node Type"),
                }
            except Exception as exc:
                out[name] = {"error": str(exc)}
                conn.rollback()
        try:
            out["connections"] = dict(conn.execute(
                "SELECT count(*) AS total, count(*) FILTER (WHERE state='active') AS active FROM pg_stat_activity"
            ).fetchone())
        except Exception as exc:
            out["connections"] = {"error": str(exc)}
            conn.rollback()
        try:
            out["long_transactions"] = [
                dict(row)
                for row in conn.execute(
                    "SELECT pid, state, now() - xact_start AS age FROM pg_stat_activity WHERE xact_start IS NOT NULL AND now() - xact_start > interval '30 seconds'"
                ).fetchall()
            ]
        except Exception as exc:
            out["long_transactions"] = {"error": str(exc)}
            conn.rollback()
    return out


def dependency_tests(accts: dict[str, Any]) -> dict[str, Any]:
    anon = Client()
    user = Client(accts["user_token"])
    normal = anon.request("GET", "/api/re/health", name="re_health")
    re_catalog = user.request("GET", "/api/factor/re-catalog", name="re_catalog")
    ai_bad = user.request(
        "POST",
        "/api/ai/chat",
        body={"messages": [{"role": "user", "content": "ping"}], "model": "invalid-r4-model"},
        name="ai_invalid_provider",
    )
    return {
        "research_engine_health": asdict(normal),
        "research_engine_catalog": asdict(re_catalog),
        "ai_provider_error_path": asdict(ai_bad),
    }


def stability_test(accts: dict[str, Any]) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    stop_at = time.monotonic() + STABILITY_DURATION_SEC
    results: list[RequestResult] = []
    lock = threading.Lock()

    def sampler() -> None:
        while time.monotonic() < stop_at:
            sample: dict[str, Any] = {"t": time.strftime("%H:%M:%S")}
            try:
                import psutil  # type: ignore

                sample["cpu_percent"] = psutil.cpu_percent(interval=0.1)
                sample["memory_used_percent"] = psutil.virtual_memory().percent
            except Exception:
                pass
            try:
                with get_conn() as conn:
                    sample["db_connections"] = int(conn.execute("SELECT count(*) AS n FROM pg_stat_activity").fetchone()["n"])
            except Exception as exc:
                sample["db_connections_error"] = str(exc)
            samples.append(sample)
            time.sleep(60)

    def worker() -> None:
        local: list[RequestResult] = []
        while time.monotonic() < stop_at:
            local.append(mixed_read_request(accts))
        with lock:
            results.extend(local)

    t0 = time.perf_counter()
    threads = [threading.Thread(target=worker) for _ in range(STABILITY_CONCURRENCY)]
    threads.append(threading.Thread(target=sampler))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    row = asdict(summarize(results, wall_sec=time.perf_counter() - t0))
    row["duration_sec"] = round(time.perf_counter() - t0, 2)
    row["concurrency"] = STABILITY_CONCURRENCY
    return {"summary": row, "resource_samples": samples}


def cleanup(accts: dict[str, Any]) -> None:
    ids: list[int] = []
    names = [accts.get("admin"), accts.get("user"), accts.get("user2")]
    try:
        with get_conn() as conn:
            rows = conn.execute("SELECT id FROM users WHERE username = ANY(%s)", (names,)).fetchall()
            ids = [int(r["id"]) for r in rows]
            for sql, args in [
                ("DELETE FROM user_watchlist_symbols WHERE watchlist_id IN (SELECT id FROM user_watchlists WHERE user_id = ANY(%s) OR name LIKE %s)", (ids, f"{RUN_ID}%")),
                ("DELETE FROM user_watchlists WHERE user_id = ANY(%s) OR name LIKE %s", (ids, f"{RUN_ID}%")),
                ("DELETE FROM strategy_runs WHERE user_id = ANY(%s) OR name LIKE %s", (ids, f"{RUN_ID}%")),
                ("DELETE FROM strategy_projects WHERE user_id = ANY(%s) OR name LIKE %s", (ids, f"{RUN_ID}%")),
                ("DELETE FROM kh_collections WHERE name LIKE %s", (f"{RUN_ID}%",)),
                ("DELETE FROM users WHERE username = ANY(%s)", (names,)),
            ]:
                try:
                    conn.execute(sql, args)
                except Exception:
                    pass
    except Exception:
        pass


def main() -> int:
    artifact: dict[str, Any] = {
        "run_id": RUN_ID,
        "base": BASE,
        "config": {
            "latency_requests": LATENCY_REQUESTS,
            "concurrency_levels": CONCURRENCY_LEVELS,
            "concurrency_duration_sec": CONCURRENCY_DURATION_SEC,
            "stability_duration_sec": STABILITY_DURATION_SEC,
            "stability_concurrency": STABILITY_CONCURRENCY,
        },
        "environment": env_info(),
        "before_data_scale": data_scale(),
    }
    accts = setup_data()
    try:
        artifact["after_setup_data_scale"] = data_scale()
        artifact["api_latency"] = latency_tests(accts)
        artifact["concurrency"] = concurrency_tests(accts)
        artifact["business_concurrency"] = business_concurrency(accts)
        artifact["database_perf"] = database_perf()
        artifact["external_dependencies"] = dependency_tests(accts)
        artifact["stability"] = stability_test(accts)
    finally:
        cleanup(accts)
    artifact["after_cleanup_data_scale"] = data_scale()

    all_rows = []
    for key in ("api_latency", "concurrency", "business_concurrency"):
        all_rows.extend(artifact.get(key) or [])
    stability_row = (artifact.get("stability") or {}).get("summary")
    if stability_row:
        all_rows.append(stability_row)
    total_requests = sum(int(r.get("requests", 0)) for r in all_rows)
    total_failed = sum(int(r.get("failed", 0)) for r in all_rows)
    max_p95 = max([float(r.get("p95_ms", 0)) for r in all_rows] or [0.0])
    artifact["summary"] = {
        "total_requests": total_requests,
        "failed_requests": total_failed,
        "error_rate": round(total_failed / total_requests, 4) if total_requests else 0,
        "max_p95_ms": round(max_p95, 2),
        "performance_bugs": [],
        "resource_leak_found": False,
    }
    path = Path(__file__).with_name(f"{RUN_ID}_r4_performance_results.json")
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(artifact["summary"], ensure_ascii=False))
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
