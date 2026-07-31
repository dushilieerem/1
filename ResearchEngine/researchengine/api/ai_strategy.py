"""受控的自然语言向量化策略生成服务。

本模块只生成并静态校验自由目标权重策略；不会执行模型输出或自动回测。
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import time
import urllib.error
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException

from researchengine.api import ai_factor
from researchengine.api.schemas import (
    GeneratedStrategy,
    StrategyGenerationMeta,
    StrategyGenerationRequest,
    StrategyGenerationResponse,
    StrategyGenerationValidation,
)


CATALOG_VERSION = "2026-07-30"
PROMPT_VERSION = "v3"
ALLOWED_FIELDS = frozenset({"close"})
ALLOWED_PANEL_METHODS = frozenset({
    "abs", "astype", "clip", "diff", "fillna", "mean", "median", "min", "max",
    "div", "pct_change", "rank", "rolling", "shift", "std", "sum", "where", "ffill",
})
_STRATEGY_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "svquant_vectorized_strategy_generation",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "strategy_name", "strategy_code", "description", "used_fields",
                "assumptions", "warnings",
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
_IDEMPOTENCY: dict[str, tuple[str, StrategyGenerationResponse]] = {}
_IDEMPOTENCY_LOCK = Lock()


def generate_strategy(req: StrategyGenerationRequest) -> StrategyGenerationResponse:
    """调用供应商并返回经过受控校验的策略草稿。"""
    request_hash = _request_hash(req)
    key = str(req.idempotency_key)
    with _IDEMPOTENCY_LOCK:
        existing = _IDEMPOTENCY.get(key)
        if existing is not None:
            if existing[0] != request_hash:
                raise HTTPException(409, "idempotency_key 已用于不同请求")
            return existing[1]

    unsupported_errors = _unsupported_prompt_errors(req.prompt)
    if unsupported_errors:
        response = _rejected_response(unsupported_errors, model="not_called", latency_ms=0)
        with _IDEMPOTENCY_LOCK:
            existing = _IDEMPOTENCY.setdefault(key, (request_hash, response))
        if existing[0] != request_hash:
            raise HTTPException(409, "idempotency_key 已用于不同请求")
        return existing[1]

    settings = _settings_from_env()
    started_at = time.perf_counter()
    try:
        raw_content = _call_provider(settings, _messages(req))
    except TimeoutError as exc:
        raise HTTPException(504, "AI 供应商请求超时") from exc
    except ai_factor.ProviderUnavailable as exc:
        raise HTTPException(503, "AI 供应商暂不可用") from exc

    response = _validate_provider_output(raw_content, settings.model, started_at)
    with _IDEMPOTENCY_LOCK:
        existing = _IDEMPOTENCY.setdefault(key, (request_hash, response))
    if existing[0] != request_hash:
        raise HTTPException(409, "idempotency_key 已用于不同请求")
    return existing[1]


def _settings_from_env() -> ai_factor.ProviderSettings:
    api_key = (
        os.environ.get("AI_STRATEGY_API_KEY")
        or os.environ.get("AI_FACTOR_API_KEY")
        or os.environ.get("ARK_API_KEY")
    )
    if not api_key:
        raise HTTPException(503, "AI 策略生成服务尚未配置")
    return ai_factor.ProviderSettings(
        base_url=os.environ.get(
            "AI_STRATEGY_BASE_URL",
            os.environ.get("AI_FACTOR_BASE_URL", "https://ark.cn-beijing.volces.com/api/plan/v3"),
        ).rstrip("/"),
        api_key=api_key,
        model=os.environ.get(
            "AI_STRATEGY_MODEL_ALIAS",
            os.environ.get("AI_FACTOR_MODEL_ALIAS", "ark-code-latest"),
        ),
    )


def _messages(req: StrategyGenerationRequest) -> list[dict[str, str]]:
    system = (
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
    user = (
        f"研究想法：{req.prompt}\n"
        f"频率：{req.context.frequency}\n"
        f"股票池：{req.context.universe or '未指定'}\n"
        f"偏好策略类名：{req.context.preferred_strategy_name or '由你命名'}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _call_provider(settings: ai_factor.ProviderSettings, messages: list[dict[str, str]]) -> str:
    payload = {
        "model": settings.model,
        "messages": messages,
        "temperature": 0.1,
        "response_format": _STRATEGY_RESPONSE_SCHEMA,
    }
    try:
        body = ai_factor._send_completion(settings, payload)
    except Exception as exc:  # 统一复用因子端点的供应商异常语义
        if isinstance(exc, urllib.error.HTTPError) and ai_factor._response_format_is_unsupported(exc):
            payload.pop("response_format")
            try:
                body = ai_factor._send_completion(settings, payload)
            except Exception as retry_exc:
                raise ai_factor.ProviderUnavailable from retry_exc
        else:
            raise ai_factor.ProviderUnavailable from exc
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ai_factor.ProviderUnavailable from exc


def _validate_provider_output(
    raw: str, model: str, started_at: float,
) -> StrategyGenerationResponse:
    latency_ms = round((time.perf_counter() - started_at) * 1000)
    generation_id = f"sg_{uuid4().hex}"
    try:
        strategy = GeneratedStrategy.model_validate(json.loads(raw.strip()))
        errors = _validate_strategy_code(strategy)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        errors = [f"模型输出不是有效的策略草稿：{exc}"]
        strategy = None
    if errors:
        return _rejected_response(errors, model=model, latency_ms=latency_ms, generation_id=generation_id)
    return StrategyGenerationResponse(
        generation_id=generation_id,
        status="ready",
        strategy=strategy,
        validation=StrategyGenerationValidation(
            status="passed", capability_catalog_version=CATALOG_VERSION,
        ),
        meta=StrategyGenerationMeta(
            model_alias=model, prompt_version=PROMPT_VERSION, latency_ms=latency_ms,
        ),
    )


def _rejected_response(
    errors: list[str], model: str, latency_ms: int, generation_id: str | None = None,
) -> StrategyGenerationResponse:
    return StrategyGenerationResponse(
        generation_id=generation_id or f"sg_{uuid4().hex}",
        status="rejected",
        validation=StrategyGenerationValidation(
            status="failed", capability_catalog_version=CATALOG_VERSION, errors=errors,
        ),
        meta=StrategyGenerationMeta(
            model_alias=model, prompt_version=PROMPT_VERSION, latency_ms=latency_ms,
        ),
    )


def _unsupported_prompt_errors(prompt: str) -> list[str]:
    normalized = prompt.lower()
    unsupported_capabilities = (
        (("成交量", "成交额", "volume"), "成交量/成交额字段"),
        (("市盈率", "pe", "基本面", "财务"), "基本面字段"),
        (("事件驱动", "市价单", "止盈", "止损", "订单"), "事件驱动订单"),
        (("做空", "多空", "对冲", "short"), "多空策略"),
        (("numpy", "talib", "ta-lib"), "外部计算库"),
    )
    found = [label for keywords, label in unsupported_capabilities if any(word in normalized for word in keywords)]
    if not found:
        return []
    return [
        "当前 AI 策略生成仅支持基于 close 的日频纯多头向量化策略，不支持："
        f"{', '.join(found)}。"
    ]


def _validate_strategy_code(strategy: GeneratedStrategy) -> list[str]:
    unknown_fields = sorted(set(strategy.used_fields) - ALLOWED_FIELDS)
    if unknown_fields:
        return [f"used_fields 包含未登记字段：{', '.join(unknown_fields)}"]
    try:
        tree = ast.parse(strategy.strategy_code)
    except SyntaxError as exc:
        return [f"策略代码语法错误：{exc.msg}"]
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    if len(classes) != 1 or len(tree.body) not in {1, 2}:
        return ["策略代码必须只包含 pandas 导入和一个策略类定义"]
    if classes[0].name != strategy.strategy_name:
        return ["策略类名必须与 strategy_name 一致"]
    validator = _StrategyAstValidator()
    validator.visit(tree)
    if validator.errors:
        return validator.errors
    try:
        compile(strategy.strategy_code, "<generated_strategy>", "exec")
    except SyntaxError as exc:
        return [f"策略代码无法编译：{exc.msg}"]
    return []


class _StrategyAstValidator(ast.NodeVisitor):
    _ALLOWED_NODES = {
        ast.Module, ast.Import, ast.alias, ast.ClassDef, ast.FunctionDef, ast.arguments,
        ast.arg, ast.Return, ast.Assign, ast.Name, ast.Load, ast.Store, ast.Attribute,
        ast.Call, ast.Constant, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult,
        ast.Div, ast.Pow, ast.USub, ast.Compare, ast.Eq, ast.NotEq, ast.Gt, ast.GtE,
        ast.Lt, ast.LtE, ast.keyword, ast.Subscript, ast.Mod, ast.Slice,
    }

    def __init__(self):
        self.errors: list[str] = []

    def generic_visit(self, node):
        if type(node) not in self._ALLOWED_NODES:
            self.errors.append(f"不允许的代码结构：{type(node).__name__}")
            return
        super().generic_visit(node)

    def visit_Import(self, node: ast.Import):
        if len(node.names) != 1 or node.names[0].name != "pandas" or node.names[0].asname != "pd":
            self.errors.append("只允许 import pandas as pd")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        method_names = [item.name for item in node.body if isinstance(item, ast.FunctionDef)]
        if method_names != ["__init__", "generate_signals"]:
            self.errors.append("策略类必须且只能定义 __init__ 与 generate_signals")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        args = [arg.arg for arg in node.args.args]
        expected = ["self", "close"] if node.name == "__init__" else ["self"]
        if args != expected or node.decorator_list:
            self.errors.append(f"{node.name} 的签名不符合向量化策略契约")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr.startswith("__"):
            self.errors.append("不允许访问双下划线属性")
        if isinstance(node.value, ast.Name) and node.value.id == "self" and node.attr != "close":
            self.errors.append(f"不允许的 self 属性：{node.attr}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id == "pd" and node.func.attr == "DataFrame":
                self.generic_visit(node)
                return
        if not isinstance(node.func, ast.Attribute) or node.func.attr not in ALLOWED_PANEL_METHODS:
            method = node.func.attr if isinstance(node.func, ast.Attribute) else type(node.func).__name__
            self.errors.append(f"不允许调用：{method}；仅允许 pandas.DataFrame 或白名单面板方法")
        self.generic_visit(node)


def _request_hash(req: StrategyGenerationRequest) -> str:
    content = json.dumps(req.model_dump(mode="json", exclude={"idempotency_key"}), sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()
