# -*- coding: utf-8 -*-
"""AI 策略生成（ADR-037 P1-3）：静态校验、能力预检与响应契约。"""
import json
import unittest

from ai.errors import AiBadOutput
from ai.router.tasks.strategy_generation import parse_generation, unsupported_prompt_errors
from services.strategy.generated_strategy_validation import validate_generated_strategy

VALID_CODE = """import pandas as pd

class Momentum:
    def __init__(self, close):
        self.close = close

    def generate_signals(self):
        score = self.close.pct_change(20)
        ranks = score.rank(axis=1, ascending=False, method='first')
        targets = (ranks <= 30) * (1.0 / 30)
        rebalance = pd.DataFrame(False, index=self.close.index, columns=self.close.columns)
        rebalance.iloc[::5] = True
        return targets.where(rebalance).ffill().fillna(0.0)
"""


def strategy(code=VALID_CODE, name="Momentum", fields=("close",)):
    return {
        "strategy_name": name,
        "strategy_code": code,
        "description": "动量",
        "used_fields": list(fields),
        "assumptions": [],
        "warnings": [],
    }


class ValidatorTest(unittest.TestCase):
    def test_template_passes(self):
        self.assertEqual(validate_generated_strategy(strategy()), [])

    def test_class_name_must_match(self):
        self.assertIn("策略类名必须与 strategy_name 一致", validate_generated_strategy(strategy(name="Other"))[0])

    def test_only_pandas_import_allowed(self):
        code = "import numpy as np\n" + VALID_CODE
        self.assertTrue(validate_generated_strategy(strategy(code=code)))

    def test_only_close_field(self):
        code = VALID_CODE.replace("self.close.pct_change", "self.volume.pct_change")
        self.assertIn("不允许的 self 属性：volume", validate_generated_strategy(strategy(code=code))[0])

    def test_control_flow_rejected(self):
        code = VALID_CODE.replace(
            "score = self.close.pct_change(20)",
            "score = self.close.pct_change(20)\n        if score is None:\n            return None",
        )
        self.assertTrue(validate_generated_strategy(strategy(code=code)))

    def test_missing_method_rejected(self):
        code = VALID_CODE.split("    def generate_signals")[0]
        self.assertIn("只能定义", validate_generated_strategy(strategy(code=code))[0])

    def test_unregistered_field(self):
        self.assertIn("未登记字段", validate_generated_strategy(strategy(fields=("close", "volume")))[0])


class ParseTest(unittest.TestCase):
    def test_ready(self):
        parsed = parse_generation(json.dumps(strategy(), ensure_ascii=False))
        self.assertEqual(parsed["errors"], [])
        self.assertEqual(parsed["strategy"]["strategy_name"], "Momentum")

    def test_invalid_code_returns_errors_not_exception(self):
        parsed = parse_generation(json.dumps(strategy(name="Nope"), ensure_ascii=False))
        self.assertTrue(parsed["errors"])
        self.assertIsNone(parsed["strategy"])

    def test_non_json_raises(self):
        with self.assertRaises(AiBadOutput):
            parse_generation("oops")


class CapabilityTest(unittest.TestCase):
    def test_unsupported_capabilities_are_named(self):
        errors = unsupported_prompt_errors("用成交量和市盈率做多空对冲")
        self.assertTrue(errors)
        text = errors[0]
        for label in ("成交量", "基本面", "多空"):
            self.assertIn(label, text)

    def test_supported_prompt_passes(self):
        self.assertEqual(unsupported_prompt_errors("每20日调仓买入过去20日动量最高的30只股票等权"), [])


if __name__ == "__main__":
    unittest.main()
