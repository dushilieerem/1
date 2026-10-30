# -*- coding: utf-8 -*-
"""策略转写端点的现行契约快照（P1-4 迁移前先钉住行为）。

转写目前仍转发研究计算服务。迁移到本地 task 时，本文件描述的
输入校验、路径与超时口径必须保持不变；届时把它改成对 `ai.router` 的断言即可。
"""
import importlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.core.strategy_transcription_input import strategy_transcription_error


class StrategyTranscriptionContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # HTTP 全部被 mock，测试不依赖部署用 .env
        with patch.dict(sys.modules, {"services.core.re_config": SimpleNamespace(RE_BASE="http://127.0.0.1:9")}):
            cls.gateway = importlib.import_module("app.routers.re_gateway")

    def test_input_precheck_rejects_obvious_garbage(self):
        for body in (None, {}, {"code": ""}, {"code": "   "}, {"code": 123}, {"code": "x" * 200_001}):
            self.assertIsNotNone(strategy_transcription_error(body))
        self.assertIsNotNone(strategy_transcription_error({"code": "x", "context": {"report_only": "yes"}}))
        self.assertIsNotNone(
            strategy_transcription_error({"code": "x", "context": {"accepted_degradations": [1]}})
        )

    def test_input_precheck_accepts_valid_payload(self):
        body = {"code": "def initialize(context): pass", "context": {"report_only": True, "accepted_degradations": ["x"]}}
        self.assertIsNone(strategy_transcription_error(body))

    def test_invalid_request_never_reaches_upstream(self):
        with patch.object(self.gateway, "forward_re") as forward:
            response = self.gateway.ai_strategy_transcriptions({"code": ""}, _user={"id": 1})
        self.assertEqual(response.status_code, 422)
        forward.assert_not_called()

    def test_valid_request_forwards_path_and_long_timeout(self):
        body = {"code": "def initialize(context): pass", "context": {}}
        with patch.object(self.gateway, "forward_re", return_value=(200, {}, {"status": "ok"})) as forward:
            self.gateway.ai_strategy_transcriptions(body, _user={"id": 1})
        forward.assert_called_once_with(
            "POST", "/api/ai/strategy-transcriptions", payload=body, timeout=600
        )


if __name__ == "__main__":
    unittest.main()
