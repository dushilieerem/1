"""AI 因子生成 API 的契约与安全边界测试。"""

from __future__ import annotations

import json
from io import BytesIO
from uuid import uuid4
from urllib.error import HTTPError

from fastapi.testclient import TestClient

from researchengine.api import ai_factor, app
from researchengine.api.schemas import GeneratedFactor


client = TestClient(app)


def _payload(key=None):
    return {
        "prompt": "生成一个 20 日动量并以成交量确认的日频因子",
        "context": {"frequency": "1d", "preferred_factor_name": "volume_momentum"},
        "idempotency_key": str(key or uuid4()),
    }


def _provider_output(code):
    return __import__("json").dumps({
        "factor_name": "volume_momentum",
        "factor_code": code,
        "description": "20 日动量乘以相对成交量。",
        "used_fields": ["close", "volume"],
        "used_library_methods": [],
        "assumptions": [],
        "warnings": ["这是研究草稿，需经回测验证。"],
    })


def _configure_provider(monkeypatch, code):
    monkeypatch.setenv("AI_FACTOR_API_KEY", "test-key")
    monkeypatch.setattr(ai_factor, "_call_provider", lambda settings, messages: _provider_output(code))
    ai_factor._IDEMPOTENCY.clear()


def test_factor_generation_returns_validated_draft(monkeypatch):
    _configure_provider(monkeypatch, '''def volume_momentum(self, window=20):
    momentum = self.close.pct_change(window)
    volume_ratio = self.volume / self.volume.rolling(window).mean()
    return momentum * volume_ratio''')

    response = client.post("/api/ai/factor-generations", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["validation"]["status"] == "passed"
    assert body["factor"]["factor_name"] == "volume_momentum"


def test_factor_generation_rejects_unsafe_code(monkeypatch):
    _configure_provider(monkeypatch, '''def volume_momentum(self):
    import os
    return self.close''')

    response = client.post("/api/ai/factor-generations", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["factor"] is None
    assert body["validation"]["errors"]


def test_factor_generation_idempotency_does_not_repeat_provider_call(monkeypatch):
    calls = []
    code = '''def volume_momentum(self):
    return self.close.pct_change(20)'''
    monkeypatch.setenv("AI_FACTOR_API_KEY", "test-key")
    monkeypatch.setattr(ai_factor, "_call_provider", lambda settings, messages: calls.append(1) or _provider_output(code))
    ai_factor._IDEMPOTENCY.clear()
    key = uuid4()

    first = client.post("/api/ai/factor-generations", json=_payload(key))
    second = client.post("/api/ai/factor-generations", json=_payload(key))

    assert first.status_code == second.status_code == 200
    assert first.json()["generation_id"] == second.json()["generation_id"]
    assert len(calls) == 1


def test_factor_generation_rejects_reused_key_with_different_request(monkeypatch):
    _configure_provider(monkeypatch, '''def volume_momentum(self):
    return self.close.pct_change(20)''')
    key = uuid4()
    assert client.post("/api/ai/factor-generations", json=_payload(key)).status_code == 200
    changed = _payload(key)
    changed["prompt"] = "另一个研究想法"

    assert client.post("/api/ai/factor-generations", json=changed).status_code == 409


def test_volcengine_provider_requests_strict_json_schema(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices": [{"message": {"content": "{}"}}]}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(ai_factor.urllib.request, "urlopen", fake_urlopen)
    result = ai_factor._call_provider(
        ai_factor.ProviderSettings("https://example.test/v3", "test-key", "test-model"),
        [{"role": "user", "content": "test"}],
    )

    payload = json.loads(captured["request"].data)
    assert result == "{}"
    assert captured["request"].full_url.endswith("/chat/completions")
    assert captured["timeout"] == 20
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True


def test_volcengine_settings_accept_official_ark_api_key_name(monkeypatch):
    monkeypatch.delenv("AI_FACTOR_API_KEY", raising=False)
    monkeypatch.setenv("ARK_API_KEY", "test-key")

    settings = ai_factor._settings_from_env()

    assert settings.api_key == "test-key"
    assert settings.base_url == "https://ark.cn-beijing.volces.com/api/plan/v3"
    assert settings.model == "deepseek-v4-flash-260425"


def test_volcengine_provider_falls_back_when_json_schema_is_unsupported(monkeypatch):
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices": [{"message": {"content": "{}"}}]}'

    def fake_urlopen(request, timeout):
        requests.append(json.loads(request.data))
        if len(requests) == 1:
            raise HTTPError(
                request.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=BytesIO(b'{"error": {"message": "response_format.type is not supported"}}'),
            )
        return FakeResponse()

    monkeypatch.setattr(ai_factor.urllib.request, "urlopen", fake_urlopen)

    result = ai_factor._call_provider(
        ai_factor.ProviderSettings("https://example.test/v3", "test-key", "test-model"),
        [{"role": "user", "content": "test"}],
    )

    assert result == "{}"
    assert "response_format" in requests[0]
    assert "response_format" not in requests[1]


def test_factor_validator_allows_safe_panel_comparison():
    factor = GeneratedFactor(
        factor_name="volume_confirmed",
        factor_code="""def volume_confirmed(self, window=20):
    return self.volume > self.volume.rolling(window).mean()""",
        description="成交量高于均值。",
        used_fields=["volume"],
    )

    assert ai_factor._validate_factor_code(factor) == []
