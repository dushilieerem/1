# -*- coding: utf-8 -*-
"""从上传文件字节抽取纯文本，供 KnowledgeHub 入库。"""
from __future__ import annotations

import io
import re
from pathlib import Path


_BINARY_EXTS = {".docx", ".pdf", ".xlsx"}
_TEXT_EXTS = {".md", ".markdown", ".html", ".htm", ".txt", ".csv", ".json", ".yaml", ".yml"}
_SUPPORTED_EXTS = _BINARY_EXTS | _TEXT_EXTS


def is_binary_doc(file_name: str) -> bool:
    return Path(file_name or "").suffix.lower() in _BINARY_EXTS


def is_extractable(file_name: str) -> bool:
    """P1-K06：可解析的文件类型（二进制或纯文本）。"""
    return Path(file_name or "").suffix.lower() in _SUPPORTED_EXTS


def extract_text(file_name: str, data: bytes) -> str:
    """按扩展名抽取文本；失败抛 ValueError。"""
    if not data:
        raise ValueError("文件内容为空")
    ext = Path(file_name or "").suffix.lower()
    if ext == ".docx":
        return _from_docx(data)
    if ext == ".pdf":
        return _from_pdf(data)
    if ext == ".xlsx":
        return _from_xlsx(data)
    if ext in _TEXT_EXTS:
        return _from_text(ext, data)
    raise ValueError(
        f"暂不支持解析「{ext or '未知类型'}」，请上传 "
        ".docx / .pdf / .xlsx / .md / .html / .txt"
    )


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文本编码（支持 UTF-8 / GB18030）")


def _from_text(ext: str, data: bytes) -> str:
    text = _decode_text(data)
    if ext in (".html", ".htm"):
        text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
        text = re.sub(r"(?i)<br\s*/?>|</(?:p|div|h[1-6]|li|tr|section|article)>", "\n", text)
        text = re.sub(r"<[^>]+>", " ", text)
        import html as html_lib

        text = html_lib.unescape(text)
    text = _normalize_ws(text)
    if not text:
        raise ValueError("文件未解析出文字")
    return text


def _from_xlsx(data: bytes) -> str:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise ValueError("服务端未安装 openpyxl，无法解析 Excel") from exc
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(f"无法打开 Excel 文件：{exc}") from exc
    parts: list[str] = []
    for sheet in wb.worksheets:
        parts.append(f"# {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if cells:
                parts.append(" | ".join(cells))
    text = _normalize_ws("\n".join(parts))
    if not text.strip():
        raise ValueError("Excel 未解析出内容")
    return text


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
