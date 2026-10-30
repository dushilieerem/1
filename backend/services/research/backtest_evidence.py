"""回测解读的确定性证据、诊断与建议实验（无模型依赖）。

从 ResearchEngine `app/api/ai_interpretation.py` 迁入，逻辑与阈值保持不变；
差异只在输出形状：这里返回普通 dict，由路由层/HTTP 边界序列化。
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from typing import Any

EVIDENCE_SCHEMA_VERSION = "1.0"
DIAGNOSTIC_CATALOG_VERSION = "v1"
PROMPT_VERSION = "v1"
DISCLAIMER = "本结果仅用于量化研究，不构成投资建议或收益承诺。"

MAX_CURVE_POINTS = 10_000
MIN_CURVE_POINTS = 60

_REF_TABLE = {
    "SAMPLE_TOO_SHORT": ("样本期偏短", "有效净值点不足一年，结论可能受单一市场阶段影响。", "warning", "low", "EXPAND_SAMPLE"),
    "NO_OUT_OF_SAMPLE": ("缺少样本外验证", "当前结果没有样本外或 Walk-forward 验证，不能据此判断泛化能力。", "critical", "low", "ADD_OUT_OF_SAMPLE"),
    "COST_ASSUMPTION_UNKNOWN": ("成本假设不完整", "佣金、印花税或滑点至少有一项未知，净收益可靠性不足。", "warning", "medium", "COMPLETE_COSTS"),
    "ZERO_COST_ASSUMPTION": ("存在零成本假设", "策略存在换手但佣金或滑点为零，表现可能被高估。", "warning", "medium", "COST_STRESS_TEST"),
    "HIGH_TURNOVER": ("换手较高", "平均单边换手率不低于 10%，策略可能对成本和执行敏感。", "warning", "medium", "SLOW_REBALANCE"),
    "DEEP_DRAWDOWN": ("最大回撤较深", "最大回撤不低于 20%，应先评估损失阶段和风险约束。", "warning", "high", "DRAWDOWN_REVIEW"),
    "WEAK_FACTOR_SIGNAL": ("因子信号较弱", "因子绝对 IC 小于 0.02，线性截面预测力偏弱。", "warning", "medium", "CHECK_FACTOR_SIGNAL"),
}

_EXPERIMENT_TABLE = {
    "EXPAND_SAMPLE": ("延长样本并分阶段验证", "回测区间", ["稳健性"], ["可能暴露策略在其他市场阶段的失效"], "固定当前参数，扩展至多个完整市场阶段并分别报告。", ["新增阶段不出现显著劣化且结论一致"]),
    "ADD_OUT_OF_SAMPLE": ("补充样本外验证", "验证方案", ["稳健性"], ["样本内表现可能下降"], "固定现有参数，保留独立留出集或执行 Walk-forward。", ["样本外结果与样本内方向一致，并记录回撤和成本差异"]),
    "COMPLETE_COSTS": ("补齐交易成本口径", "成本参数", ["成本可信度"], ["净收益可能下降"], "明确佣金、印花税和滑点后用原策略重跑。", ["所有核心成本项均有明确值"]),
    "COST_STRESS_TEST": ("执行成本压力测试", "成本档位", ["成本敏感性"], ["净收益可能下降"], "仅改变成本假设，比较基线与悲观档净收益、回撤和换手。", ["结论在两档成本下均被完整记录"]),
    "SLOW_REBALANCE": ("测试较低调仓频率", "调仓周期", ["成本", "换手"], ["可能错失信号并降低收益"], "一次只放宽调仓周期，比较净收益、回撤与换手。", ["换手下降且风险收益权衡可接受"]),
    "DRAWDOWN_REVIEW": ("复核回撤阶段", "风险约束", ["风险"], ["可能限制上涨空间"], "先对照回撤阶段与基准；再单独测试一个风险约束。", ["最大回撤改善且不以单一时期收益为代价"]),
    "CHECK_FACTOR_SIGNAL": ("检查因子方向与预处理", "因子处理", ["因子有效性"], ["处理可能降低可解释性"], "分别测试方向、滞后和去极值/中性化，保持其他条件不变。", ["独立对照中的 IC 方向和分层结果一致"]),
}

_REF_PATHS = {
    "SAMPLE_TOO_SHORT": ["coverage.equity_points"],
    "NO_OUT_OF_SAMPLE": ["assumption.validation_scheme"],
    "COST_ASSUMPTION_UNKNOWN": ["assumption.commission_rate", "assumption.stamp_tax", "assumption.slippage_rate"],
    "ZERO_COST_ASSUMPTION": ["execution.turnover", "assumption.commission_rate", "assumption.slippage_rate"],
    "HIGH_TURNOVER": ["execution.turnover"],
    "DEEP_DRAWDOWN": ["risk.max_drawdown"],
    "WEAK_FACTOR_SIGNAL": ["factor.ic_mean"],
}


def finite(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def valid_points(value: object, *, required: bool = True) -> list[tuple[date, float]] | None:
    """解析净值曲线：日期递增、值有限且为正。"""
    if value is None:
        return [] if not required else None
    if not isinstance(value, list):
        return None
    points: list[tuple[date, float]] = []
    for point in value:
        if not isinstance(point, dict):
            return None
        try:
            parsed_date = date.fromisoformat(str(point["date"]))
            parsed_value = float(point["value"])
        except (KeyError, TypeError, ValueError):
            return None
        if not math.isfinite(parsed_value) or parsed_value <= 0:
            return None
        if points and parsed_date <= points[-1][0]:
            return None
        points.append((parsed_date, parsed_value))
    return points


def max_drawdown(points: list[tuple[date, float]]) -> float:
    """单次扫描计算最大回撤，10,000 点不退化为二次复杂度。"""
    peak = points[0][1]
    maximum = 0.0
    for _, value in points:
        peak = max(peak, value)
        maximum = min(maximum, value / peak - 1)
    return maximum


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def request_hash(payload: dict[str, Any]) -> str:
    body = {k: v for k, v in payload.items() if k != "idempotency_key"}
    return hashlib.sha256(canonical(body).encode()).hexdigest()


def _item(
    evidence_id: str,
    category: str,
    label: str,
    value: object,
    status: str,
    paths: list[str],
    unit: str | None = None,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "category": category,
        "label": label,
        "value": value,
        "unit": unit,
        "status": status,
        "source_paths": paths,
        "limitations": [],
    }


def build_evidence(
    *,
    backtest_type: str,
    result: dict[str, Any],
    run_context: dict[str, Any],
    points: list[tuple[date, float]],
) -> tuple[dict[str, Any], list[str]]:
    """返回 (证据包, 诊断码)。阈值与 ResearchEngine 一致。"""
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    fingerprint = "sha256:" + hashlib.sha256(canonical(result).encode()).hexdigest()
    first, last = points[0], points[-1]
    total_return = last[1] / first[1] - 1 if first[1] else None
    drawdown = max_drawdown(points)
    items = [
        _item("identity.result_fingerprint", "identity", "结果指纹", fingerprint, "observed", ["result"]),
        _item("coverage.equity_points", "coverage", "有效净值点", len(points), "derived", ["equity_curve"]),
        _item("performance.total_return", "performance", "区间总收益", total_return, "derived", ["equity_curve"], "ratio"),
        _item("risk.max_drawdown", "risk", "最大回撤", drawdown, "derived", ["equity_curve"], "ratio"),
    ]
    for name, label, category in (
        ("annual_return", "年化收益", "performance"),
        ("sharpe", "夏普比率", "risk"),
        ("turnover", "平均单边换手", "execution"),
    ):
        value = finite(metrics.get(name))
        items.append(
            _item(
                f"{category}.{name}",
                category,
                label,
                value,
                "observed" if value is not None else "unknown",
                [f"metrics.{name}"],
                "ratio" if name != "sharpe" else None,
            )
        )

    benchmark = valid_points(result.get("benchmark_curve"), required=False)
    benchmark_return = benchmark[-1][1] / benchmark[0][1] - 1 if benchmark and benchmark[0][1] else None
    items.append(
        _item(
            "performance.benchmark_return",
            "performance",
            "同期基准收益",
            benchmark_return,
            "derived" if benchmark_return is not None else "unknown",
            ["benchmark_curve"],
            "ratio",
        )
    )

    validation = run_context.get("validation_scheme", "unknown")
    items.append(
        _item(
            "assumption.validation_scheme",
            "assumption",
            "验证方案",
            str(validation),
            "observed" if validation != "unknown" else "unknown",
            ["run_context.validation_scheme"],
        )
    )
    costs = [finite(run_context.get(name)) for name in ("commission_rate", "stamp_tax", "slippage_rate")]
    for name, value in zip(("commission_rate", "stamp_tax", "slippage_rate"), costs):
        items.append(
            _item(
                f"assumption.{name}",
                "assumption",
                name,
                value,
                "observed" if value is not None else "unknown",
                [f"run_context.{name}"],
                "ratio",
            )
        )

    diagnostic_codes: list[str] = []
    if len(points) < 252:
        diagnostic_codes.append("SAMPLE_TOO_SHORT")
    if validation in (None, "unknown", "in_sample"):
        diagnostic_codes.append("NO_OUT_OF_SAMPLE")
    if any(value is None for value in costs):
        diagnostic_codes.append("COST_ASSUMPTION_UNKNOWN")
    turnover = finite(metrics.get("turnover"))
    if turnover is not None and turnover >= 0.10:
        diagnostic_codes.append("HIGH_TURNOVER")
    if turnover and any(value == 0 for value in costs if value is not None):
        diagnostic_codes.append("ZERO_COST_ASSUMPTION")
    if drawdown <= -0.20:
        diagnostic_codes.append("DEEP_DRAWDOWN")
    if backtest_type == "factor":
        factor = result.get("factor_analysis") if isinstance(result.get("factor_analysis"), dict) else {}
        ic = finite(factor.get("ic_mean"))
        items.append(
            _item(
                "factor.ic_mean",
                "factor",
                "平均 IC",
                ic,
                "observed" if ic is not None else "unknown",
                ["factor_analysis.ic_mean"],
            )
        )
        if ic is not None and abs(ic) < 0.02:
            diagnostic_codes.append("WEAK_FACTOR_SIGNAL")

    coverage = "complete" if not any(item["status"] == "unknown" for item in items) else "partial"
    evidence = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "result_fingerprint": fingerprint,
        "coverage": coverage,
        "warnings": list(diagnostic_codes),
        "items": items,
    }
    return evidence, diagnostic_codes


def findings(codes: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, code in enumerate(codes, 1):
        title, explanation, severity, confidence, _experiment = _REF_TABLE[code]
        out.append(
            {
                "finding_id": f"finding_{index}",
                "candidate_id": code,
                "severity": severity,
                "title": title,
                "explanation": explanation,
                "evidence_refs": list(_REF_PATHS[code]),
                "confidence": confidence,
                "limitations": [],
            }
        )
    return out


def experiments(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for priority, finding in enumerate(items[:5], 1):
        experiment_id = _REF_TABLE[finding["candidate_id"]][4]
        title, variable, direction, tradeoffs, method, criteria = _EXPERIMENT_TABLE[experiment_id]
        out.append(
            {
                "experiment_id": experiment_id,
                "priority": priority,
                "hypothesis": title,
                "primary_variable": variable,
                "expected_direction": list(direction),
                "tradeoffs": list(tradeoffs),
                "validation_method": method,
                "pass_criteria": list(criteria),
                "evidence_refs": list(finding["evidence_refs"]),
                "manual_only": True,
            }
        )
    return out


def summary(codes: list[str]) -> str:
    if not codes:
        return "已生成基础绩效与风险证据；建议结合样本外验证继续研究。"
    if "NO_OUT_OF_SAMPLE" in codes:
        return "当前结果缺少样本外验证，优先验证稳健性后再讨论收益优化。"
    return "已发现需要优先验证的研究风险，请按建议逐项进行人工实验。"


def order_findings(items: list[dict[str, Any]], ids: list[str]) -> list[dict[str, Any]]:
    by_id = {item["candidate_id"]: item for item in items}
    return [by_id[i] for i in ids]


__all__ = [
    "DIAGNOSTIC_CATALOG_VERSION",
    "DISCLAIMER",
    "EVIDENCE_SCHEMA_VERSION",
    "MAX_CURVE_POINTS",
    "MIN_CURVE_POINTS",
    "PROMPT_VERSION",
    "build_evidence",
    "canonical",
    "experiments",
    "findings",
    "finite",
    "max_drawdown",
    "order_findings",
    "request_hash",
    "summary",
    "valid_points",
]
