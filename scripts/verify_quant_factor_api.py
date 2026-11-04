"""Explicit real-data acceptance using the existing authenticated SVQuant APIs.

Writes only the supplied cx_quant_ account's own development records.
Not a pytest test, not an AI performance evaluation, and never a production launcher.
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18799")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-development-write", action="store_true")
    parser.add_argument("--institutional", action="store_true", help="Use the institution quant login and API scope")
    args = parser.parse_args()
    api = "/api/inst/quant" if args.institutional else "/api"
    login_path = api + "/auth/login"
    if not args.allow_development_write:
        parser.error("explicit --allow-development-write is required")
    url = urlparse(args.base_url)
    if url.hostname not in {"127.0.0.1", "localhost"} or url.port != 18799:
        parser.error("this acceptance tool is restricted to isolated development BFF 18799")
    credentials = json.loads(args.credentials.read_text())
    if not credentials["username"].startswith("cx_quant_"):
        parser.error("dedicated cx_quant_ acceptance account required")
    payload = json.loads(args.request.read_text())
    payload = payload.get("request", payload)
    started = time.monotonic()
    with httpx.Client(base_url=args.base_url, timeout=120, trust_env=False) as client:
        assert client.get(api + "/detect/projects").status_code == 401
        login = client.post(login_path, json={
            k: credentials[k] for k in ("username", "password")
        })
        login.raise_for_status()
        client.headers["Authorization"] = "Bearer " + login.json()["token"]
        projects = client.get(api + "/detect/projects")
        projects.raise_for_status()
        existing = [p for p in projects.json()["projects"] if not p.get("sample") and not p.get("isSample")]
        project = next((p for p in existing if p.get("factorName") == payload["factor_name"]), None)
        if project is None:
            raise RuntimeError("create the acceptance research project through the UI first")
        response = client.post(api + "/backtest/factor", json=payload)
        response.raise_for_status()
        task = response.json()
        run_id = task["run_id"]
        print("submitted", run_id, flush=True)
        deadline = time.monotonic() + 180
        while task.get("status") in {"queued", "running", "pending"} and time.monotonic() < deadline:
            time.sleep(1)
            response = client.get(api + "/backtest/factor/" + run_id)
            response.raise_for_status()
            task = response.json()
        if task.get("status") != "succeeded":
            raise RuntimeError("RE task did not succeed: " + str(task.get("status")))
        result = json.loads(subprocess.check_output(
            ["node", "-e", 'let s="";process.stdin.on("data",d=>s+=d);process.stdin.on("end",()=>process.stdout.write(JSON.stringify(JSON.parse(s))));'],
            input=json.dumps(task["result"]).encode(), timeout=15,
        ))
        assert result.get("_svquant_verified_token"), "missing BFF signature"
        meta = result["meta"]
        assert meta.get("data_release_id") and meta.get("spec_hash")
        report_id = "cx_quant_" + uuid.uuid4().hex
        body = {
            "id": report_id, "projectId": project["id"],
            "factorName": payload["factor_name"],
            "description": "真实公司数据端到端验收：20日动量",
            "remark": "开发验收；不是投资审批或投资建议。",
            "request": {**payload, "_re_run_id": run_id},
            "result": result, "elapsedSec": round(time.monotonic() - started, 3),
        }
        saved = client.post(api + "/detect/runs", json=body)
        saved.raise_for_status()
        reopened = client.get(api + "/detect/runs/" + report_id)
        reopened.raise_for_status()
        stored = reopened.json()["run"]
        assert stored["result"]["_svquant_verified"] is True
        assert "_svquant_verified_token" not in stored["result"]
        assert stored["result"]["meta"]["data_release_id"] == meta["data_release_id"]
        assert stored["result"]["meta"]["spec_hash"] == meta["spec_hash"]
        assert stored["request"]["_re_run_id"] == run_id
        tampered = copy.deepcopy(body)
        tampered["id"] = report_id + "_tampered"
        tampered["result"]["meta"]["spec_hash"] = "tampered"
        rejected = client.post(api + "/detect/runs", json=tampered)
        assert rejected.status_code == 400, "tampered signed report must be rejected"
        assert client.get(api + "/detect/runs/" + tampered["id"]).status_code == 404
        client.headers.pop("Authorization")
        assert client.get(api + "/detect/runs/" + report_id).status_code == 401
    evidence = {
        "passed": True, "identity_scope": "institutional_quant" if args.institutional else "personal", "run_id": run_id, "report_id": report_id,
        "project_id": project["id"], "release_id": meta["data_release_id"],
        "spec_hash": meta["spec_hash"], "request": payload,
        "checks": ["unauthenticated access rejected", "real login",
                   "existing project", "real ResearchEngine computation",
                   "BFF signed result after actual Node JSON roundtrip", "PostgreSQL persistence and reopen",
                   "provenance retained", "tampered result rejected"],
        "model_used": False,
        "limitations": ["development integration only", "not full product acceptance",
                        "real data does not establish PIT or investment performance validity"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    main()
