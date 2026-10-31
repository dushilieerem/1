# -*- coding: utf-8 -*-
"""Agent A 在线资料检索：按问题去搜，而不是只扫最新栏目。"""
from __future__ import annotations

import base64
import hashlib
import html as html_lib
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

_TZ = timezone(timedelta(hours=8))
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_TLS_VERIFY = (os.environ.get("GATHER_TLS_VERIFY", "1") or "1").strip() not in {"0", "false", "False", "no"}
_SSL = ssl.create_default_context() if _TLS_VERIFY else ssl._create_unverified_context()
_ZH_EN = {
    "动量": "momentum",
    "反转": "reversal",
    "换手": "turnover",
    "成交量": "volume",
    "波动": "volatility",
    "价值": "value factor",
    "质量": "quality factor",
    "因子": "factor",
    "溢价": "premium",
    "异象": "return anomaly",
    "异常": "return anomaly",
    "衰减": "decay",
    "风格": "style factor",
    "流动性": "liquidity",
    "隔夜": "overnight return",
    "量价": "price volume factor",
    "微观结构": "market microstructure",
    "微观": "microstructure",
    "选股": "stock selection",
    "量化": "quantitative",
    "半导体": "semiconductor",
    "固态电池": "solid-state battery",
    "光模块": "optical module",
    "算力": "computing power",
    "CPO": "CPO optical",
}
_CN_HOSTS = (
    "eastmoney.com",
    "dfcfw.com",
    "10jqka.com.cn",
    "sina.com.cn",
    "xueqiu.com",
    "cls.cn",
    "wallstreetcn.com",
    "yicai.com",
    "stcn.com",
    "cs.com.cn",
    "hexun.com",
    "jrj.com.cn",
    "joinquant.com",
    "bigquant.com",
    "ricequant.com",
    "uqer.io",
    "zhihu.com",
    "ssrn.com",
    "arxiv.org",
    "nber.org",
    "bing.com",
    "cn.bing.com",
    "so.com",
)
_PROXY = (
    os.environ.get("GATHER_HTTP_PROXY")
    or os.environ.get("HTTPS_PROXY")
    or os.environ.get("https_proxy")
    or os.environ.get("HTTP_PROXY")
    or os.environ.get("http_proxy")
    or ""
).strip()


def _now() -> datetime:
    return datetime.now(_TZ)


def _strip_html(raw: str) -> str:
    text = html_lib.unescape(re.sub(r"<[^>]+>", "", raw or ""))
    return re.sub(r"\s+", " ", text).strip()


def _item(
    *,
    source_type: str,
    eid: str,
    title: str,
    snippet: str,
    url: str,
    published_at: str = "",
    source_label: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": eid,
        "source_type": source_type,
        "title": (title or "").strip()[:200] or eid,
        "snippet": re.sub(r"\s+", " ", (snippet or "").strip())[:2400],
        "url": (url or "").strip() or None,
        "published_at": published_at or "",
        "source_label": source_label,
        "sv_news_id": None,
        "category": source_type,
        "themes": [source_type],
        "symbols": [],
        "relevance": 0.0,
    }
    if extra:
        row.update(extra)
    return row


def _https_handler() -> urllib.request.HTTPSHandler:
    return urllib.request.HTTPSHandler(context=_SSL)


def _opener(kind: str) -> urllib.request.OpenerDirector:
    if kind == "direct":
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _https_handler(),
        )
    proxy = {"http": _PROXY, "https": _PROXY}
    return urllib.request.build_opener(
        urllib.request.ProxyHandler(proxy),
        _https_handler(),
    )


def _http_get(url: str, *, timeout: int = 12, headers: dict[str, str] | None = None) -> bytes:
    host = (urllib.parse.urlparse(url).netloc or "").lower()
    prefer_direct = any(h in host for h in _CN_HOSTS)
    if not _PROXY:
        order = ("direct",)
    else:
        order = ("direct", "proxy") if prefer_direct else ("proxy", "direct")
    last_exc: Exception | None = None
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _UA, "Accept": "*/*", **(headers or {})},
    )
    for kind in order:
        try:
            with _opener(kind).open(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue
    raise last_exc or RuntimeError("http get failed")


def _http_get_json(url: str, *, timeout: int = 12, headers: dict[str, str] | None = None) -> Any:
    raw = _http_get(url, timeout=timeout, headers=headers)
    text = raw.decode("utf-8", "replace").strip()
    if text.startswith("jQuery") or text.startswith("(") or text[:32].startswith("jQuery"):
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise json.JSONDecodeError("jsonp", text, 0)
        text = m.group(0)
    return json.loads(text)


def search_tokens(topic: str) -> list[str]:
    """短概念词，不用整句当检索词。"""
    text = (topic or "").strip()
    out: list[str] = []
    for k in sorted(_ZH_EN.keys(), key=len, reverse=True):
        if k in text and k not in out:
            out.append(k)
    extra = ("选股", "量化", "衰减", "风格", "异象", "异常", "隔夜", "量价", "流动性")
    for k in extra:
        if k in text and k not in out:
            out.append(k)
    stop = {
        "最近", "一周", "相关", "有哪些", "什么", "哪些", "要点", "请", "帮我",
        "看看", "的", "和", "与", "在", "是否", "有效", "研究", "问题",
        "近年", "仍然", "如何", "构造", "上", "近五年", "A股", "沪深",
        "这几年", "有没有", "明显", "还", "吗", "经典", "讨论",
    }
    parts = re.split(r"[\s/｜|、，,。？?！!；;：:（）()【】\[\]「」]+", text)
    for p in parts:
        s = p.strip()
        if len(s) < 2 or len(s) > 8 or s in stop:
            continue
        if s not in out:
            out.append(s)
        if len(out) >= 8:
            break
    return out[:8]


_QUERY_STOP = {
    "最近", "一周", "相关", "有哪些", "什么", "哪些", "要点", "请", "帮我",
    "看看", "的", "和", "与", "在", "是否", "有效", "研究", "问题",
    "近年", "仍然", "如何", "构造", "上", "近五年", "A股", "沪深",
    "这几年", "有没有", "还有没有", "明显", "还", "吗", "经典", "讨论",
    "公开", "线索", "最近有", "还有",
}
_WEAK_ALONE = {
    "因子", "量化", "异常", "异象", "衰减", "风格", "股票", "市场", "公司",
    "问题", "研究", "选股", "讨论", "方向", "最近", "金工", "复现",
}


def distinctive_phrases(topic: str) -> list[str]:
    """从原句抽出本题专有片段，不按主题写 if。"""
    text = (topic or "").strip()
    if not text:
        return []
    scrub = text
    for s in sorted(_QUERY_STOP, key=len, reverse=True):
        scrub = scrub.replace(s, " ")
    phrases: list[str] = []
    for k in sorted(_ZH_EN.keys(), key=len, reverse=True):
        if k in text and k not in _WEAK_ALONE:
            phrases.append(k)
    for run in re.findall(r"[\u4e00-\u9fff]+", scrub):
        if 2 <= len(run) <= 16 and run not in _WEAK_ALONE:
            phrases.append(run)
            if len(run) >= 4:
                phrases.append(run[:4])
            if len(run) >= 6:
                phrases.append(run[:6])
    for m in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,24}", text):
        if m.lower() not in {"a", "share", "the", "and", "or"}:
            phrases.append(m)
    uniq = list(dict.fromkeys(p for p in phrases if p and p not in _WEAK_ALONE))
    uniq.sort(key=lambda x: (-len(x), x))
    return uniq[:6]


def cn_search_queries(topic: str) -> list[str]:
    """中文检索：优先本题短语，不再先泛化成「因子异象 衰减」。"""
    phrases = distinctive_phrases(topic)
    out: list[str] = []
    for p in phrases[:3]:
        out.append(p)
        if "因子" not in p:
            out.append(f"{p} 因子")
    if len(phrases) >= 2:
        out.append(" ".join(phrases[:2]))
    if not out:
        toks = search_tokens(topic)
        core = [t for t in toks if t not in _WEAK_ALONE] or toks
        if core:
            out.append(core[0] + (" 因子" if "因子" not in core[0] else ""))
    return list(dict.fromkeys(q.strip() for q in out if q.strip()))[:8]


def paper_query(topic: str) -> str:
    t = topic or ""
    if any(x in t for x in ("微观结构", "微观", "订单流", "高频")):
        return "equity market microstructure order flow high frequency factor stock returns"
    if "量价" in t:
        return "price volume factor stock returns microstructure turnover"
    if "隔夜" in t:
        return "overnight return anomaly stock returns China A-share"
    if any(x in t for x in ("质量", "盈利质量")):
        return "quality factor profitability earnings quality stock returns"
    if "动量" in t and "反转" in t:
        return "momentum reversal stock returns Jegadeesh Titman Lehmann"
    if "动量" in t:
        return "Jegadeesh Titman price momentum premium stock returns"
    if "反转" in t:
        return "short-term reversal stock returns Jegadeesh Lehmann"
    if "换手" in t:
        return "turnover premium reversal stock returns"
    if any(x in t for x in ("波动", "低波")):
        return "low volatility anomaly stock returns"
    if any(x in t for x in ("流动",)):
        return "liquidity premium Amihud stock returns"
    if any(x in t for x in ("异象", "异常")):
        return "stock return anomalies asset pricing"
    toks = search_tokens(t)
    en = [_ZH_EN[t0] for t0 in toks if t0 in _ZH_EN]
    q = " ".join(dict.fromkeys(en)) if en else " ".join(toks[:4])
    if "asset pricing" not in q and "stock return" not in q:
        q = (q + " asset pricing stock returns").strip()
    return q or "asset pricing momentum factor"


_PAPER_POS = (
    "stock return",
    "asset pricing",
    "factor",
    "anomaly",
    "momentum",
    "reversal",
    "liquidity",
    "illiquid",
    "volatility",
    "microstructure",
    "turnover",
    "equity",
    "cross-section",
    "premium",
    "amihud",
    "jegadeesh",
    "price impact",
    "price discovery",
    "order flow",
    "volume",
    "因子",
    "异象",
    "动量",
    "反转",
    "换手",
    "流动性",
    "波动",
    "量价",
    "微观结构",
)
_PAPER_NEG = (
    "tutoring",
    "scipy",
    "fatalism",
    "backward causation",
    "scientific computing",
    "first price auction",
    "intelligent tutoring",
    "hi intensity mapping",
    "psychological safety",
    "unmet needs",
    "nigerian equity",
)


def _paper_on_topic(title: str, snippet: str = "") -> bool:
    """挡掉高引但和量化因子无关的论文。"""
    blob = f"{title} {snippet}".lower()
    if any(n in blob for n in _PAPER_NEG):
        return False
    return any(p in blob for p in _PAPER_POS)


def _token_hit(blob: str, tokens: list[str]) -> int:
    return sum(1 for t in tokens if t and t.lower() in blob.lower())


def _em_search(keyword: str, *, page_size: int = 10) -> dict[str, Any]:
    page_size = max(3, min(20, page_size))
    payload = {
        "uid": "",
        "keyword": keyword,
        "type": ["cmsArticleWebOld", "researchReport"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": page_size,
            },
            "researchReport": {
                "pageIndex": 1,
                "pageSize": page_size,
                "sort": "default",
            },
        },
    }
    url = (
        "https://search-api-web.eastmoney.com/search/jsonp?cb=jQuery&param="
        + urllib.parse.quote(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    )
    data = _http_get_json(
        url,
        timeout=12,
        headers={"Referer": "https://so.eastmoney.com/"},
    )
    return data.get("result") if isinstance(data, dict) else {}


@lru_cache(maxsize=16)
def _em_bundle(keyword: str, page_size: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    result = _em_search(keyword, page_size=page_size) or {}
    news_rows = result.get("cmsArticleWebOld") or []
    report_rows = result.get("researchReport") or []
    news: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    if isinstance(news_rows, list):
        for r in news_rows:
            if not isinstance(r, dict):
                continue
            title = _strip_html(str(r.get("title") or ""))
            snippet = _strip_html(str(r.get("content") or ""))
            link = str(r.get("url") or "")
            if not title:
                continue
            hid = hashlib.md5((link or title).encode("utf-8", "replace")).hexdigest()[:10]
            news.append(
                _item(
                    source_type="news",
                    eid=f"web_news:{hid}",
                    title=title,
                    snippet=snippet,
                    url=link,
                    published_at=str(r.get("date") or "")[:19],
                    source_label=str(r.get("mediaName") or "东方财富·资讯"),
                )
            )
    if isinstance(report_rows, list):
        for r in report_rows:
            if not isinstance(r, dict):
                continue
            title = _strip_html(str(r.get("title") or ""))
            org = str(r.get("source") or "")
            stock = str(r.get("stockName") or "")
            code = str(r.get("code") or "").strip()
            link = (
                f"https://data.eastmoney.com/report/info/{code}.html"
                if code
                else "https://data.eastmoney.com/report/stock.jshtml"
            )
            bits = [x for x in (org, stock) if x]
            reports.append(
                _item(
                    source_type="report",
                    eid=f"web_report:{code or hashlib.md5(title.encode()).hexdigest()[:10]}",
                    title=title,
                    snippet="｜".join(bits) if bits else title,
                    url=link,
                    published_at=str(r.get("date") or "")[:19],
                    source_label=f"东财研报·{org}" if org else "东方财富·研报",
                )
            )
    return news, reports


def _pick_em(topic: str, *, want: str, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    last_exc = ""
    for q in cn_search_queries(topic):
        try:
            news, reports = _em_bundle(q, max(10, min(20, limit)))
        except Exception as exc:  # noqa: BLE001
            last_exc = str(exc)
            continue
        rows = news if want == "news" else reports
        for it in rows:
            key = str(it.get("url") or it.get("id"))
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
            if len(out) >= limit:
                return out, warnings
        # 多组查询都试，不因首组有结果就停
    if not out:
        if last_exc:
            warnings.append(f"在线{('资讯' if want == 'news' else '研报')}检索失败: {last_exc}")
        else:
            warnings.append(f"在线{('资讯' if want == 'news' else '研报')}未命中关键词")
    return out, warnings


def _ddg_results(query: str, *, limit: int = 8) -> list[tuple[str, str, str]]:
    """返回 (title, snippet, url) 列表。"""
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    html = _http_get(url, timeout=12).decode("utf-8", "replace")
    hrefs = re.findall(r'uddg=([^&"\']+)', html)
    titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.S)
    snips = re.findall(r'class="result__snippet"[^>]*>(.*?)</', html, re.S)
    out: list[tuple[str, str, str]] = []
    n = min(len(hrefs), len(titles))
    for i in range(n):
        title = _strip_html(titles[i])
        snip = _strip_html(snips[i] if i < len(snips) else "")
        link = urllib.parse.unquote(hrefs[i])
        if "uddg=" in link:
            m = re.search(r"uddg=([^&]+)", link)
            if m:
                link = urllib.parse.unquote(m.group(1))
        if not link.startswith("http"):
            continue
        out.append((title, snip, link))
        if len(out) >= limit:
            break
    return out


def _bing_results(query: str, *, limit: int = 8) -> list[tuple[str, str, str]]:
    """必应网页结果；(title, snippet, url)。失败抛给调用方。"""
    url = "https://cn.bing.com/search?" + urllib.parse.urlencode(
        {"q": query, "setlang": "zh-CN", "count": max(8, limit)}
    )
    html = _http_get(url, timeout=12).decode("utf-8", "replace")
    blocks = re.findall(
        r'<li class="b_algo"[^>]*>([\s\S]*?)</li>',
        html,
        re.I,
    )
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for blk in blocks:
        am = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', blk, re.I)
        if not am:
            continue
        link = html_lib.unescape(am.group(1)).strip()
        title = _strip_html(am.group(2))
        if "bing.com/ck/" in link or "bing.com/aclick" in link:
            qm = re.search(r"[?&]u=a1([^&]+)", link)
            if qm:
                try:
                    raw = qm.group(1) + ("===="[: (4 - len(qm.group(1)) % 4) % 4])
                    link = base64.urlsafe_b64decode(raw.encode()).decode("utf-8", "replace")
                except Exception:  # noqa: BLE001
                    pass
        if not link.startswith("http"):
            continue
        if link in seen:
            continue
        sm = re.search(r'<p[^>]*>([\s\S]*?)</p>', blk, re.I)
        snip = _strip_html(sm.group(1) if sm else "")
        seen.add(link)
        out.append((title, snip, link))
        if len(out) >= limit:
            break
    return out


def _so_results(query: str, *, limit: int = 8) -> list[tuple[str, str, str]]:
    """360 搜索；(title, snippet, url)。用 data-mdurl 还原真实链接。"""
    url = "https://www.so.com/s?" + urllib.parse.urlencode({"q": query})
    html = _http_get(url, timeout=12).decode("utf-8", "replace")
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'<h3[^>]*class="[^"]*res-title[^"]*"[^>]*>\s*<a([^>]+)>([\s\S]*?)</a>',
        html,
        re.I,
    ):
        attrs, inner = m.group(1), m.group(2)
        md = re.search(r'data-mdurl="([^"]+)"', attrs)
        href = re.search(r'href="([^"]+)"', attrs)
        link = html_lib.unescape((md.group(1) if md else (href.group(1) if href else "")).strip())
        if not link.startswith("http"):
            continue
        if "so.com/" in link or "360.cn/" in link:
            continue
        if link in seen:
            continue
        title = _strip_html(inner)
        if not title:
            continue
        tail = html[m.end() : m.end() + 1200]
        dm = re.search(r'class="res-desc"[^>]*>([\s\S]*?)</p>', tail, re.I)
        snip = _strip_html(dm.group(1) if dm else "")
        seen.add(link)
        out.append((title, snip, link))
        if len(out) >= limit:
            break
    return out


_JUNK_HOST_FRAGMENTS = (
    "baike.baidu.com",
    "zdic.net",
    "jingyan.baidu.com",
    "wenku.baidu.com",
    "iciba.com",
    "dictionary.cambridge",
    "dict.cn",
)
_POST_ALLOW_HOSTS = (
    "joinquant.com",
    "bigquant.com",
    "ricequant.com",
    "uqer.io",
    "guba.eastmoney.com",
    "xueqiu.com",
    "zhihu.com",
    "taoguba.com.cn",
    "elite.forum",
    "csdn.net",
)


def _is_junk_host(link: str) -> bool:
    return any(h in (link or "") for h in _JUNK_HOST_FRAGMENTS)


def _on_topic(title: str, snip: str, phrases: list[str]) -> bool:
    """标题/摘要须命中本题专有片段，不能只因为写了「因子/量化」就过。"""
    blob = f"{title} {snip}"
    strong = [p for p in phrases if len(p) >= 3]
    weak2 = [p for p in phrases if len(p) == 2]
    if strong and any(p in blob for p in strong):
        return True
    if weak2 and any(p in blob for p in weak2) and any(
        k in blob for k in ("因子", "量化", "金工", "选股", "回测", "A股")
    ):
        return True
    return False


def _web_search(query: str, *, limit: int = 8) -> list[tuple[str, str, str]]:
    """先必应；无结果再 360；再 DDG。"""
    last: Exception | None = None
    try:
        rows = _bing_results(query, limit=limit)
        if rows:
            return rows
    except Exception as exc:  # noqa: BLE001
        last = exc
    try:
        rows = _so_results(query, limit=limit)
        if rows:
            return rows
    except Exception as exc:  # noqa: BLE001
        last = last or exc
    try:
        rows = _ddg_results(query, limit=limit)
        if rows:
            return rows
    except Exception as exc:  # noqa: BLE001
        last = last or exc
    if last:
        raise last
    return []


def _post_engine_results(query: str, *, limit: int = 8) -> list[tuple[str, str, str]]:
    """帖子入口：360 优先（必应中文常把专有词带到百科/菜谱）。"""
    last: Exception | None = None
    try:
        rows = _so_results(query, limit=limit)
        if rows:
            return rows
    except Exception as exc:  # noqa: BLE001
        last = exc
    try:
        rows = _bing_results(query, limit=limit)
        if rows:
            return rows
    except Exception as exc:  # noqa: BLE001
        last = last or exc
    if last:
        raise last
    return []


def _label_for_url(link: str) -> str:
    rules = (
        ("joinquant.com", "聚宽"),
        ("bigquant.com", "BigQuant"),
        ("ricequant.com", "米筐"),
        ("uqer.io", "优矿"),
        ("xueqiu.com", "雪球"),
        ("guba.eastmoney.com", "东方财富股吧"),
        ("wallstreetcn.com", "华尔街见闻"),
        ("cls.cn", "财联社"),
        ("finance.sina.com.cn", "新浪财经"),
        ("10jqka.com.cn", "同花顺"),
        ("yicai.com", "第一财经"),
        ("stcn.com", "证券时报"),
        ("cs.com.cn", "中国证券报"),
        ("zhihu.com", "知乎"),
        ("csdn.net", "CSDN"),
        ("ssrn.com", "SSRN"),
        ("arxiv.org", "arXiv"),
        ("eastmoney.com", "东方财富"),
    )
    for host, label in rules:
        if host in link:
            return label
    return "公开网页"


def _round_robin_merge(buckets: list[list[dict[str, Any]]], limit: int) -> list[dict[str, Any]]:
    """多源轮询合并，避免单一站点（如东财）占满配额。"""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    depth = 0
    while len(out) < limit:
        progressed = False
        for bucket in buckets:
            if depth >= len(bucket):
                continue
            it = bucket[depth]
            key = str(it.get("url") or it.get("id") or "")
            if not key or key in seen:
                progressed = True
                continue
            seen.add(key)
            out.append(it)
            progressed = True
            if len(out) >= limit:
                break
        if not progressed:
            break
        depth += 1
    return out


def _extract_body_from_html(page: str) -> str:
    if not page:
        return ""
    m = re.search(
        r'id=["\']ContentBody["\'][^>]*>([\s\S]*?)</div>\s*(?:<div|<!--)',
        page,
        re.I,
    )
    if not m:
        m = re.search(r'id=["\']ContentBody["\'][^>]*>([\s\S]*?)</div>', page, re.I)
    if m:
        paras = re.findall(r"<p[^>]*>([\s\S]*?)</p>", m.group(1), re.I)
        if paras:
            chunks = [_strip_html(p) for p in paras]
            text = "\n".join(c for c in chunks if c and len(c) > 8)
            if len(text) > 80:
                return text
    art = re.search(r"<article[^>]*>([\s\S]*?)</article>", page, re.I)
    if art:
        paras = re.findall(r"<p[^>]*>([\s\S]*?)</p>", art.group(1), re.I)
        text = "\n".join(_strip_html(p) for p in paras if _strip_html(p))
        if len(text) > 80:
            return text
    og = re.search(
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        page,
        re.I,
    )
    if not og:
        og = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
            page,
            re.I,
        )
    if og:
        t = _strip_html(og.group(1))
        if len(t) > 40:
            return t
    paras = re.findall(r"<p[^>]*>([\s\S]*?)</p>", page, re.I)
    chunks = [_strip_html(p) for p in paras]
    text = "\n".join(c for c in chunks if c and len(c) > 20)[:4000]
    return text


def _arxiv_id(url: str) -> str:
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]+\.[0-9]+)(?:v\d+)?", url or "", re.I)
    return m.group(1) if m else ""


def _pdf_url_candidates(url: str, extra_pdf: str = "") -> list[str]:
    out: list[str] = []
    if extra_pdf and str(extra_pdf).startswith("http"):
        out.append(str(extra_pdf).strip())
    u = (url or "").strip()
    if not u:
        return list(dict.fromkeys(out))
    low = u.lower().split("?")[0]
    if low.endswith(".pdf"):
        out.append(u)
    aid = _arxiv_id(u)
    if aid:
        out.append(f"https://arxiv.org/pdf/{aid}.pdf")
    return list(dict.fromkeys(x for x in out if x.startswith("http")))


def _extract_pdf_text(url: str, *, max_chars: int = 4000, max_pages: int = 5) -> str:
    """用 pypdf 抽前几页正文；失败返回空串。"""
    try:
        from io import BytesIO

        from pypdf import PdfReader
    except Exception:  # noqa: BLE001
        return ""
    try:
        data = _http_get(url, timeout=22)
        if not data or len(data) < 200 or not data.lstrip().startswith(b"%PDF"):
            return ""
        reader = PdfReader(BytesIO(data))
        chunks: list[str] = []
        total = 0
        for page in reader.pages[: max(1, max_pages)]:
            try:
                t = (page.extract_text() or "").strip()
            except Exception:  # noqa: BLE001
                t = ""
            if not t:
                continue
            chunks.append(t)
            total += len(t)
            if total >= max_chars:
                break
        text = re.sub(r"\s+", " ", "\n".join(chunks)).strip()
        return text[:max_chars]
    except Exception:  # noqa: BLE001
        return ""


def enrich_snippets(
    items: list[dict[str, Any]],
    *,
    max_fetch: int = 16,
    min_snip: int = 160,
    max_chars: int = 4000,
) -> list[dict[str, Any]]:
    """补抓网页正文或 PDF 前几页；论文优先；单条失败不影响其它。"""
    out: list[dict[str, Any] | None] = [None] * len(items)
    # 论文/研报优先占用抓取配额
    order = sorted(
        range(len(items)),
        key=lambda i: 0 if str(items[i].get("source_type") or "") in {"paper", "report"} else 1,
    )
    fetched = 0
    for idx in order:
        row = dict(items[idx])
        snip = str(row.get("snippet") or "")
        url = str(row.get("url") or "").strip()
        st = str(row.get("source_type") or "")
        # 论文希望尽量接近「摘要+引言」量级
        need_len = 1500 if st == "paper" else (400 if st == "report" else min_snip)
        extra_pdf = ""
        if isinstance(row.get("extra"), dict):
            extra_pdf = str(row["extra"].get("pdf_url") or "")
        elif row.get("pdf_url"):
            extra_pdf = str(row.get("pdf_url") or "")

        if fetched >= max_fetch or not url.startswith("http") or len(snip) >= need_len:
            out[idx] = row
            continue

        body = ""
        try:
            pdfs = _pdf_url_candidates(url, extra_pdf)
            # 直链 PDF 或 arXiv：优先抽 PDF 前几页
            for pdf_u in pdfs:
                body = _extract_pdf_text(pdf_u, max_chars=max_chars)
                if len(body) > 120:
                    break
            if len(body) < 80 and not any(url.lower().endswith(ext) for ext in (".pdf", ".zip", ".rar")):
                if "eastmoney.com" in url:
                    try:
                        from services.news.news_ingest import scrape_eastmoney_body

                        body = scrape_eastmoney_body(url) or ""
                    except Exception:  # noqa: BLE001
                        body = ""
                if len(body) < 80:
                    raw = _http_get(url, timeout=12).decode("utf-8", "replace")
                    body = _extract_body_from_html(raw)
            body = re.sub(r"\s+", " ", (body or "").strip())
            if len(body) > len(snip):
                row["snippet"] = body[:max_chars]
                fetched += 1
        except Exception:  # noqa: BLE001
            pass
        out[idx] = row
    return [x if x is not None else dict(items[i]) for i, x in enumerate(out)]


def _search_news_columns(*, topic: str, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    """多个东财栏目最新列表，用短词过滤；单栏失败继续。"""
    warnings: list[str] = []
    tokens = [t for t in search_tokens(topic) if len(t) <= 8]
    columns = ("350", "355", "344", "351", "352")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for col in columns:
        url = (
            "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
            f"?client=web&biz=web_news_col&column={col}&order=1&needInteractData=0"
            "&page_index=1&page_size=40&req_trace=1"
        )
        try:
            data = _http_get_json(url, timeout=8)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"资讯栏目 {col} 失败: {exc}")
            continue
        rows = ((data.get("data") or {}).get("list")) or []
        for r in rows:
            if not isinstance(r, dict):
                continue
            title = str(r.get("title") or "")
            summary = str(r.get("summary") or "")
            blob = f"{title} {summary}"
            if tokens and _token_hit(blob, tokens) == 0:
                continue
            link = str(r.get("uniqueUrl") or r.get("url") or "")
            if link in seen:
                continue
            seen.add(link)
            hid = hashlib.md5((link or title).encode("utf-8", "replace")).hexdigest()[:10]
            out.append(
                _item(
                    source_type="news",
                    eid=f"web_news:{hid}",
                    title=title,
                    snippet=summary,
                    url=link,
                    published_at=str(r.get("showTime") or ""),
                    source_label="东方财富·资讯",
                )
            )
            if len(out) >= limit:
                return out, warnings
    return out, warnings


def search_news_live(*, topic: str, limit: int = 8) -> tuple[list[dict[str, Any]], list[str]]:
    """多源资讯：东财与其它财经站均摊，单源失败继续。"""
    warnings: list[str] = []
    soft = max(4, (limit + 2) // 2)
    buckets: list[list[dict[str, Any]]] = []

    try:
        em, w = _pick_em(topic, want="news", limit=soft)
        warnings.extend(w)
        buckets.append(em)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"东财资讯搜索失败: {exc}")
        buckets.append([])

    try:
        cols, w2 = _search_news_columns(topic=topic, limit=soft)
        warnings.extend(w2)
        buckets.append(cols)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"东财栏目失败: {exc}")
        buckets.append([])

    q0 = (distinctive_phrases(topic) or cn_search_queries(topic) or [topic[:24]])[0]
    sites = (
        "wallstreetcn.com",
        "cls.cn",
        "finance.sina.com.cn",
        "yicai.com",
        "stcn.com",
        "news.10jqka.com.cn",
        "cs.com.cn",
    )
    for site in sites:
        bucket: list[dict[str, Any]] = []
        try:
            rows = _web_search(f"site:{site} {q0}", limit=4)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"资讯聚合 {site} 失败: {exc}")
            buckets.append(bucket)
            continue
        seen_local: set[str] = set()
        for title, snip, link in rows:
            if link in seen_local:
                continue
            seen_local.add(link)
            hid = hashlib.md5(link.encode()).hexdigest()[:10]
            bucket.append(
                _item(
                    source_type="news",
                    eid=f"web_news:{hid}",
                    title=title or link,
                    snippet=snip,
                    url=link,
                    source_label=_label_for_url(link),
                )
            )
        buckets.append(bucket)

    out = _round_robin_merge(buckets, limit)
    if not out and not any("失败" in w for w in warnings):
        warnings.append("在线资讯未命中关键词")
    return out, warnings


def search_reports(*, topic: str, start: datetime, end: datetime, limit: int = 8) -> tuple[list[dict[str, Any]], list[str]]:
    """研报：东财与公开聚合均摊，单查询失败继续。"""
    _ = (start, end)
    warnings: list[str] = []
    soft = max(3, (limit + 1) // 2)
    buckets: list[list[dict[str, Any]]] = []

    try:
        em, w = _pick_em(topic, want="report", limit=soft)
        warnings.extend(w)
        buckets.append(em)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"东财研报搜索失败: {exc}")
        buckets.append([])

    q0 = (distinctive_phrases(topic) or cn_search_queries(topic) or [topic[:20]])[0]
    queries = [
        f"{q0} 金工 研报",
        f"{q0} 因子 研报",
        f"site:hibor.com.cn {q0}",
        f"site:data.eastmoney.com/report {q0}",
        f"site:qianzhan.com {q0} 研报",
    ]
    for query in queries:
        bucket: list[dict[str, Any]] = []
        try:
            rows = _web_search(query, limit=5)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"研报聚合失败: {exc}")
            buckets.append(bucket)
            continue
        for title, snip, link in rows:
            blob = f"{title} {snip} {link}".lower()
            if not any(
                x in blob
                for x in (
                    "report",
                    "研报",
                    "金工",
                    "hibor",
                    "eastmoney.com/report",
                    "10jqka",
                    "因子",
                )
            ):
                continue
            hid = hashlib.md5(link.encode()).hexdigest()[:10]
            bucket.append(
                _item(
                    source_type="report",
                    eid=f"web_report:{hid}",
                    title=title or link,
                    snippet=snip,
                    url=link,
                    source_label=_label_for_url(link) if "http" in link else "研报聚合",
                )
            )
        buckets.append(bucket)

    out = _round_robin_merge(buckets, limit)
    return out, warnings


def _openalex_abstract(inv: Any) -> str:
    if not isinstance(inv, dict) or not inv:
        return ""
    size = 0
    for pos in inv.values():
        if isinstance(pos, list) and pos:
            size = max(size, max(int(p) for p in pos if str(p).isdigit() or isinstance(p, int)) + 1)
    if size <= 0 or size > 800:
        return ""
    arr = [""] * size
    for w, positions in inv.items():
        if not isinstance(positions, list):
            continue
        for p in positions:
            try:
                i = int(p)
            except (TypeError, ValueError):
                continue
            if 0 <= i < size:
                arr[i] = str(w)
    return " ".join(x for x in arr if x)[:1200]


def _paper_item(
    *,
    title: str,
    snippet: str,
    url: str,
    year: Any,
    source_label: str,
    eid: str,
    pdf_url: str = "",
) -> dict[str, Any]:
    y = str(year or "").strip()
    pub = f"{y}-01-01" if y.isdigit() else (y[:10] if y else "")
    row = _item(
        source_type="paper",
        eid=eid,
        title=title,
        snippet=snippet,
        url=url,
        published_at=pub,
        source_label=source_label,
    )
    if pdf_url and str(pdf_url).startswith("http"):
        row["pdf_url"] = str(pdf_url).strip()
    return row


def search_papers(*, topic: str, limit: int = 6) -> tuple[list[dict[str, Any]], list[str]]:
    """论文：OpenAlex / Crossref / arXiv / S2 均摊；单库失败继续。"""
    warnings: list[str] = []
    soft = max(2, (limit + 3) // 4)
    q = paper_query(topic)
    buckets: list[list[dict[str, Any]]] = []

    # OpenAlex
    oa: list[dict[str, Any]] = []
    params = {
        "search": q,
        "per_page": max(3, min(12, soft + 2)),
        "sort": "relevance_score:desc",
        "filter": "type:article",
    }
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    try:
        data = _http_get_json(
            url,
            timeout=14,
            headers={"User-Agent": "SVQuant-gather/1.0 (mailto:dev@local)"},
        )
        for r in data.get("results") or []:
            if not isinstance(r, dict):
                continue
            title = str(r.get("display_name") or "")
            year = r.get("publication_year")
            loc = (r.get("primary_location") or {}) if isinstance(r.get("primary_location"), dict) else {}
            src = (loc.get("source") or {}) if isinstance(loc.get("source"), dict) else {}
            landing = str(loc.get("landing_page_url") or r.get("id") or "")
            doi = str(r.get("doi") or "")
            url_out = doi if doi.startswith("http") else landing
            wid = str(r.get("id") or "").rsplit("/", 1)[-1]
            snippet = _openalex_abstract(r.get("abstract_inverted_index"))
            if not snippet:
                snippet = str(src.get("display_name") or "") + (f" · {year}" if year else "")
            if not _paper_on_topic(title, snippet):
                continue
            pdf_url = str(loc.get("pdf_url") or "")
            oa_meta = r.get("open_access") if isinstance(r.get("open_access"), dict) else {}
            if not pdf_url:
                pdf_url = str(oa_meta.get("oa_url") or "")
            if pdf_url and not pdf_url.lower().endswith(".pdf") and "arxiv.org/pdf/" not in pdf_url.lower():
                # oa_url 有时是落地页，仍交给 enrich 再解析
                pass
            oa.append(
                _paper_item(
                    title=title,
                    snippet=snippet,
                    url=url_out,
                    year=year,
                    source_label=str(src.get("display_name") or "OpenAlex"),
                    eid=f"web_paper:{wid or hashlib.md5(title.encode()).hexdigest()[:10]}",
                    pdf_url=pdf_url,
                )
            )
            if len(oa) >= soft + 2:
                break
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"论文库 OpenAlex 失败: {exc}")
    buckets.append(oa)

    # Crossref
    cr: list[dict[str, Any]] = []
    try:
        curl = "https://api.crossref.org/works?" + urllib.parse.urlencode(
            {"query": q, "rows": max(4, soft + 2), "select": "title,published,URL,abstract,container-title"}
        )
        data = _http_get_json(curl, timeout=14, headers={"User-Agent": "SVQuant-gather/1.0 (mailto:dev@local)"})
        items = ((data.get("message") or {}).get("items")) or []
        for r in items:
            if not isinstance(r, dict):
                continue
            titles = r.get("title") or []
            title = titles[0] if isinstance(titles, list) and titles else str(titles or "")
            year = ""
            pub = r.get("published") if isinstance(r.get("published"), dict) else {}
            parts = (pub.get("date-parts") or [[]])[0]
            if parts:
                year = parts[0]
            snippet = _strip_html(str(r.get("abstract") or ""))
            if not snippet:
                ct = r.get("container-title") or []
                snippet = ct[0] if isinstance(ct, list) and ct else ""
            if not _paper_on_topic(str(title), str(snippet)):
                continue
            cr.append(
                _paper_item(
                    title=str(title),
                    snippet=str(snippet)[:2000],
                    url=str(r.get("URL") or ""),
                    year=year,
                    source_label="Crossref",
                    eid=f"web_paper:cr_{hashlib.md5(str(title).encode()).hexdigest()[:10]}",
                )
            )
            if len(cr) >= soft + 2:
                break
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"论文库 Crossref 失败: {exc}")
    buckets.append(cr)

    # arXiv
    ax: list[dict[str, Any]] = []
    try:
        aq = paper_query(topic).replace(":", " ")
        aurl = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {
                "search_query": f"all:{aq}",
                "start": 0,
                "max_results": max(3, min(8, soft + 2)),
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
        )
        raw = _http_get(aurl, timeout=14).decode("utf-8", "replace")
        entries = re.findall(r"<entry>(.*?)</entry>", raw, re.S)
        for ent in entries:
            title = _strip_html(
                re.search(r"<title>(.*?)</title>", ent, re.S).group(1)
                if re.search(r"<title>(.*?)</title>", ent, re.S)
                else ""
            )
            summary = _strip_html(
                re.search(r"<summary>(.*?)</summary>", ent, re.S).group(1)
                if re.search(r"<summary>(.*?)</summary>", ent, re.S)
                else ""
            )
            link_m = re.search(r'<id>(https?://arxiv\.org/abs/[^<]+)</id>', ent)
            link = link_m.group(1) if link_m else ""
            year_m = re.search(r"<published>(\d{4})", ent)
            year = year_m.group(1) if year_m else ""
            if not title:
                continue
            if not _paper_on_topic(title, summary):
                continue
            aid = _arxiv_id(link)
            pdf_url = f"https://arxiv.org/pdf/{aid}.pdf" if aid else ""
            ax.append(
                _paper_item(
                    title=title,
                    snippet=summary[:2000],
                    url=link,
                    year=year,
                    source_label="arXiv",
                    eid=f"web_paper:arx_{hashlib.md5(title.encode()).hexdigest()[:10]}",
                    pdf_url=pdf_url,
                )
            )
            if len(ax) >= soft + 2:
                break
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"论文库 arXiv 失败: {exc}")
    buckets.append(ax)

    # Semantic Scholar
    s2: list[dict[str, Any]] = []
    try:
        surl = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(
            {
                "query": paper_query(topic),
                "limit": max(3, min(6, soft + 2)),
                "fields": "title,year,url,abstract,externalIds,openAccessPdf",
            }
        )
        data = _http_get_json(surl, timeout=12)
        for r in data.get("data") or []:
            if not isinstance(r, dict):
                continue
            title = str(r.get("title") or "")
            abstract = str(r.get("abstract") or "")[:2000]
            link = str(r.get("url") or "")
            ext = r.get("externalIds") if isinstance(r.get("externalIds"), dict) else {}
            doi = str((ext or {}).get("DOI") or "")
            if doi and not link:
                link = f"https://doi.org/{doi}"
            if not _paper_on_topic(title, abstract):
                continue
            oa_pdf = r.get("openAccessPdf") if isinstance(r.get("openAccessPdf"), dict) else {}
            pdf_url = str((oa_pdf or {}).get("url") or "")
            s2.append(
                _paper_item(
                    title=title,
                    snippet=abstract,
                    url=link,
                    year=r.get("year"),
                    source_label="Semantic Scholar",
                    eid=f"web_paper:s2_{hashlib.md5(title.encode()).hexdigest()[:10]}",
                    pdf_url=pdf_url,
                )
            )
            if len(s2) >= soft + 2:
                break
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"论文库 Semantic Scholar 跳过: {exc}")
    buckets.append(s2)

    out = _round_robin_merge(buckets, limit)
    if not out:
        warnings.append("论文库未命中（可换更偏学术的说法再试）")
    return out, warnings


def search_posts(*, topic: str, limit: int = 6) -> tuple[list[dict[str, Any]], list[str]]:
    """帖子：从原句抽短语检索社区站；junk/跑题丢掉后换下一组 query。"""
    warnings: list[str] = []
    phrases = distinctive_phrases(topic)
    if not phrases:
        warnings.append("公开帖子检索无命中")
        return [], warnings
    cores: list[str] = []
    for p in phrases:
        if len(p) <= 2 and any(p in c for c in cores):
            continue
        cores.append(p)
        if len(cores) >= 3:
            break
    queries: list[str] = []
    for p in cores:
        queries.extend(
            (
                f"{p} 量化",
                f"{p} 知乎",
                f"{p} 聚宽",
            )
        )
    queries = list(dict.fromkeys(queries))[:6]
    buckets: list[list[dict[str, Any]]] = []
    seen_all: set[str] = set()
    collected = 0
    for query in queries:
        bucket: list[dict[str, Any]] = []
        try:
            rows = _post_engine_results(query, limit=6)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"帖子检索跳过: {exc}")
            continue
        for title, snip, link in rows:
            if _is_junk_host(link) or link in seen_all:
                continue
            if not any(h in link for h in _POST_ALLOW_HOSTS):
                continue
            if not _on_topic(title, snip, phrases):
                continue
            seen_all.add(link)
            hid = hashlib.md5(link.encode()).hexdigest()[:10]
            bucket.append(
                _item(
                    source_type="post",
                    eid=f"web_post:{hid}",
                    title=title or link,
                    snippet=snip,
                    url=link,
                    source_label=_label_for_url(link),
                )
            )
        if bucket:
            buckets.append(bucket)
            collected += len(bucket)
            if collected >= limit:
                break

    out = _round_robin_merge(buckets, limit)
    if not out:
        warnings.append("公开帖子检索无命中（社区站未搜到与本题短语相符的帖，未用无关入门帖充数）")
    return out, warnings
