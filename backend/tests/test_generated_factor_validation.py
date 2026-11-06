# -*- coding: utf-8 -*-
"""AI 生成因子的静态校验（ADR-037 P1-3）：白名单、结构、未来数据、可编译性。"""
import unittest

from services.factor.generated_factor_validation import (
    compile_errors,
    validate_generated_factor,
    wrap_for_compile,
)

VALID_CODE = "def ret_5d(self, window=5):\n    return self.close.pct_change(window).rolling(window).mean()\n"


def factor(code=VALID_CODE, name="ret_5d", fields=("close",)):
    return {"factor_name": name, "factor_code": code, "used_fields": list(fields)}


class StructureTest(unittest.TestCase):
    def test_valid_factor_passes(self):
        self.assertEqual(validate_generated_factor(factor()), [])

    def test_unregistered_field_in_used_fields(self):
        errors = validate_generated_factor(factor(fields=("close", "pe_ttm")))
        self.assertIn("pe_ttm", errors[0])

    def test_must_be_single_function(self):
        errors = validate_generated_factor(factor(code=VALID_CODE + "\nx = 1\n"))
        self.assertIn("只能包含一个函数定义", errors[0])

    def test_name_and_self_arg_required(self):
        self.assertIn("函数名必须与 factor_name 一致", validate_generated_factor(factor(name="other"))[0])
        self.assertIn("第一个参数必须为 self", validate_generated_factor(factor(code="def ret_5d(self_):\n    return 1\n"))[0])

    def test_decorator_rejected(self):
        errors = validate_generated_factor(factor(code="@staticmethod\ndef ret_5d(self):\n    return self.close\n"))
        self.assertIn("装饰器", errors[0])

    def test_syntax_error_reported(self):
        self.assertIn("语法错误", validate_generated_factor(factor(code="def ret_5d(self):\n    return (\n"))[0])


class WhitelistTest(unittest.TestCase):
    def test_unknown_field_on_self(self):
        errors = validate_generated_factor(factor(code="def ret_5d(self):\n    return self.pe_ttm\n"))
        self.assertIn("不允许的字段：pe_ttm", errors[0])

    def test_unknown_method(self):
        errors = validate_generated_factor(factor(code="def ret_5d(self):\n    return self.close.apply(abs)\n"))
        self.assertIn("白名单", errors[0])

    def test_import_and_class_rejected(self):
        errors = validate_generated_factor(factor(code="def ret_5d(self):\n    import os\n    return 1\n"))
        self.assertTrue(errors and "不允许的代码结构" in errors[0])


class FutureDataTest(unittest.TestCase):
    def test_negative_shift_rejected(self):
        errors = validate_generated_factor(factor(code="def ret_5d(self):\n    return self.close.shift(-1)\n"))
        self.assertIn("禁止未来数据", errors[0])

    def test_centered_rolling_rejected(self):
        errors = validate_generated_factor(
            factor(code="def ret_5d(self):\n    return self.close.rolling(5, center=True).mean()\n")
        )
        self.assertIn("center=False", errors[0])

    def test_backfill_rejected(self):
        errors = validate_generated_factor(
            factor(code="def ret_5d(self):\n    return self.close.fillna(method='bfill')\n")
        )
        self.assertIn("禁止未来数据", errors[0])

    def test_positive_window_still_allowed(self):
        self.assertEqual(validate_generated_factor(factor(code="def ret_5d(self, n=5):\n    return self.close.shift(n)\n")), [])


class CompileTest(unittest.TestCase):
    def test_wrapper_indents_into_class(self):
        wrapped = wrap_for_compile(VALID_CODE)
        self.assertIn("class UserFactorLibrary(FactorLibrary)", wrapped)
        self.assertIn("    def ret_5d", wrapped)

    def test_compile_rejects_broken_code(self):
        self.assertTrue(compile_errors("def ret_5d(self):\n    return *\n"))

    def test_compile_accepts_body_indent_edge_case(self):
        self.assertEqual(compile_errors(VALID_CODE), [])


if __name__ == "__main__":
    unittest.main()


class PreprocessingCapabilityTest(unittest.TestCase):
    """QA-20: the panel can express winsorize / rank / z-score / industry demean / filters."""

    def test_winsorize_and_rank(self):
        code = ("def rev_w(self, window=5):\n"
                "    raw = -self.close.pct_change(window)\n"
                "    lo = raw.quantile(0.01, axis=1)\n"
                "    hi = raw.quantile(0.99, axis=1)\n"
                "    clipped = raw.clip(lower=lo, upper=hi, axis=0)\n"
                "    return clipped.rank(axis=1, pct=True)\n")
        self.assertEqual(validate_generated_factor(
            factor(code=code, name="rev_w", fields=("close",))), [])

    def test_zscore_and_industry_demean(self):
        code = ("def rev_ind(self, window=5):\n"
                "    raw = -self.close.pct_change(window)\n"
                "    z = raw.sub(raw.mean(axis=1), axis=0).div(raw.std(axis=1), axis=0)\n"
                "    industry = self.the_sw_industry_code\n"
                "    return z.sub(z.groupby(industry, axis=1).transform(\"mean\"))\n")
        self.assertEqual(validate_generated_factor(
            factor(code=code, name="rev_ind", fields=("close", "the_sw_industry_code"))), [])

    def test_liquidity_and_suspension_filters(self):
        code = ("def rev_liquid(self, window=5):\n"
                "    raw = -self.close.pct_change(window)\n"
                "    liquid = self.amount.rolling(20, min_periods=20).mean().rank(axis=1, pct=True).gt(0.05)\n"
                "    return raw.where(liquid).where(self.up_and_down_status.ne(\"停牌\"))\n")
        self.assertEqual(validate_generated_factor(
            factor(code=code, name="rev_liquid", fields=("close", "amount", "up_and_down_status"))), [])
