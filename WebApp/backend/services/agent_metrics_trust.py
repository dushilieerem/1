# -*- coding: utf-8 -*-
"""发帖助手：平台指标可信度（verified / unverified / conflict / casual）。

只认 context.platform_ref；不猜用户盈亏、不联网、不再跑回测。
"""
from __future__ import annotations

import re
from typing import Any

# 像平台回测/面板指标的用语（个人「赚了 1000」不算）
QUANT_CLAIM_RE = re.compile(
    r"(?i)(\bIC\b|\bRank\s*IC\b|\bIR\b|\bSharpe\b|夏普|年化|最大回撤|回撤|"
    r"换手|分层|多空|RankIC|胜率|超额收益|信息比率)"
)
# 日常分享 / 个人盈亏（不触发「未验证回测」）
CASUAL_RE = re.compile(
    r"(天气|心情|日常|今天|这\s*\d+\s*天|最近\s*\d+\s*天|"
    r"赚了|亏了|亏掉|入账|零花钱|红包)"
)
PROMISE_RE = re.compile(r"(稳赚|必涨|保证收益|稳赚不赔|闭眼买|全仓梭哈|横扫全市场)")
NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def strip_html(text: str) -> str:
    plain = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", plain).strip()


def normalize_platform_ref(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    metrics_display = raw.get("metrics_display")
    metrics = raw.get("metrics")
    if not isinstance(metrics_display, dict):
        metrics_display = {}
    if not isinstance(metrics, dict):
        metrics = {}
    # 清洗展示值
    display: dict[str, str] = {}
    for k, v in metrics_display.items():
        if v is None:
            continue
        s = str(v).strip()
        if s:
            display[str(k)[:40]] = s[:64]
    nums: dict[str, float] = {}
    for k, v in metrics.items():
        try:
            if v is None:
                continue
            nums[str(k)[:40]] = float(v)
        except (TypeError, ValueError):
            continue
    if not display and not nums and not (
        str(raw.get("factor_name") or "").strip()
    ):
        return None
    source = str(raw.get("source") or "platform").strip()[:40] or "platform"
    label = str(raw.get("label") or source).strip()[:160] or source
    filter_raw = raw.get("filter_limit_up")
    filter_limit_up: bool | None
    if filter_raw is None:
        filter_limit_up = None
    else:
        filter_limit_up = bool(filter_raw)
    return {
        "source": source,
        "label": label,
        "metrics_display": display,
        "metrics": nums,
        "factor_name": (str(raw.get("factor_name") or "").strip() or None),
        "universe": (str(raw.get("universe") or "").strip() or None),
        "period": (str(raw.get("period") or "").strip() or None),
        "universe_code": (str(raw.get("universe_code") or "").strip() or None),
        "period_code": (str(raw.get("period_code") or "").strip() or None),
        "library": (str(raw.get("library") or "").strip() or None),
        "filter_limit_up": filter_limit_up,
    }


def _allowed_number_set(ref: dict[str, Any]) -> set[float]:
    """引用里允许出现的数值（含百分数/小数两种口径的粗匹配）。"""
    out: set[float] = set()
    for v in (ref.get("metrics") or {}).values():
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        out.add(round(x, 6))
        out.add(round(x * 100, 4))
        out.add(round(x / 100, 6))
    for s in (ref.get("metrics_display") or {}).values():
        for m in NUMBER_RE.findall(str(s)):
            try:
                x = float(m)
            except ValueError:
                continue
            out.add(round(x, 6))
            out.add(round(x / 100, 6))
            out.add(round(x * 100, 4))
    return out


def _number_near_allowed(n: float, allowed: set[float], tol: float = 0.02) -> bool:
    for a in allowed:
        if abs(a) < 1e-12 and abs(n) < 1e-12:
            return True
        scale = max(abs(a), abs(n), 1e-6)
        if abs(a - n) / scale <= tol or abs(a - n) <= 0.0005:
            return True
    return False


def looks_like_quant_claim(text: str) -> bool:
    return bool(QUANT_CLAIM_RE.search(text or ""))


def looks_casual_share(text: str) -> bool:
    t = text or ""
    if looks_like_quant_claim(t):
        return False
    return bool(CASUAL_RE.search(t))


def evaluate_metrics_trust(
    *,
    title: str,
    body: str,
    platform_ref: dict[str, Any] | None,
) -> dict[str, Any]:
    """返回 data_trust 摘要 + 确定性 flags（供 Critic 合并）。"""
    plain = f"{title or ''} {strip_html(body or '')}"
    flags: list[dict[str, Any]] = []

    if PROMISE_RE.search(plain):
        flags.append(
            {
                "code": "promise_return",
                "severity": "block",
                "message": "疑似承诺收益 / 喊单表述",
            }
        )

    ref = normalize_platform_ref(platform_ref) if platform_ref else None

    if ref:
        # 面板/检测/策略分享带来的引用即真源。
        # 不再扫正文数字做 conflict：分享稿与展示口径（%、小数、日期）极易误伤，
        # 导致「刚从报告点分享就被 Critic 拦住」。有引用一律 verified。
        return {
            "status": "verified",
            "summary": "已挂平台结果，润色以引用指标为准。",
            "platform_ref": ref,
            "flags": flags,  # 仅保留 promise 等，不含 metrics_conflict
        }

    # 无平台引用
    if looks_like_quant_claim(plain) and NUMBER_RE.search(plain):
        flags.append(
            {
                "code": "unverified_metric",
                "severity": "warn",
                "message": "文中含 IC/年化/夏普等量化指标，但未挂平台面板或报告结果，指标未经验证",
            }
        )
        return {
            "status": "unverified",
            "summary": "未挂平台结果；量化数字不背书，请勿写成已回测结论。",
            "platform_ref": None,
            "flags": flags,
        }

    if looks_casual_share(plain) or not looks_like_quant_claim(plain):
        return {
            "status": "casual",
            "summary": "日常分享或个人叙述；不核对盈亏真假，不按回测指标审计。",
            "platform_ref": None,
            "flags": flags,
        }

    return {
        "status": "unverified",
        "summary": "未挂平台结果。",
        "platform_ref": None,
        "flags": flags,
    }


def trust_prompt_block(trust: dict[str, Any] | None) -> dict[str, Any]:
    """塞进 LLM user JSON 的精简块。"""
    if not trust:
        return {"data_trust_status": "unknown"}
    ref = trust.get("platform_ref")
    return {
        "data_trust_status": trust.get("status"),
        "data_trust_summary": trust.get("summary"),
        "platform_ref": {
            "source": (ref or {}).get("source"),
            "label": (ref or {}).get("label"),
            "factor_name": (ref or {}).get("factor_name"),
            "universe": (ref or {}).get("universe"),
            "period": (ref or {}).get("period"),
            "metrics_display": (ref or {}).get("metrics_display") or {},
        }
        if ref
        else None,
    }


# 读帖 / 发帖共用：平台边界（非训练集，塞进 system）
PLATFORM_KNOWLEDGE = (
    "SVQuant 平台边界：本机不存行情 bars；因子面板 IC/年化/夏普等来自 YGQuant RE 聚合缓存；"
    "日线/指数属 NBQuant 口径，禁止用外源行情或常识数字验证本平台面板；"
    "有 platform_ref 时量化数字只能复述 metrics_display / metrics，禁止改数或补未给出的指标；"
    "无 platform_ref 时不得把正文数字写成「平台已验证」。"
)


def summary_number_flags(summary: str, platform_ref: dict[str, Any] | None) -> list[dict[str, Any]]:
    """摘要出稿后闸门：带平台引用时，摘要中的小数/% 须落在引用允许集合。"""
    ref = normalize_platform_ref(platform_ref) if platform_ref else None
    if not ref or not (ref.get("metrics_display") or ref.get("metrics")):
        return []
    allowed = _allowed_number_set(ref)
    if not allowed:
        return []
    text = summary or ""
    # 跳过纯整数年份/小节；只盯带小数或百分号的量化数
    suspects: list[str] = []
    for m in re.finditer(r"[-+]?\d+\.\d+%?|[-+]?\d+%", text):
        token = m.group(0)
        try:
            n = float(token.replace("%", ""))
        except ValueError:
            continue
        if not _number_near_allowed(n, allowed):
            suspects.append(token)
    if not suspects:
        return []
    return [
        {
            "code": "summary_metrics_drift",
            "severity": "warn",
            "message": (
                "摘要中出现与平台引用不一致的数字："
                + "、".join(suspects[:6])
                + "；请以 platform_ref.metrics_display 为准"
            ),
        }
    ]
