import json
import unittest
from unittest.mock import patch

from services.core.backtest_params import validate_execution_timing


class ValidateExecutionTimingTest(unittest.TestCase):
    """共用的参数校验：非法值必须挡在转发之前。"""

    def test_valid_values_are_kept_and_trimmed(self):
        for code in ("same_close", "next_close", "next_open"):
            body = {"execution_timing": code}
            validate_execution_timing(body)
            self.assertEqual(body["execution_timing"], code)

        body = {"execution_timing": " next_open "}
        validate_execution_timing(body)
        self.assertEqual(body["execution_timing"], "next_open")

    def test_absent_value_is_left_to_research_engine(self):
        # 默认值归 RE 定义，SVQuant 再写一份会有两个来源。
        for body in ({}, {"execution_timing": None}, {"execution_timing": "   "}):
            validate_execution_timing(body)
            self.assertNotIn("execution_timing", body)

    def test_invalid_value_raises(self):
        with self.assertRaises(ValueError) as ctx:
            validate_execution_timing({"execution_timing": "same_open"})
        self.assertIn("execution_timing", str(ctx.exception))


class StrategyRouteExecutionTimingTest(unittest.TestCase):
    """策略回测路由：非法值返回 400 且不发起转发。"""

    def _call(self, body):
        from app.routers import re_gateway

        captured = {}

        def fake_forward(method, path, *, payload=None, query=None, timeout=120):
            captured["payload"] = payload
            return 200, {}, {"run_id": "r1"}

        with patch.object(re_gateway, "forward_re", side_effect=fake_forward):
            response = re_gateway.backtest_strategy_submit(body, _user={"id": "u"})
        return response, captured

    def test_invalid_value_is_rejected_before_forwarding(self):
        response, captured = self._call(
            {"strategy_code": "x", "execution_timing": "same_open"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("execution_timing", json.loads(response.body)["error"])
        self.assertNotIn("payload", captured)

    def test_valid_value_is_forwarded(self):
        response, captured = self._call(
            {"strategy_code": "x", "execution_timing": "next_open"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["payload"]["execution_timing"], "next_open")

    def test_absent_value_is_not_injected(self):
        _, captured = self._call({"strategy_code": "x"})
        self.assertNotIn("execution_timing", captured["payload"])


if __name__ == "__main__":
    unittest.main()
