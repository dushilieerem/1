# -*- coding: utf-8 -*-
"""因子面板进程内日更定时器（不依赖 cron / systemd / 计划任务）。

覆盖：触发时刻解析、下一次触发计算、全量矩阵执行与状态落盘、
以及与其它进程并发时的中止行为。
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.factor import dashboard_scheduler as dsched  # noqa: E402
from services.factor.dashboard_store import PANEL_COMBOS  # noqa: E402

LOCK_ERROR = "已有面板回测在其它进程运行，本次跳过（未抢到刷新锁）"


class ParseHhmmTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(dsched.parse_hhmm("00:00"), (0, 0))
        self.assertEqual(dsched.parse_hhmm("6:30"), (6, 30))
        self.assertEqual(dsched.parse_hhmm(" 23:59 "), (23, 59))

    def test_invalid(self):
        for bad in ("", "24:00", "12:60", "-1:00", "abc", "1200", "12", "12:"):
            self.assertIsNone(dsched.parse_hhmm(bad), f"{bad!r} 应判为非法")


class NextRunAtTest(unittest.TestCase):
    def test_later_today(self):
        now = datetime(2026, 10, 14, 8, 0)
        self.assertEqual(dsched.next_run_at(now, 18, 30), datetime(2026, 10, 14, 18, 30))

    def test_rolls_to_tomorrow_when_passed(self):
        now = datetime(2026, 10, 14, 8, 0)
        self.assertEqual(dsched.next_run_at(now, 0, 0), datetime(2026, 10, 15, 0, 0))

    def test_exact_time_rolls_to_tomorrow(self):
        # 正好在触发点上 → 取下一次，避免同一时刻反复触发
        now = datetime(2026, 10, 14, 0, 0)
        self.assertEqual(dsched.next_run_at(now, 0, 0), datetime(2026, 10, 15, 0, 0))


class RunFullMatrixTest(unittest.TestCase):
    def test_runs_every_combo_and_records_state(self):
        calls: list[dict] = []
        saved: dict = {}
        with (
            patch.object(dsched.ds, "_run_batch", side_effect=lambda **kw: calls.append(kw)),
            patch.object(dsched.ds, "read_job", return_value={"status": "done"}),
            patch.object(dsched, "_save_state", side_effect=lambda **kw: saved.update(kw)),
        ):
            out = dsched.run_full_matrix(reason="daily")

        self.assertEqual(len(calls), len(PANEL_COMBOS))
        self.assertEqual(out["ok"], len(PANEL_COMBOS))
        self.assertEqual(out["failed"], 0)
        self.assertEqual(saved["last_reason"], "daily")
        self.assertEqual(saved["last_ok"], len(PANEL_COMBOS))
        # 日更必须重算（skip_ok=False），否则行情滚动后指标永远不会更新
        self.assertTrue(all(c["skip_ok"] is False for c in calls))
        self.assertTrue(all(c["filter_suspended"] is True for c in calls))
        # 组合不重复、覆盖 2 池 × 3 周期 × 2 过滤
        got = {(c["universe"], c["period"], c["filter_limit_up"]) for c in calls}
        self.assertEqual(got, set(PANEL_COMBOS))

    def test_aborts_after_first_combo_when_lock_held(self):
        calls: list[dict] = []
        with (
            patch.object(dsched.ds, "_run_batch", side_effect=lambda **kw: calls.append(kw)),
            patch.object(
                dsched.ds,
                "read_job",
                return_value={"status": "failed", "error": LOCK_ERROR},
            ),
            patch.object(dsched, "_save_state"),
        ):
            out = dsched.run_full_matrix(reason="daily")

        # 抢不到锁说明有另一轮在跑：立刻中止，不继续把 12 组都试一遍
        self.assertEqual(len(calls), 1)
        self.assertEqual(out["failed"], 1)
        self.assertEqual(out["ok"], 0)


class StartSchedulerConfigTest(unittest.TestCase):
    """只测不会真正起线程的分支（关闭 / 时刻非法）。"""

    def test_disabled_by_env(self):
        with (
            patch("services.core.env_config.env", side_effect=lambda k, d=None: "0" if k == "SVQUANT_PANEL_DAILY_ENABLED" else d),
            patch.object(dsched.threading, "Thread") as thread_cls,
        ):
            dsched.start_dashboard_daily_scheduler()
        thread_cls.assert_not_called()

    def test_invalid_time_does_not_start_thread(self):
        def _env(key, default=None):
            if key == "SVQUANT_PANEL_DAILY_ENABLED":
                return "1"
            if key == "SVQUANT_PANEL_DAILY_AT":
                return "25:99"
            return default

        with (
            patch("services.core.env_config.env", side_effect=_env),
            patch.object(dsched.threading, "Thread") as thread_cls,
        ):
            dsched.start_dashboard_daily_scheduler()
        thread_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
