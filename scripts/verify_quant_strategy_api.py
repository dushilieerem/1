"""Real strategy API acceptance against the isolated development BFF.

Uses a project created in the UI and its saved request. No production writes,
model calls, migrations or synthetic engine responses.
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18799")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-development-write", action="store_true")
    parser.add_argument("--require-provenance", action="store_true")
    args = parser.parse_args()
    target = urlparse(args.base_url)
    if not args.allow_development_write:
        parser.error("--allow-development-write is required")
    if target.scheme != "http" or target.hostname not in {"localhost", "127.0.0.1"} or target.port != 18799:
        parser.error("restricted to isolated development BFF 18799")
    credentials = json.loads(args.credentials.read_text())
    if not credentials["username"].startswith("cx_quant_"):
        parser.error("dedicated cx_quant_ account required")
    source = json.loads(args.source_report.read_text())
    payload = {k: v for k, v in source["request"].items() if not k.startswith("_")}
    started = time.monotonic()
    with httpx.Client(base_url=args.base_url, trust_env=False, timeout=180) as client:
        assert client.get("/api/strategy/projects").status_code == 401
        login = client.post("/api/auth/login", json={k: credentials[k] for k in ("username", "password")})
        login.raise_for_status()
        client.headers["Authorization"] = "Bearer " + login.json()["token"]
        project = client.get("/api/strategy/projects/" + source["projectId"])
        project.raise_for_status()
        project = project.json()["project"]
        assert project["name"].startswith("cx_quant_"), "only dedicated acceptance projects"
        response = client.post("/api/backtest/strategy", json=payload)
        response.raise_for_status()
        # Reproduce the same JSON representation used by browser submissions.
        result = json.loads(subprocess.check_output(
            ["node", "-e", 'let s="";process.stdin.on("data",d=>s+=d);process.stdin.on("end",()=>process.stdout.write(JSON.stringify(JSON.parse(s))));'],
            input=json.dumps(response.json()).encode(), timeout=15,
        ))
        assert not result.get("error"), "engine returned an error"
        assert result.get("_svquant_verified_token"), "missing result signature"
        if args.require_provenance:
            for field in ("data_release_id", "spec_hash", "run_id"):
                assert result.get("meta", {}).get(field), "missing provenance: " + field
        body = {
            "projectId": source["projectId"], "name": project["name"],
            "description": "真实策略 API 开发验收",
            "request": source["request"], "result": result,
            "elapsedSec": round(time.monotonic() - started, 3),
        }
        response = client.post("/api/strategy/runs", json=body)
        response.raise_for_status()
        report_id = response.json()["run"]["id"]
        reopened = client.get("/api/strategy/runs/" + report_id)
        reopened.raise_for_status()
        stored = reopened.json()["run"]
        assert stored["verified"] is True
        assert stored["resultHash"]
        assert stored["request"]["strategy_code"] == source["request"]["strategy_code"]
        expected_meta = {k: v for k, v in result["meta"].items() if k != "code_hash"}
        assert stored["result"]["meta"] == expected_meta
        assert stored["result"]["date_range"] == result["date_range"]
        tampered = copy.deepcopy(body)
        tampered["name"] = "cx_quant_签名篡改验收负例_不可用于研究"
        tampered["description"] = "自动化安全验收负例：人为改写指标，仅验证不能获得 verified 标记。"
        tampered["result"]["metrics"]["sharpe"] = 12345.0
        rejected = client.post("/api/strategy/runs", json=tampered)
        # Existing strategy API keeps legacy/unverified research records; unlike
        # factor persistence it rejects trust, not necessarily storage.
        if rejected.status_code == 400:
            tamper_outcome = "rejected_http_400"
        else:
            rejected.raise_for_status()
            negative = rejected.json()["run"]
            assert negative["verified"] is False, "tampered report cannot be trusted"
            tamper_outcome = "stored_unverified_negative_test:" + negative["id"]
        client.headers.pop("Authorization")
        assert client.get("/api/strategy/runs/" + report_id).status_code == 401
    meta = result.get("meta") or {}
    evidence = {
        "passed": True, "project_id": source["projectId"], "report_id": report_id,
        "verified": stored["verified"], "result_hash": stored["resultHash"],
        "date_range": result.get("date_range"), "meta": meta,
        "tamper_outcome": tamper_outcome,
        "missing_provenance": [k for k in ("data_release_id", "spec_hash", "run_id") if not meta.get(k)],
        "checks": ["unauthenticated access rejected", "real login", "real synchronous strategy computation",
                   "Node JSON roundtrip", "signed PostgreSQL persistence and reopen", "tampered result cannot obtain verified=true"],
        "model_used": False,
        "limitations": ["development acceptance, not production", "missing provenance is not fabricated",
                        "does not establish strategy quality, PIT completeness or investment approval"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    main()
