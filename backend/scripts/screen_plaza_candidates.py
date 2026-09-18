# -*- coding: utf-8 -*-
"""Screen plaza candidates: 3y vectorized backtests against RE; print ranked table."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from services.core.re_config import RE_BASE

START, END = "2023-07-03", "2026-07-03"

CANDIDATES: list[dict] = []


def _code(name: str, body: str) -> None:
    CANDIDATES.append({"key": name, "code": body.strip() + "\n"})


_code(
    "mom60_w_csi500",
    '''
from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,
)

class Mom60Weekly(FactorPortfolioStrategy):
    selector = TopN(20)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(5)

    @factor
    def mom60(self):
        return self.close.pct_change(60)

    @signal
    def score(self):
        return self.mom60()
''',
)

_code(
    "mom12_1_csi500",
    '''
from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,
)

class Mom12_1(FactorPortfolioStrategy):
    """Jegadeesh-Titman 12-1 近似：近一年收益剔除近月。"""
    selector = TopN(20)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(20)

    @factor
    def mom_12_1(self):
        return self.close.pct_change(252) - self.close.pct_change(21)

    @signal
    def score(self):
        return self.mom_12_1()
''',
)

_code(
    "lowvol60_m_csi500",
    '''
from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,
)

class LowVol60Monthly(FactorPortfolioStrategy):
    selector = TopN(30)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(20)

    @factor
    def neg_vol60(self):
        return -self.close.pct_change().rolling(60).std()

    @signal
    def score(self):
        return self.neg_vol60()
''',
)

_code(
    "blend_mom_lowvol",
    '''
from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,
)

class BlendMomLowVol(FactorPortfolioStrategy):
    selector = TopN(20)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(10)

    @factor
    def mom40(self):
        return self.close.pct_change(40)

    @factor
    def neg_vol40(self):
        return -self.close.pct_change().rolling(40).std()

    @signal
    def score(self):
        m = self.mom40()
        v = self.neg_vol40()
        # 截面排名后等权合成
        mr = m.rank(axis=1, pct=True)
        vr = v.rank(axis=1, pct=True)
        return 0.6 * mr + 0.4 * vr
''',
)

_code(
    "quality_mom_csi300",
    '''
from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,
)

class QualityMom(FactorPortfolioStrategy):
    """中期动量 + 低换手近似（用波动代理稳定度）。"""
    selector = TopN(15)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(10)

    @factor
    def mom120(self):
        return self.close.pct_change(120)

    @factor
    def stability(self):
        return -self.close.pct_change().rolling(60).std()

    @signal
    def score(self):
        return 0.7 * self.mom120().rank(axis=1, pct=True) + 0.3 * self.stability().rank(axis=1, pct=True)
''',
)

_code(
    "rev5_skip_mom20",
    '''
from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,
)

class RevSkipMom(FactorPortfolioStrategy):
    """短期反转 + 中期动量过滤。"""
    selector = TopN(15)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(5)

    @factor
    def short_rev(self):
        return -self.close.pct_change(5)

    @factor
    def mid_mom(self):
        return self.close.pct_change(20)

    @signal
    def score(self):
        # 只要中期动量为正侧的反转候选
        gate = (self.mid_mom() > 0).astype(float)
        return self.short_rev().rank(axis=1, pct=True) * gate
''',
)

_code(
    "vol_price_thrust",
    '''
from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,
)

class VolPriceThrust(FactorPortfolioStrategy):
    """价涨量增：动量 × 成交额相对强度。"""
    selector = TopN(20)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(5)

    @factor
    def mom20(self):
        return self.close.pct_change(20)

    @factor
    def amt_rel(self):
        amt = self.amount
        return amt / amt.rolling(20).mean()

    @signal
    def score(self):
        return self.mom20().rank(axis=1, pct=True) * 0.5 + self.amt_rel().rank(axis=1, pct=True) * 0.5
''',
)

_code(
    "builtin_mom20_daily",
    '''
from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,
)

class CrossSectionalMomentumStrategy(FactorPortfolioStrategy):
    selector = TopN(10)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(1)

    @factor
    def momentum_20d(self):
        return self.close.pct_change(20)

    @signal
    def score(self):
        return self.momentum_20d()
''',
)


def _post_json(url: str, body: dict, timeout: int = 120) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": raw[:500]}


def _get_json(url: str, timeout: int = 60) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def run_bt(code: str, *, universe: str, benchmark: str) -> dict:
    body = {
        "strategy_code": code,
        "universe": universe,
        "benchmark": benchmark,
        "start": START,
        "end": END,
        "commission_rate": 0.0003,
        "stamp_tax": 0.001,
        "slippage_rate": 0.001,
        "initial_capital": 1_000_000,
        "engine_mode": "vectorized",
        "include_rebalance_logs": False,
    }
    st, data = _post_json(f"{RE_BASE}/api/backtest/strategy", body, timeout=180)
    if st in (200, 202) and data.get("run_id"):
        run_id = data["run_id"]
        deadline = time.time() + 600
        while time.time() < deadline:
            time.sleep(1.5)
            task = _get_json(f"{RE_BASE}/api/backtest/strategy/{run_id}", timeout=60)
            status = str(task.get("status") or "")
            if status == "succeeded":
                result = task.get("result") or {}
                if result.get("error"):
                    raise RuntimeError(str(result["error"]))
                return result
            if status in ("failed", "cancelled"):
                raise RuntimeError(str(task.get("error") or status))
        raise RuntimeError("timeout")
    if st == 200 and (data.get("metrics") or data.get("equity_curve")):
        if data.get("error"):
            raise RuntimeError(str(data["error"]))
        return data
    raise RuntimeError(f"HTTP {st}: {data}")


def main() -> None:
    print("RE", RE_BASE)
    rows = []
    universes = {
        "mom60_w_csi500": ("CSI500", "CSI500"),
        "mom12_1_csi500": ("CSI500", "CSI500"),
        "lowvol60_m_csi500": ("CSI500", "CSI500"),
        "blend_mom_lowvol": ("CSI500", "CSI500"),
        "quality_mom_csi300": ("CSI300", "CSI300"),
        "rev5_skip_mom20": ("CSI500", "CSI500"),
        "vol_price_thrust": ("CSI500", "CSI500"),
        "builtin_mom20_daily": ("CSI300", "CSI300"),
    }
    for c in CANDIDATES:
        key = c["key"]
        uni, bm = universes[key]
        print("running", key, uni)
        try:
            res = run_bt(c["code"], universe=uni, benchmark=bm)
            m = res.get("metrics") or {}
            row = {
                "key": key,
                "uni": uni,
                "annual": m.get("annual_return"),
                "cum": m.get("cumulative_return") or m.get("total_return"),
                "mdd": m.get("max_drawdown"),
                "sharpe": m.get("sharpe"),
                "excess": res.get("excess_return"),
                "n": len(res.get("equity_curve") or []),
                "ok": True,
                "result": res,
                "code": c["code"],
            }
            print(
                " ",
                f"ar={row['annual']}",
                f"sharpe={row['sharpe']}",
                f"mdd={row['mdd']}",
                f"n={row['n']}",
            )
        except Exception as e:
            print("  FAIL", e)
            row = {"key": key, "uni": uni, "ok": False, "err": str(e)}
        rows.append(row)

    ok = [r for r in rows if r.get("ok")]
    ok.sort(key=lambda r: (r.get("sharpe") or -99, r.get("annual") or -99), reverse=True)
    print("\n=== RANKED (sharpe, annual) ===")
    for r in ok:
        print(
            f"{r['key']:22} ar={r['annual']!s:>12} sharpe={r['sharpe']!s:>8} "
            f"mdd={r['mdd']!s:>12} excess={r['excess']!s:>10}"
        )

    # dump top picks for seed script
    out = [
        {
            "key": r["key"],
            "universe": r["uni"],
            "benchmark": r["uni"],
            "annual": r["annual"],
            "sharpe": r["sharpe"],
            "mdd": r["mdd"],
            "excess": r["excess"],
            "code": r["code"],
            "result_metrics": (r["result"].get("metrics") if r.get("result") else None),
            "has_curve": bool(r.get("result") and r["result"].get("equity_curve")),
        }
        for r in ok[:5]
    ]
    path = "scripts/_plaza_screen_top.json"
    with open(path, "w", encoding="utf-8") as f:
        # store full results for top 4 for seeding
        dump = []
        for r in ok[:4]:
            dump.append(
                {
                    "key": r["key"],
                    "universe": r["uni"],
                    "benchmark": r["uni"],
                    "code": r["code"],
                    "result": r["result"],
                }
            )
        json.dump(dump, f, ensure_ascii=False)
    print("wrote", path, "top", len(dump))


if __name__ == "__main__":
    main()
