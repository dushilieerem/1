# -*- coding: utf-8 -*-
"""因子面板目录与批跑闸门。

回归背景：同事把 RE 内置库重组为单库「主因子库」（因子名 SV01_0001 形式，
带 category_name/category_id）后，dashboard_store 仍按旧库名白名单
（momentum_lib / value_lib / …）过滤 —— 面板目录直接变空，
批跑闸门还会把「主因子库」全部判成「面板不支持非官方库因子」。

现在目录以 RE 目录快照（re_factor_catalog）为唯一真源，且不再枚举库名，
只排除本地/用户库。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.factor import dashboard_store as ds  # noqa: E402


MAIN_LIB_FACTOR = {
    "name": "SV01_0001",
    "description": "观察窗口内上涨日和下跌日谁更多，方向是否持续？",
    "display_name": "涨跌日频率差",
    "name_en": "Up-Down Day Frequency Gap",
    "library": "主因子库",
    "category_id": "SV01",
    "category_label": "动量因子",
}


def _catalog(*factors: dict) -> dict:
    return {"ok": True, "factors": list(factors)}


def _panel_factor(**overrides) -> dict:
    """load_factor_index 产出的形状（含 _run_batch 依赖的三个键）。"""
    return {
        **MAIN_LIB_FACTOR,
        "file": "",
        "unavailable": False,
        "unavailable_reason": "",
        **overrides,
    }


class LoadFactorIndexTest(unittest.TestCase):
    def test_single_main_library_is_kept(self):
        """单库「主因子库」必须被收录——旧白名单会把它过滤成 0 个因子。"""
        with patch(
            "services.factor.re_factor_catalog.fetch_re_catalog",
            return_value=_catalog(MAIN_LIB_FACTOR),
        ):
            out = ds.load_factor_index()

        self.assertEqual(len(out), 1)
        row = out[0]
        self.assertEqual(row["name"], "SV01_0001")
        self.assertEqual(row["library"], "主因子库")
        # 分类与中文短名要带出来，供前端「子类」列与分类筛选使用
        self.assertEqual(row["category_label"], "动量因子")
        self.assertEqual(row["category_id"], "SV01")
        self.assertEqual(row["display_name"], "涨跌日频率差")
        # 批跑依赖这三个键存在
        self.assertIs(row["unavailable"], False)
        self.assertEqual(row["unavailable_reason"], "")
        self.assertEqual(row["file"], "")

    def test_local_and_user_libraries_excluded(self):
        with patch(
            "services.factor.re_factor_catalog.fetch_re_catalog",
            return_value=_catalog(
                MAIN_LIB_FACTOR,
                {**MAIN_LIB_FACTOR, "name": "u1_x", "library": "custom_lib"},
                {**MAIN_LIB_FACTOR, "name": "u2_y", "library": "user_lib_2"},
            ),
        ):
            out = ds.load_factor_index()

        self.assertEqual([r["name"] for r in out], ["SV01_0001"])

    def test_display_name_falls_back_to_description(self):
        with patch(
            "services.factor.re_factor_catalog.fetch_re_catalog",
            return_value=_catalog({**MAIN_LIB_FACTOR, "display_name": None}),
        ):
            out = ds.load_factor_index()

        self.assertEqual(out[0]["display_name"], MAIN_LIB_FACTOR["description"])

    def test_re_catalog_failure_is_reported(self):
        with patch(
            "services.factor.re_factor_catalog.fetch_re_catalog",
            side_effect=RuntimeError("RE 不可达"),
        ):
            with self.assertRaises(RuntimeError):
                ds.load_factor_index()


class RunBatchLibraryGateTest(unittest.TestCase):
    """「主因子库」不得再被闸门拒绝，且要以 library_name 转发给 RE。"""

    def _run(self, factor: dict) -> tuple[dict, list[dict]]:
        captured: dict = {}

        def _fake_backtest(payload, timeout=600):
            captured["payload"] = payload
            return {
                "factor_analysis": {"ic_mean": 0.0231, "rank_ic_mean": 0.0287},
                "metrics": {"annual_return": 0.12},
            }

        stored: list[dict] = []
        with (
            patch.object(ds, "load_factor_index", return_value=[factor]),
            patch.object(ds, "call_yg_backtest", side_effect=_fake_backtest),
            patch.object(ds, "migrate_legacy_factor_dashboard_metrics"),
            patch.object(ds, "_store_metric", side_effect=stored.append),
            patch.object(ds, "write_job"),
            patch.object(ds, "read_job", return_value={}),
            patch.object(ds.time, "sleep"),
            # 拒收分支会 traceback.print_exc()，测试里不外溢
            patch.object(ds.traceback, "print_exc"),
        ):
            ds._run_batch(
                universe="CSI300",
                period="3y",
                filter_limit_up=True,
                filter_suspended=True,
                limit=None,
            )
        return captured, stored

    def test_main_library_factor_forwarded_with_library_name(self):
        captured, stored = self._run(_panel_factor())

        self.assertEqual(captured["payload"]["library_name"], "主因子库")
        self.assertEqual(captured["payload"]["factor_name"], "SV01_0001")
        self.assertEqual(len(stored), 1)
        self.assertIsNone(stored[0]["error"])
        self.assertIsNotNone(stored[0]["ic_mean"])
        # 行标题取中文短名，不是长问句
        self.assertEqual(stored[0]["name_cn"], "涨跌日频率差")

    def test_local_library_still_rejected(self):
        captured, stored = self._run(_panel_factor(library="custom_lib"))

        self.assertEqual(captured, {})
        self.assertEqual(len(stored), 1)
        self.assertIn("本地/用户库", stored[0]["error"] or "")
        self.assertIsNone(stored[0]["ic_mean"])


class SpreadDirectionTest(unittest.TestCase):
    """多空差符号：RE 口径 = Q1 − Q5（Q1 是因子值最高组、Q5 是最低组）。

    回归背景：兜底分支原本写 q5 - q1，与 RE 透传的 spread 符号相反 ——
    同一列在不同因子上方向会翻转。
    """

    def test_fallback_uses_highest_minus_lowest(self):
        # 只给分层收益、不给 spread/long_short_return → 走兜底
        data = {"factor_analysis": {"layered_returns": {"layer1": 0.14, "layer5": -0.02}}}
        m = ds.map_yg_response(data)
        self.assertAlmostEqual(m["q1_return"], 14.0, places=4)
        self.assertAlmostEqual(m["q5_return"], -2.0, places=4)
        # Q1(最高分位) − Q5(最低分位) = +16，而不是 −16
        self.assertAlmostEqual(m["long_short_spread"], 16.0, places=4)

    def test_re_spread_passed_through_wins(self):
        data = {
            "factor_analysis": {
                "layered_returns": {"layer1": 0.14, "layer5": -0.02, "spread": 0.16}
            }
        }
        m = ds.map_yg_response(data)
        self.assertAlmostEqual(m["long_short_spread"], 16.0, places=4)

    def test_lower_highest_quantile_gives_negative_spread(self):
        data = {"factor_analysis": {"layered_returns": {"layer1": -0.05, "layer5": 0.11}}}
        m = ds.map_yg_response(data)
        self.assertAlmostEqual(m["long_short_spread"], -16.0, places=4)


class RefreshLockTest(unittest.TestCase):
    """整批回测跨进程互斥：锁被占用时本轮跳过并告警，不并发压 RE、不并发写同表。"""

    def test_lock_is_exclusive_across_descriptors(self):
        with ds.refresh_lock() as first:
            self.assertTrue(first)
            # flock 按打开的 file description 计，同进程再取也会冲突
            with ds.refresh_lock() as second:
                self.assertFalse(second)
        # 释放后可重新获取
        with ds.refresh_lock() as third:
            self.assertTrue(third)

    def test_skips_without_calling_re_when_lock_held(self):
        written: list[dict] = []
        re_calls: list[str] = []
        with (
            patch.object(ds, "load_factor_index", return_value=[_panel_factor()]),
            patch.object(
                ds, "call_yg_backtest", side_effect=lambda *a, **k: re_calls.append("re")
            ),
            patch.object(ds, "write_job", side_effect=written.append),
            patch.object(ds, "read_job", return_value={"status": "running"}),
        ):
            with ds.refresh_lock() as held:
                self.assertTrue(held)
                ds._run_batch(
                    universe="CSI300",
                    period="3y",
                    filter_limit_up=True,
                    filter_suspended=True,
                    limit=None,
                )

        self.assertEqual(re_calls, [], "锁被占用时不应调用 RE")
        self.assertTrue(written)
        self.assertEqual(written[-1]["status"], "failed")
        self.assertIn("刷新锁", written[-1]["error"])

    def test_runs_normally_when_lock_free(self):
        captured: dict = {}

        def _fake_backtest(payload, timeout=600):
            captured["payload"] = payload
            return {"factor_analysis": {"ic_mean": 0.01}, "metrics": {}}

        with (
            patch.object(ds, "load_factor_index", return_value=[_panel_factor()]),
            patch.object(ds, "call_yg_backtest", side_effect=_fake_backtest),
            patch.object(ds, "migrate_legacy_factor_dashboard_metrics"),
            patch.object(ds, "_store_metric"),
            patch.object(ds, "write_job"),
            patch.object(ds, "read_job", return_value={}),
            patch.object(ds.time, "sleep"),
        ):
            ds._run_batch(
                universe="CSI300",
                period="3y",
                filter_limit_up=True,
                filter_suspended=True,
                limit=None,
            )

        self.assertIn("payload", captured)


if __name__ == "__main__":
    unittest.main()
