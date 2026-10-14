import importlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class ProxyValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 单测不依赖本机 .env，且所有 HTTP 调用均被 mock。
        with patch.dict(sys.modules, {"services.core.re_config": SimpleNamespace(RE_BASE="http://127.0.0.1:9")}):
            cls.proxy = importlib.import_module("services.factor.re_factor_async_proxy")

    def test_empty_code_cannot_fall_back_to_library(self):
        with patch.object(self.proxy, "request_json") as request:
            status, _, result = self.proxy.proxy_submit_factor_backtest({"factor_code": " ", "factor_name": "factor", "library_name": "classic_indicators"})
            self.assertEqual(status, 400)
            self.assertIn("不能为空", result["error"])
            request.assert_not_called()

    def test_builtin_passthrough_unchanged(self):
        body = {"factor_name": "SV01_0001", "library_name": "classic_indicators"}
        with patch.object(self.proxy, "request_json", return_value=(202, {}, {"run_id": "123"})) as request:
            status, headers, response = self.proxy.proxy_submit_factor_backtest(body)
            self.assertEqual(request.call_args.kwargs["payload"], body)
            self.assertEqual(status, 202)
            self.assertEqual(headers["Location"], "/api/backtest/factor/123")
            self.assertEqual(response["poll_url"], "/api/backtest/factor/123")

    def test_execution_timing_forwarded_unchanged(self):
        body = {
            "factor_name": "SV01_0001",
            "library_name": "classic_indicators",
            "execution_timing": "next_open",
        }
        with patch.object(self.proxy, "request_json", return_value=(202, {}, {"run_id": "123"})) as request:
            self.proxy.proxy_submit_factor_backtest(body)
            self.assertEqual(
                request.call_args.kwargs["payload"]["execution_timing"], "next_open"
            )

    def test_execution_timing_absent_is_left_to_research_engine(self):
        # 默认值归 RE 定义，SVQuant 不补——否则默认值会有两个来源。
        body = {"factor_name": "SV01_0001", "library_name": "classic_indicators"}
        with patch.object(self.proxy, "request_json", return_value=(202, {}, {"run_id": "123"})) as request:
            self.proxy.proxy_submit_factor_backtest(body)
            self.assertNotIn("execution_timing", request.call_args.kwargs["payload"])

    def test_invalid_execution_timing_is_rejected_before_http(self):
        body = {
            "factor_name": "SV01_0001",
            "library_name": "classic_indicators",
            "execution_timing": "same_open",
        }
        with patch.object(self.proxy, "request_json") as request:
            status, _, result = self.proxy.proxy_submit_factor_backtest(body)
            self.assertEqual(status, 400)
            self.assertIn("execution_timing", result["error"])
            request.assert_not_called()

    def test_guarded_code_forwarded_without_mutating_source_snapshot(self):
        source = "def factor(self):\n    return self.close.pct_change(100000)"
        body = {"factor_name": "factor", "factor_code": source, "_svquant_ui": {"source": source}}
        with patch.object(self.proxy, "request_json", return_value=(202, {}, {"run_id": "123"})) as request:
            self.proxy.proxy_submit_factor_backtest(body)
            forwarded = request.call_args.kwargs["payload"]
            self.assertIn("没有有效数值", forwarded["factor_code"])
            self.assertNotIn("_svquant_ui", forwarded)
            self.assertEqual(body["factor_code"], source)


if __name__ == "__main__":
    unittest.main()
