# -*- coding: utf-8 -*-
"""Targeted R4 performance fix regression suite.

This does not relax the original R4 standards. It reruns the failing surfaces with
the same concurrency, duration, and request timeout used by the baseline report.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import performance_baseline as perf


def _summary(results: list[perf.RequestResult], wall: float, *, concurrency: int, case: str) -> dict[str, Any]:
    row = asdict(perf.summarize(results, wall_sec=wall))
    row["concurrency"] = concurrency
    row["duration_sec"] = round(wall, 2)
    row["case"] = case
    return row


def _run_case(concurrency: int, duration_sec: int, factory, case: str) -> dict[str, Any]:
    results, wall = perf.run_for_duration(concurrency, duration_sec, factory)
    return _summary(results, wall, concurrency=concurrency, case=case)


def _run_fixed_count(count: int, factory, case: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    results = [factory() for _ in range(count)]
    return _summary(results, time.perf_counter() - t0, concurrency=1, case=case)


def _baseline() -> dict[str, Any]:
    path = Path(__file__).with_name("R4_PERF_TEST_1790219612_r4_performance_results.json")
    if not path.exists():
        return {"path": str(path), "found": False}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": str(path),
        "found": True,
        "auth_me_100": next((r for r in data.get("concurrency", []) if r.get("path") == "/api/auth/me"), None),
        "strategy_runs_business": next((r for r in data.get("business_concurrency", []) if r.get("path") == "/api/strategy/runs"), None),
        "re_health": data.get("external_dependencies", {}).get("research_engine_health"),
        "market_symbols_stability": data.get("stability", {}).get("summary"),
    }


def main() -> int:
    artifact: dict[str, Any] = {
        "run_id": f"R4_PERF_FIX_{int(time.time())}",
        "base": perf.BASE,
        "config": {
            "request_timeout_sec": perf.REQUEST_TIMEOUT_SEC,
            "auth_me_concurrency": 100,
            "auth_me_duration_sec": perf.CONCURRENCY_DURATION_SEC,
            "strategy_runs_concurrency": 20,
            "strategy_runs_duration_sec": 60,
            "market_symbols_concurrency": perf.STABILITY_CONCURRENCY,
            "market_symbols_duration_sec": perf.STABILITY_DURATION_SEC,
            "re_health_requests": 100,
        },
        "baseline": _baseline(),
        "environment": perf.env_info(),
        "results": {},
    }
    accts: dict[str, Any] = {}
    try:
        artifact["before_data_scale"] = perf.data_scale()
        accts = perf.setup_data()
        user = perf.Client(accts["user_token"])
        anon = perf.Client()

        # Warm the cache once before the long stability case, mirroring normal UI behavior.
        artifact["warmup_market_symbols"] = asdict(
            anon.request("GET", "/api/market-data/symbols", name="warmup_market_symbols")
        )

        artifact["results"]["re_health"] = _run_fixed_count(
            100,
            lambda: anon.request("GET", "/api/re/health", name="re_health"),
            "PERF-R4-003",
        )
        artifact["results"]["auth_me_100"] = _run_case(
            100,
            perf.CONCURRENCY_DURATION_SEC,
            lambda: user.request("GET", "/api/auth/me", name="auth_me_100"),
            "PERF-R4-001",
        )
        artifact["results"]["strategy_runs_20"] = _run_case(
            20,
            60,
            lambda: user.request("GET", "/api/strategy/runs", name="strategy_runs_20"),
            "PERF-R4-002",
        )
        artifact["results"]["market_symbols_stability"] = _run_case(
            perf.STABILITY_CONCURRENCY,
            perf.STABILITY_DURATION_SEC,
            lambda: anon.request("GET", "/api/market-data/symbols", name="market_symbols_stability"),
            "PERF-R4-004",
        )
        artifact["database_perf"] = perf.database_perf()
    finally:
        if accts:
            perf.cleanup(accts)
        artifact["after_cleanup_data_scale"] = perf.data_scale()

    total = sum(int(r.get("requests") or 0) for r in artifact["results"].values())
    failed = sum(int(r.get("failed") or 0) for r in artifact["results"].values())
    artifact["summary"] = {
        "total_requests": total,
        "failed_requests": failed,
        "error_rate": round(failed / total, 4) if total else 0,
        "max_p95_ms": max((float(r.get("p95_ms") or 0) for r in artifact["results"].values()), default=0),
        "all_related_regressions_pass": failed == 0,
    }
    path = Path(__file__).with_name(f"{artifact['run_id']}_r4_fix_regression_results.json")
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(artifact["summary"], ensure_ascii=False))
    print(path)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

