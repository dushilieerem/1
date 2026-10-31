# -*- coding: utf-8 -*-
"""策略回测结果可信签名（P0-04）。

BFF 在拿到 RE 回测结果后签发 HMAC；前端保存运行记录时回传 token。
`save_run` 校验 token 后才把 `verified` 置为 true；策略广场发布只接受
verified 的源运行。token 只绑定用户 + 结果规范化哈希，不绑定易变的请求字段。
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from services.core.env_config import env

PREFIX = "v1:"
_DROP_KEYS = {"code_hash", "_svquant_verified_token", "_svquant_ui"}


def _secret() -> bytes:
    raw = (env("RESULT_SIGNING_KEY", "") or "").strip()
    if not raw:
        raw = (env("JWT_SECRET_KEY", "") or "svquant-dev-result-key").strip()
    return hashlib.sha256(b"svquant-result:" + raw.encode("utf-8")).digest()


def _canonical(value: Any) -> Any:
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


def result_hash(result: Any) -> str:
    raw = json.dumps(_canonical(result), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sign_result(user_id: int, result: Any) -> str:
    digest = hmac.new(_secret(), f"{int(user_id)}|{result_hash(result)}".encode("utf-8"), hashlib.sha256).hexdigest()
    return PREFIX + digest


def verify_result(user_id: int, result: Any, token: str | None) -> bool:
    if not token or not str(token).startswith(PREFIX):
        return False
    expected = sign_result(user_id, result)
    return hmac.compare_digest(str(token), expected)


__all__ = ["result_hash", "sign_result", "verify_result"]
