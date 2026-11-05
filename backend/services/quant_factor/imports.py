"""AC-08a: import SVQuant existing factors into the org-shared library.

Metadata import is idempotent and never touches candidates/trials, so it does
not add K. Metrics are left pending for the bounded background batch.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from services.core.db import get_conn
from services.factor.re_factor_catalog import fetch_re_catalog

EXPECTED_CATALOG_COUNT = 331


def _import_hash(row: dict) -> str:
    identity = [
        row["source_library"], row["source_factor_id"], row["factor_name"],
        row["display_name"], row["definition"], row["definition_source"],
    ]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode("utf-8")).hexdigest()


def _metadata_rows(raw: dict) -> list[dict]:
    if not raw.get("ok") or raw.get("errors") or not raw.get("factors"):
        raise ValueError("因子库目录读取不完整，暂停导入；请恢复 RE 目录后重试")
    rows = []
    seen = set()
    for factor in raw["factors"]:
        library = str(factor.get("library") or "").strip()
        factor_id = str(factor.get("factor_id") or factor.get("name") or "").strip()
        name = str(factor.get("name") or "").strip()
        if not library or not factor_id or not name:
            raise ValueError("RE 目录存在缺少 library/factor_id/name 的条目，拒绝部分导入")
        key = (library, factor_id)
        if key in seen:
            raise ValueError(f"RE 目录存在重复因子 {library}/{factor_id}，拒绝导入")
        seen.add(key)
        row = {
            "source_library": library,
            "source_factor_id": factor_id,
            "factor_name": name,
            "display_name": str(factor.get("display_name") or "").strip(),
            "definition": str(factor.get("description") or name).strip() or name,
            "definition_source": "源码不可见（RE 内置）",
            "category": str(factor.get("category_label") or factor.get("category_name") or "").strip(),
        }
        row["import_hash"] = _import_hash(row)
        rows.append(row)
    return rows


def sync_existing(uid: int, org: int) -> dict:
    """Idempotent metadata upsert; manager-triggered by the route."""
    raw = fetch_re_catalog(include_all=True)
    rows = _metadata_rows(raw)
    with get_conn() as c:
        existing = {
            (row["source_library"], row["source_factor_id"]): row["import_hash"]
            for row in c.execute(
                "SELECT source_library,source_factor_id,import_hash FROM quant_factor_imported_factors WHERE org_id=%s",
                (org,)).fetchall()
        }
        inserted = updated = unchanged = 0
        for row in rows:
            key = (row["source_library"], row["source_factor_id"])
            old_hash = existing.get(key)
            if old_hash == row["import_hash"]:
                c.execute(
                    """UPDATE quant_factor_imported_factors SET category=%s
                       WHERE org_id=%s AND source_library=%s AND source_factor_id=%s AND category<>%s""",
                    (row["category"], org, row["source_library"], row["source_factor_id"], row["category"]))
                unchanged += 1
                continue
            c.execute(
                """INSERT INTO quant_factor_imported_factors
                   (id,org_id,created_by,source_library,source_factor_id,factor_name,
                    display_name,definition,definition_source,import_hash,category)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (org_id,source_library,source_factor_id) DO UPDATE SET
                     factor_name=EXCLUDED.factor_name,
                     display_name=EXCLUDED.display_name,
                     definition=EXCLUDED.definition,
                     definition_source=EXCLUDED.definition_source,
                     import_hash=EXCLUDED.import_hash,
                     category=EXCLUDED.category,
                     updated_at=NOW()""",
                (str(uuid.uuid4()), org, uid, row["source_library"], row["source_factor_id"],
                 row["factor_name"], row["display_name"], row["definition"],
                 row["definition_source"], row["import_hash"]))
            if old_hash is None:
                inserted += 1
            else:
                updated += 1
    return {
        "catalog_count": len(rows),
        "expected_catalog_count": EXPECTED_CATALOG_COUNT,
        "count_matches": len(rows) == EXPECTED_CATALOG_COUNT,
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
    }


REFERENCE_RULE_VERSION = "yg_v1"
REFERENCE_NOTE = "SVQuant 面板参考（yg_v1：滚动区间、多空五组、20 日调仓、次日收盘、零费率），不是 import-benchmark-v1 正式指标；不从汇总 IC 反推 NW t。"


def reference_inventory(uid: int, org: int) -> dict:
    """Existing panel cache matched by library + factor name, for first delivery.

    The panel row is a separate labelled view. It is never written into
    ``metrics`` and never counted as the PM-V5-019 formal benchmark.
    """
    with get_conn() as c:
        rows = [dict(row) for row in c.execute(
            """SELECT i.id, i.source_library, i.source_factor_id, i.factor_name,
                      i.display_name, i.definition, i.category, i.status, i.metrics_status,
                      d.universe AS reference_universe, d.period AS reference_period,
                      d.filter_limit_up AS reference_filter_limit_up,
                      d.filter_suspended AS reference_filter_suspended,
                      d.rules_version AS reference_rules_version,
                      d.rank_ic AS reference_rank_ic, d.ic_mean AS reference_ic_mean,
                      d.ir AS reference_ir, d.turnover AS reference_turnover,
                      d.coverage_pool AS reference_coverage_pool,
                      d.computed_at AS reference_computed_at
               FROM quant_factor_imported_factors i
               LEFT JOIN LATERAL (
                   SELECT x.* FROM factor_dashboard_metrics x
                   WHERE x.library=i.source_library AND x.factor_name=i.factor_name
                     AND x.rules_version=%s
                   ORDER BY (x.universe='CSI300') DESC, (x.period='3y') DESC, (x.filter_limit_up=1) DESC, (x.filter_suspended=1) DESC, x.computed_at DESC
                   LIMIT 1
               ) d ON TRUE
               WHERE i.org_id=%s
               ORDER BY i.source_library, i.source_factor_id""",
            (REFERENCE_RULE_VERSION, org)).fetchall()]
    items = []
    found = 0
    for row in rows:
        has_reference = row.get("reference_universe") is not None
        found += 1 if has_reference else 0
        item = {
            "id": row["id"],
            "source_library": row["source_library"],
            "source_factor_id": row["source_factor_id"],
            "factor_name": row["factor_name"],
            "display_name": row["display_name"],
            "definition": row["definition"],
            "category": row["category"] or "",
            "status": row["status"],
            "metrics_status": row["metrics_status"],
            "reference": None,
        }
        if has_reference:
            item["reference"] = {
                "rule_version": row["reference_rules_version"],
                "universe": row["reference_universe"],
                "period": row["reference_period"],
                "filter_limit_up": bool(row["reference_filter_limit_up"]),
                "filter_suspended": bool(row["reference_filter_suspended"]),
                # factor_dashboard_metrics stores Rank IC and turnover as percent points.
                "rank_ic": (float(row["reference_rank_ic"]) / 100.0 if row["reference_rank_ic"] is not None and -100 <= float(row["reference_rank_ic"]) <= 100 else None),
                "rank_ic_raw": row["reference_rank_ic"],
                "rank_ic_note": ("换算后仍超出 [-1,1]，口径待核对" if row["reference_rank_ic"] is not None and not -100 <= float(row["reference_rank_ic"]) <= 100 else ""),
                "ic_mean": row["reference_ic_mean"],
                "ir": row["reference_ir"],
                "turnover": (float(row["reference_turnover"]) / 100.0 if row["reference_turnover"] is not None else None),
                "coverage_pool": row["reference_coverage_pool"],
                "computed_at": row["reference_computed_at"],
                "note": REFERENCE_NOTE,
            }
        items.append(item)
    return {
        "total": len(items),
        "found": found,
        "missing": len(items) - found,
        "reference_rule_version": REFERENCE_RULE_VERSION,
        "note": REFERENCE_NOTE,
        "items": items,
    }


def summary(uid: int, org: int) -> dict:
    with get_conn() as c:
        rows = c.execute(
            """SELECT status,metrics_status,COUNT(*) AS n
               FROM quant_factor_imported_factors WHERE org_id=%s
               GROUP BY status,metrics_status ORDER BY status,metrics_status""",
            (org,)).fetchall()
    return {"by_status": [dict(row) for row in rows], "total": sum(row["n"] for row in rows)}


__all__ = ["EXPECTED_CATALOG_COUNT", "REFERENCE_RULE_VERSION", "reference_inventory", "summary", "sync_existing"]
