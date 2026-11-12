# -*- coding: utf-8 -*-
"""AI 因子生成（ADR-037 P1-3）：输出解析、静态校验、自动修正与响应契约。"""
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from ai.errors import AiNotConfigured
from app.routers import ai_factor_generation as route
from ai.router.tasks.factor_generation import is_request_rejection, parse_generation

VALID_CODE = "def ret_5d(self, window=5):\n    return self.close.pct_change(window, fill_method=None)\n"


def model_output(**overrides):
    data = {
        "factor_name": "ret_5d",
        "factor_code": VALID_CODE,
        "description": "5 日收益率",
        "used_fields": ["close"],
        "used_library_methods": [],
        "assumptions": [],
        "warnings": [],
        "outcome": "factor",
        "reason": "",
        "minimum_history": "至少 6 个收盘价",
        "missing_value_handling": "缺失保留为空",
    }
    data.update(overrides)
    return __import__("json").dumps(data, ensure_ascii=False)


def body(**overrides):
    data = {
        "prompt": "用过去 5 日收盘价计算收益率因子",
        "context": {"universe": "CSI300", "frequency": "1d", "allowed_library_names": [], "preferred_factor_name": None},
        "idempotency_key": "22222222-2222-2222-2222-222222222222",
    }
    data.update(overrides)
    return data


class ParseTest(unittest.TestCase):
    def test_valid_factor_ready(self):
        parsed = parse_generation(model_output())
        self.assertEqual(parsed["errors"], [])
        self.assertEqual(parsed["factor"]["factor_name"], "ret_5d")
        self.assertIn("历史数据要求：至少 6 个收盘价", parsed["factor"]["assumptions"])

    def test_unsupported_and_clarification_are_business_results(self):
        for outcome, label in (("unsupported", "需求暂不支持"), ("needs_clarification", "请补充因子需求")):
            with self.subTest(outcome=outcome):
                parsed = parse_generation(model_output(outcome=outcome, reason="缺少窗口"))
                self.assertIsNone(parsed["factor"])
                self.assertTrue(parsed["errors"][0].startswith(label))
                self.assertTrue(is_request_rejection(parsed["errors"]))

    def test_missing_doc_fields_are_validation_errors(self):
        parsed = parse_generation(model_output(minimum_history=""))
        self.assertIn("生成说明缺少历史数据要求", parsed["errors"][0])
        self.assertFalse(is_request_rejection(parsed["errors"]))

    def test_unsafe_code_rejected(self):
        parsed = parse_generation(model_output(factor_code="def ret_5d(self):\n    return self.close.shift(-1)\n"))
        self.assertTrue(parsed["errors"])
        self.assertTrue(parsed["errors"][0].startswith("禁止未来数据"))

    def test_non_json_is_upstream_failure(self):
        from ai.errors import AiBadOutput

        with self.assertRaises(AiBadOutput):
            parse_generation("not json")


class RouteTest(unittest.TestCase):
    def response(self, raw, model="m"):
        return {
            "content": raw,
            "model": model,
            "provider": "ark",
            "tokens_in": 1,
            "tokens_out": 1,
            "data": parse_generation(raw),
        }

    def test_ready_response_shape(self):
        with patch.object(route, "run_task", return_value=self.response(model_output())):
            out = route._generate(route._validate(body()))
        self.assertEqual(out["status"], "ready")
        self.assertTrue(out["generation_id"].startswith("fg_"))
        self.assertEqual(out["validation"]["status"], "passed")
        self.assertEqual(out["meta"]["prompt_version"], "v3")

    def test_rejected_when_code_invalid_and_repair_fails(self):
        first = self.response(model_output(factor_code="def ret_5d(self):\n    return self.close.shift(-1)\n"))
        with patch.object(route, "run_task", side_effect=[first, first]):
            out = route._generate(route._validate(body()))
        self.assertEqual(out["status"], "rejected")
        self.assertIsNone(out["factor"])
        self.assertEqual(out["validation"]["status"], "failed")

    def test_repair_succeeds_on_second_attempt(self):
        bad = self.response(model_output(factor_code="def ret_5d(self):\n    return self.close.shift(-1)\n"))
        good = self.response(model_output())
        with patch.object(route, "run_task", side_effect=[bad, good]) as call:
            out = route._generate(route._validate(body()))
        self.assertEqual(out["status"], "ready")
        self.assertEqual(call.call_count, 2)
        repair_messages = call.call_args.kwargs["messages"]
        self.assertEqual(repair_messages[-1]["role"], "user")
        self.assertIn("静态校验", repair_messages[-1]["content"])

    def test_repair_error_keeps_first_result(self):
        bad = self.response(model_output(factor_code="def ret_5d(self):\n    return self.close.shift(-1)\n"))
        with patch.object(route, "run_task", side_effect=[bad, AiNotConfigured("no key")]):
            out = route._generate(route._validate(body()))
        self.assertEqual(out["status"], "rejected")
        self.assertIn("自动修正暂未完成", out["validation"]["warnings"][0])

    def test_bad_requests_rejected_before_calling_model(self):
        for override in (
            {"prompt": ""},
            {"prompt": "x" * 2001},
            {"context": {"frequency": "1h"}},
            {"idempotency_key": "not-a-uuid"},
        ):
            with self.subTest(override=override):
                with self.assertRaises(HTTPException) as err:
                    route._validate(body(**override))
                self.assertEqual(err.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
