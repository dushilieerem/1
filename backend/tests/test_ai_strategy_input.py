import json
import importlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.core.ai_strategy_input import strategy_prompt_error


class AiStrategyInputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # HTTP均被mock，测试不应依赖部署用.env。
        with patch.dict(sys.modules, {"services.core.re_config": SimpleNamespace(RE_BASE="http://127.0.0.1:9")}):
            cls.gateway = importlib.import_module("app.routers.re_gateway")

    def test_incomplete_input(self):
        for prompt in (None, {}, "", "   \n", "好", "你好！", "！！！？？？？？？", "😀😀😀😀😀😀"):
            self.assertIsNotNone(strategy_prompt_error(prompt))
        self.assertIn("2000", strategy_prompt_error("中" * 2001))

    def test_short_specific_request(self):
        for prompt in ("生成20日动量策略", "每5日调仓买入RSI最低10只", "动量Top30等权"):
            self.assertIsNone(strategy_prompt_error(prompt))

    def test_invalid_request_does_not_invoke_model(self):
        with patch.object(self.gateway, "forward_re") as forward:
            response = self.gateway.ai_strategy_generations({"prompt": "好"}, _user={"id": 1})
        self.assertEqual(response.status_code, 422)
        self.assertIn("补充", json.loads(response.body)["detail"])
        forward.assert_not_called()

    def test_valid_request_and_validation_failure_pass_through(self):
        body = {"prompt": "生成20日动量策略", "idempotency_key": "original", "context": {"frequency": "1d"}}
        rejected = {"status": "rejected", "validation": {"status": "failed", "errors": ["只允许调用白名单中的面板方法"]}}
        with patch.object(self.gateway, "forward_re", return_value=(200, {}, rejected)) as forward:
            response = self.gateway.ai_strategy_generations(body, _user={"id": 1})
        forward.assert_called_once_with("POST", "/api/ai/strategy-generations", payload=body, timeout=600)
        self.assertEqual(json.loads(response.body), rejected)


if __name__ == "__main__":
    unittest.main()
