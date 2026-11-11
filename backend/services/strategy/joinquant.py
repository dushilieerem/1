# -*- coding: utf-8 -*-
"""聚宽策略直跑：方言识别、能力预检与代码指纹。

聚宽策略**不转写**，直接把原始源码交给 RE 的 `strategy_dialect=joinquant` 执行，
保证与聚宽金标同源；转写只是详情页里的可选动作（产物是子策略）。

本模块只做静态检查与 payload 组装，不执行任何策略代码。
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from .transcription_validation import (
    MAX_SOURCE_CHARS,
    capability_issues,
    detect_engine,
    parse_inventory,
    verdict,
)

DIALECT_NATIVE = "native"
DIALECT_JOINQUANT = "joinquant"
DIALECTS = {DIALECT_NATIVE, DIALECT_JOINQUANT}

# RE 聚宽方言当前不支持的调用（以 RE 能力清单为准，清单接口上线后改为动态拉取）
DIRECT_RUN_UNSUPPORTED = (
    (r"\bget_call_auction\s*\(", "API-UNSUPPORTED", "集合竞价数据不可用", "RE 聚宽方言未提供 get_call_auction。"),
    (r"\bget_bars\s*\(|\bget_ticks\s*\(", "API-UNSUPPORTED", "逐笔/自定义周期行情不可用", "RE 只提供日线与 timed_execution 内部的一分钟价。"),
    (r"\binout_cash\s*\(", "API-UNSUPPORTED", "出入金接口不支持", "RE 回测不支持资金进出，会改变净值口径。"),
    (
        r"\bfinance\.(?!STK_XR_XD\b|STK_INCOME_STATEMENT\b)\w+",
        "API-UNSUPPORTED",
        "财务表未实现",
        "RE 聚宽兼容层只实现 finance.STK_XR_XD 与 finance.STK_INCOME_STATEMENT。",
    ),
)

# 只保留与「直接执行安全性」有关的检查；转写特有的数据/语义降级不适用于直跑。
DIRECT_RUN_SECURITY_CODES = ("SECURITY-",)
DIRECT_RUN_OTHER_CODES = {"LOOKAHEAD"}

# 聚宽直跑的固定参数（RE 侧唯一支持的组合）
RE_ENGINE_MODE = "event"
RE_PRICE_SOURCE = "unadjusted"
RE_EXECUTION_TIMING = "next_open"


def normalize_dialect(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in DIALECTS else DIALECT_NATIVE


def code_hash(source: str) -> str:
    """源码指纹：规范化换行后取 sha256，用于幂等与「原始策略未被覆盖」的校验。"""
    normalized = str(source or "").replace("\r\n", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _issue(code: str, title: str, why: str, effect: str) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "blocker",
        "impact": "high",
        "line": None,
        "title": title,
        "why": why,
        "effect": effect,
        "options": [],
        "evidence": "聚宽直跑前置校验",
    }


def precheck(source: str, *, hint: str | None = None) -> dict[str, Any]:
    """静态预检：返回阻断项与是否可直接回测。

    `can_run_directly=False` 时调用方必须拒绝提交回测，不能静默降级。
    """
    code = str(source or "")
    issues: list[dict[str, Any]] = []

    if not code.strip():
        issues.append(_issue("CODE-EMPTY", "代码为空", "没有可执行的策略源码。", "无法回测。"))
    elif len(code) > MAX_SOURCE_CHARS:
        issues.append(
            _issue(
                "CODE-TOO-LARGE",
                f"代码超过 {MAX_SOURCE_CHARS} 字符",
                "直跑通道对源码大小有上限，避免一次提交占用过长计算。",
                "请删减无关代码后重试。",
            )
        )
    else:
        try:
            inventory = parse_inventory(code)
        except SyntaxError as exc:
            issues.append(
                _issue(
                    "CODE-SYNTAX",
                    "代码无法解析",
                    f"Python 语法错误：{exc.msg}（第 {exc.lineno} 行）。",
                    "修复语法后才能回测。",
                )
            )
        else:
            for item in capability_issues(code, inventory):
                item_code = str(item.get("code") or "")
                if item_code.startswith(DIRECT_RUN_SECURITY_CODES) or item_code in DIRECT_RUN_OTHER_CODES:
                    issues.append(item)
            for pattern, issue_code, title, why in DIRECT_RUN_UNSUPPORTED:
                match = re.search(pattern, code)
                if match:
                    issues.append(
                        {
                            **_issue(issue_code, title, why, "该调用会让直跑失败或改变口径，需改写后再回测。"),
                            "line": code[: match.start()].count("\n") + 1,
                        }
                    )

    blockers = [item for item in issues if item.get("severity") == "blocker"]
    return {
        "ok": True,
        "dialect": DIALECT_JOINQUANT,
        "engine": detect_engine(code, hint) if code.strip() else None,
        "code_hash": code_hash(code),
        "chars": len(code),
        "issues": issues,
        "blocker_count": len(blockers),
        "can_run_directly": not blockers,
        "verdict": verdict(issues) if issues else "equivalent",
    }


def build_re_payload(
    *,
    source_code: str,
    start: str,
    end: str,
    universe: Any = None,
    benchmark: str | None = None,
    initial_capital: float | None = None,
    commission_rate: float | None = None,
    stamp_tax: float | None = None,
    min_commission: float | None = None,
    slippage_rate: float | None = None,
    extra_symbols: list[str] | None = None,
) -> dict[str, Any]:
    """聚宽直跑的 RE 请求体：原始源码 + 固定方言参数。"""
    payload: dict[str, Any] = {
        "engine_mode": RE_ENGINE_MODE,
        "strategy_dialect": DIALECT_JOINQUANT,
        "strategy_code": str(source_code),
        "start": start,
        "end": end,
        "execution_price_source": RE_PRICE_SOURCE,
        "timed_execution": True,
        "execution_timing": RE_EXECUTION_TIMING,
    }
    for key, value in (
        ("universe", universe),
        ("benchmark", benchmark),
        ("initial_capital", initial_capital),
        ("commission_rate", commission_rate),
        ("stamp_tax", stamp_tax),
        ("min_commission", min_commission),
        ("slippage_rate", slippage_rate),
        ("extra_symbols", extra_symbols),
    ):
        if value is not None:
            payload[key] = value
    return payload


__all__ = [
    "DIALECTS",
    "DIALECT_JOINQUANT",
    "DIALECT_NATIVE",
    "build_re_payload",
    "code_hash",
    "normalize_dialect",
    "precheck",
]
