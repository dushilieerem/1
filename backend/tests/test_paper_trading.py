# -*- coding: utf-8 -*-
"""模拟盘纯逻辑与错误映射单元测试。"""
from __future__ import annotations

import unittest
from datetime import date, datetime
from unittest.mock import patch

from fastapi import HTTPException

from app.routers import paper as paper_router
from services.paper import re_client
from services.paper.paper_store import (
    canonical_code_hash,
    infer_engine_mode,
    initial_next_settlement_date,
)
from services.paper.re_client import PaperTradingReError
from services.paper.settlement_service import (
    PaperTradingBusy,
    PaperTradingDisabled,
    build_settlement_payload,
)


class InitialNextSettlementDateTest(unittest.TestCase):
    def test_before_close_uses_today(self):
        monday = datetime(2026, 10, 19, 10, 0)
        self.assertEqual(initial_next_settlement_date(monday), date(2026, 10, 19))

    def test_after_close_uses_next_weekday(self):
        friday = datetime(2026, 10, 23, 16, 0)
        self.assertEqual(initial_next_settlement_date(friday), date(2026, 10, 26))

    def test_weekend_uses_next_weekday(self):
        saturday = datetime(2026, 10, 24, 9, 0)
        self.assertEqual(initial_next_settlement_date(saturday), date(2026, 10, 26))

    def test_explicit_requested_date_is_kept(self):
        now = datetime(2026, 10, 22, 10, 0)
        self.assertEqual(
            initial_next_settlement_date(now, requested=date(2026, 10, 20)),
            date(2026, 10, 20),
        )

    def test_requested_future_date_is_rejected(self):
        now = datetime(2026, 10, 22, 10, 0)
        with self.assertRaises(ValueError):
            initial_next_settlement_date(now, requested=date(2026, 10, 23))


class EngineModeTest(unittest.TestCase):
    def test_infer_event_and_vectorized(self):
        self.assertEqual(infer_engine_mode("def initialize(ctx): pass"), "event")
        self.assertEqual(
            infer_engine_mode("class S:\n    def generate_signals(self): pass"),
            "vectorized",
        )
        self.assertEqual(infer_engine_mode("class S: pass"), "vectorized")

    def test_code_hash_prefix(self):
        digest = canonical_code_hash("abc")
        self.assertTrue(digest.startswith("sha256:"))
        self.assertEqual(len(digest), len("sha256:") + 64)


ACCOUNT = {
    "id": 9,
    "user_id": 1,
    "engine_mode": "event",
    "strategy_code": "class S: pass",
    "code_hash": "sha256:abc",
    "universe": "CSI300",
    "benchmark": "CSI300",
    "cash": 100000.0,
    "commission_rate": 0.0003,
    "min_commission": 5.0,
    "stamp_tax": 0.0005,
    "slippage_rate": 0.0,
    "lot_size": 100,
    "filter_st": False,
    "strategy_state": {"peak": 1.2},
    "state_hash": "sha256:state",
}


class BuildPayloadTest(unittest.TestCase):
    @patch("services.paper.settlement_service.store.list_positions")
    def test_payload_contains_snapshot_and_state(self, list_positions):
        list_positions.return_value = [
            {
                "symbol": "600519.SH",
                "quantity": 100,
                "availableQuantity": 100,
                "averageCost": 1300.0,
            }
        ]
        payload = build_settlement_payload(ACCOUNT, settlement_date=date(2026, 10, 21))
        self.assertEqual(payload["settlement_date"], "2026-10-21")
        self.assertEqual(payload["engine_mode"], "event")
        self.assertEqual(payload["expected_code_hash"], "sha256:abc")
        self.assertEqual(payload["strategy_state"], {"peak": 1.2})
        self.assertEqual(payload["strategy_state_code_hash"], "sha256:abc")
        self.assertEqual(payload["expected_state_hash"], "sha256:state")
        self.assertEqual(payload["account"]["positions"][0]["symbol"], "600519.SH")
        self.assertEqual(payload["execution"]["stamp_tax_rate"], 0.0005)


class ReClientMappingTest(unittest.TestCase):
    def _call(self, status, body):
        with patch.object(re_client, "forward_re", return_value=(status, {}, body)):
            with self.assertRaises(PaperTradingReError) as ctx:
                re_client.settle({"x": 1})
        return ctx.exception

    def test_conflict_keeps_reason_code(self):
        exc = self._call(
            409,
            {"detail": {"code": "DATA_NOT_READY", "message": "not ready"}},
        )
        self.assertEqual(exc.code, "DATA_NOT_READY")
        self.assertEqual(exc.http_status, 409)

    def test_unavailable_maps_to_502(self):
        exc = self._call(502, {"error": "upstream connection error"})
        self.assertEqual(exc.code, "RE_UNAVAILABLE")
        self.assertEqual(exc.http_status, 502)

    def test_timeout_is_504(self):
        exc = self._call(504, {"error": "upstream timeout"})
        self.assertEqual(exc.code, "RE_TIMEOUT")
        self.assertEqual(exc.http_status, 504)


class RouterErrorMappingTest(unittest.TestCase):
    def test_disabled_maps_to_503(self):
        with patch.object(
            paper_router, "manual_settle", side_effect=PaperTradingDisabled("closed")
        ):
            with self.assertRaises(HTTPException) as ctx:
                paper_router.paper_settle(1, {}, uid=1)
        self.assertEqual(ctx.exception.status_code, 503)

    def test_busy_maps_to_409(self):
        with patch.object(
            paper_router, "manual_settle", side_effect=PaperTradingBusy("busy")
        ):
            with self.assertRaises(HTTPException) as ctx:
                paper_router.paper_settle(1, {}, uid=1)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_re_422_maps_to_422(self):
        exc = PaperTradingReError(
            code="UNSUPPORTED_PORTFOLIO", message="negative", http_status=422
        )
        with patch.object(paper_router, "manual_settle", side_effect=exc):
            with self.assertRaises(HTTPException) as ctx:
                paper_router.paper_settle(1, {}, uid=1)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.detail["code"], "UNSUPPORTED_PORTFOLIO")


if __name__ == "__main__":
    unittest.main()
