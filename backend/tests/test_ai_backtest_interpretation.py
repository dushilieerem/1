# -*- coding: utf-8 -*-
"""回测解读：证据阈值、契约校验与模型排序降级（ADR-037 P1-2）。"""
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from fastapi import HTTPException

from ai.errors import AiBadOutput
from ai.router.specs import TaskRequest
from ai.router.tasks.backtest_interpretation import validate_order
from app.routers import ai_backtest
from services.research import backtest_evidence as ev


def curve(n=260, start=1.0, drift=0.001):
    day = date(2020, 1, 1)
    return [{"date": (day + timedelta(days=i)).isoformat(), "value": start * (1 + drift) ** i} for i in range(n)]


def request_body(points=None, **overrides):
    body = {
        "backtest_type": "strategy",
        "result": {"equity_curve": points if points is not None else curve(), "metrics": {"sharpe": 1.2}},
        "run_context": {"validation_scheme": "walk_forward", "commission_rate": 0.0003, "stamp_tax": 0.001, "slippage_rate": 0.0002},
        "focus": "overall",
        "idempotency_key": "11111111-1111-1111-1111-111111111111",
    }
    body.update(overrides)
    return body


class EvidenceTest(unittest.TestCase):
    def test_point_parsing_rejects_bad_series(self):
        self.assertIsNone(ev.valid_points([{"date": "2020-01-02", "value": 1}, {"date": "2020-01-01", "value": 2}]))
        self.assertIsNone(ev.valid_points([{"date": "2020-01-01", "value": 0}]))
        self.assertIsNone(ev.valid_points("nope"))
        self.assertEqual(ev.valid_points(None, required=False), [])

    def test_diagnostics_follow_research_engine_thresholds(self):
        points = ev.valid_points(curve())
        evidence, codes = ev.build_evidence(
            backtest_type="strategy",
            result={"metrics": {"turnover": 0.3}},
            run_context={"validation_scheme": "unknown", "commission_rate": 0, "stamp_tax": 0.001, "slippage_rate": 0.0002},
            points=points,
        )
        self.assertIn("NO_OUT_OF_SAMPLE", codes)
        self.assertIn("HIGH_TURNOVER", codes)
        self.assertIn("ZERO_COST_ASSUMPTION", codes)
        # validation_scheme 未知时，证据项状态为 unknown
        self.assertEqual(evidence["coverage"], "partial")

    def test_coverage_complete_when_all_fields_known(self):
        points = ev.valid_points(curve())
        evidence, codes = ev.build_evidence(
            backtest_type="strategy",
            result={
                "metrics": {"annual_return": 0.1, "sharpe": 1.2, "turnover": 0.05},
                "benchmark_curve": curve(drift=0.0005),
            },
            run_context={"validation_scheme": "out_of_sample", "commission_rate": 0.0003, "stamp_tax": 0.001, "slippage_rate": 0.0002},
            points=points,
        )
        self.assertEqual(evidence["coverage"], "complete")
        self.assertEqual(codes, [])

    def test_missing_cost_fields_make_coverage_partial(self):
        points = ev.valid_points(curve())
        evidence, codes = ev.build_evidence(
            backtest_type="strategy",
            result={"metrics": {}},
            run_context={"validation_scheme": "out_of_sample"},
            points=points,
        )
        self.assertIn("COST_ASSUMPTION_UNKNOWN", codes)
        self.assertEqual(evidence["coverage"], "partial")

    def test_deep_drawdown_and_weak_factor_signal(self):
        crashing = [{"date": (date(2020, 1, 1) + timedelta(days=i)).isoformat(), "value": 1.0 if i < 10 else 0.5} for i in range(300)]
        _, codes = ev.build_evidence(
            backtest_type="factor",
            result={"metrics": {}, "factor_analysis": {"ic_mean": 0.01}},
            run_context={"validation_scheme": "out_of_sample"},
            points=ev.valid_points(crashing),
        )
        self.assertIn("DEEP_DRAWDOWN", codes)
        self.assertIn("WEAK_FACTOR_SIGNAL", codes)

    def test_findings_and_experiments_are_linked(self):
        items = ev.findings(["NO_OUT_OF_SAMPLE", "DEEP_DRAWDOWN"])
        exps = ev.experiments(items)
        self.assertEqual([i["finding_id"] for i in items], ["finding_1", "finding_2"])
        self.assertEqual([e["priority"] for e in exps], [1, 2])
        self.assertEqual(exps[0]["experiment_id"], "ADD_OUT_OF_SAMPLE")
        self.assertTrue(exps[0]["manual_only"])


class BodyValidationTest(unittest.TestCase):
    def test_valid_body_normalised(self):
        req = ai_backtest._validate(request_body())
        self.assertEqual(req["focus"], "overall")
        self.assertEqual(req["idempotency_key"], "11111111-1111-1111-1111-111111111111")

    def test_rejects_bad_inputs(self):
        cases = [
            {"backtest_type": "unknown"},
            {"result": "nope"},
            {"focus": "nope"},
            {"question": "x" * 501},
            {"idempotency_key": "not-a-uuid"},
        ]
        for override in cases:
            with self.subTest(override=override):
                with self.assertRaises(HTTPException) as err:
                    ai_backtest._validate(request_body(**override))
                self.assertEqual(err.exception.status_code, 422)


class ResponseTest(unittest.TestCase):
    def test_short_series_is_insufficient(self):
        req = ai_backtest._validate(request_body(points=curve(30)))
        out = ai_backtest._build_response(req, 0.0)
        self.assertEqual(out["status"], "insufficient")
        self.assertEqual(out["mode"], "not_applicable")

    def test_business_error_is_rejected(self):
        body = request_body()
        body["result"]["error"] = "参数错误"
        req = ai_backtest._validate(body)
        out = ai_backtest._build_response(req, 0.0)
        self.assertEqual(out["status"], "rejected")
        self.assertIsNone(out["interpretation"])

    def test_without_model_keeps_deterministic_report(self):
        req = ai_backtest._validate(request_body())
        with patch.object(ai_backtest, "available_task", return_value=False):
            out = ai_backtest._build_response(req, 0.0)
        self.assertEqual(out["status"], "ready")
        self.assertEqual(out["mode"], "deterministic_fallback")
        self.assertEqual(out["meta"]["model_alias"], "not_configured")
        self.assertEqual(out["disclaimer"], ev.DISCLAIMER)

    def test_model_ordering_marks_llm_grounded(self):
        body = request_body()
        body["run_context"]["validation_scheme"] = "unknown"
        req = ai_backtest._validate(body)
        codes = ["NO_OUT_OF_SAMPLE"]
        with patch.object(ai_backtest, "available_task", return_value=True), patch.object(
            ai_backtest,
            "run_task",
            return_value={"model": "m", "data": {"finding_ids": list(reversed(codes))}},
        ):
            out = ai_backtest._build_response(req, 0.0)
        self.assertEqual(out["mode"], "llm_grounded")
        self.assertEqual(out["meta"]["model_alias"], "m")
        self.assertEqual([f["candidate_id"] for f in out["interpretation"]["findings"]], list(reversed(codes)))

    def test_model_failure_falls_back(self):
        req = ai_backtest._validate(request_body())
        from ai.errors import AiUpstreamError

        with patch.object(ai_backtest, "available_task", return_value=True), patch.object(
            ai_backtest, "run_task", side_effect=AiUpstreamError("boom")
        ):
            out = ai_backtest._build_response(req, 0.0)
        self.assertEqual(out["mode"], "deterministic_fallback")


class OrderValidatorTest(unittest.TestCase):
    def make(self, ids=("A", "B")):
        return TaskRequest(variables={"focus": "overall", "question": None, "candidates": [{"id": i, "title": i} for i in ids]})

    def test_accepts_exact_permutation(self):
        out = validate_order('{"finding_ids":["B","A"]}', self.make())
        self.assertEqual(out["finding_ids"], ["B", "A"])

    def test_rejects_missing_extra_or_new_ids(self):
        for raw in ['{"finding_ids":["A"]}', '{"finding_ids":["A","B","C"]}', '{"finding_ids":["A","X"]}', "not json", '{"finding_ids":"A"}']:
            with self.subTest(raw=raw):
                with self.assertRaises(AiBadOutput):
                    validate_order(raw, self.make())


if __name__ == "__main__":
    unittest.main()
