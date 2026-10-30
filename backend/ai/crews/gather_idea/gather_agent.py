# -*- coding: utf-8 -*-
"""Agent A · 信息搜集：自然语言问题 → 在线资料汇总（资讯/研报/论文/帖子）。"""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ai.crews.gather_idea.schemas import EvidencePack, GatherRequest
from ai.crews.gather_idea import web_sources

_TZ = timezone(timedelta(hours=8))
_MAX_ITEMS_HARD = 50

# 题材字段仍兼容入参，但不再走站内库；检索全部外网。


def _now() -> datetime:
    return datetime.now(_TZ)


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_TZ)
        return dt.astimezone(_TZ)
    except ValueError:
        return None


def _window_bounds(tw: dict[str, Any] | None) -> tuple[datetime, datetime]:
    end = _now()
    start = end - timedelta(days=7)
    if not isinstance(tw, dict):
        return start, end
    if tw.get("start") or tw.get("end"):
        s = _parse_dt(str(tw.get("start") or "")) or start
        e = _parse_dt(str(tw.get("end") or "")) or end
        if s > e:
            s, e = e, s
        return s, e
    preset = str(tw.get("preset") or "90d").strip().lower()
    days_map = {
        "7d": 7,
        "14d": 14,
        "30d": 30,
        "60d": 60,
        "90d": 90,
        "180d": 180,
        "1y": 365,
        "365d": 365,
        "2y": 730,
        "3y": 1095,
        "5y": 1825,
        "10y": 3650,
        "all": 36500,
    }
    days = days_map.get(preset, 90)
    return end - timedelta(days=days), end


def _as_str_list(raw: Any, *, max_n: int = 8, max_len: int = 40) -> list[str]:
    if raw is None:
        return []
    parts: list[str] = []
    if isinstance(raw, (list, tuple)):
        for x in raw:
            parts.extend(str(x).split(","))
    else:
        parts = str(raw).split(",")
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        s = p.strip()[:max_len]
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= max_n:
            break
    return out


def _search_tokens(topic: str) -> list[str]:
    return web_sources.search_tokens(topic)


def normalize_request(body: dict[str, Any], *, user_id: int) -> GatherRequest:
    topic = str(body.get("topic") or "").strip()
    if not topic:
        raise ValueError("topic 不能为空")
    if len(topic) > 240:
        raise ValueError("topic 最长 240 字")

    themes = _as_str_list(body.get("themes"))[:8]
    # 不再从 topic 关键词自动补题材：易误伤过滤；题材只认用户显式多选（可空）
    symbols = _as_str_list(body.get("symbols"), max_len=32)
    sources_in = body.get("sources") if isinstance(body.get("sources"), dict) else {}
    # 兼容旧字段 sv_news / web_public
    news = bool(sources_in.get("news", sources_in.get("sv_news", True)))
    report = bool(sources_in.get("report", True))
    paper = bool(sources_in.get("paper", True))
    post = bool(sources_in.get("post", True))

    try:
        max_items = int(body.get("max_items") or 20)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_items 须为整数") from exc
    max_items = max(1, min(_MAX_ITEMS_HARD, max_items))

    tw = body.get("time_window") if isinstance(body.get("time_window"), dict) else {"preset": "3y"}
    prefer_flash = bool(body.get("prefer_flash", False))
    language = str(body.get("language") or "zh").strip() or "zh"

    return {
        "topic": topic,
        "themes": themes,
        "symbols": symbols,
        "time_window": tw,  # type: ignore[typeddict-item]
        "sources": {
            "news": news,
            "report": report,
            "paper": paper,
            "post": post,
        },
        "max_items": max_items,
        "prefer_flash": prefer_flash,
        "language": language,
        "user_id": int(user_id),
    }


def _snippet_of(row: dict[str, Any], *, limit: int = 4000) -> str:
    text = (row.get("summary") or "").strip() or (row.get("body") or "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _title_key(title: str) -> str:
    t = re.sub(r"[\s,，。、！!？?：:；;]+", "", (title or "").strip().lower())
    return t[:80]


def _relevance(row: dict[str, Any], *, topic: str, themes: list[str], tokens: list[str]) -> float:
    title = (row.get("title") or "")
    summary = (row.get("summary") or row.get("snippet") or "")
    blob = f"{title} {summary}"
    blob_l = blob.lower()
    score = 0.15
    for th in themes:
        if th and th in blob:
            score += 0.25
    for tok in tokens:
        if tok and tok in blob:
            score += 0.12
        en = web_sources._ZH_EN.get(tok)  # type: ignore[attr-defined]
        if en and str(en).lower() in blob_l:
            score += 0.1
    if topic and topic[:12] in blob:
        score += 0.1
    row_themes = row.get("themes") or []
    if themes and any(t in row_themes for t in themes):
        score += 0.2
    if row.get("isFlash"):
        score += 0.05
    if row.get("isFeatured"):
        score += 0.05
    return max(0.0, min(1.0, score))


def _filter_window(rows: list[dict[str, Any]], start: datetime, end: datetime) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        # 论文样本期远长于资讯窗，不过滤近 N 日
        st = str(r.get("source_type") or r.get("category") or "")
        if st in {"paper", "web_paper"}:
            out.append(r)
            continue
        dt = _parse_dt(r.get("publishedAt") or r.get("published_at"))
        if dt is None:
            out.append(r)
            continue
        if start <= dt <= end + timedelta(seconds=1):
            out.append(r)
    return out


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同 URL 或同标题保留更新时间更新的一条。"""

    def _newer(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
        da = _parse_dt(a.get("publishedAt") or a.get("published_at")) or datetime.min.replace(tzinfo=_TZ)
        db = _parse_dt(b.get("publishedAt") or b.get("published_at")) or datetime.min.replace(tzinfo=_TZ)
        return a if da >= db else b

    best: dict[str, dict[str, Any]] = {}
    for r in rows:
        tkey = _title_key(r.get("title") or "")
        url = (r.get("url") or "").strip()
        key = f"t:{tkey}" if tkey else (f"u:{url}" if url else f"id:{r.get('id')}")
        if key in best:
            best[key] = _newer(best[key], r)
        else:
            best[key] = r
    return list(best.values())


def _rank(
    rows: list[dict[str, Any]],
    *,
    topic: str,
    themes: list[str],
    prefer_flash: bool,
) -> list[tuple[float, dict[str, Any]]]:
    tokens = _search_tokens(topic)
    scored: list[tuple[float, dict[str, Any]]] = []
    for r in rows:
        rel = _relevance(r, topic=topic, themes=themes, tokens=tokens)
        if prefer_flash and r.get("isFlash"):
            rel = min(1.0, rel + 0.08)
        st = _row_source(r)
        if st in {"paper", "report", "post"}:
            rel = min(1.0, rel + 0.12)
        dt = _parse_dt(r.get("publishedAt") or r.get("published_at"))
        # 轻微时效加权
        if dt is not None:
            age_h = max(0.0, (_now() - dt).total_seconds() / 3600.0)
            rel = min(1.0, rel + max(0.0, 0.08 - age_h / 500.0))
        scored.append((rel, r))
    scored.sort(
        key=lambda x: (
            x[0],
            _parse_dt(x[1].get("publishedAt") or x[1].get("published_at")) or datetime.min.replace(tzinfo=_TZ),
        ),
        reverse=True,
    )
    return scored


def _row_source(row: dict[str, Any]) -> str:
    st = str(row.get("source_type") or "")
    if st in {"sv_news"}:
        return "news"
    if st:
        return st
    return "news"


def _take_balanced(
    ranked: list[tuple[float, dict[str, Any]]],
    max_items: int,
    *,
    min_per: int = 2,
) -> list[tuple[float, dict[str, Any]]]:
    """避免单一来源占满条数，保证研报/论文/帖子能进包。"""
    buckets: dict[str, list[tuple[float, dict[str, Any]]]] = {}
    for item in ranked:
        buckets.setdefault(_row_source(item[1]), []).append(item)
    picked: list[tuple[float, dict[str, Any]]] = []
    seen: set[int] = set()
    for rows in buckets.values():
        for item in rows[:min_per]:
            k = id(item[1])
            if k in seen:
                continue
            picked.append(item)
            seen.add(k)
            if len(picked) >= max_items:
                return picked
    for item in ranked:
        k = id(item[1])
        if k in seen:
            continue
        picked.append(item)
        seen.add(k)
        if len(picked) >= max_items:
            break
    return picked


def _to_evidence_item(row: dict[str, Any], relevance: float) -> dict[str, Any]:
    # 在线源已是证据条目
    if str(row.get("id") or "").startswith(("web_", "sv_news:")):
        out = dict(row)
        out["relevance"] = round(float(relevance), 4)
        return out
    nid = int(row["id"])
    url = (row.get("url") or "").strip() or None
    cat = str(row.get("category") or "")
    st = "report" if cat == "research" else "news"
    return {
        "id": f"sv_news:{nid}",
        "source_type": st,
        "title": (row.get("title") or "").strip() or f"资讯#{nid}",
        "snippet": _snippet_of(row),
        "published_at": row.get("publishedAt") or "",
        "url": url,
        "sv_news_id": nid,
        "source_label": row.get("sourceLabel") or row.get("source") or "",
        "category": cat,
        "themes": list(row.get("themes") or []),
        "symbols": list(row.get("symbols") or []),
        "relevance": round(float(relevance), 4),
    }


def _rule_digest(items: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    if not items:
        return "", []
    bullets: list[dict[str, Any]] = []
    for it in items[:8]:
        title = (it.get("title") or "").strip()
        label = it.get("source_label") or it.get("source_type") or ""
        text = f"[{label}] {title}" if label else title
        bullets.append({"text": text[:160], "item_ids": [it["id"]]})
    digest = "根据检索到的资料，要点如下：\n" + "\n".join(
        f"- {b['text']}" for b in bullets
    )
    return digest, bullets


def _extract_json_obj(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None


def _llm_digest(
    *,
    topic: str,
    items: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], dict[str, Any], str | None]:
    """返回 digest, bullets, usage{tokens_in,out,model}, error_or_none。失败时调用方回退规则。"""
    if not items:
        return "", [], {}, None
    try:
        from ai.errors import AiError
        from ai.router import available_task, run_task
    except Exception as exc:  # noqa: BLE001
        return "", [], {}, f"AI 路由层不可用: {exc}"

    if not available_task("gather_idea.gather"):
        return "", [], {}, "LLM 未配置"

    allowed = {it["id"] for it in items}
    catalog = [
        {
            "id": it["id"],
            "source_type": it.get("source_type"),
            "title": it.get("title"),
            "snippet": (it.get("snippet") or "")[:1200],
            "source_label": it.get("source_label"),
            "published_at": it.get("published_at"),
            "themes": it.get("themes") or [],
        }
        for it in items[:20]
    ]
    system = (
        "你是量化研究资料助理。只根据给定 items 做汇总概括，禁止编造未出现的事实、数字。"
        "面向后续「可检验因子假设」：写清机制、提到的时期/样本、哪些量可能用日频 close/open/high/low/volume 检验。"
        "若资料是经典论文（动量/反转/流动性等），即使没有 A 股新闻数字，也要概括其可检验机制，不要写成「完全没有相关内容」。"
        "输出严格 JSON："
        '{"digest":"中文总述","bullets":[{"text":"要点","item_ids":["..."]}]}。'
        "每条 bullet 的 item_ids 必须全部来自给定 id；3～8 条；digest 120～400 字。"
        "不要给买卖建议。"
    )
    user = json.dumps(
        {"topic": topic, "items": catalog},
        ensure_ascii=False,
    )
    try:
        out = run_task(
            "gather_idea.gather",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    except AiError as exc:
        return "", [], {}, str(exc)
    except Exception as exc:  # noqa: BLE001
        return "", [], {}, f"LLM 调用失败: {exc}"

    usage = {
        "tokens_in": int(out.get("tokens_in") or 0),
        "tokens_out": int(out.get("tokens_out") or 0),
        "model": out.get("model") or "",
    }
    obj = _extract_json_obj(str(out.get("content") or ""))
    if not obj:
        return "", [], usage, "LLM 返回无法解析为 JSON"

    digest = str(obj.get("digest") or "").strip()
    raw_bullets = obj.get("bullets") if isinstance(obj.get("bullets"), list) else []
    bullets: list[dict[str, Any]] = []
    for b in raw_bullets[:8]:
        if not isinstance(b, dict):
            continue
        text = str(b.get("text") or "").strip()
        ids_raw = b.get("item_ids") if isinstance(b.get("item_ids"), list) else []
        ids = [str(x) for x in ids_raw if str(x) in allowed]
        if not text or not ids:
            continue
        bullets.append({"text": text[:200], "item_ids": ids})
    if not digest and not bullets:
        return "", [], usage, "LLM JSON 缺少 digest/bullets"
    if not digest and bullets:
        digest = "根据检索到的资料，要点如下：\n" + "\n".join(
            f"- {b['text']}" for b in bullets
        )
    if digest and not bullets:
        # 仍强制挂上前几条引用，避免无 citation
        bullets = [
            {"text": (it.get("title") or "")[:120], "item_ids": [it["id"]]}
            for it in items[: min(5, len(items))]
        ]
    return digest, bullets, usage, None


def _build_gaps(
    *,
    req: GatherRequest,
    items: list[dict[str, Any]],
    retrieved: int,
    counts: dict[str, int],
) -> list[str]:
    gaps: list[str] = []
    if retrieved == 0:
        gaps.append("所选来源下未检索到资料，请放宽时间窗或换问题词")
    elif not items:
        gaps.append("有候选但均落在时间窗外（论文除外），请放大 time_window")
    src = req.get("sources") or {}
    for key, label in (
        ("news", "资讯"),
        ("report", "研报"),
        ("paper", "论文"),
        ("post", "帖子"),
    ):
        if src.get(key, True) and not counts.get(key):
            gaps.append(f"{label}源本轮无命中")
    return gaps


def run_gather(body: dict[str, Any], *, user_id: int) -> EvidencePack:
    """执行 Agent A；失败抛 ValueError / 其它异常由 API 转码。"""
    t0 = time.time()
    req = normalize_request(body, user_id=user_id)
    start, end = _window_bounds(req.get("time_window"))
    warnings: list[str] = []

    raw_rows: list[dict[str, Any]] = []
    src = req.get("sources") or {}
    max_items = int(req.get("max_items") or 20)
    # 各通道多捞一些，成包时再配比截断（无站内库）
    per = max(8, min(24, max_items // 2 + 6))
    if src.get("news", True):
        live, w = web_sources.search_news_live(topic=req["topic"], limit=per)
        warnings.extend(w)
        raw_rows.extend(live)
    if src.get("report", True):
        live, w = web_sources.search_reports(
            topic=req["topic"], start=start, end=end, limit=per
        )
        warnings.extend(w)
        raw_rows.extend(live)
    if src.get("paper", True):
        live, w = web_sources.search_papers(topic=req["topic"], limit=min(12, per))
        warnings.extend(w)
        raw_rows.extend(live)
    if src.get("post", True):
        live, w = web_sources.search_posts(topic=req["topic"], limit=min(12, per))
        warnings.extend(w)
        raw_rows.extend(live)

    # 短摘要尽量补抓正文，减少上下文损失
    raw_rows = web_sources.enrich_snippets(
        raw_rows,
        max_fetch=min(22, max(10, max_items + 6)),
        max_chars=4000,
    )
    retrieved = len(raw_rows)

    windowed = _filter_window(raw_rows, start, end)
    deduped = _dedupe(windowed)
    ranked = _rank(
        deduped,
        topic=req["topic"],
        themes=req.get("themes") or [],
        prefer_flash=bool(req.get("prefer_flash")),
    )
    top = _take_balanced(ranked, max_items)
    items = [_to_evidence_item(r, rel) for rel, r in top]

    use_llm = bool(body.get("use_llm", True))
    digest_mode = "rule"
    tokens_in = 0
    tokens_out = 0
    llm_model = ""

    if use_llm and items:
        digest, bullets, usage, llm_err = _llm_digest(topic=req["topic"], items=items)
        if llm_err or not digest:
            rule_d, rule_b = _rule_digest(items)
            digest, bullets = rule_d, rule_b
            digest_mode = "rule_fallback"
            warnings.append(f"digest 回退规则摘要：{llm_err or '空结果'}")
        else:
            digest_mode = "llm"
            tokens_in = int(usage.get("tokens_in") or 0)
            tokens_out = int(usage.get("tokens_out") or 0)
            llm_model = str(usage.get("model") or "")
    else:
        digest, bullets = _rule_digest(items)
        if not use_llm:
            digest_mode = "rule_forced"

    citations = [
        {
            "id": it["id"],
            "label": (it.get("title") or "")[:40],
            "url": it.get("url"),
        }
        for it in items
    ]
    counts: dict[str, int] = {}
    for it in items:
        st = str(it.get("source_type") or "news")
        if st == "sv_news":
            st = "news"
        counts[st] = counts.get(st, 0) + 1
    gaps = _build_gaps(
        req=req,
        items=items,
        retrieved=retrieved,
        counts=counts,
    )

    pack_id = f"evp_{_now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
    elapsed_ms = int((time.time() - t0) * 1000)

    return {
        "ok": True,
        "pack_id": pack_id,
        "query": {
            "topic": req["topic"],
            "themes": req.get("themes") or [],
            "symbols": req.get("symbols") or [],
            "time_window": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "preset": (req.get("time_window") or {}).get("preset"),
            },
            "sources": req.get("sources") or {},
            "max_items": max_items,
            "prefer_flash": bool(req.get("prefer_flash")),
            "use_llm": use_llm,
            "digest_mode": digest_mode,
        },
        "items": items,  # type: ignore[typeddict-item]
        "digest": digest,
        "digest_bullets": bullets,  # type: ignore[typeddict-item]
        "citations": citations,  # type: ignore[typeddict-item]
        "gaps": gaps,
        "stats": {
            "retrieved": retrieved,
            "after_dedupe": len(deduped),
            "returned": len(items),
            "elapsed_ms": elapsed_ms,
            "source_counts": counts,
            "digest_mode": digest_mode,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "llm_model": llm_model,
        },
        "warnings": warnings,
    }
