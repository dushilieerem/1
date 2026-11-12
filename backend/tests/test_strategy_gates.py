import unittest
from datetime import date, timedelta

from services import strategy_gates as g


def result(excess=0.05, daily=0.0004, turnover=0.03, bench_daily=0.0002, n=60):
    curve, bench = [], []
    s = b = 1.0
    for i in range(n):
        if i:
            noise = (0.001 if i % 3 else -0.002)
            s *= 1 + daily + noise
            b *= 1 + bench_daily
        day = str(date(2025, 1, 1) + timedelta(days=i))
        curve.append({"date": day, "value": s})
        bench.append({"date": day, "value": b})
    return {"excess_return": excess, "metrics": {"turnover": turnover},
            "equity_curve": curve, "benchmark_curve": bench}


class NeedIrTest(unittest.TestCase):
    def test_k_zero_uses_one(self):
        self.assertEqual(g.need_ir(0), g.need_ir(1))

    def test_rises_with_k(self):
        self.assertLess(g.need_ir(1), g.need_ir(10))


class GateTest(unittest.TestCase):
    def test_missing_diagnostics_is_incomplete_not_passed(self):
        gate = g.evaluate(result(), 1)
        self.assertFalse(gate["passed"])
        self.assertFalse(gate["complete"])
        self.assertIn("2 倍成本下超额", gate["pending"])
        self.assertIn("参数邻域达标", gate["pending"])

    def test_all_six_pass(self):
        gate = g.evaluate(result(), 1, cost_2x_excess=0.04,
                          neighborhood={"cells": 9, "passed_cells": 7})
        self.assertTrue(gate["complete"])
        self.assertTrue(gate["passed"])

    def test_negative_excess_fails(self):
        gate = g.evaluate(result(daily=0.0001, bench_daily=0.0005), 1, cost_2x_excess=0.01,
                          neighborhood={"cells": 9, "passed_cells": 9})
        self.assertFalse(gate["checks"][0]["passed"])

    def test_annual_excess_uses_daily_mean_not_cumulative(self):
        data = result(daily=0.0004, bench_daily=0.0002)
        data["excess_return"] = 9.99  # cumulative value must not be used as annual
        gate = g.evaluate(data, 1)
        self.assertAlmostEqual(gate["checks"][0]["actual"], 0.0504, delta=0.01)
        self.assertLess(gate["checks"][0]["actual"], 1)

    def test_ir_from_daily_excess(self):
        gate = g.evaluate(result(daily=0.001, bench_daily=0.0002), 1)
        self.assertIsNotNone(gate["checks"][1]["actual"])
        self.assertGreater(gate["checks"][1]["actual"], 1)

    def test_turnover_annualized(self):
        gate = g.evaluate(result(turnover=0.1), 1)
        self.assertAlmostEqual(gate["checks"][3]["actual"], 25.2)
        self.assertFalse(gate["checks"][3]["passed"])

    def test_sealed_two_gates(self):
        gate = g.evaluate(result(excess=0.02), 1, sealed=True)
        self.assertTrue(gate["complete"])
        self.assertEqual(len(gate["checks"]), 2)
