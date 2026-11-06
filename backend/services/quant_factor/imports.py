"""AC-08a: import SVQuant existing factors into the org-shared library.

Metadata import is idempotent and never touches candidates/trials, so it does
not add K. Metrics are left pending for the bounded background batch.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from services.core.db import get_conn
from services.core.tenant import Tenant
from . import repo
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
                unchanged += 1
                continue
            c.execute(
                """INSERT INTO quant_factor_imported_factors
                   (id,org_id,created_by,source_library,source_factor_id,factor_name,
                    display_name,definition,definition_source,import_hash)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (org_id,source_library,source_factor_id) DO UPDATE SET
                     factor_name=EXCLUDED.factor_name,
                     display_name=EXCLUDED.display_name,
                     definition=EXCLUDED.definition,
                     definition_source=EXCLUDED.definition_source,
                     import_hash=EXCLUDED.import_hash,
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


def summary(uid: int, org: int) -> dict:
    rows = repo.imported_summary(Tenant.from_pair(uid, org))
    return {"by_status": rows, "total": sum(row["n"] for row in rows)}


__all__ = ["EXPECTED_CATALOG_COUNT", "summary", "sync_existing"]
