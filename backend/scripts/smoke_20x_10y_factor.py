# -*- coding: utf-8 -*-
"""并发 20 路官方因子 · 十年回测（走前端同路径 Vite /yg-api → RE）。"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.core.lan_http import ensure_lan_no_proxy, urlopen_direct

ensure_lan_no_proxy()

CATALOG = "http://127.0.0.1:8766/api/factor/re-catalog?all=1"
# 与检测台一致：经 Vite 代理打 RE
YG = "http://127.0.0.1:9530/yg-api/api/backtest/factor"
N = 20
TIMEOUT = 1800
START, END = "2016-08-19", "2026-08-19"

SKIP_LIBS = {"custom_lib", "draft_lib"}
OFFICIAL = {
    "momentum_lib",
    "value_lib",
    "technical_lib",
    "volatility_lib",
    "trading_lib",
    "emotion_indicators",
    "risk_indicators",
    "technical_indicators",
    "classic_indicators",
    "alpha_features",
}


def load_factors() -> list[tuple[str, str]]:
    req = urllib.request.Request(CATALOG, method="GET")
    with urlopen_direct(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    items = data.get("factors") or []
    picked: list[tuple[str, str]] = []
    seen_lib: dict[str, int] = {}
    for f in items:
        name = str(f.get("name") or "").strip()
        lib = str(f.get("library") or "").strip()
        if not name or not lib or lib not in OFFICIAL:
            continue
        if seen_lib.get(lib, 0) >= 3:
            continue
        seen_lib[lib] = seen_lib.get(lib, 0) + 1
        picked.append((name, lib))
        if len(picked) >= N:
            break
    if len(picked) < N:
        for f in items:
            name = str(f.get("name") or "").strip()
            lib = str(f.get("library") or "").strip()
            if not name or not lib or (name, lib) in picked:
                continue
            if lib not in OFFICIAL:
                continue
            picked.append((name, lib))
            if len(picked) >= N:
                break
    return picked[:N]


def run_one(name: str, lib: str) -> dict:
    body = {
        "library_name": lib,
        "factor_name": name,
        "universe": "CSI300",
        "start": START,
        "end": END,
        "filter_limit_up": True,
        "filter_suspended": True,
        "groups": 5,
        "rebalance_days": 5,
        "benchmark": "CSI300",
        "analysis_level": "core",
    }
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        YG,
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urlopen_direct(req, timeout=TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            payload = json.loads(e.read().decode("utf-8"))
        except Exception:
            payload = {"error": str(e)}
    except Exception as e:
        return {
            "name": name,
            "lib": lib,
            "status": "EXC",
            "sec": round(time.time() - t0, 1),
            "error": str(e)[:240],
        }
    err = payload.get("error") if isinstance(payload, dict) else None
    return {
        "name": name,
        "lib": lib,
        "status": status,
        "sec": round(time.time() - t0, 1),
        "error": (str(err)[:240] if err else None),
        "ok": bool(status == 200 and not err),
    }


def main() -> None:
    factors = load_factors()
    print(f"fire {len(factors)} jobs  {START}→{END}  via {YG}")
    for n, lib in factors:
        print(f"  {lib}.{n}")
    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=N) as ex:
        futs = [ex.submit(run_one, n, lib) for n, lib in factors]
        print(f"all {len(futs)} submitted in {time.time()-t0:.2f}s")
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            flag = "OK" if r.get("ok") else "FAIL"
            print(f"[{flag}] {r['lib']}.{r['name']}  HTTP {r['status']}  {r['sec']}s  {r.get('error') or ''}")
    elapsed = time.time() - t0
    ok = sum(1 for r in results if r.get("ok"))
    fail = [r for r in results if not r.get("ok")]
    print("=" * 48)
    print(f"done {ok}/{len(results)} ok in {elapsed:.1f}s")
    if fail:
        print("failures:")
        for r in fail:
            print(f"  {r['lib']}.{r['name']} status={r['status']} {r.get('error')}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
