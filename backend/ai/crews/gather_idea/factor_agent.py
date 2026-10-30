# -*- coding: utf-8 -*-
"""Agent C · 因子草稿：Idea → SVQuant factor_code（人审后再回测）。"""
from __future__ import annotations

import ast
import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

_TZ = timezone(timedelta(hours=8))
_ALLOWED_FIELDS = {"close", "open", "high", "low", "volume"}
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")


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


def _validate_factor_code(code: str, *, expect_name: str | None = None) -> tuple[str, str, list[str]]:
    """返回 (factor_name, cleaned_code, errors)。"""
    errors: list[str] = []
    src = (code or "").strip()
    src = re.sub(r"^```(?:python)?\s*", "", src, flags=re.I)
    src = re.sub(r"\s*```$", "", src)
    if not src:
        return "", "", ["factor_code 为空"]
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return "", src, [f"语法错误: {exc.msg}"]

    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if len(tree.body) != 1 or len(funcs) != 1:
        errors.append("只允许一个 def 函数，不要 class / import / 其它语句")
        return "", src, errors
    fn = funcs[0]
    name = fn.name
    if expect_name and expect_name != name:
        errors.append(f"函数名须与 factor_name 一致（{expect_name} vs {name}）")
    if not _NAME_RE.match(name):
        errors.append("factor_name 须为小写蛇形英文")
    args = [a.arg for a in fn.args.args]
    if not args or args[0] != "self":
        errors.append("第一个参数必须是 self")

    banned = (
        ast.Import,
        ast.ImportFrom,
        ast.With,
        ast.AsyncFunctionDef,
        ast.ClassDef,
    )
    for node in ast.walk(tree):
        if isinstance(node, banned):
            errors.append("不允许 import / class / with")
            break
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "open", "__import__"}:
                errors.append(f"不允许调用 {node.func.id}")
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and node.attr not in _ALLOWED_FIELDS
        ):
            errors.append(f"不允许的字段 self.{node.attr}，仅 close/open/high/low/volume")

    return name, src, list(dict.fromkeys(errors))


def _fallback_code(name: str = "price_momentum_20") -> dict[str, Any]:
    code = (
        f"def {name}(self, window=20):\n"
        f"    return self.close.pct_change(window)\n"
    )
    return {
        "factor_name": name,
        "factor_code": code,
        "description": "弱回退：过去 window 日收盘价动量。",
        "formula_nl": "close 的 window 日收益率",
        "used_fields": ["close"],
        "assumptions": ["日频面板；无未来函数"],
        "warnings": ["规则弱回退，未经回测"],
    }


def run_factor(body: dict[str, Any], *, user_id: int) -> dict[str, Any]:
    _ = user_id
    t0 = time.perf_counter()
    idea = body.get("idea") if isinstance(body.get("idea"), dict) else {}
    prompt = str(idea.get("factor_prompt") or body.get("prompt") or "").strip()
    thesis = str(idea.get("thesis") or "").strip()
    if not prompt:
        prompt = thesis
    if not prompt:
        raise ValueError("需要 idea.factor_prompt 或 thesis")
    spec = idea.get("factor_spec") if isinstance(idea.get("factor_spec"), dict) else {}
    validity = idea.get("validity") if isinstance(idea.get("validity"), dict) else {}
    preferred = re.sub(r"[^a-z0-9_]", "", str(spec.get("preferred_factor_name") or "research_factor").lower())
    if not _NAME_RE.match(preferred):
        preferred = "research_factor"

    warnings: list[str] = []
    usage: dict[str, Any] = {}
    mode = "llm"
    draft: dict[str, Any] | None = None

    try:
        from ai.errors import AiError
        from ai.router import available_task, run_task
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"AI 路由层不可用: {exc}")
        available_task = lambda _task: False  # type: ignore[assignment]
        run_task = None  # type: ignore[assignment]
        AiError = Exception  # type: ignore[misc,assignment]

    if available_task("gather_idea.factor") and run_task:
        system = (
            "你把研究假设转成 SVQuant 日频因子草稿。"
            "只输出 JSON："
            '{"factor_name":"snake","factor_code":"def snake(self, window=20):\\n    return ...",'
            '"description":"...","formula_nl":"...","used_fields":["close"]}。'
            "factor_code 只能有一个 def，第一个参数 self；只用 self.close/open/high/low/volume；"
            "可用 pct_change/rolling/shift/ewm；禁止 import/class/未来函数/买卖建议。"
            "必须实现 prompt/thesis 里的机制，禁止无视说明书一律写成收盘动量。"
            f"优先函数名 {preferred}。"
        )
        user = json.dumps(
            {
                "title": str(idea.get("title") or "")[:80],
                "prompt": prompt[:2000],
                "thesis": thesis[:500],
                "factor_spec": spec,
                "validity": validity,
            },
            ensure_ascii=False,
        )
        try:
            out = run_task(
                "gather_idea.factor",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            usage = {
                "tokens_in": int(out.get("tokens_in") or 0),
                "tokens_out": int(out.get("tokens_out") or 0),
                "model": out.get("model") or "",
            }
            obj = _extract_json_obj(str(out.get("content") or ""))
            if not obj:
                raise RuntimeError("LLM 未返回 JSON")
            name = str(obj.get("factor_name") or preferred)
            code = str(obj.get("factor_code") or "")
            got_name, cleaned, errs = _validate_factor_code(code, expect_name=None)
            if errs or not got_name:
                warnings.append("校验未过，回退动量模板：" + "；".join(errs[:3]))
                mode = "rule_fallback"
                draft = _fallback_code(preferred)
            else:
                fields = obj.get("used_fields") if isinstance(obj.get("used_fields"), list) else []
                used = [str(x) for x in fields if str(x) in _ALLOWED_FIELDS] or ["close"]
                draft = {
                    "factor_name": got_name,
                    "factor_code": cleaned,
                    "description": str(obj.get("description") or "")[:400],
                    "formula_nl": str(obj.get("formula_nl") or "")[:200],
                    "used_fields": used,
                    "assumptions": ["日频面板对齐", "草稿未经回测"],
                    "warnings": ["不构成买卖建议"],
                }
                if name != got_name:
                    warnings.append("已用代码中的函数名")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"生成失败回退模板: {exc}")
            mode = "rule_fallback"
            draft = _fallback_code(preferred)
    else:
        mode = "rule_fallback"
        warnings.append("LLM 未配置，使用动量模板")
        draft = _fallback_code(preferred)

    assert draft is not None
    start = str(validity.get("suggested_start") or "2018-01-01")[:10]
    end = str(validity.get("suggested_end") or datetime.now(_TZ).strftime("%Y-%m-%d"))[:10]
    oos = str(validity.get("oos_split") or "2023-01-01")[:10]
    universe = str(spec.get("universe") or "CSI300")
    elapsed = int((time.perf_counter() - t0) * 1000)
    return {
        "ok": True,
        "draft_id": f"fdr_{datetime.now(_TZ).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
        "idea_id": str(idea.get("id") or ""),
        "pack_id": str(body.get("pack_id") or ""),
        "bundle_id": str(body.get("bundle_id") or ""),
        "factor": draft,
        "backtest_hint": {
            "factor_name": draft["factor_name"],
            "factor_code": draft["factor_code"],
            "universe": universe if universe in {"CSI300", "CSI500", "CSI1000", "SSE50"} else "CSI300",
            "start": start,
            "end": end,
            "oos_split": oos,
            "portfolio_type": "long_only",
            "rebalance_days": 1,
            "groups": 5,
            "benchmark": "CSI300",
            "analysis_level": "core",
        },
        "gaps": [],
        "warnings": warnings,
        "stats": {
            "elapsed_ms": elapsed,
            "tokens_in": int(usage.get("tokens_in") or 0),
            "tokens_out": int(usage.get("tokens_out") or 0),
            "llm_model": usage.get("model") or "",
            "factor_mode": mode,
        },
    }
