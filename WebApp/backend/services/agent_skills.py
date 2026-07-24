# -*- coding: utf-8 -*-
"""Skill 注册表：可被多 Agent 复用的能力原子。"""
from __future__ import annotations

import json
import re
from html import unescape
from typing import Any, Callable

from services.llm_client import LlmError, chat_completions, llm_configured

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
        "你是 SVQuant 量化社区的 Writer。润色帖子标题。"
        "中文、简洁、不超过 120 字、不夸张营销、不加整句引号。"
        "只返回 JSON：{\"title\":\"...\"}"
    )
    user_msg = json.dumps(
        {
            "section": section,
            "title": title,
            "body_excerpt": strip_html(body)[:500],
            "flags": (board or {}).get("flags") or [],
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
    if not llm_configured():
        out = _mock_polish_body(body, title)
        return {
            "board_patch": {"draft": {"body": out}},
            "outputs": {"body": out},
            "tokens_in": 0,
            "tokens_out": 0,
            "provider": "mock_local",
        }
    system = (
        "你是 SVQuant 量化社区的 Writer。润色正文。"
        "保留事实与数字；使用简单 HTML（多个 <p> 分段，可用 strong/ul/li/code）；"
        "每个要点或自然段单独一个 <p>，禁止整篇挤进一个段落；不要编造回测结果。"
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
        "board_patch": {"draft": {"body": new_body}},
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
        text = (title + " " + strip_html(body)).lower()
        if any(k in text for k in ("怎么", "报错", "咋办", "如何", "？", "?")):
            sug = "qa"
        elif any(k in text for k in ("换手", "ic", "因子", "分层")):
            sug = "factor"
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

    system = (
        "你是 SVQuant 社区 Router。根据标题正文代码建议分区。"
        "可选：strategy / factor / qa / hotspot / official（official 仅当内容像官方公告）。"
        "只返回 JSON：{\"section\":\"...\",\"reason\":\"...\"}"
    )
    user_msg = json.dumps(
        {
            "current_section": cur,
            "title": title,
            "body_excerpt": strip_html(body)[:800],
            "has_code": bool(code.strip()),
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
    plain = strip_html(body)

    if not llm_configured():
        flags: list[dict[str, Any]] = []
        # 启发式：百分号/年化/夏普等且无「未」「大约」「好像」弱化词时告警
        suspicious = re.findall(
            r"(年化|超额|夏普|回撤|振幅|IC)[^。；\n]{0,20}(\d+(?:\.\d+)?\s*%?)",
            plain,
        )
        for name, num in suspicious[:5]:
            flags.append(
                {
                    "code": "unverified_metric",
                    "severity": "warn",
                    "message": f"疑似无出处量化表述：{name}≈{num}",
                }
            )
        if re.search(r"(稳赚|必涨|保证收益|稳赚不赔)", plain + title):
            flags.append(
                {
                    "code": "promise_return",
                    "severity": "block",
                    "message": "疑似承诺收益表述",
                }
            )
        decision = "approve"
        if any(f.get("severity") == "block" for f in flags):
            decision = "block"
        elif flags:
            decision = "revise"
        return {
            "board_patch": {
                "flags": flags,
                "artifacts": {"audit_report": {"flags": flags, "decision": decision}},
                "votes": [
                    {
                        "agent": "critic",
                        "decision": decision,
                        "reason": "本地启发式审计",
                    }
                ],
            },
            "outputs": {"audit_decision": decision, "flags": flags},
            "tokens_in": 0,
            "tokens_out": 0,
            "provider": "mock_local",
        }

    system = (
        "你是 SVQuant Critic。检查帖子是否夸大、编造无出处数字、承诺收益。"
        "不要改写正文。返回 JSON："
        '{"decision":"approve|revise|block","flags":[{"code":"...","severity":"info|warn|block","message":"..."}]}'
        "decision=revise 表示需 Writer 删改可疑句；block 表示严重违规。"
        "若原文已标明「没数据/纯感受/未统计」则不要对模糊感受乱打 flag。"
    )
    user_msg = json.dumps(
        {"title": title, "body": body[:6000]},
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
    flags = []
    for f in raw_flags[:12]:
        if not isinstance(f, dict):
            continue
        flags.append(
            {
                "code": str(f.get("code") or "issue")[:64],
                "severity": str(f.get("severity") or "warn")[:16],
                "message": str(f.get("message") or "")[:300],
            }
        )
    if flags and decision == "approve":
        decision = "revise"
    return {
        "board_patch": {
            "flags": flags,
            "artifacts": {"audit_report": {"flags": flags, "decision": decision}},
            "votes": [
                {
                    "agent": "critic",
                    "decision": decision,
                    "reason": f"审计 {len(flags)} 条",
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
        "不要新增新的精确数字；可改为「未统计/待补充/纯感受」。"
        "保持简单 HTML，正文用多个 <p> 分段，不要整篇一个段落。"
        "只返回 JSON：{\"title\":\"...\",\"body\":\"...\"}"
    )
    user_msg = json.dumps(
        {"title": title, "body": body[:6000], "flags": flags},
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
}

SINGLE_SKILLS = ("polish_title", "polish_body")


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
    return out
