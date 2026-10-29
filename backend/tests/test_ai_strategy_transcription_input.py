import importlib
import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.core.strategy_transcription_input import strategy_transcription_error


class StrategyTranscriptionInputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # HTTP 均被 mock，测试不依赖部署用 .env。
        with patch.dict(sys.modules, {"services.core.re_config": SimpleNamespace(RE_BASE="http://127.0.0.1:9")}):
            cls.gateway = importlib.import_module("app.routers.re_gateway")

    def test_incomplete_or_invalid_input(self):
        for body in (
            None,
            {},
            {"code": None},
            {"code": 123},
            {"code": ""},
            {"code": "   \n"},
            {"code": "x", "context": []},
            {"code": "x", "context": {"accepted_degradations": "daily_approx"}},
            {"code": "x", "context": {"accepted_degradations": [1]}},
            {"code": "x", "context": {"report_only": "yes"}},
        ):
            self.assertIsNotNone(strategy_transcription_error(body))
        self.assertIn("200,000", strategy_transcription_error({"code": "x" * 200_001}))

    def test_valid_request(self):
        body = {
            "code": "def initialize(context):\n    pass",
            "context": {
                "target": {"engine_mode": "auto", "universe": "CSI500"},
                "accepted_degradations": ["daily_approx"],
                "report_only": False,
            },
            "idempotency_key": "8ecb2eb2-6f7f-4d64-93b2-7e63b34ff2a8",
        }
        self.assertIsNone(strategy_transcription_error(body))

    def test_invalid_request_does_not_invoke_re(self):
        with patch.object(self.gateway, "forward_re") as forward:
            response = self.gateway.ai_strategy_transcriptions({"code": ""}, _user={"id": 1})
        self.assertEqual(response.status_code, 422)
        self.assertIn("粘贴", json.loads(response.body)["detail"])
        forward.assert_not_called()

    def test_needs_input_response_passes_through(self):
        body = {
            "code": "def initialize(context):\n    pass",
            "context": {"target": {"engine_mode": "auto"}},
            "idempotency_key": "key-1",
        }
        upstream = {
            "status": "needs_input",
            "verdict": "blocked",
            "runnable": False,
            "issues": [{"code": "API-UNSUPPORTED", "severity": "blocker"}],
        }
        with patch.object(self.gateway, "forward_re", return_value=(200, {}, upstream)) as forward:
            response = self.gateway.ai_strategy_transcriptions(body, _user={"id": 1})
        forward.assert_called_once_with(
            "POST",
            "/api/ai/strategy-transcriptions",
            payload=body,
            timeout=600,
        )
        self.assertEqual(json.loads(response.body), upstream)


if __name__ == "__main__":
    unittest.main()
