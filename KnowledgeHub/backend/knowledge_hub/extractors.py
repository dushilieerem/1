# -*- coding: utf-8 -*-
"""从上传文件字节抽取纯文本，供 KnowledgeHub 入库。"""
from __future__ import annotations

import io
import re
from pathlib import Path


_BINARY_EXTS = {".docx", ".pdf"}


def is_binary_doc(file_name: str) -> bool:
    return Path(file_name or "").suffix.lower() in _BINARY_EXTS


def extract_text(file_name: str, data: bytes) -> str:
    """按扩展名抽取文本；失败抛 ValueError。"""
    if not data:
        raise ValueError("文件内容为空")
    ext = Path(file_name or "").suffix.lower()
    if ext == ".docx":
        return _from_docx(data)
    if ext == ".pdf":
        return _from_pdf(data)
    raise ValueError(f"暂不支持解析「{ext or '未知类型'}」，请上传 .docx / .pdf 或文本文件")


def _from_docx(data: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise ValueError("服务端未安装 python-docx，无法解析 Word") from exc
    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"无法打开 Word 文件：{exc}") from exc
    parts: list[str] = []
    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if t:
            parts.append(t)
    for table in doc.tables:
        for row in table.rows:
            cells = [(c.text or "").strip() for c in row.cells]
            line = " | ".join(c for c in cells if c)
            if line:
                parts.append(line)
    text = "\n\n".join(parts).strip()
    if not text:
        raise ValueError("Word 文件未解析出文字（可能是空文档或仅含图片）")
    return text


def _from_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError("服务端未安装 pypdf，无法解析 PDF") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"无法打开 PDF：{exc}") from exc
    pages: list[str] = []
    for page in reader.pages:
        try:
            raw = page.extract_text() or ""
        except Exception:
            raw = ""
        cleaned = _normalize_ws(raw)
        if cleaned:
            pages.append(cleaned)
        elif len(reader.pages) <= 3:
            # 短文档空白页可跳过；全空后面统一报错
            continue
    text = "\n\n".join(pages).strip()
    if not text:
        raise ValueError(
            "PDF 未解析出文字（可能是扫描件/图片版，需 OCR；本阶段仅支持可选中文本的 PDF）"
        )
    return text


def _normalize_ws(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()
