# -*- coding: utf-8 -*-
"""因子目录定时同步（P1-F04）：开关、间隔校验、单次同步与幂等启动。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.factor import catalog_scheduler as csched  # noqa: E402


def _env(**values: str):
    """按 key 返回配置值，其余返回调用方给的默认值。"""

    def _lookup(key, default=None):
        return values.get(key, default)

    return _lookup


class CatalogSchedulerTest(unittest.TestCase):
    def setUp(self):
        csched._started = False
        csched._thread = None

    def tearDown(self):
        csched._started = False
        csched._thread = None

    def test_disabled_by_env(self):
        with (
            patch(
                "services.core.env_config.env",
                side_effect=_env(RE_CATALOG_SYNC_ENABLED="0"),
            ),
            patch.object(csched.threading, "Thread") as thread_cls,
        ):
            csched.start_re_catalog_sync_scheduler()
        thread_cls.assert_not_called()

    def test_zero_interval_does_not_start_thread(self):
        with (
            patch(
                "services.core.env_config.env",
                side_effect=_env(RE_CATALOG_SYNC_INTERVAL_SEC="0"),
            ),
            patch.object(csched.threading, "Thread") as thread_cls,
        ):
            csched.start_re_catalog_sync_scheduler()
        thread_cls.assert_not_called()

    def test_invalid_interval_does_not_start_thread(self):
        with (
            patch(
                "services.core.env_config.env",
                side_effect=_env(RE_CATALOG_SYNC_INTERVAL_SEC="abc"),
            ),
            patch.object(csched.threading, "Thread") as thread_cls,
        ):
            csched.start_re_catalog_sync_scheduler()
        thread_cls.assert_not_called()

    def test_enabled_starts_daemon_thread_once(self):
        with (
            patch(
                "services.core.env_config.env",
                side_effect=_env(RE_CATALOG_SYNC_INTERVAL_SEC="60"),
            ),
            patch.object(csched.threading, "Thread") as thread_cls,
        ):
            csched.start_re_catalog_sync_scheduler()
            csched.start_re_catalog_sync_scheduler()

        # 调度线程 + 队列 worker 各一个；重复调用不得继续增加
        self.assertEqual(thread_cls.call_count, 2)
        self.assertGreaterEqual(
            sum(1 for c in thread_cls.call_args_list if c.kwargs.get("daemon")), 2
        )

    def test_sync_once_calls_both_scopes_and_returns_result(self):
        expected = {
            "ok": True,
            "primary": {"factors": 10},
            "all": {"factors": 20},
            "consistency": {"ok": True, "warnings": []},
            "errors": [],
        }
        with patch(
            "services.factor.re_factor_catalog.sync_all_scopes",
            return_value=expected,
        ) as sync:
            out = csched.sync_once()

        sync.assert_called_once_with()
        self.assertEqual(out, expected)


if __name__ == "__main__":
    unittest.main()
