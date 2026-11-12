# -*- coding: utf-8 -*-
"""资讯真源拉取：CLS / 东财(市场+研报+政策) / 巨潮 / 见闻 / 同花顺 → news_items。"""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Any

from psycopg.types.json import Json

from services.core.db import get_conn
from services.news.news_store import (
    SOURCE_LABELS,
    ensure_news_schema,
    enforce_news_retention,
    record_ingest_run,
)

TZ8 = timezone(timedelta(hours=8))
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

_SYM_RE = re.compile(r"\b(\d{6})\.(SH|SZ|BJ)\b", re.I)
_HTML_BLOCK_RE = re.compile(
    r"</(?:p|div|h[1-6]|li|tr|blockquote|section|article)\s*>",
    re.I,
)
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_LINE_RE = re.compile(r"[ \t\u00a0]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def _cls_sign(params: dict[str, str]) -> str:
    """财联社 web 签名：md5(sha1(按 key 排序后的 query))。"""
    raw = "&".join(f"{k}={params[k]}" for k in sorted(params))
    sha1 = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return hashlib.md5(sha1.encode("utf-8")).hexdigest()


def _get_json(url: str, *, timeout: int = 20, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(
        url, headers={**UA, "Accept": "application/json,*/*", **(headers or {})}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return json.loads(raw)


def _post_form(url: str, form: dict[str, Any], *, timeout: int = 20) -> Any:
    data = urllib.parse.urlencode({k: str(v) for k, v in form.items()}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            **UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json,*/*",
            "Referer": "http://www.cninfo.com.cn/new/index.jsp",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _get_text(url: str, *, timeout: int = 20, referer: str | None = None) -> str:
    headers = {**UA, "Accept": "text/html,*/*"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _html_to_text(html: str) -> str:
    """HTML → 纯文本：解码实体、保留段落换行。"""
    if not html:
        return ""
    s = html_lib.unescape(html)
    s = _BR_RE.sub("\n", s)
    s = _HTML_BLOCK_RE.sub("\n\n", s)
    s = _HTML_TAG_RE.sub("", s)
    lines = [_WS_LINE_RE.sub(" ", ln).strip() for ln in s.splitlines()]
    s = "\n".join(ln for ln in lines if ln)
    s = _MULTI_NL_RE.sub("\n\n", s).strip()
    return s


def scrape_eastmoney_body(article_url: str) -> str:
    """从东财文章页抽正文：优先按 <p> 分段，解码 &#xxxx;。"""
    if not article_url:
        return ""
    if "/report/info/" in article_url or "data.eastmoney.com/report/" in article_url:
        return scrape_eastmoney_report(article_url)
    try:
        page = _get_text(article_url, timeout=15, referer="https://finance.eastmoney.com/")
    except Exception:
        return ""
    m = re.search(
        r'id=["\']ContentBody["\'][^>]*>([\s\S]*?)</div>\s*(?:<div|<!--)',
        page,
        re.I,
    )
    if not m:
        m = re.search(r'id=["\']ContentBody["\'][^>]*>([\s\S]*?)</div>', page, re.I)
    if not m:
        return ""
    inner = m.group(1)
    paras = re.findall(r"<p[^>]*>([\s\S]*?)</p>", inner, re.I)
    if paras:
        chunks: list[str] = []
        for p in paras:
            t = _html_to_text(p)
            if not t:
                continue
            # 跳过广告/推荐尾巴
            if any(x in t for x in ("点击查看", "相关报道", "文章来源：", "责任编辑")):
                if len(t) < 40 or t.startswith(("文章来源", "责任编辑", "点击查看")):
                    continue
            chunks.append(t)
        text = "\n\n".join(chunks)
    else:
        text = _html_to_text(inner)
    for cut in ("文章来源：", "风险提示：", "责任编辑：", "郑重声明："):
        idx = text.find(cut)
        if idx > 120:
            text = text[:idx].strip()
    return text[:20000]


def scrape_eastmoney_report(article_url: str) -> str:
    """东财研报详情：#ctx-content 投资要点/摘要（全文多为 PDF）。"""
    if not article_url:
        return ""
    try:
        page = _get_text(article_url, timeout=15, referer="https://data.eastmoney.com/")
    except Exception:
        return ""
    m = re.search(r'id=["\']ctx-content["\'][^>]*>([\s\S]*?)</div>', page, re.I)
    if not m:
        return ""
    inner = m.group(1)
    paras = re.findall(r"<p[^>]*>([\s\S]*?)</p>", inner, re.I)
    chunks: list[str] = []
    for p in paras:
        t = _html_to_text(p)
        if t:
            chunks.append(t)
    text = "\n\n".join(chunks).strip()
    if not text:
        return ""
    pdfs = re.findall(r"https://pdf\.dfcfw\.com/pdf/[^\"'\s<>]+", page)
    pdf = pdfs[0] if pdfs else ""
    if pdf:
        text = f"{text}\n\n——\n完整研报 PDF：{pdf}"
    return text[:20000]


def _parse_dt(value: Any) -> datetime:
    """解析源站时间；字段缺失或格式不认识时兜底为当前时间（调用方需注意兜底语义）。

    兜底值语义上是「抓取时刻」而非发布时间，入库后不应再被重抓覆盖
    （见 upsert_news_items 的 ON CONFLICT 处理）。
    """
    if value is None:
        return datetime.now(TZ8)
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=TZ8)
    s = str(value).strip()
    if s.isdigit():
        return _parse_dt(int(s))
    for fmt in (
        # 东财研报 publishDate 带毫秒后缀（如 2026-10-09 00:00:00.000）
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        # 仅日期，按当日 00:00(+8) 处理
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=TZ8)
        except ValueError:
            continue
    return datetime.now(TZ8)


def _code_to_symbol(code: str) -> str | None:
    c = (code or "").strip()
    if not re.fullmatch(r"\d{6}", c):
        return None
    if c.startswith(("5", "6", "9")) or c.startswith("688"):
        return f"{c}.SH"
    if c.startswith(("4", "8")):
        return f"{c}.BJ"
    return f"{c}.SZ"


def _extract_symbols(*texts: str, extra: list[Any] | None = None) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def add(code: str) -> None:
        c = code.upper()
        if c not in seen:
            seen.add(c)
            found.append(c)

    for item in extra or []:
        if isinstance(item, str):
            s = item.strip()
            if _SYM_RE.fullmatch(s):
                add(s)
            else:
                sym = _code_to_symbol(s)
                if sym:
                    add(sym)
        elif isinstance(item, dict):
            code = str(
                item.get("symbol")
                or item.get("code")
                or item.get("stock_code")
                or item.get("secCode")
                or ""
            ).strip()
            if _SYM_RE.fullmatch(code):
                add(code)
            else:
                sym = _code_to_symbol(code)
                if sym:
                    add(sym)
    blob = " ".join(t for t in texts if t)
    for m in _SYM_RE.finditer(blob):
        add(f"{m.group(1)}.{m.group(2).upper()}")
    return found[:8]


def _themes_from_tags(tags: Any) -> list[str]:
    out: list[str] = []
    if isinstance(tags, list):
        for t in tags:
            if isinstance(t, str) and t.strip():
                out.append(t.strip())
            elif isinstance(t, dict):
                name = str(
                    t.get("name")
                    or t.get("title")
                    or t.get("subject_name")
                    or ""
                ).strip()
                if name:
                    out.append(name)
    elif isinstance(tags, str) and tags.strip():
        out.extend(x.strip() for x in tags.split(",") if x.strip())
    seen: set[str] = set()
    uniq: list[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq[:8]


def _hash_key(source: str, url: str, title: str, published_at: datetime) -> str:
    base = f"{source}|{url.strip()}|{title.strip()}|{published_at.isoformat()}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _norm_item(
    *,
    source: str,
    title: str,
    summary: str,
    body: str,
    url: str,
    published_at: datetime,
    category: str,
    symbols: list[str],
    themes: list[str],
    is_flash: bool,
    raw_key: str | None = None,
) -> dict[str, Any] | None:
    title = html_lib.unescape((title or "").strip())
    summary = html_lib.unescape((summary or "").strip())
    body = html_lib.unescape((body or summary or "").strip())
    url = (url or "").strip()
    if not title and not summary:
        return None
    if not title:
        title = summary[:80]
    if not summary:
        summary = (body[:160] if body else title).replace("\n", " ")
    # 摘要单行
    summary = _WS_LINE_RE.sub(" ", summary.replace("\n", " ")).strip()
    key = raw_key or _hash_key(source, url or title, title, published_at)
    from services.news.news_tag_dict import enrich_news_tags

    themes_out, industries_out = enrich_news_tags(
        title=title,
        summary=summary,
        body=body,
        themes=list(themes or []),
    )
    return {
        "source": source,
        "title": title[:300],
        "summary": summary[:800],
        "body": body[:20000],
        "url": url[:500],
        "published_at": published_at,
        "category": category,
        "symbols": symbols,
        "themes": themes_out,
        "industries": industries_out,
        "is_flash": bool(is_flash),
        "is_featured": False,
        "raw_hash": key
        if len(key) == 40 and re.fullmatch(r"[0-9a-f]+", key)
        else hashlib.sha1(key.encode()).hexdigest(),
    }


def fetch_cls(*, limit: int = 20) -> list[dict[str, Any]]:
    """财联社电报：api/cache?name=telegraph + 签名。"""
    params = {"app": "CailianpressWeb", "os": "web", "sv": "8.4.6"}
    params["sign"] = _cls_sign(params)
    url = "https://www.cls.cn/api/cache?name=telegraph&" + urllib.parse.urlencode(params)
    data = _get_json(url, headers={"Referer": "https://www.cls.cn/telegraph"})
    if int(data.get("errno") or 0) != 0:
        raise RuntimeError(str(data.get("msg") or "cls api error"))
    rows = ((data.get("data") or {}).get("roll_data")) or []
    out: list[dict[str, Any]] = []
    for r in rows[: max(1, min(50, limit))]:
        content = _html_to_text(str(r.get("content") or r.get("brief") or ""))
        title = str(r.get("title") or "").strip() or content[:80]
        aid = r.get("id")
        link = f"https://www.cls.cn/detail/{aid}" if aid else "https://www.cls.cn/telegraph"
        stocks = r.get("stock_list") if isinstance(r.get("stock_list"), list) else []
        themes = _themes_from_tags(r.get("subjects") or [])
        item = _norm_item(
            source="cls",
            title=title,
            summary=content[:800],
            body=content,
            url=link,
            published_at=_parse_dt(r.get("ctime")),
            category="flash",
            symbols=_extract_symbols(title, content, extra=stocks),
            themes=themes,
            is_flash=True,
            raw_key=f"cls:telegraph:{aid}",
        )
        if item:
            out.append(item)
    return out


def fetch_eastmoney(*, limit: int = 20, enrich_body: bool = True) -> list[dict[str, Any]]:
    url = (
        "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
        "?client=web&biz=web_news_col&column=350&order=1&needInteractData=0"
        f"&page_index=1&page_size={max(1, min(50, limit))}&req_trace=1"
    )
    data = _get_json(url)
    rows = ((data.get("data") or {}).get("list")) or []
    out: list[dict[str, Any]] = []
    for r in rows:
        title = str(r.get("title") or "")
        summary = str(r.get("summary") or "")
        link = str(r.get("uniqueUrl") or r.get("url") or "")
        pub = _parse_dt(r.get("showTime"))
        body = summary
        if enrich_body and link:
            scraped = scrape_eastmoney_body(link)
            if len(scraped) > len(body):
                body = scraped
        item = _norm_item(
            source="eastmoney",
            title=title,
            summary=summary,
            body=body,
            url=link,
            published_at=pub,
            category="market",
            symbols=_extract_symbols(title, summary, body),
            themes=_themes_from_tags([r.get("mediaName")] if r.get("mediaName") else []),
            is_flash=False,
            raw_key=f"eastmoney:{r.get('code') or link}",
        )
        if item:
            out.append(item)
    return out


def fetch_eastmoney_research(*, limit: int = 20, enrich_body: bool = True) -> list[dict[str, Any]]:
    """东财研报列表（reportapi）→ category=research；源仍记 eastmoney。"""
    today = datetime.now(TZ8).date()
    begin = (today - timedelta(days=30)).isoformat()
    end = today.isoformat()
    qs = urllib.parse.urlencode(
        {
            "industryCode": "*",
            "pageSize": max(1, min(50, limit)),
            "industry": "*",
            "rating": "*",
            "ratingChange": "*",
            "beginTime": begin,
            "endTime": end,
            "pageNo": 1,
            "fields": "",
            "qType": 0,
            "orgCode": "",
            "rcode": "",
            "p": 1,
            "isPublish": "false",
        }
    )
    url = f"https://reportapi.eastmoney.com/report/list?{qs}"
    data = _get_json(
        url,
        headers={"Referer": "https://data.eastmoney.com/report/stock.jshtml"},
    )
    rows = data.get("data") or []
    out: list[dict[str, Any]] = []
    for r in rows[: max(1, min(50, limit))]:
        title = str(r.get("title") or "").strip()
        info = str(r.get("infoCode") or "").strip()
        org = str(r.get("orgSName") or r.get("orgName") or "").strip()
        stock_name = str(r.get("stockName") or "").strip()
        stock_code = str(r.get("stockCode") or "").strip()
        rating = str(r.get("emRatingName") or r.get("ratingName") or "").strip()
        link = (
            f"https://data.eastmoney.com/report/info/{info}.html"
            if info
            else "https://data.eastmoney.com/report/stock.jshtml"
        )
        bits = [x for x in (org, f"{stock_name}({stock_code})" if stock_code else stock_name, rating) if x]
        summary = "｜".join(bits) if bits else title
        body = summary or title
        if enrich_body and link:
            scraped = scrape_eastmoney_report(link)
            if scraped:
                body = scraped
                # 列表摘要偏短时，用正文首段补摘要
                first = scraped.split("\n\n", 1)[0].strip()
                if first and (len(summary) < 40 or summary == title):
                    summary = first[:800]
        themes = ["研报"]
        if org:
            themes.append(org)
        item = _norm_item(
            source="eastmoney",
            title=title,
            summary=summary[:800],
            body=body,
            url=link,
            published_at=_parse_dt(r.get("publishDate")),
            category="research",
            symbols=_extract_symbols(title, summary, body, extra=[stock_code] if stock_code else []),
            themes=themes,
            is_flash=False,
            raw_key=f"eastmoney:research:{info or title}",
        )
        if item:
            out.append(item)
    return out


def fetch_eastmoney_policy(*, limit: int = 20) -> list[dict[str, Any]]:
    """东财政策向栏目（column=355）→ category=policy；源仍记 eastmoney。"""
    url = (
        "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
        "?client=web&biz=web_news_col&column=355&order=1&needInteractData=0"
        f"&page_index=1&page_size={max(1, min(50, limit))}&req_trace=1"
        "&fields=code,title,summary,showTime,uniqueUrl,url,mediaName"
    )
    data = _get_json(url, headers={"Referer": "https://finance.eastmoney.com/"})
    rows = ((data.get("data") or {}).get("list")) or []
    out: list[dict[str, Any]] = []
    for r in rows:
        title = str(r.get("title") or "")
        summary = str(r.get("summary") or "")
        link = str(r.get("uniqueUrl") or r.get("url") or "")
        pub = _parse_dt(r.get("showTime"))
        body = summary or title
        if link:
            scraped = scrape_eastmoney_body(link)
            if len(scraped) > len(body):
                body = scraped
        themes = ["政策"]
        media = str(r.get("mediaName") or "").strip()
        if media:
            themes.append(media)
        item = _norm_item(
            source="eastmoney",
            title=title,
            summary=summary or title,
            body=body,
            url=link,
            published_at=pub,
            category="policy",
            symbols=_extract_symbols(title, summary, body),
            themes=themes,
            is_flash=False,
            raw_key=f"eastmoney:policy:{r.get('code') or link}",
        )
        if item:
            out.append(item)
    return out


def fetch_cninfo(*, limit: int = 20) -> list[dict[str, Any]]:
    """巨潮公告列表（标题 + PDF 链；全文为 PDF，站内存摘要说明）。"""
    data = _post_form(
        "http://www.cninfo.com.cn/new/hisAnnouncement/query",
        {
            "pageNum": 1,
            "pageSize": max(1, min(30, limit)),
            "column": "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": "",
            "searchkey": "",
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": "",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        },
    )
    rows = data.get("announcements") or []
    out: list[dict[str, Any]] = []
    for r in rows:
        title = str(r.get("announcementTitle") or "").strip()
        code = str(r.get("secCode") or "").strip()
        name = str(r.get("secName") or "").strip()
        adjunct = str(r.get("adjunctUrl") or "").strip()
        pdf = f"http://static.cninfo.com.cn/{adjunct}" if adjunct else "https://www.cninfo.com.cn/"
        pub = _parse_dt(r.get("announcementTime"))
        summary = f"{name}（{code}）披露公告：{title}" if code else title
        body = (
            f"{summary}\n\n"
            f"法定信披原文为 PDF，请打开源站或附件查看全文。\n"
            f"附件：{pdf}"
        )
        aid = str(r.get("announcementId") or adjunct or title)
        item = _norm_item(
            source="cninfo",
            title=title or summary,
            summary=summary[:800],
            body=body,
            url=pdf,
            published_at=pub,
            category="announce",
            symbols=_extract_symbols(extra=[code] if code else []),
            themes=["法定公告"],
            is_flash=False,
            raw_key=f"cninfo:{aid}",
        )
        if item:
            out.append(item)
    return out


def fetch_wallstreetcn(*, limit: int = 20) -> list[dict[str, Any]]:
    url = (
        "https://api-one-wscn.awtmt.com/apiv1/content/lives"
        f"?channel=global-channel&client=pc&limit={max(1, min(50, limit))}"
    )
    data = _get_json(url)
    rows = ((data.get("data") or {}).get("items")) or []
    out: list[dict[str, Any]] = []
    for r in rows:
        title = str(r.get("title") or r.get("highlight_title") or "").strip()
        content = _html_to_text(str(r.get("content_text") or r.get("content") or ""))
        if not title:
            title = content[:80]
        link = str(r.get("uri") or "")
        if link and link.startswith("/"):
            link = "https://wallstreetcn.com" + link
        pub = _parse_dt(r.get("display_time"))
        themes = _themes_from_tags(r.get("tags") or r.get("related_themes"))
        item = _norm_item(
            source="wallstreetcn",
            title=title,
            summary=content[:800] if content else title,
            body=content or title,
            url=link,
            published_at=pub,
            category="global",
            symbols=_extract_symbols(title, content, extra=r.get("symbols") or []),
            themes=themes,
            is_flash=len(content) < 220,
            raw_key=f"wallstreetcn:{r.get('id') or link}",
        )
        if item:
            out.append(item)
    return out


def fetch_10jqka(*, limit: int = 20) -> list[dict[str, Any]]:
    url = "https://news.10jqka.com.cn/tapp/news/push/stock/?page=1&tag=&track=website"
    data = _get_json(url)
    rows = ((data.get("data") or {}).get("list")) or []
    out: list[dict[str, Any]] = []
    for r in rows[: max(1, min(50, limit))]:
        title = str(r.get("title") or "")
        digest = str(r.get("digest") or "")
        link = str(r.get("url") or r.get("shareUrl") or "")
        pub = _parse_dt(r.get("ctime") or r.get("rtime"))
        themes = _themes_from_tags(r.get("tags") or r.get("tag"))
        stocks = r.get("stock") if isinstance(r.get("stock"), list) else []
        item = _norm_item(
            source="10jqka",
            title=title,
            summary=digest or title,
            body=digest or title,
            url=link,
            published_at=pub,
            category="flash" if len(digest) < 180 else "market",
            symbols=_extract_symbols(title, digest, extra=stocks),
            themes=themes,
            is_flash=True,
            raw_key=f"10jqka:{r.get('seq') or r.get('id') or link or title}",
        )
        if item:
            out.append(item)
    return out


FETCHERS = {
    "cls": fetch_cls,
    "eastmoney": fetch_eastmoney,
    "em_research": fetch_eastmoney_research,
    "em_policy": fetch_eastmoney_policy,
    "cninfo": fetch_cninfo,
    "wallstreetcn": fetch_wallstreetcn,
    "10jqka": fetch_10jqka,
}

# 彭博：本机访问 bloomberg.com/asia 超时，bloombergchina 403；需代理或官方 API，暂不入库。
UNSUPPORTED_SOURCES = {
    "bloomberg": "彭博公开站本机超时/403；需海外出口或官方终端 API。一期外链官网即可。",
}


def upsert_news_items(items: list[dict[str, Any]]) -> dict[str, int]:
    if not items:
        return {"upserted": 0}
    with get_conn() as conn:
        for it in items:
            # published_at 一经确定不再被重抓覆盖：_parse_dt 在源字段缺失/解析失败时
            # 会兜底成抓取时刻，若用 EXCLUDED 覆盖，会把首次解析出的真实发布时间冲掉，
            # 且每次定时重抓都会漂移（东财研报曾因此全部变成抓取时间）。
            conn.execute(
                """
                INSERT INTO news_items (
                  title, summary, body, published_at, source, category, url,
                  symbols, themes, industries, raw_hash, is_flash, is_featured
                ) VALUES (
                  %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (raw_hash) DO UPDATE SET
                  title = EXCLUDED.title,
                  summary = EXCLUDED.summary,
                  body = CASE
                    WHEN length(EXCLUDED.body) >= length(COALESCE(news_items.body, ''))
                    THEN EXCLUDED.body ELSE news_items.body END,
                  published_at = news_items.published_at,
                  symbols = EXCLUDED.symbols,
                  themes = EXCLUDED.themes,
                  industries = EXCLUDED.industries,
                  is_flash = EXCLUDED.is_flash,
                  url = CASE
                    WHEN length(EXCLUDED.url) > 0 THEN EXCLUDED.url ELSE news_items.url END
                """,
                (
                    it["title"],
                    it["summary"],
                    it["body"],
                    it["published_at"],
                    it["source"],
                    it["category"],
                    it["url"],
                    Json(it.get("symbols") or []),
                    Json(it.get("themes") or []),
                    Json(it.get("industries") or []),
                    it["raw_hash"],
                    it.get("is_flash", False),
                    it.get("is_featured", False),
                ),
            )
    # 写入后立刻 FIFO 裁剪，避免定时任务未加载新代码时持续超限
    try:
        enforce_news_retention()
    except Exception as exc:
        print(f"[news] retention after upsert fail: {exc}")
    return {"upserted": len(items)}


def backfill_news_tags(*, limit: int = 200) -> int:
    """给已入库条目补 themes / industries（字典命中）。"""
    from services.news.news_tag_dict import enrich_news_tags

    updated = 0
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, title, summary, body, themes, industries
            FROM news_items
            ORDER BY published_at DESC
            LIMIT %s
            """,
            (max(1, min(500, limit)),),
        ).fetchall()
        for row in rows:
            old_t = row["themes"] if isinstance(row["themes"], list) else []
            old_i = row["industries"] if isinstance(row["industries"], list) else []
            themes, industries = enrich_news_tags(
                title=row["title"] or "",
                summary=row["summary"] or "",
                body=row["body"] or "",
                themes=[str(x) for x in old_t],
                industries=[str(x) for x in old_i],
            )
            if themes == [str(x) for x in old_t] and industries == [str(x) for x in old_i]:
                continue
            conn.execute(
                """
                UPDATE news_items
                SET themes = %s, industries = %s
                WHERE id = %s
                """,
                (Json(themes), Json(industries), int(row["id"])),
            )
            updated += 1
    return updated


def enrich_news_body(news_id: int) -> dict[str, Any]:
    """对已入库且正文偏短/格式差的条目补抓（目前主要东财 HTML）。"""
    ensure_news_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM news_items WHERE id = %s", (int(news_id),)
        ).fetchone()
        if not row:
            raise KeyError(news_id)
        source = row["source"]
        url = row["url"] or ""
        body = row["body"] or ""
        summary = row["summary"] or ""
        new_body = body
        if source == "eastmoney" and url:
            scraped = scrape_eastmoney_body(url)
            bad_fmt = (
                ("&#" in body)
                or ("\n\n" not in body and len(body) > 400)
                or ("来源：东方财富研报" in body)
                or ("原文：https://data.eastmoney.com/report/" in body)
            )
            if scraped and (len(scraped) > len(body) + 20 or bad_fmt):
                new_body = scraped
        elif "&#" in body:
            new_body = html_lib.unescape(body)
        if new_body == body and (not body or body == summary):
            return {
                "ok": True,
                "id": int(news_id),
                "enriched": False,
                "message": "未能抓到更长正文，请看源站原文",
            }
        if new_body != body:
            conn.execute(
                "UPDATE news_items SET body = %s WHERE id = %s",
                (new_body[:20000], int(news_id)),
            )
        return {
            "ok": True,
            "id": int(news_id),
            "enriched": new_body != body,
            "bodyLen": len(new_body),
        }


def purge_demo_seeds() -> int:
    """清除「站内演示」种子，避免与真源混排。"""
    with get_conn() as conn:
        cur = conn.execute(
            """
            DELETE FROM news_items
            WHERE raw_hash LIKE 'seed:%'
               OR body LIKE '%（站内演示正文）%'
            """
        )
        return int(cur.rowcount or 0)


def refresh_eastmoney_bodies(*, limit: int = 40) -> int:
    """批量重抓东财正文（市场新闻 + 研报摘要）。"""
    updated = 0
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, url, body, category
            FROM news_items
            WHERE source = 'eastmoney' AND COALESCE(url, '') <> ''
            ORDER BY published_at DESC
            LIMIT %s
            """,
            (max(1, min(80, limit)),),
        ).fetchall()
    for row in rows:
        scraped = scrape_eastmoney_body(row["url"] or "")
        if not scraped:
            continue
        old = row["body"] or ""
        bad = (
            ("&#" in old)
            or ("\n\n" not in old and len(old) > 400)
            or ("来源：东方财富研报" in old)
            or ("原文：https://data.eastmoney.com/report/" in old)
        )
        if len(scraped) > len(old) + 20 or bad:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE news_items SET body = %s WHERE id = %s",
                    (scraped[:20000], int(row["id"])),
                )
            updated += 1
    return updated


def backfill_eastmoney_research_dates(*, max_pages: int = 40) -> dict[str, int]:
    """回填东财研报 published_at：历史数据曾因 ".000" 毫秒后缀解析失败被兜底为抓取时间。

    重新拉 reportapi 列表建立 infoCode → 发布日期 映射，按 URL 中的 infoCode 纠正库内条目。
    窗口从库内最早 created_at 往前推 2 天，覆盖所有存量研报。
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, url, published_at, created_at
            FROM news_items
            WHERE source = 'eastmoney' AND category = 'research'
            """
        ).fetchall()
    if not rows:
        return {"rows": 0, "matched": 0, "updated": 0, "skipped": 0, "fetched": 0}

    by_code: dict[str, list[Any]] = {}
    for r in rows:
        m = re.search(r"/report/info/([0-9A-Za-z]+)\.html", r["url"] or "")
        if m:
            by_code.setdefault(m.group(1), []).append(r)

    begin = (min(r["created_at"] for r in rows).date() - timedelta(days=2)).isoformat()
    end = datetime.now(TZ8).date().isoformat()
    date_map: dict[str, datetime] = {}
    for page_no in range(1, max(1, max_pages) + 1):
        qs = urllib.parse.urlencode(
            {
                "industryCode": "*",
                "pageSize": 50,
                "industry": "*",
                "rating": "*",
                "ratingChange": "*",
                "beginTime": begin,
                "endTime": end,
                "pageNo": page_no,
                "fields": "",
                "qType": 0,
                "orgCode": "",
                "rcode": "",
                "p": page_no,
                "isPublish": "false",
            }
        )
        data = _get_json(
            f"https://reportapi.eastmoney.com/report/list?{qs}",
            headers={"Referer": "https://data.eastmoney.com/report/stock.jshtml"},
        )
        page = data.get("data") or []
        if not page:
            break
        for r in page:
            info = str(r.get("infoCode") or "").strip()
            raw = r.get("publishDate")
            if info and raw and info not in date_map:
                date_map[info] = _parse_dt(raw)
        # 已集齐全部目标 infoCode 或翻到末页即可停
        if len(page) < 50 or set(by_code) <= set(date_map):
            break

    matched = updated = 0
    with get_conn() as conn:
        for code, items in by_code.items():
            dt = date_map.get(code)
            if dt is None:
                continue
            matched += len(items)
            for r in items:
                if r["published_at"] != dt:
                    conn.execute(
                        "UPDATE news_items SET published_at = %s WHERE id = %s",
                        (dt, int(r["id"])),
                    )
                    updated += 1
    return {
        "rows": len(rows),
        "matched": matched,
        "updated": updated,
        "skipped": len(rows) - matched,
        "fetched": len(date_map),
    }


def _retry_config() -> tuple[int, float]:
    """P1-C06：每源失败重试次数与线性退避基数。"""
    from services.core.env_config import env

    try:
        retries = max(0, min(5, int(env("NEWS_FETCH_RETRIES", "2") or "2")))
    except (TypeError, ValueError):
        retries = 2
    try:
        backoff = max(0.0, min(60.0, float(env("NEWS_FETCH_BACKOFF_SEC", "2") or "2")))
    except (TypeError, ValueError):
        backoff = 2.0
    return retries, backoff


def ingest_news(
    *,
    sources: list[str] | None = None,
    limit_per_source: int = 15,
) -> dict[str, Any]:
    """P1-O06：多实例下同一时刻只允许一轮抓取。"""
    from services.core.distributed_lock import advisory_lock

    with advisory_lock("svquant:news:ingest") as acquired:
        if not acquired:
            return {"ok": False, "skipped": True, "reason": "another instance is ingesting"}
        return _ingest_news_impl(sources=sources, limit_per_source=limit_per_source)


def _ingest_news_impl(
    *,
    sources: list[str] | None = None,
    limit_per_source: int = 15,
) -> dict[str, Any]:
    ensure_news_schema()
    wanted = sources or list(FETCHERS.keys())
    per_source: dict[str, Any] = {}
    all_items: list[dict[str, Any]] = []
    errors: dict[str, str] = {}

    for sid in wanted:
        if sid in UNSUPPORTED_SOURCES:
            errors[sid] = UNSUPPORTED_SOURCES[sid]
            per_source[sid] = {
                "ok": False,
                "count": 0,
                "label": SOURCE_LABELS.get(sid, sid),
                "error": UNSUPPORTED_SOURCES[sid],
            }
            continue
        fn = FETCHERS.get(sid)
        if not fn:
            errors[sid] = "unsupported source"
            continue
        attempts = 0
        last_exc: Exception | None = None
        items: list[dict[str, Any]] = []
        retries, backoff = _retry_config()
        for attempt in range(retries + 1):
            attempts = attempt + 1
            try:
                items = fn(limit=limit_per_source)
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < retries:
                    time.sleep(backoff * (attempt + 1))
        if last_exc is None:
            per_source[sid] = {
                "ok": True,
                "count": len(items),
                "label": SOURCE_LABELS.get(sid, sid),
                "attempts": attempts,
            }
            all_items.extend(items)
        else:
            errors[sid] = str(last_exc)[:240]
            per_source[sid] = {
                "ok": False,
                "count": 0,
                "label": SOURCE_LABELS.get(sid, sid),
                "error": str(last_exc)[:240],
                "attempts": attempts,
            }

    uniq: dict[str, dict[str, Any]] = {}
    for it in all_items:
        uniq[it["raw_hash"]] = it
    batch = list(uniq.values())
    stats = upsert_news_items(batch)
    purged = purge_demo_seeds() if batch else 0
    retention: dict[str, int] = {}
    try:
        retention = enforce_news_retention()
    except Exception:
        retention = {}
    refreshed = 0
    em_touched = any(
        sid in ("eastmoney", "em_research", "em_policy") for sid in (wanted or [])
    ) or any(
        s.get("ok")
        and s.get("label")
        in (
            SOURCE_LABELS.get("eastmoney"),
            SOURCE_LABELS.get("em_research"),
            SOURCE_LABELS.get("em_policy"),
        )
        for s in per_source.values()
    )
    if em_touched:
        try:
            refreshed = refresh_eastmoney_bodies(limit=30)
        except Exception:
            refreshed = 0
    retagged = 0
    try:
        retagged = backfill_news_tags(limit=max(80, limit_per_source * 8))
    except Exception:
        retagged = 0
    result = {
        "ok": True,
        "fetched": len(batch),
        "upserted": stats["upserted"],
        "purgedDemo": purged,
        "retention": retention or None,
        "refreshedEastmoney": refreshed,
        "retagged": retagged,
        "sources": per_source,
        "errors": errors or None,
        "note": (
            "正文完整度：东财长文可抓全文；研报为列表摘要+详情链；政策栏目可抓全文；"
            "财联社/见闻电报本身即全文短讯；同花顺多为摘要；巨潮为公告标题+PDF；彭博暂不可用。"
        ),
    }
    try:
        record_ingest_run(result)  # P1-C07：抓取健康留痕
    except Exception:
        pass
    return result


def start_news_ingest_scheduler() -> None:
    """后台定时拉取（用户页不暴露按钮）。NEWS_INGEST_INTERVAL_SEC=0 关闭。"""
    import threading
    import time

    try:
        from services.core.env_config import env

        raw = env("NEWS_INGEST_INTERVAL_SEC", "900") or "900"
        interval = int(raw)
    except Exception:
        interval = 900
    if interval <= 0:
        print("  news ingest scheduler: disabled (NEWS_INGEST_INTERVAL_SEC<=0)")
        return

    limit = 12
    try:
        from services.core.env_config import env as _env

        limit = int(_env("NEWS_INGEST_LIMIT", "12") or "12")
    except Exception:
        pass

    # P1-O06：调度只负责入队；任意实例的 worker 领取执行
    from services.core.job_queue import enqueue, start_worker

    def _run(payload: dict[str, Any]) -> dict[str, Any]:
        n = int(payload.get("limit") or limit)
        return ingest_news(limit_per_source=n)

    start_worker("news.ingest", _run, poll_sec=max(5, min(30, interval // 10)))

    def _loop() -> None:
        # 启动后稍等再首拉，避免拖慢 API 就绪
        time.sleep(min(45, max(5, interval // 20)))
        while True:
            try:
                enqueue("news.ingest", {"limit": limit})
                print("[news] scheduled ingest enqueued")
            except Exception as exc:
                print(f"[news] enqueue fail: {exc}")
            time.sleep(interval)

    threading.Thread(target=_loop, name="news-ingest", daemon=True).start()
    print(f"  news ingest scheduler: every {interval}s · limit/source={limit}")
