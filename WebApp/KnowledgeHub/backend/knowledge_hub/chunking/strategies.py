# -*- coding: utf-8 -*-
"""内置分块策略。复制本文件中任一函数作模板，再在 registry 自动发现（本模块被 import）。"""
from __future__ import annotations

import re
from typing import Any

from knowledge_hub.chunking.registry import register


def _piece(ordinal: int, text: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ordinal": ordinal, "text": text, "meta": meta or {}}


@register(
    "markdown_heading",
    label_zh="按 Markdown 标题",
    description="按 # / ## 等标题切分，适合手册与章节文档",
    default_options={"window": 1200},
)
def markdown_heading(text: str, *, window: int = 1200, **_: Any) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return []
    parts = re.split(r"(?=^#{1,6}\s)", raw, flags=re.M)
    chunks: list[dict[str, Any]] = []
    ordinal = 0
    buf = ""
    title = ""
    for part in parts:
        piece = part.strip()
        if not piece:
            continue
        m = re.match(r"^(#{1,6})\s+(.+)$", piece, flags=re.M)
        heading = m.group(2).strip() if m else ""
        if len(buf) + len(piece) > window and buf:
            chunks.append(_piece(ordinal, buf.strip(), {"title": title}))
            ordinal += 1
            buf = piece
            title = heading or title
        else:
            if not buf:
                title = heading or title
            buf = (buf + "\n\n" + piece).strip() if buf else piece
            if heading:
                title = heading
    if buf.strip():
        chunks.append(_piece(ordinal, buf.strip(), {"title": title}))
    return chunks


@register(
    "plain_window",
    label_zh="固定窗口",
    description="按字符窗口滑动切分，适合纯文本",
    default_options={"window": 800, "overlap": 120},
)
def plain_window(
    text: str, *, window: int = 800, overlap: int = 120, **_: Any
) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return []
    window = max(100, int(window))
    overlap = max(0, min(int(overlap), window - 1))
    step = max(1, window - overlap)
    out: list[dict[str, Any]] = []
    i = 0
    ordinal = 0
    n = len(raw)
    while i < n:
        piece = raw[i : i + window].strip()
        if piece:
            out.append(_piece(ordinal, piece, {"start": i}))
            ordinal += 1
        i += step
    return out


@register(
    "qa_pair",
    label_zh="问答对",
    description="按空行或 Q:/A: 模式切成问答块",
    default_options={},
)
def qa_pair(text: str, **_: Any) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return []
    blocks = re.split(r"\n\s*\n", raw)
    out: list[dict[str, Any]] = []
    for i, b in enumerate(blocks):
        t = b.strip()
        if t:
            out.append(_piece(i, t, {"kind": "qa"}))
    if not out:
        out.append(_piece(0, raw, {"kind": "qa"}))
    return out


@register(
    "table_row",
    label_zh="表格行",
    description="Markdown 表格按行切分；非表格则退回固定窗口",
    default_options={"window": 800, "overlap": 80},
)
def table_row(text: str, *, window: int = 800, overlap: int = 80, **kw: Any) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    lines = raw.splitlines()
    table_lines = [ln for ln in lines if "|" in ln]
    if len(table_lines) < 2:
        return plain_window(raw, window=window, overlap=overlap, **kw)
    header = table_lines[0]
    out: list[dict[str, Any]] = []
    ordinal = 0
    for ln in table_lines[1:]:
        if re.match(r"^\s*\|?\s*[-:]+", ln):
            continue
        piece = f"{header}\n{ln}".strip()
        if piece:
            out.append(_piece(ordinal, piece, {"kind": "table_row"}))
            ordinal += 1
    return out or plain_window(raw, window=window, overlap=overlap, **kw)


@register(
    "paragraph_merge",
    label_zh="按段落合并",
    description="按空行/段落切分后合并到窗口大小，适合 Word/会议纪要等纯文本",
    default_options={"window": 1000},
)
def paragraph_merge(text: str, *, window: int = 1000, **_: Any) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return []
    window = max(200, int(window))
    # 空行分段；若几乎无空行，则按单行当作段
    paras = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    if len(paras) <= 1:
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        if len(lines) >= 3:
            paras = lines
        elif paras:
            pass
        else:
            return plain_window(raw, window=window, overlap=min(120, window // 5))
    chunks: list[dict[str, Any]] = []
    ordinal = 0
    buf = ""
    for para in paras:
        if not buf:
            buf = para
            continue
        # +2 for blank line join
        if len(buf) + 2 + len(para) <= window:
            buf = f"{buf}\n\n{para}"
        else:
            chunks.append(_piece(ordinal, buf.strip(), {"kind": "paragraph"}))
            ordinal += 1
            buf = para
    if buf.strip():
        chunks.append(_piece(ordinal, buf.strip(), {"kind": "paragraph"}))
    return chunks


# 一级结构标题：1. / 1、 / 一、 / （一） / 第x章/节 / 「姓名——主题」纪要头
_NUMBERED_HEAD = re.compile(
    r"^(?:"
    r"第[一二三四五六七八九十百零〇0-9]+[章节条]\s*\S*"
    r"|[一二三四五六七八九十]+[、.．]\s*\S+"
    r"|[（(][一二三四五六七八九十0-9]+[）)]\s*\S+"
    r"|[0-9]{1,2}[、.．]\s+\S+"
    r"|[0-9]{1,2}\.\s+\S+"
    r"|[\u4e00-\u9fff]{2,4}——[^，。；、]{2,40}"  # 马睿祥——社区模块…（排除长句破折号）
    r")$"
)


@register(
    "numbered_heading",
    label_zh="按编号标题",
    description="按 1. / 1、 / 一、 / 第x章 及「姓名——主题」切分；子节会带上父级「姓名——主题」便于检索。无此类父标题时行为与普通编号切分相同",
    default_options={"window": 1400},
)
def numbered_heading(text: str, *, window: int = 1400, **_: Any) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return []
    window = max(200, int(window))
    lines = raw.splitlines()
    heads: list[int] = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            continue
        if _NUMBERED_HEAD.match(s) and len(s) <= 80:
            heads.append(i)
    if not heads:
        return paragraph_merge(raw, window=min(window, 1000))

    sections: list[tuple[str, str]] = []
    first = heads[0]
    if first > 0:
        preamble = "\n".join(lines[:first]).strip()
        if preamble:
            sections.append(("导言", preamble))
    for hi, start in enumerate(heads):
        end = heads[hi + 1] if hi + 1 < len(heads) else len(lines)
        title = lines[start].strip()
        body = "\n".join(lines[start:end]).strip()
        if body:
            sections.append((title, body))

    # 一节一块；纪要「姓名——主题」作为父标题写入子节正文，便于检索（待办不丢人名）
    person_re = re.compile(r"^[\u4e00-\u9fff]{2,4}——")
    chunks: list[dict[str, Any]] = []
    ordinal = 0
    parent = ""
    for title, body in sections:
        body = body.strip()
        if not body:
            continue
        if person_re.match(title):
            parent = title
            # 仅标题行、无实质内容 → 不单独成块，留给后续小节继承父标题
            if body == title or len(body) <= len(title) + 8:
                continue
        text = body
        meta_title = title
        if parent and not person_re.match(title):
            if not text.startswith(parent):
                text = f"{parent}\n\n{text}"
            meta_title = f"{parent} · {title}"
        if len(text) <= window:
            chunks.append(_piece(ordinal, text, {"title": meta_title, "parent": parent or None}))
            ordinal += 1
            continue
        for sc in paragraph_merge(text, window=window):
            meta = {"title": meta_title, "parent": parent or None, **(sc.get("meta") or {})}
            chunks.append(_piece(ordinal, sc["text"], meta))
            ordinal += 1
    return chunks or paragraph_merge(raw, window=min(window, 1000))


@register(
    "structured_fields",
    label_zh="按结构化字段",
    description="KnowledgeUnit 每个非空字段一块；空列表/空串跳过",
    default_options={},
)
def structured_fields(
    text: str,
    *,
    payload: dict[str, Any] | None = None,
    **_: Any,
) -> list[dict[str, Any]]:
    """plain 文本路径兜底；结构化 ingest 直接调 payload_utils。"""
    from knowledge_hub.payload_utils import iter_structured_field_chunks

    if payload:
        return iter_structured_field_chunks(payload)
    raw = (text or "").strip()
    if not raw:
        return []
    return paragraph_merge(raw, window=1200)
