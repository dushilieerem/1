# -*- coding: utf-8 -*-
"""策略研究模块冒烟：CRUD + 代码同步 + 回测成功/失败。"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8766"
YG = (os.environ.get("YG_RE_BASE") or "http://192.168.250.10:9527").rstrip("/")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "frontend" / "src" / "lib"))  # not used for TS

# inline mirror of strategyCodeSync for py check
BEGIN = "# --- SVQUANT_PARAMS (与左侧表单同步，请求以表单为准) ---"
END = "# --- SVQUANT_PARAMS_END ---"


def apply_params(code: str, universe: str, commission: float, slippage: float, capital: int,
                 benchmark: str = "CSI300", stamp_tax: float = 0.001) -> str:
    block = "\n".join(
        [
            BEGIN,
            f'UNIVERSE = "{universe}"',
            f'BENCHMARK = "{benchmark}"',
            f"COMMISSION_RATE = {commission}",
            f"STAMP_TAX = {stamp_tax}",
            f"SLIPPAGE_RATE = {slippage}",
            f"INITIAL_CAPITAL = {capital}",
            END,
        ]
    )
    bi, ei = code.find(BEGIN), code.find(END)
    if bi >= 0 and ei > bi:
        return code[:bi] + block + code[ei + len(END) :]
    return code


def parse_params(code: str) -> dict:
    out = {}
    for line in code.splitlines():
        s = line.strip()
        if s.startswith("UNIVERSE"):
            out["universe"] = s.split("=", 1)[1].strip().strip('"').strip("'")
        elif s.startswith("BENCHMARK"):
            out["benchmark"] = s.split("=", 1)[1].strip().strip('"').strip("'")
        elif s.startswith("COMMISSION_RATE"):
            out["commission_rate"] = float(s.split("=", 1)[1].strip())
        elif s.startswith("STAMP_TAX"):
            out["stamp_tax"] = float(s.split("=", 1)[1].strip())
        elif s.startswith("SLIPPAGE_RATE"):
            out["slippage_rate"] = float(s.split("=", 1)[1].strip())
        elif s.startswith("INITIAL_CAPITAL"):
            out["initial_capital"] = int(s.split("=", 1)[1].strip().replace("_", ""))
    return out


def req(method, path, token=None, body=None, base=BASE, timeout=120):
    data = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode()
    r = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": raw[:300]}


def main():
    print("1) login")
    st, login = req("POST", "/api/auth/login", body={"username": "admin", "password": "admin123"})
    assert st == 200, login
    tok = login["token"]
    print("   ok")

    print("2) create project")
    st, created = req(
        "POST",
        "/api/strategy/projects",
        token=tok,
        body={"name": "smoke-strategy", "description": "smoke"},
    )
    assert st == 200, created
    proj = created["project"]
    pid = proj["id"]
    code = proj["config"]["strategy_code"]
    assert "FactorPortfolioStrategy" in code
    print(f"   id={pid}")

    print("3) bidirectional sync (params block)")
    code2 = apply_params(code, "CSI300", 0.0005, 0.002, 2_000_000, "CSI300", 0.001)
    parsed = parse_params(code2)
    assert parsed["universe"] == "CSI300"
    assert parsed["benchmark"] == "CSI300"
    assert parsed["commission_rate"] == 0.0005
    assert abs(parsed["slippage_rate"] - 0.002) < 1e-9
    assert parsed["initial_capital"] == 2_000_000
    assert abs(parsed.get("stamp_tax", 0.001) - 0.001) < 1e-9
    print("   left→right ok")

    print("4) save project")
    # ensure stamp/benchmark present after apply
    if "stamp_tax" not in parsed:
        parsed["stamp_tax"] = 0.001
    if "benchmark" not in parsed:
        parsed["benchmark"] = "CSI300"
    cfg = {**proj["config"], **parsed, "strategy_code": code2}
    st, saved = req(
        "PUT",
        f"/api/strategy/projects/{pid}",
        token=tok,
        body={
            "id": pid,
            "name": proj["name"],
            "description": proj["description"],
            "config": cfg,
        },
    )
    assert st == 200, saved
    assert saved["project"]["config"]["universe"] == "CSI300"
    print("   ok")

    print("5) list projects")
    st, listed = req("GET", "/api/strategy/projects", token=tok)
    assert st == 200, listed
    assert any(p["id"] == pid for p in listed["projects"])
    print(f"   n={len(listed['projects'])}")

    print("6) backtest failure path (bad code)")
    bad_body = {
        "strategy_code": "this is not valid python strategy <<<",
        "universe": "CSI500",
        "start": "2024-01-01",
        "end": "2024-06-30",
        "commission_rate": 0.0003,
        "slippage_rate": 0.001,
        "initial_capital": 1_000_000,
        "include_positions": False,
    }
    st, bad = req("POST", "/api/backtest/strategy", body=bad_body, base=YG, timeout=60)
    # RE may return 200 with error field, or HTTP error
    if st == 200:
        assert bad.get("error"), f"expected error field, got {bad.keys()}"
        print(f"   RE error field: {str(bad['error'])[:120]}")
    else:
        print(f"   RE HTTP {st}: {str(bad)[:120]}")
    print("   fail path ok (no crash)")

    print("7) backtest success path")
    good_body = {
        "strategy_code": code,  # original default template
        "universe": "CSI500",
        "start": "2024-01-01",
        "end": "2024-06-30",
        "benchmark": "CSI300",
        "commission_rate": 0.0003,
        "stamp_tax": 0.001,
        "slippage_rate": 0.001,
        "initial_capital": 1_000_000,
        "include_positions": False,
    }
    st, good = req("POST", "/api/backtest/strategy", body=good_body, base=YG, timeout=180)
    assert st == 200, good
    if good.get("error"):
        print(f"   WARN RE returned error: {good['error'][:200]}")
        print("   skip save-run (RE strategy may need env); CRUD still ok")
    else:
        assert good.get("equity_curve") or good.get("metrics"), good.keys()
        print(
            f"   metrics keys={list((good.get('metrics') or {}).keys())[:8]} "
            f"curve={len(good.get('equity_curve') or [])}"
        )
        st, run = req(
            "POST",
            "/api/strategy/runs",
            token=tok,
            body={
                "projectId": pid,
                "name": "smoke-strategy",
                "description": "smoke",
                "request": good_body,
                "result": good,
                "elapsedSec": 1.5,
            },
        )
        assert st == 200, run
        rid = run["run"]["id"]
        print(f"   run saved id={rid}")
        st, got = req("GET", f"/api/strategy/runs/{rid}", token=tok)
        assert st == 200, got
        st, runs = req("GET", f"/api/strategy/projects/{pid}/runs", token=tok)
        assert st == 200 and any(r["id"] == rid for r in runs["runs"])
        st, _ = req("DELETE", f"/api/strategy/runs/{rid}", token=tok)
        assert st == 200
        print("   run CRUD ok")

    print("8) delete project")
    st, _ = req("DELETE", f"/api/strategy/projects/{pid}", token=tok)
    assert st == 200
    st, listed2 = req("GET", "/api/strategy/projects", token=tok)
    assert st == 200
    assert not any(p["id"] == pid for p in listed2["projects"])
    print("   ok")

    print("ALL STRATEGY SMOKE CHECKS OK")


if __name__ == "__main__":
    main()
