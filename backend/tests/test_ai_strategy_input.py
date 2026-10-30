import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.routers import ai_strategy_generation as route
from services.core.ai_strategy_input import strategy_prompt_error


class AiStrategyInputTest(unittest.TestCase):
    def test_incomplete_input(self):
        for prompt in (None, {}, "", "   \n", "好", "你好！", "！！！？？？？？？", "😀😀😀😀😀😀"):
            self.assertIsNotNone(strategy_prompt_error(prompt))
        self.assertIn("2000", strategy_prompt_error("中" * 2001))

    def test_short_specific_request(self):
        for prompt in ("生成20日动量策略", "每5日调仓买入RSI最低10只", "动量Top30等权"):
            self.assertIsNone(strategy_prompt_error(prompt))

    def test_invalid_request_does_not_invoke_model(self):
        with patch.object(route, "run_task") as run:
            with self.assertRaises(HTTPException) as err:
                route.ai_strategy_generations({"prompt": "好"}, _user={"id": 1})
        self.assertEqual(err.exception.status_code, 422)
        self.assertIn("补充", str(err.exception.detail))
        run.assert_not_called()

    def test_unsupported_capability_rejected_without_calling_model(self):
        body = {
            "prompt": "用成交量做多空对冲策略",
            "context": {"frequency": "1d"},
            "idempotency_key": "44444444-4444-4444-4444-444444444444",
        }
        with patch.object(route, "run_task") as run:
            response = route.ai_strategy_generations(body, _user={"id": 1})
        run.assert_not_called()
        self.assertEqual(response["status"], "rejected")
        self.assertEqual(response["meta"]["model_alias"], "not_called")
        self.assertIn("成交量", response["validation"]["errors"][0])

    def test_valid_request_uses_router_task(self):
        body = {
            "prompt": "生成20日动量Top30等权策略",
            "context": {"frequency": "1d", "universe": "CSI300"},
            "idempotency_key": "55555555-5555-5555-5555-555555555555",
        }
        rejected = {"content": "{}", "model": "m", "data": {"strategy": None, "errors": ["策略类名必须与 strategy_name 一致"]}}
        with patch.object(route, "run_task", return_value=rejected) as run:
            response = route.ai_strategy_generations(body, _user={"id": 1})
        self.assertEqual(run.call_args.args[0], "research.generate_strategy")
        self.assertEqual(response["status"], "rejected")
        self.assertIsNone(response["strategy"])
        self.assertEqual(response["validation"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
