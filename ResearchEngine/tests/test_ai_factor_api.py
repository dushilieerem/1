"""AI 因子生成 API 的契约与安全边界测试。"""

from __future__ import annotations

import json
from io import BytesIO
from uuid import uuid4
from urllib.error import HTTPError

import pandas as pd
import numpy as np
from fastapi.testclient import TestClient

from app.api import ai_factor, ai_strategy
from app.main import app
from app.schemas.backtest import GeneratedFactor, GeneratedStrategy


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
    assert settings.model == "ark-code-latest"


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


def _strategy_payload(key=None):
    return {
        "prompt": "生成一个 20 日动量 Top 3 等权日频策略",
        "context": {"frequency": "1d", "preferred_strategy_name": "MomentumTop3Strategy"},
        "idempotency_key": str(key or uuid4()),
    }


def _strategy_provider_output(code):
    return json.dumps({
        "strategy_name": "MomentumTop3Strategy",
        "strategy_code": code,
        "description": "持有动量最高的三只股票。",
        "used_fields": ["close"],
        "assumptions": [],
        "warnings": ["这是研究草稿，需经回测验证。"],
    })


def _configure_strategy_provider(monkeypatch, code):
    monkeypatch.setenv("AI_STRATEGY_API_KEY", "test-key")
    monkeypatch.setattr(
        ai_strategy, "_call_provider", lambda settings, messages: _strategy_provider_output(code)
    )
    ai_strategy._IDEMPOTENCY.clear()


def test_strategy_generation_returns_validated_vectorized_draft(monkeypatch):
    _configure_strategy_provider(monkeypatch, '''import pandas as pd

class MomentumTop3Strategy:
    def __init__(self, close):
        self.close = close

    def generate_signals(self):
        momentum = self.close.pct_change(20)
        ranks = momentum.rank(axis=1, ascending=False, method="first")
        weights = pd.DataFrame(0.0, index=self.close.index, columns=self.close.columns)
        weights[ranks <= 3] = 1.0 / 3
        return weights''')

    response = client.post("/api/ai/strategy-generations", json=_strategy_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["validation"]["status"] == "passed"
    assert body["strategy"]["strategy_name"] == "MomentumTop3Strategy"


def test_strategy_generation_rejects_unsafe_code(monkeypatch):
    _configure_strategy_provider(monkeypatch, '''import os

class MomentumTop3Strategy:
    def __init__(self, close):
        self.close = close

    def generate_signals(self):
        return self.close''')

    response = client.post("/api/ai/strategy-generations", json=_strategy_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["strategy"] is None


def test_strategy_generation_idempotency(monkeypatch):
    calls = []
    code = '''import pandas as pd

class MomentumTop3Strategy:
    def __init__(self, close):
        self.close = close

    def generate_signals(self):
        return pd.DataFrame(0.0, index=self.close.index, columns=self.close.columns)'''
    monkeypatch.setenv("AI_STRATEGY_API_KEY", "test-key")
    monkeypatch.setattr(
        ai_strategy,
        "_call_provider",
        lambda settings, messages: calls.append(1) or _strategy_provider_output(code),
    )
    ai_strategy._IDEMPOTENCY.clear()
    key = uuid4()

    first = client.post("/api/ai/strategy-generations", json=_strategy_payload(key))
    second = client.post("/api/ai/strategy-generations", json=_strategy_payload(key))

    assert first.status_code == second.status_code == 200
    assert first.json()["generation_id"] == second.json()["generation_id"]
    assert len(calls) == 1


def test_strategy_validator_allows_target_weight_matrix():
    strategy = GeneratedStrategy(
        strategy_name="MomentumTop3Strategy",
        strategy_code='''import pandas as pd

class MomentumTop3Strategy:
    def __init__(self, close):
        self.close = close

    def generate_signals(self):
        weights = pd.DataFrame(0.0, index=self.close.index, columns=self.close.columns)
        return weights''',
        description="空仓权重矩阵。",
        used_fields=["close"],
    )

    assert ai_strategy._validate_strategy_code(strategy) == []


def test_strategy_validator_allows_twenty_day_momentum_top_thirty_rebalance():
    strategy = GeneratedStrategy(
        strategy_name="MomentumTop30Strategy",
        strategy_code='''import pandas as pd

class MomentumTop30Strategy:
    def __init__(self, close):
        self.close = close

    def generate_signals(self):
        momentum = self.close.pct_change(20)
        ranks = momentum.rank(axis=1, ascending=False, method="first")
        targets = (ranks <= 30) * (1.0 / 30)
        rebalance = pd.DataFrame(False, index=self.close.index, columns=self.close.columns)
        rebalance.iloc[::20] = True
        return targets.where(rebalance).ffill().fillna(0.0)''',
        description="每 20 日持有动量最高的 30 只股票。",
        used_fields=["close"],
    )

    assert ai_strategy._validate_strategy_code(strategy) == []

    namespace = {}
    exec(strategy.strategy_code, namespace)
    close = pd.DataFrame(
        {f"stock_{number:02d}": range(number, number + 45) for number in range(31)}
    )
    weights = namespace["MomentumTop30Strategy"](close).generate_signals()
    assert weights.iloc[:20].sum(axis=1).eq(0.0).all()
    assert np.isclose(weights.iloc[20:].sum(axis=1), 1.0).all()


def test_strategy_validator_allows_ma_deviation_top_ten():
    strategy = GeneratedStrategy(
        strategy_name="MaDeviationTop10Strategy",
        strategy_code='''import pandas as pd

class MaDeviationTop10Strategy:
    def __init__(self, close):
        self.close = close

    def generate_signals(self):
        ma20 = self.close.rolling(20).mean()
        deviation = (self.close / ma20 - 1.0).abs()
        ranks = deviation.rank(axis=1, ascending=False, method="first")
        return (ranks <= 10) * 0.1''',
        description="每日持有偏离 20 日均线最大的 10 只股票。",
        used_fields=["close"],
    )

    assert ai_strategy._validate_strategy_code(strategy) == []


def test_strategy_validator_allows_daily_equal_weight_for_ma_signal():
    strategy = GeneratedStrategy(
        strategy_name="MaSignalStrategy",
        strategy_code='''import pandas as pd

class MaSignalStrategy:
    def __init__(self, close):
        self.close = close

    def generate_signals(self):
        selected = self.close.rolling(5).mean() > self.close.rolling(20).mean()
        return selected.astype(float).div(selected.sum(axis=1), axis=0).fillna(0.0)''',
        description="每日等权持有短均线高于长均线的股票。",
        used_fields=["close"],
    )

    assert ai_strategy._validate_strategy_code(strategy) == []


def test_strategy_generation_rejects_prompt_outside_close_long_only_scope(monkeypatch):
    calls = []
    monkeypatch.setattr(ai_strategy, "_call_provider", lambda *args: calls.append(1))
    ai_strategy._IDEMPOTENCY.clear()

    response = client.post("/api/ai/strategy-generations", json={
        "prompt": "用 numpy 和 talib 计算 RSI，再做多空对冲。",
        "context": {"frequency": "1d"},
        "idempotency_key": str(uuid4()),
    })

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert "外部计算库" in response.json()["validation"]["errors"][0]
    assert "多空策略" in response.json()["validation"]["errors"][0]
    assert calls == []


def test_strategy_generation_prompt_contains_validated_templates():
    prompt = ai_strategy._messages(_strategy_payload_to_request())[0]["content"]

    assert "rebalance.iloc[::REBALANCE_DAYS] = True" in prompt
    assert "selected.astype(float).div(selected.sum(axis=1), axis=0).fillna(0.0)" in prompt


def _strategy_payload_to_request():
    from app.schemas.backtest import StrategyGenerationRequest

    return StrategyGenerationRequest.model_validate(_strategy_payload())
