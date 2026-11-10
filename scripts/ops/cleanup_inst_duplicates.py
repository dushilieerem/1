#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""机构端历史脏数据清理：重复研究案、重复授权、同案多份在途议案。

安全策略：
- 默认 dry-run，只读不写。
- 只允许连接库名含 _test/_dev/_ci/_e2e/_local 的库；精确库名 svquant 永不允许。
- 不删除任何业务记录：重复研究案归档为 closed，在途议案作废，重复 qualified 授权撤销；
  已成交订单/成交/持仓一律不动，只输出人工复核清单。
- 所有写操作逐条写 inst_audit_event。

用法：
  python scripts/ops/cleanup_inst_duplicates.py                 # dry-run
  python scripts/ops/cleanup_inst_duplicates.py --apply         # 执行归档/作废/撤销
  python scripts/ops/cleanup_inst_duplicates.py --archive-test-cases --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.core.db import database_url, get_conn  # noqa: E402
from services.institution import inst_service as svc  # noqa: E402

STAMP = "duplicate_cleanup_2026-11-10"
ACTIVE_PROPOSAL_STATUSES = (
    "draft",
    "partner_review",
    "risk_precheck",
    "chairman_review",
    "authorized",
)
TEST_CASE_PATTERNS = ("TST%", "APR%", "DIM%", "ROL%", "RSK%", "EVD%", "TEST%")


def _db_name() -> str:
    return urlparse(database_url()).path.lstrip("/").split("/")[0]


def _guard_db(name: str, *, allow_production: bool, apply: bool, confirm: bool) -> None:
    safe = name.endswith(("_test", "_dev", "_ci", "_e2e", "_local")) or any(
        token in name for token in ("_test", "_dev", "_e2e", "_ci")
    )
    if name == "svquant":
        if not allow_production:
            raise SystemExit(
                "拒绝连接生产库 'svquant'：dry-run 需显式 --allow-production，"
                "apply 还需 --confirm-production。"
            )
        if apply and not confirm:
            raise SystemExit("生产库 apply 必须同时给 --allow-production --confirm-production。")
        return
    if not safe:
        raise SystemExit(
            f"拒绝连接数据库 {name!r}：清理脚本只允许 *_test/*_dev/*_ci/*_e2e/*_local，"
            "或库名 svquant 加 --allow-production。"
        )


def _iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _case_rows(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.id, c.org_id, c.company_id, c.case_no, c.stage, c.stage_no,
               c.stage_state, c.terminal_reason, c.updated_at,
               co.symbol, co.name AS company_name
          FROM inst_research_case c
          JOIN inst_company co ON co.id=c.company_id
         WHERE c.stage <> 'closed'
         ORDER BY c.org_id, c.company_id, c.updated_at DESC NULLS LAST, c.id DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _duplicate_case_groups(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[int, int], list[dict]] = {}
    for row in rows:
        groups.setdefault((int(row["org_id"]), int(row["company_id"])), []).append(row)
    result = []
    for (org_id, company_id), items in groups.items():
        if len(items) < 2:
            continue
        # 优先保留未关闭且最近更新的案；都关闭时保留最近更新。
        items.sort(
            key=lambda r: (
                str(r.get("stage_state") or "") != "closed",
                r.get("updated_at") or datetime.min.replace(tzinfo=timezone.utc),
                int(r["id"]),
            ),
            reverse=True,
        )
        result.append(
            {
                "org_id": org_id,
                "company_id": company_id,
                "symbol": items[0].get("symbol"),
                "company_name": items[0].get("company_name"),
                "keep": items[0],
                "archive": items[1:],
            }
        )
    return result


def _duplicate_auths(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT a.id, a.proposal_version_id, a.status, a.issued_at, a.revoked_at,
               p.org_id, p.case_id,
               EXISTS (SELECT 1 FROM inst_order o WHERE o.authorization_id=a.id) AS has_order
          FROM inst_authorization a
          JOIN inst_proposal_version pv ON pv.id=a.proposal_version_id
          JOIN inst_proposal p ON p.id=pv.proposal_id
         WHERE a.status IN ('qualified', 'filled')
         ORDER BY a.proposal_version_id, a.id
        """
    ).fetchall()
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(int(row["proposal_version_id"]), []).append(dict(row))
    out = []
    for version_id, items in grouped.items():
        if len(items) < 2:
            continue
        items.sort(
            key=lambda r: (
                bool(r.get("has_order")),
                str(r.get("status")) == "filled",
                -int(r["id"]),
            ),
            reverse=True,
        )
        out.append({"proposal_version_id": version_id, "keep": items[0], "extra": items[1:]})
    return out


def _duplicate_proposals(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT p.id, p.org_id, p.case_id, p.status, p.updated_at, p.direction,
               co.symbol, co.name AS company_name
          FROM inst_proposal p
          JOIN inst_research_case c ON c.id=p.case_id
          JOIN inst_company co ON co.id=c.company_id
         WHERE p.stale_at IS NULL AND p.status = ANY(%s)
         ORDER BY p.case_id, p.updated_at DESC NULLS LAST, p.id DESC
        """,
        (list(ACTIVE_PROPOSAL_STATUSES),),
    ).fetchall()
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(int(row["case_id"]), []).append(dict(row))
    out = []
    for case_id, items in grouped.items():
        if len(items) < 2:
            continue
        items.sort(
            key=lambda r: (
                r.get("updated_at") or datetime.min.replace(tzinfo=timezone.utc),
                int(r["id"]),
            ),
            reverse=True,
        )
        out.append({"case_id": case_id, "keep": items[0], "extra": items[1:]})
    return out


def _test_cases(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        name = str(row.get("company_name") or "")
        if any(symbol.startswith(p.rstrip("%")) for p in TEST_CASE_PATTERNS) or (
            "测试" in name or "自检" in name
        ):
            out.append(row)
    return out


def _archive_case(conn, row: dict, *, keep_id: int, reason: str) -> None:
    before = {
        "stage": row.get("stage"),
        "stage_no": row.get("stage_no"),
        "stage_state": row.get("stage_state"),
        "terminal_reason": row.get("terminal_reason"),
    }
    conn.execute(
        """
        UPDATE inst_research_case
           SET stage='closed',
               stage_state='closed',
               terminal_reason=%s,
               stage_gate=COALESCE(stage_gate, '{}'::jsonb)
                          || jsonb_build_object('cleanup', %s::text, 'kept_case_id', %s::int),
               updated_at=NOW()
         WHERE id=%s
        """,
        (reason, STAMP, keep_id, int(row["id"])),
    )
    conn.execute(
        """
        UPDATE inst_proposal
           SET stale_at=NOW(), stale_reason=%s, status='rejected', updated_at=NOW()
         WHERE case_id=%s AND stale_at IS NULL AND status = ANY(%s)
        """,
        (reason, int(row["id"]), list(ACTIVE_PROPOSAL_STATUSES)),
    )
    conn.execute(
        """
        UPDATE inst_authorization a
           SET status='revoked', revoked_at=NOW(), revoke_reason=%s
          FROM inst_proposal_version pv
          JOIN inst_proposal p ON p.id=pv.proposal_id
         WHERE a.proposal_version_id=pv.id AND p.case_id=%s AND a.status='qualified'
        """,
        (reason, int(row["id"])),
    )
    svc._audit(
        conn,
        org_id=int(row["org_id"]),
        actor_member_id=None,
        action="cleanup.duplicate_case.archive",
        object_type="inst_research_case",
        object_id=int(row["id"]),
        before=before,
        after={"status": "closed", "kept_case_id": keep_id, "reason": reason},
    )


def _revoke_auth(conn, auth: dict, *, keep_id: int, reason: str) -> None:
    if str(auth.get("status")) != "qualified":
        return
    conn.execute(
        "UPDATE inst_authorization SET status='revoked', revoked_at=NOW(), revoke_reason=%s "
        "WHERE id=%s AND status='qualified'",
        (reason, int(auth["id"])),
    )
    svc._audit(
        conn,
        org_id=int(auth.get("org_id") or 0),
        actor_member_id=None,
        action="cleanup.duplicate_authorization.revoke",
        object_type="inst_authorization",
        object_id=int(auth["id"]),
        before={"status": auth.get("status")},
        after={"status": "revoked", "kept_authorization_id": keep_id, "reason": reason},
    )


def _reject_proposal(conn, proposal: dict, *, keep_id: int, reason: str) -> None:
    conn.execute(
        "UPDATE inst_proposal SET stale_at=NOW(), stale_reason=%s, status='rejected', updated_at=NOW() "
        "WHERE id=%s AND stale_at IS NULL",
        (reason, int(proposal["id"])),
    )
    svc._audit(
        conn,
        org_id=int(proposal["org_id"]),
        actor_member_id=None,
        action="cleanup.duplicate_proposal.reject",
        object_type="inst_proposal",
        object_id=int(proposal["id"]),
        before={"status": proposal.get("status")},
        after={"status": "rejected", "kept_proposal_id": keep_id, "reason": reason},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="执行写操作；默认只读 dry-run")
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="允许连接库名 svquant（生产）；dry-run 仍需显式开启",
    )
    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="生产库 apply 的二次确认，必须与 --allow-production 同时使用",
    )
    parser.add_argument(
        "--archive-test-cases",
        action="store_true",
        help="同时归档 TST/APR/DIM/ROL/RSK/EVD/TEST 等测试公司研究案",
    )
    parser.add_argument("--report-file", default=None)
    args = parser.parse_args()

    name = _db_name()
    _guard_db(
        name,
        allow_production=args.allow_production,
        apply=args.apply,
        confirm=args.confirm_production,
    )

    with get_conn() as conn:
        cases = _case_rows(conn)
        duplicate_cases = _duplicate_case_groups(cases)
        duplicate_auths = _duplicate_auths(conn)
        duplicate_proposals = _duplicate_proposals(conn)
        test_cases = _test_cases(cases) if args.archive_test_cases else []
        archive_ids = {
            int(x["id"]) for group in duplicate_cases for x in group["archive"]
        } | {int(x["id"]) for x in test_cases}

        report = {
            "database": name,
            "mode": "apply" if args.apply else "dry-run",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "duplicate_case_groups": [
                {
                    "org_id": g["org_id"],
                    "company_id": g["company_id"],
                    "symbol": g["symbol"],
                    "company_name": g["company_name"],
                    "keep": {
                        "id": int(g["keep"]["id"]),
                        "case_no": g["keep"].get("case_no"),
                        "stage_no": g["keep"].get("stage_no"),
                    },
                    "archive": [
                        {
                            "id": int(x["id"]),
                            "case_no": x.get("case_no"),
                            "stage_no": x.get("stage_no"),
                        }
                        for x in g["archive"]
                    ],
                }
                for g in duplicate_cases
            ],
            "duplicate_authorizations": [
                {
                    "proposal_version_id": g["proposal_version_id"],
                    "keep": g["keep"],
                    "extra": g["extra"],
                }
                for g in duplicate_auths
            ],
            "duplicate_proposals": [
                {
                    "case_id": g["case_id"],
                    "keep": g["keep"],
                    "extra": g["extra"],
                }
                for g in duplicate_proposals
            ],
            "test_cases": [
                {
                    "id": int(x["id"]),
                    "symbol": x.get("symbol"),
                    "company_name": x.get("company_name"),
                    "case_no": x.get("case_no"),
                }
                for x in test_cases
            ],
            "summary": {
                "duplicate_case_groups": len(duplicate_cases),
                "cases_to_archive": len(archive_ids),
                "duplicate_authorization_groups": len(duplicate_auths),
                "qualified_authorizations_to_revoke": sum(
                    1 for g in duplicate_auths for x in g["extra"] if x.get("status") == "qualified"
                ),
                "filled_authorizations_manual_review": sum(
                    1 for g in duplicate_auths for x in g["extra"] if x.get("status") == "filled"
                ),
                "duplicate_proposal_groups": len(duplicate_proposals),
                "proposals_to_reject": sum(len(g["extra"]) for g in duplicate_proposals),
                "test_cases_to_archive": len(test_cases),
            },
        }

        if args.apply:
            archived_case_ids: set[int] = set()
            for group in duplicate_cases:
                for row in group["archive"]:
                    if int(row["id"]) in archived_case_ids:
                        continue
                    _archive_case(
                        conn,
                        row,
                        keep_id=int(group["keep"]["id"]),
                        reason="同公司重复研究案，归档旧案（保留最新有效案）",
                    )
                    archived_case_ids.add(int(row["id"]))
            for row in test_cases:
                if int(row["id"]) in archived_case_ids:
                    continue
                _archive_case(
                    conn,
                    row,
                    keep_id=0,
                    reason="测试/自检公司研究案，归档清理",
                )
                archived_case_ids.add(int(row["id"]))
            for group in duplicate_auths:
                for auth in group["extra"]:
                    _revoke_auth(
                        conn,
                        auth,
                        keep_id=int(group["keep"]["id"]),
                        reason="同一议案版本重复授权，撤销多余授权",
                    )
            for group in duplicate_proposals:
                for proposal in group["extra"]:
                    _reject_proposal(
                        conn,
                        proposal,
                        keep_id=int(group["keep"]["id"]),
                        reason="同一研究案多份在途议案，保留最新一份",
                    )
            report["applied"] = True

    out_path = Path(args.report_file) if args.report_file else (
        ROOT / "docs/测试设计/evidence" / f"inst-duplicate-cleanup-{date.today():%Y%m%d}" / "report.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    s = report["summary"]
    print(f"database={name} mode={report['mode']}")
    print(
        "重复研究案组={duplicate_case_groups} 待归档案={cases_to_archive} "
        "重复授权组={duplicate_authorization_groups} 待撤销qualified={qualified_authorizations_to_revoke} "
        "已成交重复授权(人工复核)={filled_authorizations_manual_review} "
        "同案多议案组={duplicate_proposal_groups} 待作废议案={proposals_to_reject}".format(**s)
    )
    if args.archive_test_cases:
        print(f"测试公司研究案={s['test_cases_to_archive']}")
    print(f"report={out_path}")
    if not args.apply:
        print("dry-run：未写任何数据；确认后加 --apply 执行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
