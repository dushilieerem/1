# -*- coding: utf-8 -*-
"""AI 策略转写（ADR-037 P1-4）：确定性校验、输出解析与端点响应契约。"""
import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from ai.errors import AiNotConfigured, AiTimeout, AiUpstreamError
from ai.router.tasks.strategy_transcription import parse_generation
from app.routers import ai_transcription as route
from services.strategy.transcription_validation import (
    capability_issues,
    detect_engine,
    parse_inventory,
    redact_secrets,
    resolve_issues,
    transcription_mappings,
    validate_transcribed_strategy,
)

JQ_EVENT = '''def initialize(context):
    g.stocks = get_index_stocks('000905.XSHG')
    run_daily(trade, time='open')

def trade(context):
    hist = attribute_history(g.stocks, 20, '1d', ['close'])
    for s in g.stocks:
        order_target_percent(s, 0.1)
'''

JQ_MINUTE = '''def initialize(context):
    run_daily(check, time='every_bar')

def check(context):
    for s in get_index_stocks('000300.XSHG'):
        bars = get_price(s, count=30, frequency='1m', fields=['close'])
        if bars.close.iloc[-1] > bars.close.mean():
            order_target_percent(s, 0.05)
'''

JQ_ROE = '''def initialize(context):
    run_daily(check, time='open')

def check(context):
    df = get_fundamentals(query(indicator.roe).filter(indicator.roe > 15))
    for s in get_index_stocks('000300.XSHG'):
        order_target_value(s, 10000)
'''

JQ_VECTORIZED = '''def initialize(context):
    prices = get_price('000001.XSHE', count=21, fields=['close'])
'''

JQ_PE = '''def initialize(context):
    run_daily(check, time='open')

def check(context):
    df = get_fundamentals(query(valuation.pe_ratio).filter(valuation.pe_ratio < 20))
    for s in get_index_stocks('000300.XSHG'):
        order_target_value(s, 10000)
'''

EVENT_CODE = '''class RsiReversalEventStrategy:
    required_fields = frozenset({"close"})

    def initialize(self, context):
        context.schedule.daily(self.rebalance)

    def rebalance(self, context):
        close = context.data.history(context.data.symbols, ["close"], 21)["close"]
        if close.empty:
            return
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rsi = 100 - 100 / (1 + gain / loss.replace(0, float("nan")))
        latest = rsi.iloc[-1]
        for symbol in context.data.symbols:
            value = latest.get(symbol)
            if value != value:
                continue
            held = context.portfolio.quantity(symbol) > 0
            if value < 30 and not held:
                equity = context.portfolio.cash + sum(
                    context.portfolio.quantity(s) * close[s].iloc[-1]
                    for s in context.portfolio.positions
                )
                context.orders.target_value(symbol, equity * 0.1)
            elif value > 70 and held:
                context.orders.close(symbol)
'''

VECTORIZED_CODE = '''import pandas as pd

class MomentumTop3Strategy:
    def __init__(self, close):
        self.close = close

    def generate_signals(self):
        momentum = self.close.pct_change(20)
        ranks = momentum.rank(axis=1, ascending=False, method="first")
        weights = pd.DataFrame(0.0, index=self.close.index, columns=self.close.columns)
        weights[ranks <= 3] = 1.0 / 3
        return weights
'''

VALID_KEY = "11111111-1111-1111-1111-111111111111"


def model_output(code=EVENT_CODE, name="RsiReversalEventStrategy") -> str:
    return json.dumps(
        {
            "strategy_name": name,
            "strategy_code": code,
            "description": "由聚宽策略转写的受控草稿。",
            "used_fields": ["close"],
            "assumptions": [],
            "warnings": ["仅为研究草稿，需回测验证。"],
        },
        ensure_ascii=False,
    )


def strategy(code=EVENT_CODE, name="RsiReversalEventStrategy", fields=("close",)) -> dict:
    return {
        "strategy_name": name,
        "strategy_code": code,
        "description": "草稿",
        "used_fields": list(fields),
        "assumptions": [],
        "warnings": [],
    }


def body(code=JQ_EVENT, *, accepted=None, report_only=False, engine_mode="auto") -> dict:
    return {
        "code": code,
        "context": {
            "target": {"engine_mode": engine_mode},
            "accepted_degradations": list(accepted or []),
            "report_only": report_only,
        },
        "idempotency_key": VALID_KEY,
    }


def router_output(raw: str, engine: str = "event", model: str = "test-model") -> dict:
    return {"content": raw, "model": model, "data": parse_generation(raw, engine)}


class InventoryTest(unittest.TestCase):
    def test_event_markers_select_event_engine(self):
        self.assertEqual(detect_engine(JQ_EVENT, "auto"), "event")
        self.assertEqual(detect_engine("x = 1", "auto"), "vectorized")
        self.assertEqual(detect_engine(JQ_EVENT, "vectorized"), "vectorized")

    def test_inventory_collects_calls_imports_and_classes(self):
        inventory = parse_inventory("import pandas as pd\nclass A:\n    def f(self):\n        return pd.DataFrame()\n")
        self.assertTrue(inventory["imports"])
        self.assertTrue(inventory["calls"])
        self.assertEqual(inventory["classes"][0]["name"], "A")
        self.assertEqual(inventory["functions"][0]["name"], "f")


class CapabilityTest(unittest.TestCase):
    def codes(self, source):
        return {item["code"] for item in capability_issues(source, parse_inventory(source))}

    def test_event_source_reports_known_degradations(self):
        self.assertTrue({"SEMANTIC-UNIVERSE", "SEMANTIC-ORDER", "SEMANTIC-FQ"} <= self.codes(JQ_EVENT))

    def test_minute_source_is_blocker(self):
        issue = next(
            item
            for item in capability_issues(JQ_MINUTE, parse_inventory(JQ_MINUTE))
            if item["code"] == "API-UNSUPPORTED"
        )
        self.assertEqual(issue["severity"], "blocker")
        self.assertIn("daily_approx", {opt["id"] for opt in issue["options"]})

    def test_financial_source_is_blocker(self):
        issues = capability_issues(JQ_ROE, parse_inventory(JQ_ROE))
        issue = next(item for item in issues if item["code"] == "DATA-MISSING")
        self.assertEqual(issue["severity"], "blocker")

    def test_pe_source_is_degraded_not_blocked(self):
        source = JQ_PE
        inventory = parse_inventory(source)
        issue = next(
            item for item in capability_issues(source, inventory) if item["code"] == "SEMANTIC-DATA"
        )
        self.assertEqual(issue["severity"], "degraded")
        mapping = next(item for item in transcription_mappings(source, inventory) if item["jq"] == "get_fundamentals")
        self.assertEqual(mapping["status"], "degraded")

    def test_security_and_lookahead_are_detected(self):
        codes = self.codes("import os\nos.system('x')\nvalue = close.shift(-1)\n")
        self.assertIn("SECURITY-IO", codes)
        self.assertIn("LOOKAHEAD", codes)

    def test_g_import_is_blocked(self):
        codes = self.codes("from jqdata import *\n" + JQ_EVENT)
        self.assertIn("CONTRACT-IMPORT", codes)

    def test_resolve_issues_accepts_generatable_degradation(self):
        issues = capability_issues(JQ_MINUTE, parse_inventory(JQ_MINUTE))
        resolved, notes, unresolved = resolve_issues(issues, {"daily_approx"})
        minute = next(item for item in resolved if item["code"] == "API-UNSUPPORTED")
        self.assertEqual(minute["severity"], "degraded")
        self.assertTrue(minute["accepted"])
        self.assertFalse(unresolved)
        self.assertTrue(any(note.startswith("已接受降级") for note in notes))

    def test_redact_secrets_masks_credentials(self):
        redacted = redact_secrets("API_KEY = 'sk-abcdefghijklmnop'\nTOKEN: 'abc1234567890'")
        self.assertNotIn("sk-abcdefghijklmnop", redacted)
        self.assertNotIn("abc1234567890", redacted)
        self.assertIn("***REDACTED***", redacted)


class StaticValidationTest(unittest.TestCase):
    def test_vectorized_template_passes(self):
        checks, errors = validate_transcribed_strategy(
            strategy(VECTORIZED_CODE, "MomentumTop3Strategy"), "vectorized"
        )
        self.assertEqual(errors, [])
        self.assertTrue(all(item["status"] == "pass" for item in checks))

    def test_event_template_passes(self):
        self.assertEqual(validate_transcribed_strategy(strategy(), "event")[1], [])

    def test_class_name_must_match(self):
        errors = validate_transcribed_strategy(strategy(name="Other"), "event")[1]
        self.assertIn("策略类名必须与 strategy_name 一致", errors[0])

    def test_unsafe_generated_code_fails_security_check(self):
        unsafe = "import os\n\nclass Bad:\n    def initialize(self, context):\n        os.system('echo bad')\n"
        checks, errors = validate_transcribed_strategy(strategy(unsafe, "Bad"), "event")
        self.assertIn("禁止文件/网络/命令执行调用", errors)
        security = next(item for item in checks if item["id"] == "security")
        self.assertEqual(security["status"], "fail")

    def test_event_contract_requires_initialize(self):
        code = EVENT_CODE.replace("def initialize(self, context):", "def start(self, context):")
        self.assertIn("initialize", validate_transcribed_strategy(strategy(code), "event")[1][0])

    def test_unregistered_field_rejected(self):
        errors = validate_transcribed_strategy(strategy(fields=("close", "roe")), "event")[1]
        self.assertIn("未登记字段", errors[0])

    def test_future_data_rejected(self):
        code = VECTORIZED_CODE.replace("self.close.pct_change(20)", "self.close.shift(-1)")
        checks, errors = validate_transcribed_strategy(
            strategy(code, "MomentumTop3Strategy"), "vectorized"
        )
        self.assertIn("禁止负周期 shift（未来数据）", errors)
        future = next(item for item in checks if item["id"] == "future_data")
        self.assertEqual(future["status"], "fail")


class ParseTest(unittest.TestCase):
    def test_ready_strategy(self):
        parsed = parse_generation(model_output(), "event")
        self.assertEqual(parsed["errors"], [])
        self.assertEqual(parsed["strategy"]["strategy_name"], "RsiReversalEventStrategy")
        self.assertEqual([item["status"] for item in parsed["checks"]], ["pass"] * 5)

    def test_non_json_is_business_failure_not_exception(self):
        parsed = parse_generation("oops", "event")
        self.assertIsNone(parsed["strategy"])
        self.assertTrue(parsed["errors"][0].startswith("模型输出不是有效的策略草稿"))
        self.assertEqual(parsed["checks"][0]["status"], "fail")

    def test_non_object_json_is_rejected(self):
        parsed = parse_generation("[]", "event")
        self.assertTrue(parsed["errors"])
        self.assertIsNone(parsed["strategy"])

    def test_wrong_array_type_is_rejected(self):
        raw = model_output().replace('"used_fields": ["close"]', '"used_fields": "close"')
        self.assertIn("数组字段类型不正确", parse_generation(raw, "event")["errors"][0])


class RouteContractTest(unittest.TestCase):
    def setUp(self):
        route._IDEMPOTENCY.clear()

    def call(self, payload, output):
        with patch.object(route, "run_task", return_value=output) as run:
            return route.ai_strategy_transcriptions(payload, _user={"id": 1}), run

    def test_ready_response_matches_re_contract(self):
        response, run = self.call(body(), router_output(model_output()))
        self.assertEqual(run.call_args.args[0], "research.transcribe_strategy")
        self.assertEqual(
            set(response),
            {
                "transcription_id", "status", "verdict", "target_engine", "runnable",
                "requires_ack", "summary", "issues", "mappings", "assumptions",
                "checks", "errors", "strategy", "meta",
            },
        )
        self.assertTrue(response["transcription_id"].startswith("st_"))
        self.assertEqual(response["status"], "ready")
        self.assertEqual(response["verdict"], "degraded")
        self.assertEqual(response["target_engine"], "event")
        self.assertTrue(response["runnable"])
        self.assertTrue(response["requires_ack"])
        self.assertEqual(response["strategy"]["strategy_name"], "RsiReversalEventStrategy")
        self.assertEqual(response["errors"], [])
        self.assertEqual([item["status"] for item in response["checks"]], ["pass"] * 5)
        self.assertTrue({"SEMANTIC-UNIVERSE", "SEMANTIC-ORDER", "SEMANTIC-FQ"} <= {
            item["code"] for item in response["issues"]
        })
        self.assertEqual(
            set(response["meta"]),
            {"model_alias", "prompt_version", "capability_catalog_version", "data_version", "latency_ms"},
        )
        self.assertEqual(response["meta"]["prompt_version"], "v1")
        self.assertEqual(response["meta"]["capability_catalog_version"], "2026-10-29")
        self.assertEqual(response["meta"]["data_version"], "unknown")
        self.assertEqual(response["meta"]["model_alias"], "test-model")

    def test_vectorized_request_uses_vectorized_checks(self):
        response, _ = self.call(
            body(JQ_VECTORIZED, engine_mode="vectorized"),
            router_output(model_output(VECTORIZED_CODE, "MomentumTop3Strategy"), "vectorized"),
        )
        self.assertEqual(response["target_engine"], "vectorized")
        self.assertEqual(response["status"], "ready")
        self.assertEqual(response["strategy"]["strategy_code"], VECTORIZED_CODE)

    def test_minute_strategy_needs_input_without_model_call(self):
        with patch.object(route, "run_task") as run:
            response = route.ai_strategy_transcriptions(body(JQ_MINUTE), _user={"id": 1})
        run.assert_not_called()
        self.assertEqual(response["status"], "needs_input")
        self.assertEqual(response["verdict"], "blocked")
        self.assertFalse(response["runnable"])
        self.assertTrue(response["requires_ack"])
        self.assertIsNone(response["strategy"])
        self.assertEqual(response["checks"], [])
        self.assertIn("API-UNSUPPORTED", {item["code"] for item in response["issues"]})
        self.assertEqual(response["meta"]["model_alias"], "not_called")

    def test_accepted_degradation_unblocks_minute_strategy(self):
        response, _ = self.call(
            body(JQ_MINUTE, accepted=["daily_approx"]),
            router_output(model_output()),
        )
        self.assertEqual(response["status"], "ready")
        minute = next(item for item in response["issues"] if item["code"] == "API-UNSUPPORTED")
        self.assertEqual(minute["severity"], "degraded")
        self.assertTrue(minute["accepted"])
        self.assertTrue(any("已接受降级" in note for note in response["assumptions"]))

    def test_report_only_returns_no_code(self):
        response, run = self.call(
            body(report_only=True), router_output(model_output())
        )
        run.assert_not_called()
        self.assertEqual(response["status"], "report_only")
        self.assertFalse(response["runnable"])
        self.assertFalse(response["requires_ack"])
        self.assertIsNone(response["strategy"])
        self.assertEqual(response["checks"], [])
        self.assertTrue(response["issues"])

    def test_unsafe_generated_code_is_rejected(self):
        unsafe = "import os\n\nclass BadStrategy:\n    def initialize(self, context):\n        os.system('echo bad')\n"
        response, _ = self.call(body(), router_output(model_output(unsafe, "BadStrategy")))
        self.assertEqual(response["status"], "rejected")
        self.assertIsNone(response["strategy"])
        self.assertTrue(response["errors"])
        security = next(item for item in response["checks"] if item["id"] == "security")
        self.assertEqual(security["status"], "fail")
        self.assertIn("CONTRACT-GENERATED", {item["code"] for item in response["issues"]})

    def test_422_precheck_never_calls_model(self):
        cases = [
            {"code": ""},
            {"code": "x" * 200_001},
            {"code": JQ_EVENT, "idempotency_key": "not-a-uuid"},
            body(JQ_EVENT, engine_mode="unsupported"),
            {"code": JQ_EVENT, "extra": 1},
            {"code": JQ_EVENT, "context": {"accepted_degradations": "daily_approx"}},
            {"code": JQ_EVENT, "context": {"report_only": "yes"}},
            {"code": JQ_EVENT, "context": {"target": {"initial_capital": 0}}},
        ]
        for payload in cases:
            with self.subTest(payload=str(payload)[:60]):
                with patch.object(route, "run_task") as run:
                    with self.assertRaises(HTTPException) as err:
                        route.ai_strategy_transcriptions(payload, _user={"id": 1})
                self.assertEqual(err.exception.status_code, 422)
                run.assert_not_called()

    def test_idempotency_returns_cached_and_rejects_conflict(self):
        output = router_output(model_output())
        with patch.object(route, "run_task", return_value=output) as run:
            first = route.ai_strategy_transcriptions(body(), _user={"id": 1})
            second = route.ai_strategy_transcriptions(body(), _user={"id": 1})
        self.assertEqual(first["transcription_id"], second["transcription_id"])
        self.assertEqual(run.call_count, 1)
        with self.assertRaises(HTTPException) as err:
            route.ai_strategy_transcriptions(body(JQ_VECTORIZED), _user={"id": 1})
        self.assertEqual(err.exception.status_code, 409)

    def test_upstream_errors_map_to_http_status(self):
        for exc, status in (
            (AiNotConfigured("no key"), 503),
            (AiTimeout("slow"), 504),
            (AiUpstreamError("boom"), 502),
        ):
            with self.subTest(status=status):
                with patch.object(route, "run_task", side_effect=exc):
                    with self.assertRaises(HTTPException) as err:
                        route.ai_strategy_transcriptions(body(), _user={"id": 1})
                self.assertEqual(err.exception.status_code, status)


class EndpointHttpTest(unittest.TestCase):
    """经 FastAPI 路由层验证路径、状态码与 JSON 字段（含 null 字段）。"""

    def setUp(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(route.router)
        app.dependency_overrides[route.require_user] = lambda: {"id": 1}
        self.client = TestClient(app)
        route._IDEMPOTENCY.clear()

    def test_ready_json_keeps_re_null_fields(self):
        with patch.object(route, "run_task", return_value=router_output(model_output())):
            response = self.client.post("/api/ai/strategy-transcriptions", json=body())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        issue = next(item for item in data["issues"] if item["code"] == "SEMANTIC-UNIVERSE")
        self.assertIn("accepted", issue)
        self.assertIsNone(issue["accepted"])
        self.assertEqual(data["strategy"]["warnings"], ["仅为研究草稿，需回测验证。"])
        self.assertIsNone(data["checks"][0]["line"])
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["meta"]["prompt_version"], "v1")

    def test_http_422_and_409(self):
        with patch.object(route, "run_task") as run:
            bad = self.client.post(
                "/api/ai/strategy-transcriptions",
                json={"code": "", "idempotency_key": VALID_KEY},
            )
        self.assertEqual(bad.status_code, 422)
        self.assertIsInstance(bad.json()["detail"], str)
        run.assert_not_called()

        with patch.object(route, "run_task", return_value=router_output(model_output())):
            self.assertEqual(
                self.client.post("/api/ai/strategy-transcriptions", json=body()).status_code, 200
            )
        conflict = self.client.post(
            "/api/ai/strategy-transcriptions", json=body(JQ_VECTORIZED)
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["detail"], "idempotency_key 已用于不同请求")


if __name__ == "__main__":
    unittest.main()
