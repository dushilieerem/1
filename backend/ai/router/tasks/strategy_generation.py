# -*- coding: utf-8 -*-
"""AI 向量化策略生成：prompt、输出契约与静态校验（ADR-037 P1-3，自 ResearchEngine 迁入）。

模型输出永不执行；只接受 `import pandas as pd` + 单个策略类的白名单子集。
"""
from __future__ import annotations

import json
from typing import Any

from ai.errors import AiBadOutput
from ai.gateway.providers import SLOT_CODE
from ai.router.specs import TaskRequest, TaskSpec, register
from services.strategy.generated_strategy_validation import (
    ALLOWED_FIELDS,
    ALLOWED_PANEL_METHODS,
    validate_generated_strategy,
)

CATALOG_VERSION = "2026-07-30"
PROMPT_VERSION = "v3"

STRATEGY_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "svquant_strategy_generation",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "strategy_name", "strategy_code", "description",
                "used_fields", "assumptions", "warnings",
            ],
            "properties": {
                "strategy_name": {"type": "string"},
                "strategy_code": {"type": "string"},
                "description": {"type": "string"},
                "used_fields": {"type": "array", "items": {"type": "string"}},
                "assumptions": {"type": "array", "items": {"type": "string"}},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}

SYSTEM_PROMPT = (
    "你是 SVQuant 向量化策略生成器。只输出 JSON 对象，不要 Markdown。"
    "JSON 必须有 strategy_name、strategy_code、description、used_fields、assumptions、warnings。"
    "strategy_code 必须只含一个类，类名等于 strategy_name，且只定义 "
    "__init__(self, close) 与 generate_signals(self)。只允许 import pandas as pd，"
    "只可读取 self.close 并以 pandas.DataFrame 返回日期×标的目标权重。"
    "你只会收到已通过能力预检的、仅依赖 close 的日频纯多头策略需求；"
    "不得添加或假设 prompt 中不存在的字段、外部库、事件订单或空头头寸。"
    "可调用面板方法："
    f"{', '.join(sorted(ALLOWED_PANEL_METHODS))}。禁止未来数据、文件、网络、"
    "动态执行、双下划线属性、订单、回测调用和投资建议。"
    "不要使用 for、if、lambda、numpy、pandas.Series、loc、日期取模、"
    "布尔 & 或其他未列出的方法。必须以以下已验证模板为基础，只替换类名和参数：\n"
    "import pandas as pd\n\n"
    "class StrategyName:\n"
    "    def __init__(self, close):\n"
    "        self.close = close\n\n"
    "    def generate_signals(self):\n"
    "        score = self.close.pct_change(WINDOW)\n"
    "        ranks = score.rank(axis=1, ascending=False, method='first')\n"
    "        targets = (ranks <= TOP_N) * (1.0 / TOP_N)\n"
    "        rebalance = pd.DataFrame(False, index=self.close.index, columns=self.close.columns)\n"
    "        rebalance.iloc[::REBALANCE_DAYS] = True\n"
    "        return targets.where(rebalance).ffill().fillna(0.0)\n"
    "反转策略将 ascending 改为 True；低波动策略将 score 改为 "
    "self.close.pct_change(WINDOW).rolling(WINDOW).std() 并使用 ascending=True；"
    "有条件筛选时使用 targets = (ranks <= TOP_N) * (condition) * (1.0 / TOP_N)。"
    "每日均线条件等权可使用 selected.astype(float).div(selected.sum(axis=1), axis=0).fillna(0.0)。"
)

_UNSUPPORTED_CAPABILITIES = (
    (("成交量", "成交额", "volume"), "成交量/成交额字段"),
    (("市盈率", "pe", "基本面", "财务"), "基本面字段"),
    (("事件驱动", "市价单", "止盈", "止损", "订单"), "事件驱动订单"),
    (("做空", "多空", "对冲", "short"), "多空策略"),
    (("numpy", "talib", "ta-lib"), "外部计算库"),
)


def build_messages(request: TaskRequest) -> list[dict[str, Any]]:
    variables = request.variables
    user = (
        f"研究想法：{variables.get('prompt') or ''}\n"
        f"频率：{variables.get('frequency') or '1d'}\n"
        f"股票池：{variables.get('universe') or '未指定'}\n"
        f"偏好策略类名：{variables.get('preferred_strategy_name') or '由你命名'}"
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def unsupported_prompt_errors(prompt: str) -> list[str]:
    """能力预检：仅支持基于 close 的日频纯多头向量化策略。"""
    normalized = (prompt or "").lower()
    found = [label for keywords, label in _UNSUPPORTED_CAPABILITIES if any(word in normalized for word in keywords)]
    if not found:
        return []
    return [
        "当前 AI 策略生成仅支持基于 close 的日频纯多头向量化策略，不支持："
        f"{', '.join(found)}。"
    ]


def _str_list(value: object) -> list[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return None
    return list(value)


def parse_generation(raw: str) -> dict[str, Any]:
    """解析模型输出并静态校验；返回 {strategy, errors}。

    非 JSON 视为上游失败；校验不通过是业务结果。
    """
    try:
        data = json.loads((raw or "").strip())
    except json.JSONDecodeError as exc:
        raise AiBadOutput(f"模型输出不是有效的策略草稿：{exc}") from exc
    if not isinstance(data, dict):
        raise AiBadOutput("模型输出不是有效的策略草稿：期望 JSON 对象")

    used_fields = _str_list(data.get("used_fields"))
    assumptions = _str_list(data.get("assumptions"))
    warnings = _str_list(data.get("warnings"))
    strategy = {
        "strategy_name": data.get("strategy_name"),
        "strategy_code": data.get("strategy_code"),
        "description": data.get("description"),
        "used_fields": used_fields or [],
        "assumptions": assumptions or [],
        "warnings": warnings or [],
    }
    errors: list[str] = []
    if (
        not isinstance(strategy["strategy_name"], str)
        or not isinstance(strategy["strategy_code"], str)
        or not isinstance(strategy["description"], str)
    ):
        errors.append("模型输出不是有效的策略草稿：缺少必要的文本字段")
    if used_fields is None or assumptions is None or warnings is None:
        errors.append("模型输出不是有效的策略草稿：数组字段类型不正确")
    if not errors:
        errors = validate_generated_strategy(strategy)
    return {"strategy": None if errors else strategy, "errors": errors}


STRATEGY_TASK = register(
    TaskSpec(
        task_id="research.generate_strategy",
        description="自然语言 → 向量化策略草稿（只生成与静态校验，不执行）",
        slot=SLOT_CODE,
        temperature=0.1,
        max_tokens=None,
        timeout_sec=120,
        response_format=STRATEGY_SCHEMA,
        prompt=build_messages,
        validator=lambda raw, request: parse_generation(raw),
    )
)

__all__ = [
    "CATALOG_VERSION",
    "PROMPT_VERSION",
    "STRATEGY_SCHEMA",
    "STRATEGY_TASK",
    "SYSTEM_PROMPT",
    "build_messages",
    "parse_generation",
    "unsupported_prompt_errors",
]
