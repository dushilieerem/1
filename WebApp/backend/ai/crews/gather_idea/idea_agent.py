# -*- coding: utf-8 -*-
"""Agent B · Idea 生成：EvidencePack → IdeaBundle（LLM + 规则弱回退）。"""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

_TZ = timezone(timedelta(hours=8))
_MAX_ITEMS = 20
_MAX_SNIPPET = 900
_MAX_IDEAS_HARD = 10
_FOCUS_OK = {"theme", "factor", "risk", "mixed"}
_HORIZON_OK = {"short", "medium"}
_CONF_OK = {"low", "mid", "high"}


def _now_stamp() -> str:
    return datetime.now(_TZ).strftime("%Y%m%d_%H%M%S")


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


_FIELDS_OK = {"close", "open", "high", "low", "volume"}
_UNIVERSE_OK = {"CSI300", "CSI500", "CSI1000", "SSE50"}
_REGIME_OK = {"persistent", "event", "structural"}


def _advice_validity(*, regime: str = "persistent", why: str = "") -> dict[str, str]:
    """仅分析建议：哪段市况/制度后可能更好。不是下游必跑回测窗。"""
    return {
        "regime": regime if regime in _REGIME_OK else "persistent",
        "suggested_start": "",
        "suggested_end": "",
        "oos_split": "",
        "why_window": (why or "").strip()[:400],
        "decay_notes": "仅供参考；因子草稿/检测页可由人另设回测（平台常默认近十年），不必采用本建议。",
    }


def _normalize_validity(raw: Any) -> dict[str, str]:
    out = _advice_validity()
    if not isinstance(raw, dict):
        return out
    regime = str(raw.get("regime") or "persistent").strip().lower()
    if regime not in _REGIME_OK:
        regime = "persistent"
    out["regime"] = regime
    for k in ("suggested_start", "suggested_end", "oos_split"):
        v = str(raw.get(k) or "").strip()[:10]
        if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            y = int(v[:4])
            # 文献出版年（如 Weaver 1991）不能当 A 股回测起点
            if k == "suggested_start" and y < 2005:
                continue
            out[k] = v
    why = str(raw.get("why_window") or "").strip()
    if why:
        out["why_window"] = why[:400]
    notes = str(raw.get("decay_notes") or "").strip()
    if notes:
        out["decay_notes"] = notes[:240]
    return out


def _normalize_factor_spec(raw: Any) -> dict[str, Any]:
    spec = {
        "universe": "CSI300",
        "frequency": "1d",
        "used_fields": ["close", "volume"],
        "preferred_factor_name": "",
        "direction": "high_good",
    }
    if not isinstance(raw, dict):
        return spec
    uni = str(raw.get("universe") or "CSI300").strip().upper()
    spec["universe"] = uni if uni in _UNIVERSE_OK else "CSI300"
    spec["frequency"] = "1d"
    fields = raw.get("used_fields") if isinstance(raw.get("used_fields"), list) else []
    clean = [str(x) for x in fields if str(x) in _FIELDS_OK]
    spec["used_fields"] = clean[:6] or ["close"]
    name = re.sub(r"[^a-zA-Z0-9_]", "", str(raw.get("preferred_factor_name") or ""))[:48]
    spec["preferred_factor_name"] = name
    d = str(raw.get("direction") or "high_good").strip()
    spec["direction"] = d if d in {"high_good", "low_good"} else "high_good"
    return spec


def _normalize_preference(raw: Any) -> dict[str, str]:
    pref: dict[str, str] = {"focus": "factor", "horizon": "medium", "note": ""}
    if not isinstance(raw, dict):
        return pref
    focus = str(raw.get("focus") or "factor").strip().lower()
    pref["focus"] = focus if focus in _FOCUS_OK else "factor"
    horizon = str(raw.get("horizon") or "medium").strip().lower()
    pref["horizon"] = horizon if horizon in _HORIZON_OK else "medium"
    note = str(raw.get("note") or "").strip()[:200]
    pref["note"] = note
    return pref


_EVENT_MARKERS = (
    "IPO",
    "上市发行",
    "发布会",
    "股东大会",
    "减持",
    "增发",
    "调研纪要",
    "业绩会",
    "路演",
)
_SRC_RANK = {"paper": 0, "report": 1, "post": 2, "news": 3}


def _looks_like_event(text: str) -> bool:
    blob = text or ""
    return any(k in blob for k in _EVENT_MARKERS)


def _pack_topic(pack: dict[str, Any]) -> str:
    q = pack.get("query") if isinstance(pack.get("query"), dict) else {}
    return str((q or {}).get("topic") or "").strip()


def _items_for_llm(pack: dict[str, Any]) -> list[dict[str, Any]]:
    """论文/研报优先，其次命中原问题的条目。"""
    items = [it for it in (pack.get("items") or []) if isinstance(it, dict)]
    topic = _pack_topic(pack)
    head = topic[:8] if topic else ""

    def _key(it: dict[str, Any]) -> tuple[int, int]:
        st = str(it.get("source_type") or "news")
        blob = f"{it.get('title') or ''} {it.get('snippet') or ''}"
        hit = 0 if (head and head in blob) else 1
        return (_SRC_RANK.get(st, 9), hit)

    return sorted(items, key=_key)


def _compact_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in items[:_MAX_ITEMS]:
        if not isinstance(it, dict):
            continue
        iid = str(it.get("id") or "").strip()
        if not iid:
            continue
        out.append(
            {
                "id": iid,
                "title": str(it.get("title") or "").strip()[:160],
                "snippet": str(it.get("snippet") or "").strip()[:_MAX_SNIPPET],
                "themes": list(it.get("themes") or [])[:6]
                if isinstance(it.get("themes"), list)
                else [],
                "published_at": str(it.get("published_at") or "")[:32],
                "sv_news_id": it.get("sv_news_id"),
                "source_label": str(it.get("source_label") or "")[:40],
                "source_type": str(it.get("source_type") or "")[:20],
                "url": it.get("url"),
            }
        )
    return out


def _normalize_pack(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("pack 须为对象")
    pack_id = str(raw.get("pack_id") or "").strip()
    if not pack_id:
        raise ValueError("pack.pack_id 必填")
    items_raw = raw.get("items") if isinstance(raw.get("items"), list) else []
    items = _compact_items(items_raw)  # type: ignore[arg-type]
    bullets_raw = (
        raw.get("digest_bullets")
        if isinstance(raw.get("digest_bullets"), list)
        else []
    )
    bullets: list[dict[str, Any]] = []
    for b in bullets_raw[:12]:
        if not isinstance(b, dict):
            continue
        text = str(b.get("text") or "").strip()
        ids_raw = b.get("item_ids") if isinstance(b.get("item_ids"), list) else []
        ids = [str(x) for x in ids_raw if str(x).strip()]
        if text:
            bullets.append({"text": text[:200], "item_ids": ids[:6]})
    gaps_raw = raw.get("gaps") if isinstance(raw.get("gaps"), list) else []
    return {
        "pack_id": pack_id,
        "digest": str(raw.get("digest") or "").strip()[:2000],
        "digest_bullets": bullets,
        "items": items,
        "gaps": [str(g).strip() for g in gaps_raw if str(g).strip()][:8],
        "query": raw.get("query") if isinstance(raw.get("query"), dict) else {},
    }


def _filter_ideas(
    raw_ideas: list[Any],
    *,
    allowed: set[str],
    max_ideas: int,
    items: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    by_id = {str(it.get("id")): it for it in (items or []) if isinstance(it, dict)}
    ideas: list[dict[str, Any]] = []
    for raw in raw_ideas[: max_ideas * 2]:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()[:80]
        thesis = str(raw.get("thesis") or "").strip()[:500]
        if not title or not thesis:
            continue
        cites_raw = (
            raw.get("citation_ids")
            if isinstance(raw.get("citation_ids"), list)
            else []
        )
        cites = [str(x) for x in cites_raw if str(x) in allowed]
        if not cites:
            warnings.append(f"丢弃无合法引用的 idea：{title[:30]}")
            continue
        conf = str(raw.get("confidence") or "low").strip().lower()
        if conf not in _CONF_OK:
            conf = "low"
        risks_raw = (
            raw.get("risk_notes")
            if isinstance(raw.get("risk_notes"), list)
            else []
        )
        risks = [str(r).strip()[:120] for r in risks_raw if str(r).strip()][:4]
        if not risks:
            risks = ["基于有限公开资料的假设，需下游回测量化", "不构成买卖建议"]
        next_step = str(raw.get("suggested_next") or "").strip()[:200]
        convertible = bool(raw.get("convertible", True))
        prompt = str(raw.get("factor_prompt") or "").strip()[:2000]
        spec = _normalize_factor_spec(raw.get("factor_spec"))
        validity = _normalize_validity(raw.get("validity"))
        cite_types = {str((by_id.get(c) or {}).get("source_type") or "") for c in cites}
        if convertible and _looks_like_event(f"{title} {thesis}") and cite_types <= {"news", ""}:
            convertible = False
            prompt = ""
            warnings.append(f"事件/叙事类降为不可转：{title[:30]}")
        if convertible and len(prompt) < 20:
            convertible = False
            prompt = ""
        if not next_step:
            next_step = (
                "将 factor_prompt 交给因子草稿 Agent；回测区间由人在检测页设定，不必采用本建议时段"
                if convertible
                else "当前更像事件/叙事，补量价机制后再转因子，或继续搜集"
            )
        ideas.append(
            {
                "id": f"idea_{len(ideas) + 1}",
                "title": title,
                "thesis": thesis,
                "citation_ids": cites[:6],
                "suggested_next": next_step,
                "risk_notes": risks,
                "confidence": conf,
                "convertible": convertible,
                "factor_prompt": prompt,
                "factor_spec": spec,
                "validity": validity,
            }
        )
        if len(ideas) >= max_ideas:
            break
    if not ideas and raw_ideas:
        warnings.append("LLM 产出均未通过 citation 校验")
    return ideas, warnings


def _rule_ideas(
    pack: dict[str, Any],
    *,
    max_ideas: int,
    preference: dict[str, str],
) -> list[dict[str, Any]]:
    """弱回退：从 bullets / items 扩写成可溯源 idea，不编造事实。"""
    _ = preference
    items: list[dict[str, Any]] = pack["items"]
    if not items:
        return []
    topic = _pack_topic(pack)
    eventish = _looks_like_event(topic)
    convertible = not eventish
    regime = (
        "event"
        if eventish
        else "structural"
        if any(k in topic for k in ("注册制", "科创板", "做市", "改革"))
        else "persistent"
    )
    bullets: list[dict[str, Any]] = pack.get("digest_bullets") or []
    seeds: list[tuple[str, list[str]]] = []
    for b in bullets:
        ids = [x for x in (b.get("item_ids") or []) if x]
        if ids:
            seeds.append((str(b.get("text") or "")[:120], ids[:3]))
    if not seeds:
        for it in items[:max_ideas]:
            seeds.append((str(it.get("title") or "")[:120], [it["id"]]))

    ideas: list[dict[str, Any]] = []
    for text, cites in seeds[:max_ideas]:
        why = (
            "规则弱回退，未做时段分析。若题涉制度/板块（如科创板、注册制），应优先看落地后的样本；"
            "具体哪段更好需 LLM 或人工判断。下游回测由人设，不必采用本条。"
        )
        if regime == "structural":
            why = (
                "规则弱回退：题面偏制度/结构变化，逻辑上更应看改革落地之后，"
                "而不是从文献出版年往前拉到 1990 年代。下游回测由人设。"
            )
        validity = _advice_validity(regime=regime, why=why)
        hook = topic or text[:80]
        prompt = ""
        next_step = "当前为规则弱回退；建议确认 LLM 可用后重跑，再交给因子草稿"
        if convertible:
            prompt = (
                f"围绕研究问题「{hook}」，用 close 与 volume 表达「"
                f"{text[:80]}"
                "」的可检验方向。只使用 self.close/self.volume 等面板字段，"
                "禁止未来函数；函数名用英文蛇形。该草稿需能提交 SVQuant POST /api/backtest/factor。"
            )
            next_step = "将 factor_prompt 交给因子草稿 Agent；回测区间由人在检测页设定"
        ideas.append(
            {
                "id": f"idea_{len(ideas) + 1}",
                "title": (text[:40] + ("…" if len(text) > 40 else "")) or "证据衍生假设",
                "thesis": (
                    f"基于资料「{text}」，假设相关量价特征在截面上可排序。{why}"
                )[:500],
                "citation_ids": cites,
                "suggested_next": next_step,
                "risk_notes": [
                    "规则弱回退，未走 LLM 深推理",
                    "未给出强时段建议；勿把文献出版年当成回测起点",
                    "不构成买卖建议",
                ],
                "confidence": "low",
                "convertible": convertible,
                "factor_prompt": prompt[:2000],
                "factor_spec": _normalize_factor_spec(
                    {"universe": "CSI300", "used_fields": ["close", "volume"]}
                ),
                "validity": validity,
            }
        )
    return ideas


def _llm_ideas(
    *,
    pack: dict[str, Any],
    preference: dict[str, str],
    max_ideas: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], str | None]:
    items = pack["items"]
    if not items:
        return [], {}, None
    try:
        from ai.gateway.llm_client import LlmError, chat_completions, llm_configured
    except Exception as exc:  # noqa: BLE001
        return [], {}, f"LLM 模块不可用: {exc}"

    if not llm_configured():
        return [], {}, "LLM 未配置"

    topic = _pack_topic(pack)
    ordered = _items_for_llm(pack) or items
    allowed = {it["id"] for it in items}
    system = (
        "你是量化研究假设助理。只根据证据包生成可交给因子草稿 Agent 的研究假设。"
        "必须紧扣用户问题 topic，不要把包内无关材料扩成另一套逻辑。"
        "禁止编造资料中未出现的事实/数字。禁止买卖建议与收益承诺。"
        "产品写死偏因子：尽量产出 convertible=true 的日频量价假设；"
        "若只是主题炒作/IPO/会议、无法写成量价因子：convertible=false，factor_prompt 空。"
        "SVQuant 因子形态：def name(self, ...): 只用 self.close/open/high/low/volume 日频面板。"
        "每条 idea 必须含：title, thesis, citation_ids, suggested_next, risk_notes, "
        "confidence(low|mid|high), convertible(bool), factor_prompt, factor_spec, validity。"
        "factor_prompt：1～2000字中文，描述要生成的日频因子。"
        "factor_spec：universe(CSI300|CSI500|CSI1000|SSE50), frequency=1d, "
        "used_fields, preferred_factor_name, direction(high_good|low_good)。"
        "【validity 是分析建议，不是下游必跑回测窗】"
        "下游检测页常由人设近十年；你只回答：这条假设更可能在哪段市况/制度后表现更好。"
        "validity.why_window 必填：用机制说话（如科创板做市落地后、注册制主板实施后、"
        "拥挤期、熊市反转等）。禁止套话「覆盖完整牛熊所以从 1991/2018 跑到今天」。"
        "suggested_start/end 仅当机制能推出具体年才填（如 STAR 2019-07 后用 2019-07-01）；"
        "禁止把参考文献出版年（Weaver 1991 等）当样本起点；起点一般不要早于 2005。"
        "oos_split 可空。decay_notes 写失效/拥挤风险。"
        "经典资产定价机制（动量、反转、换手、非流动性、隔夜、质量）即使证据是论文，"
        "也应 convertible=true，factor_prompt 写成仅用 close/open/high/low/volume。"
        "可转假设优先引用 paper/report；纯资讯事件不要标可转。"
        '输出严格 JSON：{"ideas":[...],"gaps":["..."]}。'
        f"idea 数量 3～{max_ideas}。"
    )
    user = json.dumps(
        {
            "topic": topic,
            "preference": preference,
            "max_ideas": max_ideas,
            "digest": pack.get("digest") or "",
            "digest_bullets": pack.get("digest_bullets") or [],
            "source_counts": {
                st: sum(1 for it in items if str(it.get("source_type") or "news") == st)
                for st in ("news", "report", "paper", "post")
            },
            "platform_factor_hint": {
                "fields": ["close", "open", "high", "low", "volume"],
                "universes": ["CSI300", "CSI500", "CSI1000", "SSE50"],
                "note": "下游回测窗由人设；validity 只做表现时段建议",
            },
            "items": [
                {
                    "id": it["id"],
                    "source_type": it.get("source_type"),
                    "source_label": it.get("source_label"),
                    "title": it.get("title"),
                    "snippet": it.get("snippet"),
                    "url": it.get("url"),
                    "published_at": it.get("published_at"),
                }
                for it in ordered
            ],
            "gaps_from_pack": pack.get("gaps") or [],
        },
        ensure_ascii=False,
    )
    try:
        out = chat_completions(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
            max_tokens=4500,
        )
    except LlmError as exc:
        return [], {}, str(exc)
    except Exception as exc:  # noqa: BLE001
        return [], {}, f"LLM 调用失败: {exc}"

    usage = {
        "tokens_in": int(out.get("tokens_in") or 0),
        "tokens_out": int(out.get("tokens_out") or 0),
        "model": out.get("model") or "",
    }
    obj = _extract_json_obj(str(out.get("content") or ""))
    if not obj:
        return [], usage, "LLM 返回无法解析为 JSON"

    raw_ideas = obj.get("ideas") if isinstance(obj.get("ideas"), list) else []
    ideas, cite_warn = _filter_ideas(
        raw_ideas,
        allowed=allowed,
        max_ideas=max_ideas,
        items=items,
    )
    gaps_llm = obj.get("gaps") if isinstance(obj.get("gaps"), list) else []
    usage["_gaps_llm"] = [str(g).strip() for g in gaps_llm if str(g).strip()][:6]
    usage["_cite_warn"] = cite_warn
    if not ideas:
        return [], usage, "LLM 未产出有效 idea（或缺合法 citation）"
    return ideas, usage, None


def run_idea(body: dict[str, Any], *, user_id: int) -> dict[str, Any]:
    """主入口：校验 EvidencePack → 生成 IdeaBundle。"""
    _ = user_id  # 配额在 pipeline 记账
    t0 = time.perf_counter()
    pack = _normalize_pack(body.get("pack"))
    preference = _normalize_preference(body.get("preference"))
    preference["focus"] = "factor"
    try:
        max_ideas = int(body.get("max_ideas") or 5)
    except (TypeError, ValueError):
        max_ideas = 5
    max_ideas = max(1, min(max_ideas, _MAX_IDEAS_HARD))

    gaps: list[str] = list(pack.get("gaps") or [])
    warnings: list[str] = []
    mode = "llm"
    usage: dict[str, Any] = {}
    ideas: list[dict[str, Any]] = []

    if not pack["items"]:
        gaps.append("证据条目为空，无法生成带引用的 idea")
        mode = "empty"
    else:
        ideas, usage, llm_err = _llm_ideas(
            pack=pack, preference=preference, max_ideas=max_ideas
        )
        gaps.extend(usage.pop("_gaps_llm", []) or [])
        warnings.extend(usage.pop("_cite_warn", []) or [])
        if llm_err or not ideas:
            ideas = _rule_ideas(pack, max_ideas=max_ideas, preference=preference)
            mode = "rule_fallback" if ideas else "failed"
            if llm_err:
                warnings.append(f"idea 回退规则生成：{llm_err}")
            if not ideas:
                gaps.append("无法生成 idea")
        else:
            mode = "llm"

    elapsed = int((time.perf_counter() - t0) * 1000)
    bundle_id = f"idb_{_now_stamp()}_{uuid.uuid4().hex[:6]}"
    ok = bool(ideas) or mode == "empty"
    return {
        "ok": ok and mode != "failed",
        "bundle_id": bundle_id,
        "pack_id": pack["pack_id"],
        "ideas": ideas,
        "gaps": gaps,
        "warnings": warnings,
        "stats": {
            "elapsed_ms": elapsed,
            "tokens_in": int(usage.get("tokens_in") or 0),
            "tokens_out": int(usage.get("tokens_out") or 0),
            "llm_model": usage.get("model") or "",
            "idea_mode": mode,
            "returned": len(ideas),
            "max_ideas": max_ideas,
            "preference": preference,
        },
        "error": None if (ideas or mode == "empty") else "生成失败",
    }
