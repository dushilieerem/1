# -*- coding: utf-8 -*-
"""社区正文服务端 HTML 白名单清洗（P0-05）。

不依赖第三方库：用标准库 HTMLParser 重新生成允许的子集。
- 丢弃 script/style/iframe 等危险标签及其内容；
- 属性只保留 a[href,title]、img[src,alt,title]；
- 链接只允许 http(s)、mailto、站内相对路径；
- 图片只允许 http(s)、data:image/；
- 文本统一转义，避免“原样入库”。
"""
from __future__ import annotations

import html
from html.parser import HTMLParser

ALLOWED_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "s", "del",
    "ul", "ol", "li", "blockquote", "code", "pre", "a", "img",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr",
    "table", "thead", "tbody", "tr", "th", "td",
}
VOID_TAGS = {"br", "hr", "img"}
DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "noscript"}


def _safe_url(value: str, *, image: bool = False) -> str | None:
    v = html.unescape((value or "").strip())
    low = v.lower()
    if image and low.startswith("data:image/"):
        return v
    if low.startswith(("http://", "https://", "mailto:")):
        return v
    if not image and v.startswith(("/", "#")):
        return v
    return None


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._drop_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            self._drop_depth += 1
            return
        if self._drop_depth or tag not in ALLOWED_TAGS:
            return
        clean: list[tuple[str, str]] = []
        for key, value in attrs:
            k = (key or "").lower()
            val = value or ""
            if tag == "a" and k in {"href", "title"}:
                if k == "href":
                    val = _safe_url(val) or ""
                    if not val:
                        continue
                clean.append((k, val))
            elif tag == "img" and k in {"src", "alt", "title"}:
                if k == "src":
                    val = _safe_url(val, image=True) or ""
                    if not val:
                        continue
                clean.append((k, val))
        if tag == "a":
            clean.append(("rel", "noopener noreferrer nofollow"))
        attr_text = "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in clean)
        self.parts.append(f"<{tag}{attr_text}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() in ALLOWED_TAGS and tag.lower() not in VOID_TAGS:
            self.parts.append(f"</{tag.lower()}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            self._drop_depth = max(0, self._drop_depth - 1)
            return
        if self._drop_depth or tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._drop_depth:
            self.parts.append(html.escape(data, quote=False))


def sanitize_community_html(raw: str) -> str:
    parser = _Sanitizer()
    try:
        parser.feed(raw or "")
        parser.close()
    except Exception:
        return html.escape(raw or "", quote=False)
    return "".join(parser.parts).strip()


__all__ = ["sanitize_community_html"]
