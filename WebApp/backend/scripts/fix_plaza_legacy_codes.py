# -*- coding: utf-8 -*-
"""Fix plaza-from-run items so 极速运行 works on current RE."""
from __future__ import annotations

import json
import re

from services.core.db import get_conn

NEW_IMPORT = """from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight,
    EveryNTradingDays,
    FactorPortfolioStrategy,
    TopN,
    factor,
    signal,
)"""

# id 5: multifactor — panel 已无 total_mv/pe_ttm 别名，改为现网可用字段，逻辑仍为多因子合成
MF_CODE = '''from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight,
    EveryNTradingDays,
    FactorPortfolioStrategy,
    TopN,
    factor,
    signal,
)

# --- SVQUANT_PARAMS (与左侧表单同步，请求以表单为准) ---
UNIVERSE = "CSI500"
BENCHMARK = "CSI300"
COMMISSION_RATE = 0.0003
STAMP_TAX = 0.001
SLIPPAGE_RATE = 0.001
INITIAL_CAPITAL = 1_000_000
TOP_N = 30
REBALANCE_DAYS = 20
# --- SVQUANT_PARAMS_END ---


class MultiFactorSampleStrategy(FactorPortfolioStrategy):
    """动量 + 低流动性拥挤度 + 低换手，赋权相加合成。"""

    selector = TopN(30)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(20)

    @factor
    def momentum_20d(self, window: int = 20):
        return self.close.pct_change(window)

    @factor
    def small_amount(self):
        """相对不拥挤：近 20 日成交额均值越低越好。"""
        return -self.amount.rolling(20).mean()

    @factor
    def low_turnover(self):
        return -self.turnover.rolling(20).mean()

    @signal
    def score(self):
        return (
            0.5 * self.rank(self.momentum_20d())
            + 0.3 * self.rank(self.small_amount())
            + 0.2 * self.rank(self.low_turnover())
        )
'''


def _rewrite_quantcore(code: str) -> str:
    code = re.sub(
        r"from\s+quantcore\s+import\s*\([^)]*\)",
        NEW_IMPORT,
        code,
        count=1,
        flags=re.DOTALL,
    )
    code = re.sub(
        r"from\s+app\.quantcore\s+import\s*\([^)]*\)",
        NEW_IMPORT,
        code,
        count=1,
        flags=re.DOTALL,
    )
    return code


def main() -> None:
    with get_conn() as conn:
        for iid in (5, 6, 7):
            row = conn.execute(
                "SELECT id, title, snapshot FROM strategy_plaza_items WHERE id=%s",
                (iid,),
            ).fetchone()
            if not row:
                print("missing", iid)
                continue
            snap = row["snapshot"]
            if isinstance(snap, str):
                snap = json.loads(snap)
            code = str(snap.get("strategy_code") or "")
            if iid == 5:
                code = MF_CODE
                snap["engine_mode"] = "vectorized"
            elif iid == 7:
                code = _rewrite_quantcore(code)
                snap["engine_mode"] = "vectorized"
            elif iid == 6:
                # event strategy
                snap["engine_mode"] = "event"
            snap["strategy_code"] = code
            conn.execute(
                """
                UPDATE strategy_plaza_items
                SET snapshot = %s::jsonb, updated_at = NOW()
                WHERE id = %s
                """,
                (json.dumps(snap, ensure_ascii=False), iid),
            )
            print(
                "patched",
                iid,
                row["title"],
                "mode",
                snap.get("engine_mode"),
                "qc",
                "quantcore" in code,
                "new",
                "app.services.strategy.vectorized" in code,
            )


if __name__ == "__main__":
    main()
