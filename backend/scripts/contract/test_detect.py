# -*- coding: utf-8 -*-
"""detect 契约（含跨用户隔离）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from http_client import assert_error, assert_keys, login, req  # noqa: E402


def test_detect_list_and_isolation() -> None:
    st, _ = req("GET", "/api/detect/projects")
    assert_error(st, _, 401)

    for u, p in [("admin", "admin123"), ("max", "123456")]:
        tok = login(u, p)
        st, proj = req("GET", "/api/detect/projects?visible=1", token=tok)
        assert st == 200, proj
        assert_keys(proj, "ok", "projects")

    m = login("max", "123456")
    st, runs = req("GET", "/api/detect/projects/sample_momentum_5d/runs", token=m)
    assert st == 200, runs
    assert_keys(runs, "ok", "runs")
    if runs["runs"]:
        rid = runs["runs"][0]["id"]
        # 另一用户若存在则交叉读应 404；否则跳过
        try:
            x = login("maruixiang", "123456")
        except AssertionError:
            return
        st, cross = req("GET", f"/api/detect/runs/{rid}", token=x)
        assert st == 404, (st, cross)


def main() -> None:
    test_detect_list_and_isolation()
    print("contract.detect OK")


if __name__ == "__main__":
    main()
