# -*- coding: utf-8 -*-
"""机构端业务接口：公司池、研究、辩论、议案、审批、授权、模拟执行、投后。

所有接口都在 `/api/inst/*` 下，只接受机构令牌（scope=inst）。
`require_inst_user` 返回的上下文含 org / role / member_id；写操作的职责分离在服务层校验。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_inst_user
from services.institution import inst_service as svc

router = APIRouter(tags=["institution-workflow"], prefix="/api/inst")


def _ctx(ctx: dict[str, Any]) -> tuple[int, int | None, str]:
    org_id = int((ctx.get("org") or {}).get("id") or 0)
    member_id = int(ctx.get("member_id") or 0) or None
    role = str(ctx.get("role") or "")
    return org_id, member_id, role


def _require_ws(ctx: dict[str, Any], workspace: str) -> None:
    access = (ctx.get("permissions") or {}).get(workspace, "none")
    if access == "none":
        raise HTTPException(status_code=403, detail="当前角色无权访问该工作区")


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, svc.AiUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail="机构端服务异常")


@router.get("/overview")
def overview(ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, _, role = _ctx(ctx)
    _require_ws(ctx, "overview")
    return {"ok": True, **svc.overview(org_id, role)}


@router.get("/companies")
def companies(
    market: str | None = None,
    q: str | None = None,
    pool_status: str | None = None,
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "ideas")
    return {"ok": True, "items": svc.list_companies(org_id, market=market, q=q, pool_status=pool_status)}


@router.get("/companies/{company_id}")
def company(company_id: int, ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "research")
    data = svc.get_company(org_id, company_id)
    if not data:
        raise HTTPException(status_code=404, detail="公司不存在")
    return {"ok": True, **data}


@router.post("/companies/{company_id}/pool")
def update_pool(
    company_id: int,
    body: dict[str, Any],
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "ideas")
    try:
        return svc.update_company_pool(
            org_id,
            company_id,
            pool_status=str(body.get("pool_status") or "research"),
            reason=body.get("reason"),
            actor_member_id=member_id,
        )
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/cases")
def cases(
    company_id: int | None = None,
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "research")
    return {"ok": True, "items": svc.list_cases(org_id, company_id=company_id)}


@router.post("/cases")
def create_case(body: dict[str, Any], ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "research")
    try:
        return {"ok": True, **svc.create_case(org_id, int(body.get("company_id") or 0), member_id)}
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/cases/{case_id}")
def case_detail(case_id: int, ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "research")
    data = svc.get_case(org_id, case_id)
    if not data:
        raise HTTPException(status_code=404, detail="研究案不存在")
    return {"ok": True, **data}


@router.post("/cases/{case_id}/research")
def generate_research(
    case_id: int,
    body: dict[str, Any] | None = None,
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "research")
    payload = body or {}
    try:
        return {
            "ok": True,
            **svc.generate_research(
                org_id,
                case_id,
                mode=str(payload.get("mode") or "full"),
                actor_member_id=member_id,
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/research/{version_id}/review")
def review_research(
    version_id: int,
    body: dict[str, Any],
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "research")
    try:
        return {
            "ok": True,
            **svc.review_research(
                org_id,
                version_id,
                decision=str(body.get("decision") or "approve"),
                comment=body.get("comment"),
                actor_member_id=member_id,
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/cases/{case_id}/ai/memo")
def research_memo(case_id: int, ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "research")
    try:
        return {"ok": True, **svc.ai_research_memo(org_id, case_id)}
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/proposals/{proposal_id}/ai/risk-review")
def risk_review_ai(proposal_id: int, ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "approvals")
    try:
        return {"ok": True, **svc.ai_risk_review(org_id, proposal_id)}
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/proposals/{proposal_id}/ai/chairman-memo")
def chairman_memo_ai(proposal_id: int, ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "approvals")
    try:
        return {"ok": True, **svc.ai_chairman_memo(org_id, proposal_id)}
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/cases/{case_id}/debate")
def start_debate(
    case_id: int,
    body: dict[str, Any] | None = None,
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "debate")
    payload = body or {}
    try:
        return {
            "ok": True,
            **svc.start_debate(
                org_id,
                case_id,
                actor_member_id=member_id,
                use_ai=bool(payload.get("use_ai", True)),
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/debates/{session_id}")
def debate(session_id: int, ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "debate")
    data = svc.get_debate(org_id, session_id)
    if not data:
        raise HTTPException(status_code=404, detail="辩论不存在")
    return {"ok": True, **data}


@router.get("/proposals")
def proposals(
    status: str | None = None,
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "approvals")
    return {"ok": True, "items": svc.list_proposals(org_id, status=status)}


@router.post("/cases/{case_id}/proposals")
def create_proposal(
    case_id: int,
    body: dict[str, Any],
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "approvals")
    try:
        return {
            "ok": True,
            **svc.create_proposal(
                org_id,
                case_id,
                actor_member_id=member_id,
                direction=str(body.get("direction") or "buy"),
                target_weight=float(body.get("target_weight") or 0.05),
                config=body.get("config") or {},
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/proposals/{proposal_id}")
def proposal_detail(proposal_id: int, ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "approvals")
    data = svc.get_proposal(org_id, proposal_id)
    if not data:
        raise HTTPException(status_code=404, detail="议案不存在")
    return {"ok": True, **data}


@router.post("/proposals/{proposal_id}/partner")
def partner_review(
    proposal_id: int,
    body: dict[str, Any],
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "approvals")
    try:
        return {
            "ok": True,
            **svc.partner_review(
                org_id,
                proposal_id,
                decision=str(body.get("decision") or "approve"),
                comment=body.get("comment"),
                updates=body.get("updates") or {},
                actor_member_id=member_id,
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/proposals/{proposal_id}/chairman")
def chairman_review(
    proposal_id: int,
    body: dict[str, Any],
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "approvals")
    try:
        return {
            "ok": True,
            **svc.chairman_review(
                org_id,
                proposal_id,
                decision=str(body.get("decision") or "approve"),
                comment=body.get("comment"),
                actor_member_id=member_id,
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/proposals/{proposal_id}/risk-check")
def risk_check(
    proposal_id: int,
    body: dict[str, Any] | None = None,
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "approvals")
    payload = body or {}
    try:
        return {
            "ok": True,
            **svc.risk_check(
                org_id, proposal_id, actor_member_id=member_id, comment=payload.get("comment")
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/proposals/{proposal_id}/authorize")
def authorize(proposal_id: int, ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "approvals")
    try:
        return {"ok": True, **svc.authorize(org_id, proposal_id, actor_member_id=member_id)}
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/authorizations")
def authorizations(
    status: str | None = None,
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "execution")
    return {"ok": True, "items": svc.list_authorizations(org_id, status=status)}


@router.post("/authorizations/{authorization_id}/execute")
def execute(
    authorization_id: int,
    body: dict[str, Any] | None = None,
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "execution")
    payload = body or {}
    try:
        price = payload.get("price")
        return {
            "ok": True,
            **svc.execute_authorization(
                org_id,
                authorization_id,
                actor_member_id=member_id,
                price=float(price) if price is not None else None,
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/portfolio")
def portfolio(ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "portfolio")
    return {"ok": True, **svc.portfolio(org_id)}


@router.get("/monitor")
def monitor(ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "monitor")
    return {"ok": True, **svc.monitor(org_id)}


@router.post("/monitor/events")
def create_event(body: dict[str, Any], ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "monitor")
    try:
        return {
            "ok": True,
            **svc.create_monitor_event(
                org_id,
                int(body.get("company_id") or 0),
                event_type=str(body.get("type") or "manual"),
                severity=str(body.get("severity") or "info"),
                detail=str(body.get("detail") or ""),
                actor_member_id=member_id,
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/monitor/exits")
def create_exit(body: dict[str, Any], ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "monitor")
    try:
        return {
            "ok": True,
            **svc.create_exit_case(
                org_id,
                int(body.get("company_id") or 0),
                reason_type=str(body.get("reason_type") or "other"),
                memo=str(body.get("memo") or ""),
                actor_member_id=member_id,
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/audit")
def audit(limit: int = 100, ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "overview")
    return {"ok": True, "items": svc.list_audit(org_id, limit=limit)}
