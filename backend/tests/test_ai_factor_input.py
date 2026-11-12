import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.routers import ai_factor_generation as route
from services.core.ai_factor_input import factor_prompt_error


class AiFactorInputTest(unittest.TestCase):
    def test_incomplete_input(self):
        for prompt in (None, {}, "", "   \n", "好", "你好！", "！！！？？？？？？", "😀😀😀😀😀😀"):
            self.assertIsNotNone(factor_prompt_error(prompt))
        self.assertIn("2000", factor_prompt_error("中" * 2001))

    def test_formula_and_short_specific_request(self):
        for prompt in ("生成20日动量因子", "close / close.shift(20) - 1", "14日RSI"):
            self.assertIsNone(factor_prompt_error(prompt))

    def test_invalid_request_does_not_invoke_model(self):
        with patch.object(route, "run_task") as run:
            with self.assertRaises(HTTPException) as err:
                route.ai_factor_generations({"prompt": "好"}, _user={"id": 1})
        self.assertEqual(err.exception.status_code, 422)
        self.assertIn("补充", str(err.exception.detail))
        run.assert_not_called()

    def test_valid_request_uses_router_task_and_returns_contract(self):
        body = {
            "prompt": "生成20日收盘价波动率因子",
            "context": {"frequency": "1d"},
            "idempotency_key": "33333333-3333-3333-3333-333333333333",
        }
        rejected = {
            "content": "{}",
            "model": "m",
            "data": {"outcome": "unsupported", "reason": "缺少数据", "factor": None, "errors": ["需求暂不支持：缺少数据"]},
        }
        with patch.object(route, "run_task", return_value=rejected) as run:
            response = route.ai_factor_generations(body, _user={"id": 1})
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], "research.generate_factor")
        self.assertEqual(response["status"], "rejected")
        self.assertEqual(response["validation"]["status"], "failed")
        self.assertIsNone(response["factor"])


if __name__ == "__main__":
    unittest.main()
