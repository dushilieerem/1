"""受控的自然语言因子生成服务。

本模块只生成并静态校验 ``FactorLibrary`` 的单个方法；不会执行模型输出。
真实密钥仅从环境变量读取，供应商调用使用 OpenAI 兼容的 Chat Completions 协议。
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException

from researchengine.api.schemas import (
    FactorGenerationMeta,
    FactorGenerationRequest,
    FactorGenerationResponse,
    FactorGenerationValidation,
    GeneratedFactor,
)


CATALOG_VERSION = "2026-07-01"
PROMPT_VERSION = "v1"
ALLOWED_FIELDS = frozenset({"open", "high", "low", "close", "volume", "amount"})
ALLOWED_METHODS = frozenset({
    "abs", "clip", "diff", "fillna", "mean", "median", "min", "max", "pct_change",
    "rank", "rolling", "shift", "std", "sum", "where",
})
_FACTOR_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "svquant_factor_generation",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "factor_name", "factor_code", "description", "used_fields",
                "used_library_methods", "assumptions", "warnings",
            ],
            "properties": {
                "factor_name": {"type": "string"},
                "factor_code": {"type": "string"},
                "description": {"type": "string"},
                "used_fields": {"type": "array", "items": {"type": "string"}},
                "used_library_methods": {"type": "array", "items": {"type": "string"}},
                "assumptions": {"type": "array", "items": {"type": "string"}},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}
_IDEMPOTENCY: dict[str, tuple[str, FactorGenerationResponse]] = {}
_IDEMPOTENCY_LOCK = Lock()


@dataclass(frozen=True)
class ProviderSettings:
    base_url: str
    api_key: str
    model: str


def generate_factor(req: FactorGenerationRequest) -> FactorGenerationResponse:
    """调用 Provider，解析输出，并在返回前执行静态校验。"""
    request_hash = _request_hash(req)
    key = str(req.idempotency_key)
    with _IDEMPOTENCY_LOCK:
        existing = _IDEMPOTENCY.get(key)
        if existing is not None:
            if existing[0] != request_hash:
                raise HTTPException(409, "idempotency_key 已用于不同请求")
            return existing[1]

    settings = _settings_from_env()
    started_at = time.perf_counter()
    try:
        raw_content = _call_provider(settings, _messages(req))
    except TimeoutError as exc:
        raise HTTPException(504, "AI 供应商请求超时") from exc
    except ProviderUnavailable as exc:
        raise HTTPException(503, "AI 供应商暂不可用") from exc

    response = _validate_provider_output(raw_content, settings.model, started_at)
    with _IDEMPOTENCY_LOCK:
        # 竞争请求也只保留首次完成的结果，避免重复计费结果不一致。
        existing = _IDEMPOTENCY.setdefault(key, (request_hash, response))
    if existing[0] != request_hash:
        raise HTTPException(409, "idempotency_key 已用于不同请求")
    return existing[1]


def _settings_from_env() -> ProviderSettings:
    # ``ARK_API_KEY`` 与火山方舟官方 SDK 示例保持一致；前者是本服务的专用配置名。
    api_key = os.environ.get("AI_FACTOR_API_KEY") or os.environ.get("ARK_API_KEY")
    if not api_key:
        raise HTTPException(503, "AI 因子生成服务尚未配置")
    return ProviderSettings(
        base_url=os.environ.get(
            "AI_FACTOR_BASE_URL", "https://ark.cn-beijing.volces.com/api/plan/v3"
        ).rstrip("/"),
        api_key=api_key,
        model=os.environ.get("AI_FACTOR_MODEL_ALIAS", "ark-code-latest"),
    )


def _messages(req: FactorGenerationRequest) -> list[dict[str, str]]:
    libraries = ", ".join(req.context.allowed_library_names) or "无"
    system = (
        "你是 SVQuant 因子生成器。只输出 JSON 对象，不要 Markdown。"
        "JSON 必须有 factor_name、factor_code、description、used_fields、"
        "used_library_methods、assumptions、warnings。factor_code 必须只含一个 "
        "def 方法，第一个参数为 self。只可读取字段："
        f"{', '.join(sorted(ALLOWED_FIELDS))}。禁止 import、文件、网络、动态执行、"
        "双下划线属性和投资建议。不要调用 self.get_data、self.get_field 或任何未列出的 "
        "self 方法。合法示例：def momentum_20(self, window=20):\n"
        "    return self.close.pct_change(window)"
    )
    user = (
        f"研究想法：{req.prompt}\n"
        f"频率：{req.context.frequency}\n"
        f"股票池：{req.context.universe or '未指定'}\n"
        f"可用内置库：{libraries}\n"
        f"偏好名称：{req.context.preferred_factor_name or '由你命名'}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _call_provider(settings: ProviderSettings, messages: list[dict[str, str]]) -> str:
    payload = {
        "model": settings.model,
        "messages": messages,
        "temperature": 0.1,
        "response_format": _FACTOR_RESPONSE_SCHEMA,
    }
    try:
        body = _send_completion(settings, payload)
    except urllib.error.HTTPError as exc:
        if not _response_format_is_unsupported(exc):
            raise ProviderUnavailable from exc
        # 部分方舟模型不支持 json_schema；仍以受控提示词和本地 JSON/AST 校验保障边界。
        payload.pop("response_format")
        try:
            body = _send_completion(settings, payload)
        except (urllib.error.HTTPError, urllib.error.URLError, KeyError, IndexError, TypeError, json.JSONDecodeError) as retry_exc:
            raise ProviderUnavailable from retry_exc
    except (urllib.error.URLError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ProviderUnavailable from exc
    return body["choices"][0]["message"]["content"]


def _send_completion(settings: ProviderSettings, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{settings.base_url}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _response_format_is_unsupported(error: urllib.error.HTTPError) -> bool:
    if error.code != 400:
        return False
    try:
        message = json.loads(error.read().decode("utf-8")).get("error", {}).get("message", "")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return "response_format.type" in message and "not supported" in message


class ProviderUnavailable(Exception):
    """供应商不可用；不向客户端暴露供应商原始异常。"""


def _validate_provider_output(raw: str, model: str, started_at: float) -> FactorGenerationResponse:
    latency_ms = round((time.perf_counter() - started_at) * 1000)
    generation_id = f"fg_{uuid4().hex}"
    try:
        data = json.loads(raw.strip())
        factor = GeneratedFactor.model_validate(data)
        errors = _validate_factor_code(factor)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        errors = [f"模型输出不是有效的因子草稿：{exc}"]
        factor = None

    validation = FactorGenerationValidation(
        status="passed" if not errors else "failed",
        capability_catalog_version=CATALOG_VERSION,
        errors=errors,
    )
    return FactorGenerationResponse(
        generation_id=generation_id,
        status="ready" if factor is not None and not errors else "rejected",
        factor=factor if not errors else None,
        validation=validation,
        meta=FactorGenerationMeta(
            model_alias=model, prompt_version=PROMPT_VERSION, latency_ms=latency_ms,
        ),
    )


def _validate_factor_code(factor: GeneratedFactor) -> list[str]:
    unknown_fields = sorted(set(factor.used_fields) - ALLOWED_FIELDS)
    if unknown_fields:
        return [f"used_fields 包含未登记字段：{', '.join(unknown_fields)}"]
    try:
        tree = ast.parse(factor.factor_code)
    except SyntaxError as exc:
        return [f"因子代码语法错误：{exc.msg}"]
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        return ["因子代码必须且只能包含一个函数定义"]
    function = tree.body[0]
    if function.name != factor.factor_name or not function.args.args or function.args.args[0].arg != "self":
        return ["函数名必须与 factor_name 一致，且第一个参数必须为 self"]
    if function.decorator_list:
        return ["因子代码不允许使用装饰器"]

    validator = _FactorAstValidator()
    validator.visit(tree)
    if validator.errors:
        return validator.errors
    try:
        # 因子回测实际会把函数缩进并包装为 FactorLibrary 子类；这里复用相同规则。
        from researchengine.api.runner import _wrap_factor_code

        compile(_wrap_factor_code(factor.factor_code), "<generated_factor>", "exec")
    except SyntaxError as exc:
        return [f"因子代码无法编译：{exc.msg}"]
    return []


class _FactorAstValidator(ast.NodeVisitor):
    """默认拒绝的 AST 检查器，仅接受简单面板计算表达式。"""

    _ALLOWED_NODES = {
        ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign,
        ast.Name, ast.Load, ast.Store, ast.Attribute, ast.Call, ast.Constant,
        ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow,
        ast.USub, ast.Compare, ast.Eq, ast.NotEq, ast.Gt, ast.GtE, ast.Lt, ast.LtE,
        ast.keyword,
    }

    def __init__(self):
        self.errors: list[str] = []

    def generic_visit(self, node):
        if type(node) not in self._ALLOWED_NODES:
            self.errors.append(f"不允许的代码结构：{type(node).__name__}")
            return
        super().generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr.startswith("__"):
            self.errors.append("不允许访问双下划线属性")
        if isinstance(node.value, ast.Name) and node.value.id == "self" and node.attr not in ALLOWED_FIELDS:
            self.errors.append(f"不允许的字段：{node.attr}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if not isinstance(node.func, ast.Attribute) or node.func.attr not in ALLOWED_METHODS:
            self.errors.append("只允许调用白名单中的面板方法")
        self.generic_visit(node)


def _request_hash(req: FactorGenerationRequest) -> str:
    content = json.dumps(req.model_dump(mode="json", exclude={"idempotency_key"}), sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()
