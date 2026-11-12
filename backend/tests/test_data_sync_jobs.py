# -*- coding: utf-8 -*-
"""数据同步队列任务：生产库放行开关与 payload 传递。"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from services.data import sync_jobs


class SyncJobHandlerTest(unittest.TestCase):
    def test_production_flag_comes_from_env(self):
        with patch("services.data.view_sync.sync_view", return_value={"status": "ok", "view_id": "v"}) as m, \
                patch.dict(os.environ, {"SVQUANT_DATA_SYNC_ALLOW_PRODUCTION": "1"}):
            out = sync_jobs._handle({"view": "current", "force": False})
        m.assert_called_once_with("current", force=False, allow_production=True)
        self.assertEqual(out["status"], "ok")

    def test_production_blocked_without_flag(self):
        with patch("services.data.view_sync.sync_view", return_value={"status": "ok"}) as m, \
                patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SVQUANT_DATA_SYNC_ALLOW_PRODUCTION", None)
            sync_jobs._handle({"view": "current"})
        self.assertFalse(m.call_args.kwargs["allow_production"])

    def test_force_is_forwarded(self):
        with patch("services.data.view_sync.sync_view", return_value={"status": "ok"}) as m, \
                patch.dict(os.environ, {"SVQUANT_DATA_SYNC_ALLOW_PRODUCTION": "true"}):
            sync_jobs._handle({"view": "current", "force": True})
        self.assertTrue(m.call_args.kwargs["force"])


class EnqueueTest(unittest.TestCase):
    def test_payload_shape(self):
        with patch.object(sync_jobs, "enqueue", return_value=42) as m:
            job_id = sync_jobs.enqueue_sync("current", force=True)
        self.assertEqual(job_id, 42)
        kind, payload = m.call_args.args
        self.assertEqual(kind, "data.sync")
        self.assertEqual(payload, {"view": "current", "force": True})


if __name__ == "__main__":
    unittest.main()
