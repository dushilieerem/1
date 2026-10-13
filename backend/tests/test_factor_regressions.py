import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from services.factor.code_validation import validated_factor_code
from services.factor.user_library_store import update_library_factor


class FactorValuesTest(unittest.TestCase):
    def run_factor(self, source, close):
        namespace = {}
        exec(validated_factor_code(source, "factor"), namespace)
        engine = type("Engine", (), {"close": close, **{k: v for k, v in namespace.items() if callable(v)}})()
        return engine.factor()

    def test_long_lookback_is_rejected_on_actual_matrix(self):
        prices = pd.DataFrame({"A": range(1, 101), "B": range(10, 110)})
        with self.assertRaisesRegex(ValueError, "历史行情不足"):
            self.run_factor("def factor(self):\n    return self.close.pct_change(100000)", prices)

    def test_valid_nan_warmup_and_zero_factors_unchanged(self):
        prices = pd.DataFrame({"A": range(1, 101)})
        result = self.run_factor("def factor(self):\n    return self.close.pct_change(5)", prices)
        pd.testing.assert_frame_equal(result, prices.pct_change(5))
        zero = prices * 0
        pd.testing.assert_frame_equal(self.run_factor("def factor(self):\n    return self.close", zero), zero)

    def test_infinite_empty_none_and_missing_returns_rejected(self):
        for data in (pd.DataFrame(), pd.DataFrame({"A": [float("inf"), -float("inf")]})):
            with self.assertRaisesRegex(ValueError, "有效数值"):
                self.run_factor("def factor(self):\n    return self.close", data)
        for code in ("def factor(self):\n    return None", "def factor(self):\n    x = 1"):
            with self.assertRaisesRegex(ValueError, "返回"):
                self.run_factor(code, pd.DataFrame())

    def test_helpers_and_conditional_returns_preserved(self):
        code = """def factor(self):
    def periods():
        return 5
    if len(self.close) > 5:
        return self.close.pct_change(periods())
    return self.close
"""
        data = pd.DataFrame({"A": range(1, 12)})
        pd.testing.assert_frame_equal(self.run_factor(code, data), data.pct_change(5))

    def test_bad_source_or_missing_entry_rejected(self):
        for code in ("", "# comment", "def other(self):\n    return self.close", "def factor(:"):
            with self.assertRaises(ValueError):
                validated_factor_code(code, "factor")


class FactorEditTest(unittest.TestCase):
    def db(self, owned=True, clash=False):
        conn = MagicMock()
        row = {"id": 3, "library_id": 2, "name": "old_factor", "body": "def old_factor(self):\n    return self.close", "formula_ready": True}
        conn.execute.return_value.fetchone.side_effect = [
            {"id": 2, "name": "test"} if owned else None,
            row,
            {"id": 4} if clash else None,
            {**row, "name": "new_factor", "method_name": "new_factor"},
        ]
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        return conn, ctx

    @patch("services.factor.user_library_store.ensure_user_libraries_schema")
    def test_rename_and_description_update_scoped_to_owner(self, _schema):
        conn, ctx = self.db()
        with patch("services.factor.user_library_store.get_conn", return_value=ctx):
            update_library_factor(7, 2, 3, name="new_factor", description="新说明")
        writes = [(str(call.args[0]), call.args[1]) for call in conn.execute.call_args_list if "SET name" in str(call.args[0])]
        self.assertEqual(len(writes), 1)
        sql, args = writes[0]
        self.assertEqual(args[:2], ("new_factor", "new_factor"))
        self.assertIn("def new_factor(self)", args[2])
        self.assertEqual(args[3], "新说明")
        self.assertEqual(args[-3:], (7, 2, 3))
        self.assertNotIn("detect_runs", sql)

    @patch("services.factor.user_library_store.ensure_user_libraries_schema")
    def test_duplicate_and_unowned_rejected(self, _schema):
        for owned, clash, error in ((True, True, ValueError), (False, False, KeyError)):
            conn, ctx = self.db(owned, clash)
            with patch("services.factor.user_library_store.get_conn", return_value=ctx):
                with self.assertRaises(error):
                    update_library_factor(7, 2, 3, name="new_factor")
            self.assertFalse(any("UPDATE " in str(call.args[0]) for call in conn.execute.call_args_list))

    @patch("services.factor.user_library_store.ensure_user_libraries_schema")
    def test_clearing_existing_code_rejected(self, _schema):
        _, ctx = self.db()
        with patch("services.factor.user_library_store.get_conn", return_value=ctx):
            with self.assertRaisesRegex(ValueError, "不能为空"):
                update_library_factor(7, 2, 3, body="   ")


if __name__ == "__main__":
    unittest.main()
