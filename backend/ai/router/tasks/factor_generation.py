# -*- coding: utf-8 -*-
"""AI 因子生成：prompt、输出契约与静态校验（ADR-037 P1-3，自 ResearchEngine 迁入）。

模型输出永不执行：本模块只做 JSON 解析 + `generated_factor_validation` 的静态检查。
"需求不支持/需澄清" 是合法结果（HTTP 200 + status=rejected），不是异常。
"""
from __future__ import annotations

import json
from typing import Any

from ai.errors import AiBadOutput
from ai.gateway.providers import SLOT_CODE
from ai.router.specs import TaskRequest, TaskSpec, register
from services.factor.generated_factor_validation import (
    ALLOWED_FIELDS,
    ALLOWED_METHODS,
    validate_generated_factor,
)

CATALOG_VERSION = "2026-07-01"
PROMPT_VERSION = "v2"

GENERATION_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "svquant_factor_generation",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "factor_name", "factor_code", "description", "used_fields",
                "used_library_methods", "assumptions", "warnings", "outcome", "reason",
                "minimum_history", "missing_value_handling",
            ],
            "properties": {
                "factor_name": {"type": "string"},
                "factor_code": {"type": "string"},
                "description": {"type": "string"},
                "used_fields": {"type": "array", "items": {"type": "string"}},
                "used_library_methods": {"type": "array", "items": {"type": "string"}},
                "assumptions": {"type": "array", "items": {"type": "string"}},
                "warnings": {"type": "array", "items": {"type": "string"}},
                "outcome": {"type": "string", "enum": ["factor", "unsupported", "needs_clarification"]},
                "reason": {"type": "string"},
                "minimum_history": {"type": "string"},
                "missing_value_handling": {"type": "string"},
            },
        },
    },
}

SYSTEM_PROMPT = (
    "你是 SVQuant 因子生成器。只输出 JSON 对象，不要 Markdown。"
    "JSON 必须有 factor_name、factor_code、description、used_fields、"
    "used_library_methods、assumptions、warnings、outcome、reason、minimum_history、missing_value_handling。"
    "outcome为factor表示可生成，reason为空字符串；"
    "若需求与因子研究无关或缺少计算逻辑，outcome为needs_clarification并用reason说明需补充什么；"
    "若需要未支持的数据或操作，outcome为unsupported并用reason明确说明能力边界。"
    "后两种情况factor_name、factor_code、description、minimum_history、missing_value_handling为空字符串，数组为空；"
    "不要通过raise、返回常数或替代数据伪造可用因子。"
    "可生成时factor_code 必须只含一个 "
    "def 方法，第一个参数为 self。只可读取字段："
    f"{', '.join(sorted(ALLOWED_FIELDS))}。禁止 import、文件、网络、动态执行、"
    "双下划线属性和投资建议。不要调用 self.get_data、self.get_field 或任何未列出的 "
    "self 方法。允许的面板方法仅为："
    f"{', '.join(sorted(ALLOWED_METHODS))}。"
    "不允许使用np、pd、math、sqrt、pow方法、astype或外部函数；平方根使用 ** 0.5。"
    "允许简单赋值、算术、比较及return，不使用if、raise、循环或辅助函数。"
    "只使用当前及历史数据；shift和pct_change的periods必须是可确定的非负整数，"
    "可以使用正整数默认参数及其简单算术，不得用负周期或rolling(center=True)读取未来数据。"
    "缺失值保留为空；pct_change需显式fill_method=None；滚动窗口明确min_periods，"
    "前值为0时用where置空。description解释计算公式、输出单位和含义；"
    "minimum_history必须具体解释最少历史观察值，missing_value_handling必须解释缺失值及零分母处理，"
    "两者都不能留空；assumptions补充其他假设，覆盖用户明确提出的说明要求。"
    "例如20个日收益率需至少21个收盘价，rolling(20,min_periods=20).std(ddof=1)，"
    "在价格完整时前20个观察位置为空，第21个可输出；不能误写前21日均为空。"
    "不是跳过缺失值向更早日期凑20条。不得声称未做的处理。"
    "合法示例：def momentum_20(self, window=20):\n"
    "    previous = self.close.shift(window)\n"
    "    return self.close / previous.where(previous != 0) - 1"
)


def build_messages(request: TaskRequest) -> list[dict[str, Any]]:
    variables = request.variables
    libraries = ", ".join(variables.get("allowed_library_names") or []) or "无"
    user = (
        f"研究想法：{variables.get('prompt') or ''}\n"
        f"频率：{variables.get('frequency') or '1d'}\n"
        f"股票池：{variables.get('universe') or '未指定'}\n"
        f"内置库上下文：{libraries}（本接口仍只允许上述面板表达式，不调用内置库方法）\n"
        f"偏好名称：{variables.get('preferred_factor_name') or '由你命名'}"
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def _str_list(value: object) -> list[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return None
    return list(value)


def parse_generation(raw: str) -> dict[str, Any]:
    """解析模型输出并做静态校验；返回 {outcome, reason, factor, errors}。

    只有「不是 JSON」算上游失败；校验不通过是业务结果，交由调用方转成 rejected。
    """
    try:
        data = json.loads((raw or "").strip())
    except json.JSONDecodeError as exc:
        raise AiBadOutput(f"模型输出不是有效的因子草稿：{exc}") from exc
    if not isinstance(data, dict):
        raise AiBadOutput("模型输出不是有效的因子草稿：期望 JSON 对象")

    outcome = data.get("outcome")
    if outcome in ("unsupported", "needs_clarification"):
        label = "需求暂不支持" if outcome == "unsupported" else "请补充因子需求"
        reason = str(data.get("reason") or "请说明可用数据、计算公式和周期").strip()
        return {"outcome": outcome, "reason": reason, "factor": None, "errors": [f"{label}：{reason}"]}
    if outcome != "factor":
        return {
            "outcome": str(outcome or ""),
            "reason": "",
            "factor": None,
            "errors": ["模型返回了无效的需求处理状态"],
        }

    used_fields = _str_list(data.get("used_fields"))
    used_methods = _str_list(data.get("used_library_methods"))
    assumptions = _str_list(data.get("assumptions"))
    warnings = _str_list(data.get("warnings"))
    factor = {
        "factor_name": data.get("factor_name"),
        "factor_code": data.get("factor_code"),
        "description": data.get("description"),
        "used_fields": used_fields or [],
        "used_library_methods": used_methods or [],
        "assumptions": assumptions or [],
        "warnings": warnings or [],
    }
    errors: list[str] = []
    if not isinstance(factor["factor_name"], str) or not isinstance(factor["factor_code"], str) or not isinstance(factor["description"], str):
        errors.append("模型输出不是有效的因子草稿：缺少必要的文本字段")
    if used_fields is None or used_methods is None or assumptions is None or warnings is None:
        errors.append("模型输出不是有效的因子草稿：数组字段类型不正确")

    if not errors:
        errors = validate_generated_factor(factor)
        # 协议必填项映射到 assumptions，公开接口与前端无需迁移。
        for field, label in (("minimum_history", "历史数据要求"), ("missing_value_handling", "缺失值处理")):
            value = data.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"生成说明缺少{label}")
            else:
                note = f"{label}：{value.strip()}"
                if note not in factor["assumptions"]:
                    factor["assumptions"].append(note)

    return {"outcome": "factor", "reason": "", "factor": factor, "errors": errors}


def is_request_rejection(errors: list[str]) -> bool:
    """区分「需求本身不支持」与「代码不合规」：后者才值得自动修正一次。"""
    return any(error.startswith(("需求暂不支持：", "请补充因子需求：")) for error in errors)


FACTOR_TASK = register(
    TaskSpec(
        task_id="research.generate_factor",
        description="自然语言 → 单方法因子草稿（只生成与静态校验，不执行）",
        slot=SLOT_CODE,
        temperature=0.1,
        max_tokens=None,
        timeout_sec=120,
        response_format=GENERATION_SCHEMA,
        prompt=build_messages,
        validator=lambda raw, request: parse_generation(raw),
    )
)

__all__ = [
    "CATALOG_VERSION",
    "FACTOR_TASK",
    "GENERATION_SCHEMA",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "build_messages",
    "is_request_rejection",
    "parse_generation",
]
