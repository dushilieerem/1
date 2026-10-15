"""Regression: migrated turnover gaps must be selected for full backfill."""
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from scripts import backfill_dashboard_q1 as backfill


class DashboardBackfillTest(unittest.TestCase):
    def test_selects_either_missing_quantile_without_treating_zero_as_missing(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE factor_dashboard_metrics (
            universe TEXT, period TEXT, filter_limit_up INTEGER, error TEXT,
            q1_return REAL, q5_return REAL, q1_turnover REAL, q5_turnover REAL
        )""")
        conn.executemany("INSERT INTO factor_dashboard_metrics VALUES (?,?,?,?,?,?,?,?)", [
            ("CSI300", "3y", 1, None, 90, -29, None, None),  # migrated cache
            ("CSI300", "1y", 1, "", 10, 5, .3, None),  # Q5 alone missing
            ("CSI300", "3m", 1, None, 10, 5, None, .4),  # Q1 alone missing
            ("CSI500", "3y", 1, None, 0, 0, 0, 0),  # valid zeros
            ("CSI500", "1y", 1, "failed", None, None, None, None),
            ("CSI500", "3m", 1, None, 10, None, .3, .4),  # Q5 return missing
        ])

        @contextmanager
        def connection():
            yield conn

        with patch.object(backfill.ds, "migrate_legacy_factor_dashboard_metrics"), \
             patch.object(backfill, "get_conn", connection):
            self.assertEqual(set(backfill.combos_needing_backfill()), {
                ("CSI300", "3y", True), ("CSI300", "1y", True),
                ("CSI300", "3m", True), ("CSI500", "3m", True),
            })

    def test_backfill_requests_full_analysis(self):
        with patch.object(backfill, "combos_needing_backfill", return_value=[("CSI300", "3y", True)]), \
             patch.object(backfill, "run_one", return_value={"status": "done"}) as run:
            with self.assertRaises(SystemExit) as result:
                backfill.main()
            self.assertEqual(result.exception.code, 0)
            run.assert_called_once_with("CSI300", "3y", filter_limit_up=True,
                                        limit=None, analysis_level="full")


if __name__ == "__main__":
    unittest.main()
