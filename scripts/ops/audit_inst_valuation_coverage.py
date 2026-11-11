# -*- coding: utf-8 -*-
"""只读审计：全部在上市标的的估值模型覆盖情况。

输出 CSV：symbol,name,market,price,available,method,shares_source,base,ratio,reason,error
用法：
  python scripts/ops/audit_inst_valuation_coverage.py --workers 8
  python scripts/ops/audit_inst_valuation_coverage.py --limit 100
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from services.core.db import get_conn  # noqa: E402
from services.institution.research_service import _build_research  # noqa: E402


def _universe(limit: int | None) -> list[dict[str, Any]]:
    sql = (
        "SELECT DISTINCT ON (symbol) id, symbol, name, market, industry, data_status, ref_price "
        "FROM inst_company WHERE org_id=1 AND symbol IS NOT NULL ORDER BY symbol, id DESC"
    )
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql).fetchall()]
    if limit:
        rows = rows[:limit]
    return rows


def _audit_one(company: dict[str, Any]) -> dict[str, Any]:
    symbol = str(company.get("symbol") or "")
    price = company.get("ref_price")
    try:
        built = _build_research(company)
        valuation = built.get("valuation") or {}
        latest = (built.get("facts") or {}).get("financials") or []
        price = (built.get("facts") or {}).get("price") or price
        method = str(valuation.get("method") or "")
        available = bool(valuation.get("available")) or (
            method not in {"", "unavailable"} and valuation.get("base") is not None
        )
        base = valuation.get("base")
        ratio = None
        try:
            if base is not None and price:
                ratio = round(float(base) / float(price), 4)
        except (TypeError, ValueError):
            ratio = None
        return {
            "symbol": symbol,
            "name": company.get("name") or "",
            "market": company.get("market") or "",
            "price": price,
            "available": int(available),
            "method": method or "missing",
            "shares_source": valuation.get("shares_source") or "",
            "base": base,
            "ratio": ratio,
            "reason": valuation.get("reason") or "",
            "error": "",
            "financial_rows": len(latest),
        }
    except Exception as exc:  # noqa: BLE001 - 审计要记录单票失败，不中断全量
        return {
            "symbol": symbol,
            "name": company.get("name") or "",
            "market": company.get("market") or "",
            "price": price,
            "available": 0,
            "method": "error",
            "shares_source": "",
            "base": None,
            "ratio": None,
            "reason": "",
            "error": f"{type(exc).__name__}: {exc}"[:300],
            "financial_rows": 0,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--out",
        default=str(BACKEND / "output" / f"inst_valuation_coverage_{date.today():%Y%m%d}.csv"),
    )
    args = parser.parse_args()
    companies = _universe(args.limit or None)
    print(f"universe={len(companies)} workers={args.workers}", flush=True)
    started = time.time()
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(_audit_one, c): c for c in companies}
        for index, future in enumerate(as_completed(futures), start=1):
            rows.append(future.result())
            if index % 500 == 0:
                print(f"  {index}/{len(companies)} {round(time.time()-started,1)}s", flush=True)
    rows.sort(key=lambda r: r["symbol"])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [
            "symbol", "name", "market", "price", "available", "method",
            "shares_source", "base", "ratio", "reason", "error", "financial_rows",
        ])
        writer.writeheader()
        writer.writerows(rows)
    methods = Counter(str(r["method"]) for r in rows)
    reasons = Counter(str(r["reason"]) for r in rows if not int(r["available"]))
    promoted = sum(1 for r in rows if int(r["available"]))
    print(f"elapsed={round(time.time()-started,1)}s available={promoted}/{len(rows)} ({promoted/len(rows) if rows else 0:.1%})")
    print("methods=", dict(methods.most_common()))
    print("unavailable_reasons=", dict(reasons.most_common(10)))
    print("out=", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
