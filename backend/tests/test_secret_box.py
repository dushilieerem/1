# -*- coding: utf-8 -*-
"""P0-08：敏感配置加密。"""
from __future__ import annotations

from services.core.secret_box import decrypt_secret, encrypt_secret, is_encrypted


def test_encrypt_roundtrip_and_no_plaintext() -> None:
    raw = "sk-test-123456"
    enc = encrypt_secret(raw)
    assert enc.startswith("enc:v1:")
    assert raw not in enc
    assert is_encrypted(enc)
    assert decrypt_secret(enc) == raw


def test_plaintext_passthrough_and_empty() -> None:
    assert decrypt_secret("legacy-plain") == "legacy-plain"
    assert encrypt_secret("") == ""
