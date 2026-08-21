# -*- coding: utf-8 -*-
"""按模块顺序跑契约；失败即停。

用法:
  cd WebApp/backend
  python scripts/contract/run_all.py
  set CONTRACT_BASE=http://127.0.0.1:8767 && python scripts/contract/run_all.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _run(name: str) -> None:
    path = HERE / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


def main() -> None:
    from http_client import BASE

    print(f"CONTRACT_BASE={BASE}")
    for name in ("test_auth.py", "test_detect.py", "test_modules.py"):
        print(f"--- {name} ---")
        _run(name)
    print("ALL CONTRACTS OK")


if __name__ == "__main__":
    main()
