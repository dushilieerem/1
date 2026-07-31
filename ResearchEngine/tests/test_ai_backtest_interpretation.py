"""AI 回测解读 API 的确定性证据、降级与边界测试。"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from researchengine.api import ai_interpretation, app


client = TestClient(app)


def _curve(days: int) -> list[dict[str, object]]:
    start = date(2024, 1, 1)
    return [
        {"date": (start + timedelta(days=index)).isoformat(), "value": 1.0 + index * 0.002}
        for index in range(days)
    ]


def _payload(key=None, days=80) -> dict:
    return {
        "backtest_type": "strategy",
        "result": {
            "metrics": {"turnover": 0.12, "sharpe": 1.1},
            "equity_curve": _curve(days),
            "benchmark_curve": _curve(days),
            "error": None,
        },
        "run_context": {"validation_scheme": "in_sample", "commission_rate": 0.0},
        "focus": "robustness",
        "idempotency_key": str(key or uuid4()),
    }


def test_interpretation_returns_deterministic_evidence_and_research_first_experiments(monkeypatch):
    monkeypatch.delenv("AI_BACKTEST_INTERPRETATION_API_KEY", raising=False)
    monkeypatch.delenv("AI_FACTOR_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    ai_interpretation._IDEMPOTENCY.clear()

    response = client.post("/api/ai/backtest-interpretations", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["mode"] == "deterministic_fallback"
    assert body["evidence"]["result_fingerprint"].startswith("sha256:")
    assert "NO_OUT_OF_SAMPLE" in body["evidence"]["warnings"]
    assert body["interpretation"]["experiments"][0]["experiment_id"] == "EXPAND_SAMPLE"
    assert all(item["manual_only"] for item in body["interpretation"]["experiments"])


def test_interpretation_returns_insufficient_without_calling_provider(monkeypatch):
    ai_interpretation._IDEMPOTENCY.clear()
    monkeypatch.setenv("AI_BACKTEST_INTERPRETATION_API_KEY", "test-key")
    monkeypatch.setattr(ai_interpretation, "_provider_order", lambda *args: (_ for _ in ()).throw(AssertionError()))

    response = client.post("/api/ai/backtest-interpretations", json=_payload(days=59))

    assert response.status_code == 200
    assert response.json()["status"] == "insufficient"
    assert response.json()["mode"] == "not_applicable"


def test_interpretation_idempotency_reuses_the_same_result(monkeypatch):
    monkeypatch.delenv("AI_BACKTEST_INTERPRETATION_API_KEY", raising=False)
    monkeypatch.delenv("AI_FACTOR_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    ai_interpretation._IDEMPOTENCY.clear()
    key = uuid4()

    first = client.post("/api/ai/backtest-interpretations", json=_payload(key))
    second = client.post("/api/ai/backtest-interpretations", json=_payload(key))

    assert first.status_code == second.status_code == 200
    assert first.json()["interpretation_id"] == second.json()["interpretation_id"]


def test_interpretation_rejects_non_increasing_equity_dates():
    body = _payload()
    body["result"]["equity_curve"] = list(reversed(body["result"]["equity_curve"]))

    response = client.post("/api/ai/backtest-interpretations", json=body)

    assert response.status_code == 422
