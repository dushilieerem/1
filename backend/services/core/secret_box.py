# -*- coding: utf-8 -*-
"""敏感配置加密（P0-08）：AES-256-GCM，密文格式 `enc:v1:<base64>`。

主密钥优先读 `SECRET_ENCRYPTION_KEY`（base64 32 字节）；未配置时从
`JWT_SECRET_KEY` 派生（仅本地/过渡；生产必须单独配置并轮换）。
"""
from __future__ import annotations

import base64
import hashlib
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from services.core.env_config import env

PREFIX = "enc:v1:"


def _master_key() -> bytes:
    raw = (env("SECRET_ENCRYPTION_KEY", "") or "").strip()
    if raw:
        try:
            key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
            if len(key) == 32:
                return key
        except Exception:
            pass
        # 非 base64 时按口令派生，避免启动失败。
        return hashlib.sha256(raw.encode("utf-8")).digest()
    seed = (env("JWT_SECRET_KEY", "") or "svquant-dev-secret").encode("utf-8")
    return hashlib.sha256(b"svquant-secret-box:" + seed).digest()


def is_encrypted(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt_secret(value: str) -> str:
    plain = value or ""
    if not plain or is_encrypted(plain):
        return plain
    key = _master_key()
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plain.encode("utf-8"), b"svquant-secret")
    return PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_secret(value: str) -> str:
    raw = value or ""
    if not is_encrypted(raw):
        return raw
    try:
        blob = base64.urlsafe_b64decode(raw[len(PREFIX):].encode("ascii"))
        nonce, ciphertext = blob[:12], blob[12:]
        return AESGCM(_master_key()).decrypt(nonce, ciphertext, b"svquant-secret").decode("utf-8")
    except Exception:
        return ""


__all__ = ["decrypt_secret", "encrypt_secret", "is_encrypted"]
