# -*- coding: utf-8 -*-
"""P1-K06：KnowledgeHub 文本类文件抽取。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "KnowledgeHub" / "backend"))

from knowledge_hub.extractors import extract_text, is_extractable  # noqa: E402


def test_markdown_and_txt_are_supported() -> None:
    assert is_extractable("notes.md")
    assert is_extractable("readme.txt")
    assert extract_text("notes.md", "# 标题\n\n正文".encode("utf-8")) == "# 标题\n\n正文"


def test_html_is_converted_to_text() -> None:
    html = b"<html><style>.x{}</style><body><h1>Hello</h1><p>world &amp; more</p></body></html>"
    text = extract_text("page.html", html)
    assert "Hello" in text
    assert "world & more" in text
    assert "<h1>" not in text


def test_unknown_extension_is_rejected() -> None:
    assert not is_extractable("a.exe")
    try:
        extract_text("a.exe", b"x")
    except ValueError as exc:
        assert "暂不支持" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("应拒绝未知扩展名")
