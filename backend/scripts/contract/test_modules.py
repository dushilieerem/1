# -*- coding: utf-8 -*-
"""strategy / factor / watchlists / news / community 轻量契约。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from http_client import assert_error, assert_keys, login, req  # noqa: E402


def test_strategy() -> None:
    tok = login()
    st, data = req("GET", "/api/strategy/projects?visible=1", token=tok)
    assert st == 200, data
    assert_keys(data, "ok", "projects")
    st, lib = req("GET", "/api/strategy/library", token=tok)
    assert st in (200, 404), lib


def test_factor() -> None:
    st, cat = req("GET", "/api/factor/re-catalog")
    assert st in (200, 502), cat
    if st == 200:
        assert isinstance(cat, dict)
    st, idx = req("GET", "/api/factor/index")
    assert st == 200, idx
    st, dash = req("GET", "/api/factor/dashboard/status")
    assert st == 200, dash


def test_watchlists_news() -> None:
    tok = login()
    st, wl = req("GET", "/api/watchlists", token=tok)
    assert st == 200, wl
    assert_keys(wl, "ok", "watchlists")
    st, news = req("GET", "/api/news?limit=5")
    assert st == 200, news
    st, d = req("GET", "/api/news/dict")
    assert st == 200, d


def test_community() -> None:
    st, posts = req("GET", "/api/community/posts?limit=5")
    assert st == 200, posts
    tok = login()
    st, fav = req("GET", "/api/community/favorites?limit=5", token=tok)
    assert st == 200, fav
    st, unauth = req("GET", "/api/community/favorites")
    assert_error(st, unauth, 401)


def test_agent_ai_meta() -> None:
    tok = login()
    st, usage = req("GET", "/api/agent/usage/me?days=1", token=tok)
    assert st == 200, usage
    st, models = req("GET", "/api/ai/chat/models")
    assert st == 200, models
    st, speech = req("GET", "/api/ai/speech/status")
    assert st == 200, speech


def main() -> None:
    test_strategy()
    test_factor()
    test_watchlists_news()
    test_community()
    test_agent_ai_meta()
    print("contract.modules OK")


if __name__ == "__main__":
    main()
