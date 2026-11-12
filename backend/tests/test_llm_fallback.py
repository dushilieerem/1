# -*- coding: utf-8 -*-
"""P1-A03：模型兜底、重试与结果缓存。"""
from __future__ import annotations

import json
import sys

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai.errors import AiTimeout  # noqa: E402
from ai.gateway import providers  # noqa: E402


class _Resp:
    def __init__(self, data: dict) -> None:
        self._raw = json.dumps(data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def read(self) -> bytes:
        return self._raw


def _ok(model: str) -> _Resp:
    return _Resp(
        {
            "model": model,
            "choices": [{"message": {"content": f"from {model}"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4},
        }
    )


def _target(model: str, provider: str = "ark") -> providers.ChatTarget:
    return providers.ChatTarget(
        provider=provider,
        base_url="http://llm.local/v1",
        api_key="k",
        model=model,
        timeout=5,
    )


def test_fallback_model_used_when_primary_times_out(monkeypatch) -> None:
    env = {
        "LLM_FALLBACK_MODELS": "backup",
        "LLM_MAX_RETRIES": "0",
        "LLM_CACHE_TTL_SEC": "0",
    }
    monkeypatch.setattr(providers, "env", lambda k, d=None: env.get(k, d))
    monkeypatch.setattr(
        providers,
        "resolve_target",
        lambda model=None, **kw: _target(model) if model else _target("primary"),
    )

    calls: list[str] = []

    def fake_send(target, payload, *, timeout, stream):
        calls.append(target.model)
        if target.model == "primary":
            raise AiTimeout("primary down")
        return _ok(target.model)

    monkeypatch.setattr(providers, "_send", fake_send)
    out = providers.complete(_target("primary"), messages=[{"role": "user", "content": "hi"}])
    assert calls == ["primary", "backup"]
    assert out["content"] == "from backup"
    assert out["fallback_from"] == "primary"


def test_retry_same_model_before_fallback(monkeypatch) -> None:
    env = {"LLM_MAX_RETRIES": "1", "LLM_CACHE_TTL_SEC": "0"}
    monkeypatch.setattr(providers, "env", lambda k, d=None: env.get(k, d))
    monkeypatch.setattr(providers.time, "sleep", lambda _s: None)

    calls = {"n": 0}

    def fake_send(target, payload, *, timeout, stream):
        calls["n"] += 1
        if calls["n"] == 1:
            raise AiTimeout("transient")
        return _ok(target.model)

    monkeypatch.setattr(providers, "_send", fake_send)
    out = providers.complete(_target("primary"), messages=[{"role": "user", "content": "hi"}])
    assert calls["n"] == 2
    assert out["content"] == "from primary"


def test_cache_hit_skips_upstream(monkeypatch) -> None:
    env = {"LLM_CACHE_TTL_SEC": "60", "LLM_MAX_RETRIES": "0"}
    monkeypatch.setattr(providers, "env", lambda k, d=None: env.get(k, d))
    monkeypatch.setattr(providers, "_CACHE", providers._CompletionCache())

    calls = {"n": 0}

    def fake_send(target, payload, *, timeout, stream):
        calls["n"] += 1
        return _ok(target.model)

    monkeypatch.setattr(providers, "_send", fake_send)
    target = _target("primary")
    first = providers.complete(target, messages=[{"role": "user", "content": "hi"}])
    second = providers.complete(target, messages=[{"role": "user", "content": "hi"}])
    assert calls["n"] == 1
    assert second["cached"] is True
    assert second["content"] == first["content"]


def _truncated() -> _Resp:
    return _Resp(
        {
            "model": "primary",
            "choices": [{"message": {"content": "", "reasoning_content": "thinking..."}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3000, "completion_tokens_details": {"reasoning_tokens": 3000}},
        }
    )


def test_normalize_detects_reasoning_token_exhaustion() -> None:
    from ai.errors import AiOutputTruncated

    with pytest.raises(AiOutputTruncated) as exc:
        providers._normalize(
            {
                "choices": [{"message": {"content": "", "reasoning_content": "x" * 100}, "finish_reason": "length"}],
                "usage": {"completion_tokens": 3000, "completion_tokens_details": {"reasoning_tokens": 3000}},
            },
            _target("primary"),
            max_tokens=3000,
        )
    assert "3000" in exc.value.detail
    assert "reasoning_tokens" in exc.value.detail


def test_normalize_keeps_finish_reason_and_reasoning_usage() -> None:
    out = providers._normalize(
        {
            "model": "primary",
            "choices": [
                {
                    "message": {"content": '{"ok":true}', "reasoning_content": "short"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 30, "completion_tokens_details": {"reasoning_tokens": 20}},
        },
        _target("primary"),
        max_tokens=3000,
    )
    assert out["content"] == '{"ok":true}'
    assert out["finish_reason"] == "stop"
    assert out["reasoning_tokens"] == 20
    assert out["reasoning_chars"] == 5


def test_complete_expands_max_tokens_after_truncation(monkeypatch) -> None:
    env = {"LLM_MAX_RETRIES": "0", "LLM_CACHE_TTL_SEC": "0", "LLM_MAX_OUTPUT_TOKENS": "32000"}
    monkeypatch.setattr(providers, "env", lambda k, d=None: env.get(k, d))
    monkeypatch.setattr(providers.time, "sleep", lambda _s: None)

    budgets: list[int] = []

    def fake_send(target, payload, *, timeout, stream):
        budgets.append(int(payload.get("max_tokens") or 0))
        if len(budgets) == 1:
            return _truncated()
        return _ok(target.model)

    monkeypatch.setattr(providers, "_send", fake_send)
    out = providers.complete(
        _target("primary"), messages=[{"role": "user", "content": "hi"}], max_tokens=3000
    )
    assert budgets == [3000, 6000]
    assert out["content"] == "from primary"


def test_content_filter_empty_is_not_retried(monkeypatch) -> None:
    env = {"LLM_MAX_RETRIES": "2", "LLM_CACHE_TTL_SEC": "0"}
    monkeypatch.setattr(providers, "env", lambda k, d=None: env.get(k, d))
    calls = {"n": 0}

    def fake_send(target, payload, *, timeout, stream):
        calls["n"] += 1
        return _Resp(
            {
                "choices": [{"message": {"content": ""}, "finish_reason": "content_filter"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 0},
            }
        )

    monkeypatch.setattr(providers, "_send", fake_send)
    import pytest

    with pytest.raises(Exception) as exc:
        providers.complete(_target("primary"), messages=[{"role": "user", "content": "hi"}], max_tokens=3000)
    assert "内容审核" in str(exc.value)
    assert calls["n"] == 1
