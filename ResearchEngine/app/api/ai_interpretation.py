"""受控的 AI 回测解读服务。

先从用户提交的回测快照构建可复算证据和诊断；模型（若已配置）只能为
既有候选排序。供应商不可用时始终返回确定性报告，不影响原回测 API。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from datetime import date
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException

from app.api import llm_provider
from app.schemas.backtest import (
    BacktestEvidenceItem,
    BacktestEvidencePackage,
    BacktestExperiment,
    BacktestFinding,
    BacktestInterpretation,
    BacktestInterpretationMeta,
    BacktestInterpretationRequest,
    BacktestInterpretationResponse,
)


EVIDENCE_SCHEMA_VERSION = "1.0"
DIAGNOSTIC_CATALOG_VERSION = "v1"
PROMPT_VERSION = "v1"
DISCLAIMER = "本结果仅用于量化研究，不构成投资建议或收益承诺。"
_IDEMPOTENCY: dict[str, tuple[str, BacktestInterpretationResponse]] = {}
_IDEMPOTENCY_LOCK = Lock()

_FINDING_ORDER_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "svquant_backtest_finding_order",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["finding_ids"],
            "properties": {
                "finding_ids": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}

_DIAGNOSTICS = {
    "SAMPLE_TOO_SHORT": ("样本期偏短", "有效净值点不足一年，结论可能受单一市场阶段影响。", "warning", "low", "EXPAND_SAMPLE"),
    "NO_OUT_OF_SAMPLE": ("缺少样本外验证", "当前结果没有样本外或 Walk-forward 验证，不能据此判断泛化能力。", "critical", "low", "ADD_OUT_OF_SAMPLE"),
    "COST_ASSUMPTION_UNKNOWN": ("成本假设不完整", "佣金、印花税或滑点至少有一项未知，净收益可靠性不足。", "warning", "medium", "COMPLETE_COSTS"),
    "ZERO_COST_ASSUMPTION": ("存在零成本假设", "策略存在换手但佣金或滑点为零，表现可能被高估。", "warning", "medium", "COST_STRESS_TEST"),
    "HIGH_TURNOVER": ("换手较高", "平均单边换手率不低于 10%，策略可能对成本和执行敏感。", "warning", "medium", "SLOW_REBALANCE"),
    "DEEP_DRAWDOWN": ("最大回撤较深", "最大回撤不低于 20%，应先评估损失阶段和风险约束。", "warning", "high", "DRAWDOWN_REVIEW"),
    "WEAK_FACTOR_SIGNAL": ("因子信号较弱", "因子绝对 IC 小于 0.02，线性截面预测力偏弱。", "warning", "medium", "CHECK_FACTOR_SIGNAL"),
}
_EXPERIMENTS = {
    "EXPAND_SAMPLE": ("延长样本并分阶段验证", "回测区间", ["稳健性"], ["可能暴露策略在其他市场阶段的失效"], "固定当前参数，扩展至多个完整市场阶段并分别报告。", ["新增阶段不出现显著劣化且结论一致"]),
    "ADD_OUT_OF_SAMPLE": ("补充样本外验证", "验证方案", ["稳健性"], ["样本内表现可能下降"], "固定现有参数，保留独立留出集或执行 Walk-forward。", ["样本外结果与样本内方向一致，并记录回撤和成本差异"]),
    "COMPLETE_COSTS": ("补齐交易成本口径", "成本参数", ["成本可信度"], ["净收益可能下降"], "明确佣金、印花税和滑点后用原策略重跑。", ["所有核心成本项均有明确值"]),
    "COST_STRESS_TEST": ("执行成本压力测试", "成本档位", ["成本敏感性"], ["净收益可能下降"], "仅改变成本假设，比较基线与悲观档净收益、回撤和换手。", ["结论在两档成本下均被完整记录"]),
    "SLOW_REBALANCE": ("测试较低调仓频率", "调仓周期", ["成本", "换手"], ["可能错失信号并降低收益"], "一次只放宽调仓周期，比较净收益、回撤与换手。", ["换手下降且风险收益权衡可接受"]),
    "DRAWDOWN_REVIEW": ("复核回撤阶段", "风险约束", ["风险"], ["可能限制上涨空间"], "先对照回撤阶段与基准；再单独测试一个风险约束。", ["最大回撤改善且不以单一时期收益为代价"]),
    "CHECK_FACTOR_SIGNAL": ("检查因子方向与预处理", "因子处理", ["因子有效性"], ["处理可能降低可解释性"], "分别测试方向、滞后和去极值/中性化，保持其他条件不变。", ["独立对照中的 IC 方向和分层结果一致"]),
}


def interpret_backtest(req: BacktestInterpretationRequest) -> BacktestInterpretationResponse:
    """返回可引用的证据与解读；幂等键只在当前进程内保存。"""
    if os.environ.get("AI_BACKTEST_INTERPRETATION_ENABLED", "true").lower() == "false":
        raise HTTPException(503, "AI 回测解读服务已关闭")
    request_hash = _request_hash(req)
    key = str(req.idempotency_key)
    with _IDEMPOTENCY_LOCK:
        existing = _IDEMPOTENCY.get(key)
        if existing is not None:
            if existing[0] != request_hash:
                raise HTTPException(409, "idempotency_key 已用于不同请求")
            return existing[1]

    started = time.perf_counter()
    response = _build_response(req, started)
    with _IDEMPOTENCY_LOCK:
        existing = _IDEMPOTENCY.setdefault(key, (request_hash, response))
    if existing[0] != request_hash:
        raise HTTPException(409, "idempotency_key 已用于不同请求")
    return existing[1]


def _build_response(req: BacktestInterpretationRequest, started: float) -> BacktestInterpretationResponse:
    result = req.result
    if result.get("error"):
        return _terminal_response("rejected", "提交的回测结果包含业务错误，无法进行解读。", started)
    points = _valid_points(result.get("equity_curve"))
    if points is None:
        raise HTTPException(422, "equity_curve 必须是日期递增、值为有限数值的序列")
    if len(points) > 10_000:
        raise HTTPException(400, "单条净值曲线最多 10,000 点")
    if len(points) < 60:
        return _terminal_response("insufficient", "有效净值点少于 60，建议补齐数据后再解读。", started)

    evidence, diagnostic_codes = _build_evidence(req, points)
    findings = _findings(diagnostic_codes)
    experiments = _experiments(findings)
    interpretation = BacktestInterpretation(
        summary=_summary(diagnostic_codes), findings=findings, experiments=experiments,
    )
    mode = "deterministic_fallback"
    model_alias = "not_configured"
    # 模型只参与排序；请求中只包含候选 ID 与证据 ID，数值永不发送。
    if _provider_configured():
        model_alias = os.environ.get("AI_BACKTEST_INTERPRETATION_MODEL_ALIAS", "ark-code-latest")
        try:
            ordered = _provider_order(req, findings, model_alias)
            interpretation.findings = _order_findings(findings, ordered)
            interpretation.experiments = _experiments(interpretation.findings)
            mode = "llm_grounded"
        except llm_provider.ProviderUnavailable:
            pass
    return BacktestInterpretationResponse(
        interpretation_id=f"bi_{uuid4().hex}", status="ready", mode=mode,
        evidence=evidence, interpretation=interpretation, disclaimer=DISCLAIMER,
        meta=_meta(model_alias, started),
    )


def _terminal_response(status: str, summary: str, started: float) -> BacktestInterpretationResponse:
    evidence = BacktestEvidencePackage(schema_version=EVIDENCE_SCHEMA_VERSION, result_fingerprint="sha256:unavailable", coverage="insufficient", warnings=[status.upper()], items=[])
    interpretation = None if status == "rejected" else BacktestInterpretation(summary=summary)
    return BacktestInterpretationResponse(interpretation_id=f"bi_{uuid4().hex}", status=status, mode="not_applicable", evidence=evidence, interpretation=interpretation, disclaimer=DISCLAIMER, meta=_meta("not_called", started))


def _build_evidence(req: BacktestInterpretationRequest, points: list[tuple[date, float]]) -> tuple[BacktestEvidencePackage, list[str]]:
    result = req.result
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    fingerprint = "sha256:" + hashlib.sha256(_canonical(result).encode()).hexdigest()
    first, last = points[0], points[-1]
    total_return = last[1] / first[1] - 1 if first[1] else None
    drawdown = _max_drawdown(points)
    items = [
        _item("identity.result_fingerprint", "identity", "结果指纹", fingerprint, "observed", ["result"]),
        _item("coverage.equity_points", "coverage", "有效净值点", len(points), "derived", ["equity_curve"]),
        _item("performance.total_return", "performance", "区间总收益", total_return, "derived", ["equity_curve"], "ratio"),
        _item("risk.max_drawdown", "risk", "最大回撤", drawdown, "derived", ["equity_curve"], "ratio"),
    ]
    for name, label, category in (("annual_return", "年化收益", "performance"), ("sharpe", "夏普比率", "risk"), ("turnover", "平均单边换手", "execution")):
        value = _finite(metrics.get(name))
        items.append(_item(f"{category}.{name}", category, label, value, "observed" if value is not None else "unknown", [f"metrics.{name}"], "ratio" if name != "sharpe" else None))
    benchmark = _valid_points(result.get("benchmark_curve"), required=False)
    benchmark_return = benchmark[-1][1] / benchmark[0][1] - 1 if benchmark and benchmark[0][1] else None
    items.append(_item("performance.benchmark_return", "performance", "同期基准收益", benchmark_return, "derived" if benchmark_return is not None else "unknown", ["benchmark_curve"], "ratio"))
    validation = req.run_context.get("validation_scheme", "unknown")
    items.append(_item("assumption.validation_scheme", "assumption", "验证方案", str(validation), "observed" if validation != "unknown" else "unknown", ["run_context.validation_scheme"]))
    costs = [_finite(req.run_context.get(name)) for name in ("commission_rate", "stamp_tax", "slippage_rate")]
    for name, value in zip(("commission_rate", "stamp_tax", "slippage_rate"), costs):
        items.append(_item(f"assumption.{name}", "assumption", name, value, "observed" if value is not None else "unknown", [f"run_context.{name}"], "ratio"))
    diagnostic_codes: list[str] = []
    if len(points) < 252: diagnostic_codes.append("SAMPLE_TOO_SHORT")
    if validation in (None, "unknown", "in_sample"): diagnostic_codes.append("NO_OUT_OF_SAMPLE")
    if any(value is None for value in costs): diagnostic_codes.append("COST_ASSUMPTION_UNKNOWN")
    turnover = _finite(metrics.get("turnover"))
    if turnover is not None and turnover >= 0.10: diagnostic_codes.append("HIGH_TURNOVER")
    if turnover and any(value == 0 for value in costs if value is not None): diagnostic_codes.append("ZERO_COST_ASSUMPTION")
    if drawdown <= -0.20: diagnostic_codes.append("DEEP_DRAWDOWN")
    if req.backtest_type == "factor":
        factor = result.get("factor_analysis") if isinstance(result.get("factor_analysis"), dict) else {}
        ic = _finite(factor.get("ic_mean"))
        items.append(_item("factor.ic_mean", "factor", "平均 IC", ic, "observed" if ic is not None else "unknown", ["factor_analysis.ic_mean"]))
        if ic is not None and abs(ic) < 0.02: diagnostic_codes.append("WEAK_FACTOR_SIGNAL")
    coverage = "complete" if not any(item.status == "unknown" for item in items) else "partial"
    return BacktestEvidencePackage(schema_version=EVIDENCE_SCHEMA_VERSION, result_fingerprint=fingerprint, coverage=coverage, warnings=diagnostic_codes, items=items), diagnostic_codes


def _findings(codes: list[str]) -> list[BacktestFinding]:
    findings = []
    for index, code in enumerate(codes, 1):
        title, explanation, severity, confidence, _ = _DIAGNOSTICS[code]
        refs = _refs_for(code)
        findings.append(BacktestFinding(finding_id=f"finding_{index}", candidate_id=code, severity=severity, title=title, explanation=explanation, evidence_refs=refs, confidence=confidence, limitations=[]))
    return findings


def _experiments(findings: list[BacktestFinding]) -> list[BacktestExperiment]:
    experiments = []
    for priority, finding in enumerate(findings[:5], 1):
        experiment_id = _DIAGNOSTICS[finding.candidate_id][4]
        title, variable, direction, tradeoffs, method, criteria = _EXPERIMENTS[experiment_id]
        experiments.append(BacktestExperiment(experiment_id=experiment_id, priority=priority, hypothesis=title, primary_variable=variable, expected_direction=direction, tradeoffs=tradeoffs, validation_method=method, pass_criteria=criteria, evidence_refs=finding.evidence_refs))
    return experiments


def _provider_configured() -> bool:
    return bool(os.environ.get("AI_BACKTEST_INTERPRETATION_API_KEY") or os.environ.get("AI_FACTOR_API_KEY") or os.environ.get("ARK_API_KEY"))


def _provider_order(req: BacktestInterpretationRequest, findings: list[BacktestFinding], model: str) -> list[str]:
    settings = llm_provider.ProviderSettings(os.environ.get("AI_BACKTEST_INTERPRETATION_BASE_URL", os.environ.get("AI_FACTOR_BASE_URL", "https://ark.cn-beijing.volces.com/api/plan/v3")).rstrip("/"), os.environ.get("AI_BACKTEST_INTERPRETATION_API_KEY") or os.environ.get("AI_FACTOR_API_KEY") or os.environ.get("ARK_API_KEY", ""), model)
    candidates = [{"id": item.candidate_id, "title": item.title} for item in findings]
    messages = [{"role": "system", "content": "只输出 JSON：{\"finding_ids\":[...] }。只能排列提供的 ID，不得生成数值、投资建议或新事实。"}, {"role": "user", "content": json.dumps({"focus": req.focus, "question": req.question, "candidates": candidates}, ensure_ascii=False)}]
    try:
        raw = llm_provider.complete(
            settings,
            messages,
            response_format=_FINDING_ORDER_RESPONSE_SCHEMA,
        )
        data = json.loads(raw)
        ids = data.get("finding_ids")
        valid = {item.candidate_id for item in findings}
        if not isinstance(ids, list) or set(ids) != valid or len(ids) != len(valid):
            raise llm_provider.ProviderUnavailable
        return ids
    except (json.JSONDecodeError, TypeError, llm_provider.ProviderUnavailable):
        raise llm_provider.ProviderUnavailable


def _order_findings(findings: list[BacktestFinding], ids: list[str]) -> list[BacktestFinding]:
    by_id = {item.candidate_id: item for item in findings}
    return [by_id[item_id] for item_id in ids]


def _summary(codes: list[str]) -> str:
    if not codes:
        return "已生成基础绩效与风险证据；建议结合样本外验证继续研究。"
    if "NO_OUT_OF_SAMPLE" in codes:
        return "当前结果缺少样本外验证，优先验证稳健性后再讨论收益优化。"
    return "已发现需要优先验证的研究风险，请按建议逐项进行人工实验。"


def _valid_points(value: object, required: bool = True) -> list[tuple[date, float]] | None:
    if value is None:
        return [] if not required else None
    if not isinstance(value, list): return None
    points: list[tuple[date, float]] = []
    for point in value:
        if not isinstance(point, dict): return None
        try: parsed_date = date.fromisoformat(str(point["date"])); parsed_value = float(point["value"])
        except (KeyError, TypeError, ValueError): return None
        if not math.isfinite(parsed_value) or parsed_value <= 0 or (points and parsed_date <= points[-1][0]): return None
        points.append((parsed_date, parsed_value))
    return points


def _item(evidence_id: str, category: str, label: str, value: object, status: str, paths: list[str], unit: str | None = None) -> BacktestEvidenceItem:
    return BacktestEvidenceItem(evidence_id=evidence_id, category=category, label=label, value=value, unit=unit, status=status, source_paths=paths)


def _refs_for(code: str) -> list[str]:
    return {"SAMPLE_TOO_SHORT": ["coverage.equity_points"], "NO_OUT_OF_SAMPLE": ["assumption.validation_scheme"], "COST_ASSUMPTION_UNKNOWN": ["assumption.commission_rate", "assumption.stamp_tax", "assumption.slippage_rate"], "ZERO_COST_ASSUMPTION": ["execution.turnover", "assumption.commission_rate", "assumption.slippage_rate"], "HIGH_TURNOVER": ["execution.turnover"], "DEEP_DRAWDOWN": ["risk.max_drawdown"], "WEAK_FACTOR_SIGNAL": ["factor.ic_mean"]}[code]


def _finite(value: object) -> float | None:
    try: number = float(value)
    except (TypeError, ValueError): return None
    return number if math.isfinite(number) else None


def _max_drawdown(points: list[tuple[date, float]]) -> float:
    """单次扫描计算最大回撤，保证 10,000 点快照不退化为二次复杂度。"""
    peak = points[0][1]
    maximum = 0.0
    for _, value in points:
        peak = max(peak, value)
        maximum = min(maximum, value / peak - 1)
    return maximum


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _request_hash(req: BacktestInterpretationRequest) -> str:
    return hashlib.sha256(_canonical(req.model_dump(mode="json", exclude={"idempotency_key"})).encode()).hexdigest()


def _meta(model_alias: str, started: float) -> BacktestInterpretationMeta:
    return BacktestInterpretationMeta(model_alias=model_alias, prompt_version=PROMPT_VERSION, diagnostic_catalog_version=DIAGNOSTIC_CATALOG_VERSION, latency_ms=round((time.perf_counter() - started) * 1000))
