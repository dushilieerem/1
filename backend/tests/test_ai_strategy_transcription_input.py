# -*- coding: utf-8 -*-
"""策略转写输入预检（services.core.strategy_transcription_input）单测。

端点级契约（422 不触达模型、走 research.transcribe_strategy）见
`test_ai_transcription_contract.py` 与 `test_ai_strategy_transcription.py`。
"""
import unittest

from services.core.strategy_transcription_input import strategy_transcription_error


class StrategyTranscriptionInputTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
