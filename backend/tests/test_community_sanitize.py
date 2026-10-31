# -*- coding: utf-8 -*-
"""P0-05：社区正文服务端白名单清洗。"""
from __future__ import annotations

from services.community.sanitize import sanitize_community_html


def test_drops_script_and_event_handlers() -> None:
    out = sanitize_community_html('<script>alert(1)</script><p onclick="x">hi</p>')
    assert "script" not in out
    assert "onclick" not in out
    assert "<p>hi</p>" in out


def test_drops_javascript_urls() -> None:
    out = sanitize_community_html('<a href="javascript:alert(1)">x</a>')
    assert "javascript" not in out
    assert "<a rel=" in out


def test_keeps_allowed_markup_and_escapes_text() -> None:
    out = sanitize_community_html("<strong>ok</strong> 1 < 2")
    assert "<strong>ok</strong>" in out
    assert "1 &lt; 2" in out


def test_drops_iframe() -> None:
    out = sanitize_community_html('<iframe src="https://x"></iframe><p>ok</p>')
    assert "iframe" not in out
    assert "<p>ok</p>" in out
