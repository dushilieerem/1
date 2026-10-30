# -*- coding: utf-8 -*-
"""策略转写迁入本地 `ai.router` 后的契约（ADR-037 P1-4）。

原 re_gateway 转发断言改为：合法请求经 `research.transcribe_strategy` 执行，
422 前置校验不触达模型；输入校验、路径与超时口径保持不变。
"""
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from ai.router import get_task
from app.routers import ai_transcription as route
from services.core.strategy_transcription_input import strategy_transcription_error

VALID_BODY = {
    "code": "def initialize(context):\n    pass",
    "context": {"target": {"engine_mode": "auto"}},
    "idempotency_key": "22222222-2222-2222-2222-222222222222",
}


class StrategyTranscriptionContractTest(unittest.TestCase):
    def setUp(self):
        route._IDEMPOTENCY.clear()

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

    def test_task_spec_keeps_re_model_parameters(self):
        spec = get_task("research.transcribe_strategy")
        self.assertEqual(spec.slot, "code")
        self.assertEqual(spec.temperature, 0.1)
        self.assertIsNone(spec.max_tokens)
        self.assertEqual(spec.timeout_sec, 600)
        self.assertIsNotNone(spec.response_format)
        self.assertIsNotNone(spec.prompt)
        self.assertIsNotNone(spec.validator)

    def test_invalid_request_never_reaches_model(self):
        with patch.object(route, "run_task") as run:
            with self.assertRaises(HTTPException) as err:
                route.ai_strategy_transcriptions({"code": ""}, _user={"id": 1})
        self.assertEqual(err.exception.status_code, 422)
        self.assertIn("粘贴", str(err.exception.detail))
        run.assert_not_called()

    def test_valid_request_goes_through_registered_router_task(self):
        rejected = {
            "content": "{}",
            "model": "m",
            "data": {
                "strategy": None,
                "checks": [],
                "errors": ["策略类名必须与 strategy_name 一致"],
            },
        }
        with patch.object(route, "run_task", return_value=rejected) as run:
            response = route.ai_strategy_transcriptions(VALID_BODY, _user={"id": 1})
        self.assertEqual(run.call_args.args, ("research.transcribe_strategy",))
        variables = run.call_args.kwargs["variables"]
        self.assertEqual(variables["code"], VALID_BODY["code"])
        self.assertEqual(variables["target_engine"], "event")
        self.assertIn("issues", variables)
        self.assertIn("mappings", variables)
        self.assertEqual(response["status"], "rejected")
        self.assertTrue(response["errors"])
        self.assertEqual(response["meta"]["prompt_version"], "v1")


if __name__ == "__main__":
    unittest.main()
