# -*- coding: utf-8 -*-
"""策略/因子回测结果可信签名（P0-04）。

BFF 在拿到 RE 回测结果后签发 HMAC；前端保存运行记录时回传 token。
`save_run` 校验 token 后才把 `verified` 置为 true；策略广场发布只接受
verified 的源运行。token 只绑定用户 + 结果规范化哈希，不绑定易变的请求字段。

规范化必须跨 Python/JavaScript 一致：结果经浏览器 ``JSON.parse`` /
``JSON.stringify`` 往返后，``954.0`` 会变成 ``954``、``1e-07`` 会变成
``1e-7``、``-0.0`` 会变成 ``0``。因此这里按 ECMAScript Number-to-string
规则输出数字，而不是直接使用 ``json.dumps`` 的 Python 浮点格式。
旧版 Python 规范化签出的 token 仍可验签（兼容历史数据）。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
from decimal import Decimal
from typing import Any

from services.core.env_config import env

PREFIX = "v1:"
_DROP_KEYS = {"code_hash", "_svquant_verified_token", "_svquant_ui"}
_MAX_SAFE_INT = 2**53


def _secret() -> bytes:
    raw = (env("RESULT_SIGNING_KEY", "") or "").strip()
    if not raw:
        raw = (env("JWT_SECRET_KEY", "") or "svquant-dev-result-key").strip()
    return hashlib.sha256(b"svquant-result:" + raw.encode("utf-8")).digest()


def _canonical(value: Any) -> Any:
    """旧版规范化：仅用于兼容历史 token，勿再用于新签名。"""
    if isinstance(value, dict):
        return {
            str(k): _canonical(v)
            for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))
            if str(k) not in _DROP_KEYS
        }
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    return value


def _legacy_result_hash(result: Any) -> str:
    raw = json.dumps(_canonical(result), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _js_number(value: int | float) -> str:
    """按 ECMAScript Number::toString(10) 规范化一个数字。"""
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) <= _MAX_SAFE_INT:
            return str(value)
        value = float(value)
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return "null"
    if number == 0:
        return "0"

    sign = "-" if number < 0 else ""
    decimal = Decimal(repr(abs(number)))
    _, digits_tuple, exponent = decimal.as_tuple()
    digits = list(digits_tuple)
    # repr 可能带尾随 0（如 954.0 的 Decimal 是 9540E-1），先归一成最短有效数字。
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1

    digit_text = "".join(str(d) for d in digits)
    k = len(digit_text)
    n = k + exponent  # 小数点位置：value = 0.digits * 10**n

    if k <= n <= 21:
        body = digit_text + "0" * (n - k)
    elif 0 < n <= 21:
        body = digit_text[:n] + "." + digit_text[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digit_text
    else:
        exp = n - 1
        mantissa = digit_text[0] + ("." + digit_text[1:] if k > 1 else "")
        body = mantissa + "e" + ("+" if exp >= 0 else "-") + str(abs(exp))
    return sign + body


def _canonical_json(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return _js_number(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical_json(v) for v in value) + "]"
    if isinstance(value, dict):
        items = sorted(
            ((str(k), v) for k, v in value.items() if str(k) not in _DROP_KEYS),
            key=lambda kv: kv[0],
        )
        return "{" + ",".join(
            json.dumps(k, ensure_ascii=False) + ":" + _canonical_json(v)
            for k, v in items
        ) + "}"
    return json.dumps(str(value), ensure_ascii=False)


def result_hash(result: Any) -> str:
    return hashlib.sha256(_canonical_json(result).encode("utf-8")).hexdigest()


def _digest(user_id: int, result_hash_value: str) -> str:
    return hmac.new(
        _secret(),
        f"{int(user_id)}|{result_hash_value}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def sign_result(user_id: int, result: Any) -> str:
    return PREFIX + _digest(int(user_id), result_hash(result))


def verify_result(user_id: int, result: Any, token: str | None) -> bool:
    if not token or not str(token).startswith(PREFIX):
        return False
    token_text = str(token)
    if hmac.compare_digest(token_text, sign_result(user_id, result)):
        return True
    # 兼容旧版 Python-only 规范化签出的历史 token。
    legacy = PREFIX + _digest(int(user_id), _legacy_result_hash(result))
    return hmac.compare_digest(token_text, legacy)


__all__ = ["result_hash", "sign_result", "verify_result"]
