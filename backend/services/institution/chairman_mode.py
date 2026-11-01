# -*- coding: utf-8 -*-
"""AI Chairman 模式（FR-APR 系列）：预检查、模拟批准、人工移交。

边界：AI 只做预检查与建议，**不写审批、不改状态、不解除风控阻断**。
任何“模拟批准”结果都带 binding=False，最终仍由真人 Chairman 表决。
"""
from __future__ import annotations

from typing import Any


def _check(key: str, label: str, ok: bool, severity: str, detail: str) -> dict[str, Any]:
    return {"key": key, "label": label, "ok": bool(ok), "severity": severity, "detail": detail}


def evaluate(
    *,
    proposal_status: str,
    snapshot: dict[str, Any],
    approvals: dict[str, dict[str, Any]],
    risk_checks: list[dict[str, Any]] | None,
    evidence_count: int,
    ai_available: bool,
    proposer_is_reviewer: bool = False,
) -> dict[str, Any]:
    """确定性预检查。返回 checks + 建议，不做任何持久化。"""
    checks: list[dict[str, Any]] = []

    checks.append(
        _check(
            "status",
            "议案已进入 Chairman 审议",
            proposal_status == "chairman_review",
            "block",
            f"当前状态：{proposal_status}",
        )
    )
    partner = approvals.get("partner") or {}
    checks.append(
        _check(
            "partner",
            "合伙人已批准",
            partner.get("decision") in {"approve", "conditional"},
            "block",
            f"合伙人：{partner.get('decision') or '缺失'}",
        )
    )
    chairman = approvals.get("chairman") or {}
    checks.append(
        _check(
            "chairman_pending",
            "Chairman 尚未表决",
            not chairman.get("decision"),
            "warn",
            f"Chairman：{chairman.get('decision') or '待表决'}",
        )
    )
    risk = approvals.get("risk_precheck") or {}
    checks.append(
        _check(
            "risk_precheck",
            "执行前风控复核通过",
            risk.get("decision") == "pass",
            "block",
            f"风控复核：{risk.get('decision') or '未执行'}",
        )
    )
    if risk_checks is not None:
        blocked = [c for c in risk_checks if str(c.get("status")) == "block"]
        checks.append(
            _check(
                "risk_items",
                "硬性风控项全部通过",
                not blocked,
                "block",
                "；".join(str(c.get("label")) for c in blocked) if blocked else "全部通过",
            )
        )
    checks.append(
        _check("evidence", "研究证据 ≥1 条", evidence_count > 0, "block", f"证据 {evidence_count} 条")
    )
    qty = snapshot.get("qty")
    price = snapshot.get("price") or snapshot.get("price_high")
    checks.append(
        _check(
            "order",
            "委托数量与价格已填写",
            bool(qty) and bool(price),
            "block",
            f"数量 {qty or '缺失'} / 价格 {price or '缺失'}",
        )
    )
    low, high = snapshot.get("price_low"), snapshot.get("price_high")
    inverted = low is not None and high is not None and float(low) > float(high)
    checks.append(
        _check("price_range", "价格区间合法", not inverted, "block", f"{low} - {high}")
    )
    checks.append(
        _check(
            "currency",
            "基准币种为 CNY（多币种敞口未支持）",
            str(snapshot.get("currency") or "CNY") == "CNY",
            "warn",
            f"币种：{snapshot.get('currency') or 'CNY'}",
        )
    )
    checks.append(
        _check(
            "proposer",
            "提案人与审批人分离",
            not proposer_is_reviewer,
            "block",
            "提案人不得审批自己的议案" if proposer_is_reviewer else "已分离",
        )
    )
    checks.append(
        _check(
            "ai",
            "AI 辅助可用",
            ai_available,
            "warn",
            "AI 不可用不影响真人审议" if not ai_available else "可用",
        )
    )

    blocks = [c for c in checks if c["severity"] == "block" and not c["ok"]]
    warns = [c for c in checks if c["severity"] == "warn" and not c["ok"]]
    ready = not blocks
    if not ready:
        recommendation = "human_required"
    elif warns:
        recommendation = "conditional_candidate"
    else:
        recommendation = "approve_candidate"

    return {
        "checks": checks,
        "ready": ready,
        "recommendation": recommendation,
        "blocking": [c["key"] for c in blocks],
        "warnings": [c["key"] for c in warns],
        "binding": False,
        "requires_human": True,
        "summary": (
            "预检查全部通过，可提交真人 Chairman 表决"
            if ready and not warns
            else ("预检查通过但存在提醒项，建议 Chairman 带条件审议" if ready else "存在阻断项，不能进入表决")
        ),
    }


__all__ = ["evaluate"]
