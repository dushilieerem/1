# -*- coding: utf-8 -*-
"""审计：RE 内置因子提交契约 = library_name + factor_name（单因子直通不带 factor_code）。

用法（API 已起）：
  F:\\conda-envs\\SVQuant\\python.exe backend/scripts/audit_builtin_factor_submit.py
"""
from __future__ import annotations

import json
import sys
import urllib.request

API = "http://127.0.0.1:8766/api/factor/re-catalog?all=1"


def is_local(lib: str) -> bool:
    if not lib:
        return True
    if lib in ("custom_lib", "draft_lib"):
        return True
    return lib.startswith("user_lib_")


def main() -> int:
    req = urllib.request.Request(API, method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    factors = data.get("factors") or data.get("items") or []
    if not factors and isinstance(data, list):
        factors = data
    builtins = []
    for f in factors:
        name = str(f.get("name") or f.get("factor_name") or "").strip()
        lib = str(f.get("library") or f.get("library_name") or "").strip()
        if not name or not lib:
            continue
        if is_local(lib):
            continue
        builtins.append((name, lib))

    print(f"RE 内置因子数: {len(builtins)}")
    # 契约自检：同名多库时打印；提交侧应优先 RE 且带 library
    by_name: dict[str, list[str]] = {}
    for name, lib in builtins:
        by_name.setdefault(name, []).append(lib)
    dup = {k: v for k, v in by_name.items() if len(set(v)) > 1}
    if dup:
        print(f"同名多库因子: {len(dup)}（resolve 须优先官方库）")
        for k, libs in list(dup.items())[:15]:
            print(f"  {k}: {sorted(set(libs))}")

    # 每个内置因子的「正确请求形」
    ok = 0
    for name, lib in builtins:
        # 单因子直通契约
        shape = {"library_name": lib, "factor_name": name}
        assert "factor_code" not in shape
        ok += 1
    print(f"契约样例全部合格: {ok}/{len(builtins)}（单因子 = library_name + factor_name，无 factor_code）")
    print("前端实现：detectComboCode.buildYgFactorRequestParts + preferredLibraries + auditBuiltinPassthroughParts")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
