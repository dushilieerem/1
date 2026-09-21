# -*- coding: utf-8 -*-
"""Skill 注册表：可被多 Agent 复用的能力原子。"""
from __future__ import annotations

import json
import os
import re
from html import unescape
from typing import Any, Callable

from ai.gateway.llm_client import LlmError, chat_completions, llm_configured
from ai.crews._shared.metrics_trust import (
    PLATFORM_KNOWLEDGE,
    PROMISE_RE,
    QUANT_CLAIM_RE,
    evaluate_metrics_trust,
    summary_number_flags,
    trust_prompt_block,
)

SkillFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]

SECTION_IDS = ("strategy", "factor", "qa", "hotspot", "official")
SECTION_LABELS = {
    "strategy": "策略分享",
    "factor": "因子笔记",
    "qa": "问答",
    "hotspot": "热点分析",
    "official": "官方",
}


def strip_html(text: str) -> str:
    plain = re.sub(r"<[^>]+>", " ", text or "")
    plain = unescape(plain)
    return re.sub(r"\s+", " ", plain).strip()


def extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise LlmError("无法解析模型 JSON")
    data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise LlmError("模型 JSON 非对象")
    return data


def _draft_from(board: dict[str, Any], ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    d = dict((board or {}).get("draft") or {})
    if ctx:
        for k in ("title", "body", "section", "code_snippet"):
            if k in ctx and ctx[k] is not None and k not in d:
                d[k] = ctx[k]
    return d


def _board_trust(board: dict[str, Any], ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    """优先用 board.artifacts；单技能路径则现场评估 context.platform_ref。"""
    art = (board or {}).get("artifacts") or {}
    if isinstance(art.get("data_trust"), dict) and art.get("data_trust"):
        trust = {
            "status": art["data_trust"].get("status"),
            "summary": art["data_trust"].get("summary"),
            "platform_ref": art.get("platform_ref"),
            "flags": list((board or {}).get("flags") or []),
        }
        if trust.get("platform_ref") or trust.get("status"):
            return trust
    d = _draft_from(board, ctx)
    ref = None
    if ctx and ctx.get("platform_ref") is not None:
        ref = ctx.get("platform_ref")
    elif art.get("platform_ref") is not None:
        ref = art.get("platform_ref")
    return evaluate_metrics_trust(
        title=str(d.get("title") or ""),
        body=str(d.get("body") or ""),
        platform_ref=ref,
    )


def _mock_polish_title(title: str, section: str) -> str:
    t = (title or "").strip() or "未命名分享"
    t = re.sub(r"\s+", " ", t)
    if len(t) > 100:
        t = t[:97] + "…"
    t = re.sub(r"[！!]{2,}", "！", t)
    t = re.sub(r"[？?]{2,}", "？", t)
    if section == "qa" and not t.endswith("？") and not t.endswith("?"):
        if len(t) < 40:
            t = f"{t}？"
    return t[:120]


def _mock_polish_body(body: str, title: str) -> str:
    b = (body or "").strip()
    if not b:
        safe_title = (title or "本帖").strip() or "本帖"
        return (
            f"<p><strong>{safe_title}</strong></p>"
            f"<p>本文整理了研究要点，欢迎评论交流。内容由 SVQuant Agent 辅助润色。</p>"
        )
    if "<" not in b:
        paras = [p.strip() for p in re.split(r"\n{2,}", b) if p.strip()]
        if not paras:
            paras = [b]
        return "".join(f"<p>{p}</p>" for p in paras)
    return b


def skill_polish_title(ctx: dict[str, Any], board: dict[str, Any]) -> dict[str, Any]:
    d = _draft_from(board, ctx)
    title = str(d.get("title") or "")
    body = str(d.get("body") or "")
    section = str(d.get("section") or "strategy")
    trust = _board_trust(board, ctx)
    if not llm_configured():
        out = _mock_polish_title(title, section)
        return {
            "board_patch": {"draft": {"title": out}},
            "outputs": {"title": out},
            "tokens_in": 0,
            "tokens_out": 0,
            "provider": "mock_local",
        }
    system = (
        "你是 SVQuant 量化社区的 Writer（三 Agent 之 Writer）。润色帖子标题。"
        "中文、简洁、不超过 120 字、不夸张营销、不加整句引号。"
        f"{PLATFORM_KNOWLEDGE}"
        "关于数字："
        "- verified：标题里若写量化指标，只能用 platform_ref.metrics_display 里已有的值，禁止编造或改数；"
        "- unverified：不要把用户手写的 IC/年化写成已证实结论；可弱化或去掉具体数；"
        "- casual：日常分享，正常润色即可，不要当成回测帖。"
        "只返回 JSON：{\"title\":\"...\"}"
    )
    user_msg = json.dumps(
        {
            "section": section,
            "title": title,
            "body_excerpt": strip_html(body)[:500],
            "flags": (board or {}).get("flags") or [],
            **trust_prompt_block(trust),
        },
        ensure_ascii=False,
    )
    result = chat_completions(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.35,
        max_tokens=200,
    )
    parsed = extract_json_object(result["content"])
    new_title = str(parsed.get("title") or "").strip() or title
    new_title = new_title[:120]
    return {
        "board_patch": {"draft": {"title": new_title}},
        "outputs": {"title": new_title},
        "tokens_in": result["tokens_in"],
        "tokens_out": result["tokens_out"],
        "provider": result.get("provider") or "openai_compatible",
        "model": result.get("model"),
    }


def skill_polish_body(ctx: dict[str, Any], board: dict[str, Any]) -> dict[str, Any]:
    d = _draft_from(board, ctx)
    title = str(d.get("title") or "")
    body = str(d.get("body") or "")
    section = str(d.get("section") or "strategy")
    code = str(d.get("code_snippet") or "")
    trust = _board_trust(board, ctx)
    if not llm_configured():
        out = _mock_polish_body(body, title)
        return {
            "board_patch": {
                "draft": {"body": out},
                "artifacts": {
                    "data_trust": {
                        "status": trust.get("status"),
                        "summary": trust.get("summary"),
                    },
                    "platform_ref": trust.get("platform_ref"),
                },
            },
            "outputs": {"body": out},
            "tokens_in": 0,
            "tokens_out": 0,
            "provider": "mock_local",
        }
    system = (
        "你是 SVQuant 量化社区的 Writer（三 Agent 之 Writer）。润色正文。"
        f"{PLATFORM_KNOWLEDGE}"
        "使用简单 HTML（多个 <p> 分段，可用 strong/ul/li/code）；"
        "每个要点或自然段单独一个 <p>，禁止整篇挤进一个段落。"
        "数字规则（必须遵守）："
        "1) verified：量化指标只能使用 platform_ref.metrics_display 中的值；"
        "   保留原文结构与免责声明，不要另编指标，不要在文末再加「数据来源」说明（引用已在上下文）；"
        "2) unverified：不要编造回测；对 IC/年化/夏普等具体数改为「未经验证/待补充」或删除；"
        "3) casual：天气、心情、个人赚亏等日常叙述保留，不要当成因子回测去改。"
        "若 board.flags 有异议，优先改掉或弱化对应表述。"
        "只返回 JSON：{\"body\":\"...\"}"
    )
    user_msg = json.dumps(
        {
            "section": section,
            "title": title,
            "body": body[:6000],
            "has_code": bool(code.strip()),
            "flags": (board or {}).get("flags") or [],
            **trust_prompt_block(trust),
        },
        ensure_ascii=False,
    )
    result = chat_completions(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.35,
        max_tokens=1200,
    )
    parsed = extract_json_object(result["content"])
    new_body = str(parsed.get("body") or "").strip() or body
    return {
        "board_patch": {
            "draft": {"body": new_body},
            "artifacts": {
                "data_trust": {
                    "status": trust.get("status"),
                    "summary": trust.get("summary"),
                },
                "platform_ref": trust.get("platform_ref"),
            },
        },
        "outputs": {"body": new_body},
        "tokens_in": result["tokens_in"],
        "tokens_out": result["tokens_out"],
        "provider": result.get("provider") or "openai_compatible",
        "model": result.get("model"),
    }


def skill_suggest_section(ctx: dict[str, Any], board: dict[str, Any]) -> dict[str, Any]:
    d = _draft_from(board, ctx)
    title = str(d.get("title") or "")
    body = str(d.get("body") or "")
    cur = str(d.get("section") or "strategy")
    code = str(d.get("code_snippet") or "")

    if not llm_configured():
        trust = _board_trust(board, ctx)
        ref = trust.get("platform_ref") if isinstance(trust, dict) else None
        src = str((ref or {}).get("source") or "")
        text = (title + " " + strip_html(body)).lower()
        if any(k in text for k in ("怎么", "报错", "咋办", "如何", "？", "?")):
            sug = "qa"
        elif src in ("factor_detect", "factor_panel") or any(
            k in text for k in ("换手", "ic", "因子", "分层")
        ):
            sug = "factor"
        elif src == "strategy_report":
            sug = "strategy"
        elif any(k in text for k in ("这周", "行情", "波动", "瞎聊", "感受")):
            sug = "hotspot"
        else:
            sug = "strategy" if code.strip() or "策略" in text else cur
        if sug not in SECTION_IDS:
            sug = cur
        return {
            "board_patch": {
                "draft": {"section": sug},
                "artifacts": {
                    "section_suggestion": {
                        "section": sug,
                        "label": SECTION_LABELS.get(sug, sug),
                        "reason": "本地规则建议",
                    }
                },
            },
            "outputs": {"section": sug},
            "tokens_in": 0,
            "tokens_out": 0,
            "provider": "mock_local",
        }

    trust = _board_trust(board, ctx)
    system = (
        "你是 SVQuant 社区 Router。根据标题正文代码建议分区。"
        "可选：strategy / factor / qa / hotspot / official（official 仅当内容像官方公告）。"
        "若 platform_ref.source 为 factor_detect / factor_panel：优先 factor，除非正文明显是问答。"
        "若 platform_ref.source 为 strategy_report：优先 strategy。"
        "用户已选分区合理时可保持 current_section。"
        "只返回 JSON：{\"section\":\"...\",\"reason\":\"...\"}"
    )
    user_msg = json.dumps(
        {
            "current_section": cur,
            "title": title,
            "body_excerpt": strip_html(body)[:800],
            "has_code": bool(code.strip()),
            **trust_prompt_block(trust),
        },
        ensure_ascii=False,
    )
    result = chat_completions(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        max_tokens=200,
    )
    parsed = extract_json_object(result["content"])
    sug = str(parsed.get("section") or cur).strip()
    if sug not in SECTION_IDS or sug == "official":
        # 非 admin 场景避免乱建议 official
        sug = cur if sug == "official" else (sug if sug in SECTION_IDS else cur)
    reason = str(parsed.get("reason") or "").strip() or "模型建议"
    return {
        "board_patch": {
            "draft": {"section": sug},
            "artifacts": {
                "section_suggestion": {
                    "section": sug,
                    "label": SECTION_LABELS.get(sug, sug),
                    "reason": reason,
                }
            },
        },
        "outputs": {"section": sug},
        "tokens_in": result["tokens_in"],
        "tokens_out": result["tokens_out"],
        "provider": result.get("provider") or "openai_compatible",
        "model": result.get("model"),
    }


def skill_audit_claims(ctx: dict[str, Any], board: dict[str, Any]) -> dict[str, Any]:
    d = _draft_from(board, ctx)
    title = str(d.get("title") or "")
    body = str(d.get("body") or "")
    trust = _board_trust(board, ctx)
    det_flags = list(trust.get("flags") or [])

    if not llm_configured():
        # 确定性审计：重新评估当前草稿（润色后可能已改）
        trust2 = evaluate_metrics_trust(
            title=title,
            body=body,
            platform_ref=trust.get("platform_ref"),
        )
        flags = list(trust2.get("flags") or [])
        decision = "approve"
        if any(f.get("severity") == "block" for f in flags):
            decision = "block"
        elif flags:
            decision = "revise"
        return {
            "board_patch": {
                "flags": flags,
                "artifacts": {
                    "audit_report": {"flags": flags, "decision": decision},
                    "data_trust": {
                        "status": trust2.get("status"),
                        "summary": trust2.get("summary"),
                    },
                    "platform_ref": trust2.get("platform_ref"),
                },
                "votes": [
                    {
                        "agent": "critic",
                        "decision": decision,
                        "reason": f"本地启发式+平台引用审计（{trust2.get('status')}）",
                    }
                ],
            },
            "outputs": {"audit_decision": decision, "flags": flags},
            "tokens_in": 0,
            "tokens_out": 0,
            "provider": "mock_local",
        }

    system = (
        "你是 SVQuant Critic（三 Agent 之 Critic）。检查帖子夸大、承诺收益、以及量化数字可信度。"
        "不要改写正文。返回 JSON："
        '{"decision":"approve|revise|block","flags":[{"code":"...","severity":"info|warn|block","message":"..."}]}'
        "规则："
        "- data_trust_status=casual：天气/心情/个人赚亏等日常叙述，不要打 unverified_metric；"
        "- data_trust_status=verified：正文来自平台面板/检测/策略分享，指标已是真源。"
        "  不要因数字格式、日期区间、股票池代码等打 metrics_conflict，不要因此 block；"
        "  除非出现稳赚/必涨等承诺收益，否则应 approve；"
        "- unverified：对 IC/年化/夏普等具体回测数字打 unverified_metric（warn），decision=revise 即可，不要 block；"
        "- 稳赚/必涨/保证收益 → promise_return（block）；"
        "- 不要因为「赚了1000块」这种个人盈亏去要求平台验证。"
        "decision=revise 需 Writer 删改；block 仅用于严重违规（承诺收益），不要对分享帖 block。"
    )
    user_msg = json.dumps(
        {
            "title": title,
            "body": body[:6000],
            "deterministic_flags": det_flags,
            **trust_prompt_block(trust),
        },
        ensure_ascii=False,
    )
    result = chat_completions(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
        max_tokens=800,
    )
    parsed = extract_json_object(result["content"])
    decision = str(parsed.get("decision") or "approve").strip().lower()
    if decision not in ("approve", "revise", "block"):
        decision = "approve"
    raw_flags = parsed.get("flags") if isinstance(parsed.get("flags"), list) else []
    flags: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in list(det_flags) + list(raw_flags):
        if not isinstance(src, dict):
            continue
        item = {
            "code": str(src.get("code") or "issue")[:64],
            "severity": str(src.get("severity") or "warn")[:16],
            "message": str(src.get("message") or "")[:300],
        }
        key = f"{item['code']}:{item['message']}"
        if key in seen:
            continue
        seen.add(key)
        flags.append(item)
        if len(flags) >= 12:
            break
    # casual 时丢掉误伤的 unverified（模型偶发）
    if trust.get("status") == "casual":
        flags = [f for f in flags if f.get("code") != "unverified_metric"]
    # 已挂平台引用：丢掉模型误报的 metrics_conflict；禁止仅因数字 block
    if trust.get("status") == "verified":
        flags = [
            f
            for f in flags
            if f.get("code") not in ("metrics_conflict", "unverified_metric")
        ]
        if decision == "block" and not any(
            f.get("code") == "promise_return" or f.get("severity") == "block"
            for f in flags
        ):
            decision = "approve"
    if any(f.get("code") == "promise_return" or f.get("severity") == "block" for f in flags):
        decision = "block"
    elif flags and decision == "approve":
        decision = "revise"
    # 润色后重评 status（冲突可能已消失）
    trust2 = evaluate_metrics_trust(
        title=title,
        body=body,
        platform_ref=trust.get("platform_ref"),
    )
    return {
        "board_patch": {
            "flags": flags,
            "artifacts": {
                "audit_report": {"flags": flags, "decision": decision},
                "data_trust": {
                    "status": trust2.get("status"),
                    "summary": trust2.get("summary"),
                },
                "platform_ref": trust2.get("platform_ref"),
            },
            "votes": [
                {
                    "agent": "critic",
                    "decision": decision,
                    "reason": f"审计 {len(flags)} 条（trust={trust2.get('status')}）",
                }
            ],
        },
        "outputs": {"audit_decision": decision, "flags": flags},
        "tokens_in": result["tokens_in"],
        "tokens_out": result["tokens_out"],
        "provider": result.get("provider") or "openai_compatible",
        "model": result.get("model"),
    }


def skill_strip_unverifiable(ctx: dict[str, Any], board: dict[str, Any]) -> dict[str, Any]:
    d = _draft_from(board, ctx)
    title = str(d.get("title") or "")
    body = str(d.get("body") or "")
    flags = list((board or {}).get("flags") or [])

    if not flags:
        return {
            "board_patch": {},
            "outputs": {"body": body, "title": title},
            "tokens_in": 0,
            "tokens_out": 0,
            "provider": "noop",
        }

    if not llm_configured():
        # 弱化：去掉带 % 且无「约/未」的短句（粗暴但可演示回流）
        plain_paras = re.split(r"(?<=[。！？\n])", body)
        kept = []
        for p in plain_paras:
            if re.search(r"\d+(?:\.\d+)?\s*%", p) and not re.search(
                r"(未|没有|大约|好像|约|模糊)", p
            ):
                kept.append("<p>（已删除无出处量化表述，改为待补充。）</p>")
            else:
                kept.append(p)
        new_body = "".join(kept) if kept else body
        new_title = title
        if re.search(r"\d+(?:\.\d+)?\s*%", title) and "约" not in title:
            new_title = re.sub(r"\d+(?:\.\d+)?\s*%", "（待核实）", title)[:120]
        return {
            "board_patch": {
                "draft": {"title": new_title, "body": new_body},
                "flags": [],
                "votes": [
                    {
                        "agent": "writer",
                        "decision": "approve",
                        "reason": "已按 flags 删改（mock）",
                    }
                ],
            },
            "outputs": {"title": new_title, "body": new_body},
            "tokens_in": 0,
            "tokens_out": 0,
            "provider": "mock_local",
        }

    system = (
        "你是 SVQuant Writer。根据 Critic 的 flags 删改标题/正文中的不可核实表述。"
        "若有 platform_ref.metrics_display：量化数字改回引用值，不要另编。"
        "不要新增新的精确回测数字；可改为「未统计/待补充/纯感受」。"
        "日常赚亏叙述若无 promise_return flag，可保留。"
        "保持简单 HTML，正文用多个 <p> 分段，不要整篇一个段落。"
        "只返回 JSON：{\"title\":\"...\",\"body\":\"...\"}"
    )
    trust = _board_trust(board, ctx)
    user_msg = json.dumps(
        {
            "title": title,
            "body": body[:6000],
            "flags": flags,
            **trust_prompt_block(trust),
        },
        ensure_ascii=False,
    )
    result = chat_completions(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.25,
        max_tokens=1400,
    )
    parsed = extract_json_object(result["content"])
    new_title = str(parsed.get("title") or title).strip()[:120] or title
    new_body = str(parsed.get("body") or body).strip() or body
    return {
        "board_patch": {
            "draft": {"title": new_title, "body": new_body},
            "flags": [],
            "votes": [
                {
                    "agent": "writer",
                    "decision": "approve",
                    "reason": "已按审计 flags 删改",
                }
            ],
        },
        "outputs": {"title": new_title, "body": new_body},
        "tokens_in": result["tokens_in"],
        "tokens_out": result["tokens_out"],
        "provider": result.get("provider") or "openai_compatible",
        "model": result.get("model"),
    }


def _read_limits() -> tuple[int, int]:
    """0 或负数 = 不截断（默认不截，尽量读全文）。"""
    try:
        body_max = int(os.environ.get("AGENT_READ_BODY_MAX", "0") or "0")
    except ValueError:
        body_max = 0
    try:
        code_max = int(os.environ.get("AGENT_READ_CODE_MAX", "0") or "0")
    except ValueError:
        code_max = 0
    return body_max, code_max


def _maybe_truncate(text: str, limit: int) -> tuple[str, bool]:
    if limit <= 0 or len(text) <= limit:
        return text, False
    return text[:limit], True


def _source_from(board: dict[str, Any], ctx: dict[str, Any] | None = None) -> dict[str, str]:
    src = dict((board or {}).get("source") or {})
    if ctx:
        for k in ("title", "body", "code_snippet"):
            if k in ctx and ctx[k] is not None and not src.get(k):
                src[k] = str(ctx[k])
    d = _draft_from(board, ctx)
    return {
        "title": str(src.get("title") or d.get("title") or ""),
        "body": str(src.get("body") or d.get("body") or ""),
        "code_snippet": str(src.get("code_snippet") or d.get("code_snippet") or ""),
    }


def _mock_summary_md(*, title: str, body: str, truncated: bool) -> str:
    plain = strip_html(body)
    excerpt = plain[:120] + ("…" if len(plain) > 120 else "")
    limit_note = "原文过长已截断。" if truncated else "本地 mock。"
    return (
        f"## 背景\n\n{(title or '未命名帖').strip()}\n\n"
        f"## 方法或观点\n\n{excerpt or '（正文为空）'}\n\n"
        f"## 结论\n\n见原文要点。\n\n"
        f"## 局限\n\n{limit_note}\n"
    )


def skill_lookup_panel_metrics(ctx: dict[str, Any], board: dict[str, Any]) -> dict[str, Any]:
    """按因子名查 PostgreSQL 中的面板指标，写回 artifacts.platform_ref（不调 LLM）。"""
    from services.factor.dashboard_store import lookup_panel_metric
    from ai.crews._shared.metrics_trust import normalize_platform_ref

    art = (board or {}).get("artifacts") or {}
    ref = art.get("platform_ref") or (ctx or {}).get("platform_ref") or {}
    if not isinstance(ref, dict):
        ref = {}
    name = str(
        (ctx or {}).get("factor_name")
        or ref.get("factor_name")
        or ""
    ).strip()
    uni = str(
        (ctx or {}).get("universe_code")
        or ref.get("universe_code")
        or ref.get("universe")
        or "CSI300"
    ).strip() or "CSI300"
    per = str(
        (ctx or {}).get("period_code")
        or ref.get("period_code")
        or ref.get("period")
        or "3y"
    ).strip() or "3y"
    if uni and not re.match(r"^[A-Za-z0-9_]+$", uni):
        uni = "CSI300"
    if per and not re.match(r"^[0-9]+[my]$", per, re.I):
        per = "3y"
    filt_raw = (ctx or {}).get("filter_limit_up", ref.get("filter_limit_up"))
    filt = True if filt_raw is None else bool(filt_raw)
    if not name:
        return {
            "board_patch": {},
            "outputs": {"ok": False, "error": "缺少 factor_name"},
            "tokens_in": 0,
            "tokens_out": 0,
            "provider": "local",
        }
    looked = lookup_panel_metric(
        factor_name=name,
        library=str((ctx or {}).get("library") or ref.get("library") or "") or None,
        universe=uni,
        period=per,
        filter_limit_up=filt,
    )
    if not looked:
        return {
            "board_patch": {},
            "outputs": {"ok": False, "error": "面板缓存未命中"},
            "tokens_in": 0,
            "tokens_out": 0,
            "provider": "local",
        }
    merged = normalize_platform_ref({**ref, **looked})
    return {
        "board_patch": {
            "artifacts": {
                "platform_ref": merged,
                "panel_lookup": True,
            }
        },
        "outputs": {"ok": True, "platform_ref": merged},
        "tokens_in": 0,
        "tokens_out": 0,
        "provider": "local",
    }


def skill_summarize_post(ctx: dict[str, Any], board: dict[str, Any]) -> dict[str, Any]:
    """读帖 Summarizer：忠实压缩，不改正文、不编造未出现的回测数字。"""
    src = _source_from(board, ctx)
    title = src["title"]
    body = src["body"]
    code = src["code_snippet"]
    body_max, code_max = _read_limits()
    truncated = bool(board.get("truncated"))
    body, t1 = _maybe_truncate(body, body_max)
    code, t2 = _maybe_truncate(code, code_max)
    truncated = truncated or t1 or t2

    art = (board or {}).get("artifacts") or {}
    ref = art.get("platform_ref") or (ctx or {}).get("platform_ref")
    trust = _board_trust(board, ctx)
    has_ref = bool(ref)

    if not llm_configured():
        summary = _mock_summary_md(title=title, body=body, truncated=truncated)
        gate = summary_number_flags(summary, ref if isinstance(ref, dict) else None)
        return {
            "board_patch": {
                "summary_md": summary,
                "truncated": truncated,
                "flags": list(board.get("flags") or []) + gate,
                "artifacts": {"summary_source": "mock_local"},
            },
            "outputs": {"summary_md": summary, "flags": gate},
            "tokens_in": 0,
            "tokens_out": 0,
            "provider": "mock_local",
        }

    system = (
        "你是 SVQuant 读帖摘要员（Summarizer）。只根据给定标题/正文/代码与 platform_ref 归纳，"
        "输出 JSON：{\"summary_md\":\"...\"}。"
        "summary_md 用简短 Markdown，必须用二级标题：## 背景 / ## 方法或观点 / ## 结论 / ## 局限（无则省略）。"
        "硬性要求：全文控制在 250 字以内（约半屏侧栏可读完）；"
        "不要复述表格逐格数字、不要大段抄原文、不要逐条展开清单；"
        "每节最多 2～3 句或 3 条要点。表格只提炼结论倾向。"
        "禁止输出 HTML 标签；只用 Markdown。"
        f"{PLATFORM_KNOWLEDGE}"
        "有 platform_ref.metrics_display 时：结论里的 IC/年化/夏普等必须原样使用这些展示值，禁止改数、禁止补未给出的指标。"
        "无 platform_ref 时：不要把正文数字写成平台已验证结果。"
        "正文以「来自因子面板/因子检测/策略回测自动摘要」开头，或已有 platform_ref 时："
        "视为已挂平台来源；「局限」禁止写「未挂平台结果 / 指标未验证 / 未见平台引用」。"
        "不要建议分区、不要改原文、不要代写评论。中文。"
    )
    code_for_prompt = code if code_max <= 0 else code[:code_max]
    user_msg = json.dumps(
        {
            "title": title,
            "body": body,
            "code_snippet": code_for_prompt,
            "truncated": truncated,
            "has_platform_ref": has_ref,
            "max_chars": 250,
            **trust_prompt_block(trust),
            "note": "务必短摘要；超长视为失败风格。若 truncated=true，在局限一句带过。",
        },
        ensure_ascii=False,
    )
    result = chat_completions(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        max_tokens=450,
    )
    parsed = extract_json_object(result["content"])
    summary = str(parsed.get("summary_md") or "").strip()
    if not summary:
        raise LlmError("摘要为空")
    gate = summary_number_flags(summary, ref if isinstance(ref, dict) else None)
    prev_flags = list(board.get("flags") or [])
    return {
        "board_patch": {
            "summary_md": summary,
            "truncated": truncated,
            "flags": prev_flags + gate,
            "artifacts": {"summary_source": "llm"},
        },
        "outputs": {"summary_md": summary, "flags": gate},
        "tokens_in": result["tokens_in"],
        "tokens_out": result["tokens_out"],
        "provider": result.get("provider") or "openai_compatible",
        "model": result.get("model"),
    }


def skill_flag_read_risks(ctx: dict[str, Any], board: dict[str, Any]) -> dict[str, Any]:
    """读帖 RiskFlagger：只列阅读风险，不改摘要、不回流 revise。"""
    src = _source_from(board, ctx)
    title = src["title"]
    body = src["body"]
    summary = str((board or {}).get("summary_md") or (ctx or {}).get("summary_md") or "")
    plain = f"{title}\n{strip_html(body)}\n{summary}"
    art = (board or {}).get("artifacts") or {}
    has_ref = bool(art.get("platform_ref") or (ctx or {}).get("platform_ref"))
    if not has_ref:
        from ai.crews._shared.metrics_trust import body_claims_platform_share

        has_ref = body_claims_platform_share(body)
    prev_flags = list(board.get("flags") or [])

    flags: list[dict[str, Any]] = list(prev_flags)
    if PROMISE_RE.search(plain):
        flags.append(
            {
                "code": "promise_language",
                "severity": "warn",
                "message": "原文含疑似承诺收益 / 喊单表述，阅读时勿当投资建议",
            }
        )
    if QUANT_CLAIM_RE.search(plain) and not has_ref:
        flags.append(
            {
                "code": "unverified_metrics",
                "severity": "info",
                "message": "文中有回测/面板类指标用语，未见平台引用，请自行核实出处",
            }
        )

    # 有平台引用时去掉误报的「未见平台引用 / 指标未验证」类 flag
    if has_ref:
        drop_codes = {"unverified_metrics", "unverified_metric"}
        drop_substr = ("未见平台引用", "未挂平台", "指标未经验证", "指标未验证")
        flags = [
            f
            for f in flags
            if str(f.get("code") or "") not in drop_codes
            and not any(s in str(f.get("message") or "") for s in drop_substr)
        ]

    if not llm_configured():
        # 去重
        seen: set[str] = set()
        uniq: list[dict[str, Any]] = []
        for f in flags:
            m = str(f.get("message") or "")
            if m and m not in seen:
                uniq.append(f)
                seen.add(m)
        return {
            "board_patch": {"flags": uniq},
            "outputs": {"flags": uniq},
            "tokens_in": 0,
            "tokens_out": 0,
            "provider": "mock_local",
        }

    system = (
        "你是 SVQuant 读帖风险标注员（RiskFlagger）。只根据原文与摘要列出阅读风险，"
        "输出 JSON：{\"flags\":[{\"code\":\"...\",\"severity\":\"warn|info\",\"message\":\"...\"}]}。"
        "不要改摘要正文；不要滥报；无风险时 flags 为空数组。"
        f"{PLATFORM_KNOWLEDGE}"
        "有 platform_ref 时不要再报「指标未经验证」或「未见平台引用」；可提示面板缓存≠实盘。"
        "正文含「来自因子面板/检测/策略回测自动摘要」视同已有平台来源，勿再报未见平台引用。"
        "关注：承诺收益、无出处夸张、把回测当实盘等。中文短句。"
    )
    user_msg = json.dumps(
        {
            "title": title,
            "body": strip_html(body)[:8000],
            "summary_md": summary[:4000],
            "seed_flags": flags,
            "has_platform_ref": has_ref,
            **trust_prompt_block(_board_trust(board, ctx)),
        },
        ensure_ascii=False,
    )
    result = chat_completions(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
        max_tokens=600,
    )
    parsed = extract_json_object(result["content"])
    raw_flags = parsed.get("flags")
    out_flags: list[dict[str, Any]] = []
    if isinstance(raw_flags, list):
        for f in raw_flags:
            if not isinstance(f, dict):
                continue
            msg = str(f.get("message") or "").strip()
            if not msg:
                continue
            out_flags.append(
                {
                    "code": str(f.get("code") or "read_risk")[:64],
                    "severity": str(f.get("severity") or "warn")[:16],
                    "message": msg[:200],
                }
            )
    # 确定性种子 flags 与模型结果合并去重（按 message）
    seen = {str(f.get("message") or "") for f in out_flags}
    for f in flags:
        m = str(f.get("message") or "")
        if m and m not in seen:
            out_flags.append(f)
            seen.add(m)
    return {
        "board_patch": {"flags": out_flags},
        "outputs": {"flags": out_flags},
        "tokens_in": result["tokens_in"],
        "tokens_out": result["tokens_out"],
        "provider": result.get("provider") or "openai_compatible",
        "model": result.get("model"),
    }


SKILL_REGISTRY: dict[str, dict[str, Any]] = {
    "polish_title": {
        "id": "polish_title",
        "name": "润色标题",
        "description": "润色社区帖标题",
        "run": skill_polish_title,
        "cost_hint": 1,
    },
    "polish_body": {
        "id": "polish_body",
        "name": "润色正文",
        "description": "润色社区帖正文",
        "run": skill_polish_body,
        "cost_hint": 1,
    },
    "suggest_section": {
        "id": "suggest_section",
        "name": "建议分区",
        "description": "建议社区分区",
        "run": skill_suggest_section,
        "cost_hint": 1,
    },
    "audit_claims": {
        "id": "audit_claims",
        "name": "审计夸大表述",
        "description": "检查无出处数字与承诺收益",
        "run": skill_audit_claims,
        "cost_hint": 1,
    },
    "strip_unverifiable": {
        "id": "strip_unverifiable",
        "name": "删改不可核实句",
        "description": "按审计 flags 改写草稿",
        "run": skill_strip_unverifiable,
        "cost_hint": 1,
    },
    "summarize_post": {
        "id": "summarize_post",
        "name": "读帖摘要",
        "description": "将社区帖压缩为 TL;DR Markdown",
        "run": skill_summarize_post,
        "cost_hint": 1,
    },
    "flag_read_risks": {
        "id": "flag_read_risks",
        "name": "读帖风险标注",
        "description": "标出阅读风险点，不改摘要",
        "run": skill_flag_read_risks,
        "cost_hint": 1,
    },
    "lookup_panel_metrics": {
        "id": "lookup_panel_metrics",
        "name": "查面板指标",
        "description": "按因子×池×周期查询 PostgreSQL 因子面板指标",
        "run": skill_lookup_panel_metrics,
        "cost_hint": 0,
    },
}

SINGLE_SKILLS = ("polish_title", "polish_body", "summarize_post")


def get_skill(skill_id: str) -> dict[str, Any]:
    sk = SKILL_REGISTRY.get(skill_id)
    if not sk:
        raise ValueError(f"未知 skill: {skill_id}")
    return sk


def run_skill(
    skill_id: str,
    *,
    board: dict[str, Any],
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sk = get_skill(skill_id)
    fn: SkillFn = sk["run"]
    result = fn(dict(ctx or {}), board)
    result["skill"] = skill_id
    return result


def apply_board_patch(board: dict[str, Any], patch: dict[str, Any] | None) -> dict[str, Any]:
    if not patch:
        return board
    out = dict(board)
    if "draft" in patch and isinstance(patch["draft"], dict):
        draft = dict(out.get("draft") or {})
        draft.update(patch["draft"])
        out["draft"] = draft
    if "flags" in patch:
        out["flags"] = list(patch["flags"] or [])
    if "votes" in patch and isinstance(patch["votes"], list):
        votes = list(out.get("votes") or [])
        votes.extend(patch["votes"])
        out["votes"] = votes
    if "artifacts" in patch and isinstance(patch["artifacts"], dict):
        arts = dict(out.get("artifacts") or {})
        arts.update(patch["artifacts"])
        out["artifacts"] = arts
    for key in ("summary_md", "source_post_id", "truncated"):
        if key in patch:
            out[key] = patch[key]
    if "source" in patch and isinstance(patch["source"], dict):
        src = dict(out.get("source") or {})
        src.update(patch["source"])
        out["source"] = src
    return out
