import unittest

from services import strategy_diagnostics as d


def gate():
    return {"checks": [
        {"name": "扣费后年化超额", "actual": 0.05, "passed": True},
        {"name": "信息比率（按试验数校正）", "actual": 1.2, "passed": True},
        {"name": "相对基准最大回撤", "actual": 0.05, "passed": True},
        {"name": "单边年换手", "actual": 5.0, "passed": True},
        {"name": "2 倍成本下超额", "actual": None, "passed": None},
        {"name": "参数邻域达标", "actual": None, "passed": None},
    ], "passed": False, "complete": False, "pending": ["2 倍成本下超额", "参数邻域达标"]}


class MergedGateTest(unittest.TestCase):
    def test_diagnostics_fill_pending_checks(self):
        out = d.merged_gate({"gate": gate()}, {
            "cost_2x": {"payload": {"excess": 0.01, "passed": True}},
            "neighborhood": {"payload": {"passed_cells": 7, "required": 6}},
        })
        self.assertTrue(out["complete"])
        self.assertTrue(out["passed"])
        self.assertEqual(out["pending"], [])

    def test_failed_neighborhood_blocks(self):
        out = d.merged_gate({"gate": gate()}, {
            "cost_2x": {"payload": {"excess": 0.01, "passed": True}},
            "neighborhood": {"payload": {"passed_cells": 2, "required": 6}},
        })
        self.assertTrue(out["complete"])
        self.assertFalse(out["passed"])
