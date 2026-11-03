# -*- coding: utf-8 -*-
"""机构端业务接口：公司池、研究、辩论、议案、审批、授权、模拟执行、投后。

所有接口都在 `/api/inst/*` 下，只接受机构令牌（scope=inst）。
`require_inst_user` 返回的上下文含 org / role / member_id；写操作的职责分离在服务层校验。
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response

from app.deps import require_inst_user
from services.institution import inst_service as svc
from services.institution.valuation import run_dcf

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
    limit: int = 60,
    offset: int = 0,
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "ideas")
    return {
        "ok": True,
        **svc.list_companies(
            org_id,
            market=market,
            q=q,
            pool_status=pool_status,
            limit=limit,
            offset=offset,
        ),
    }


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


@router.post("/companies/{company_id}/dcf")
def company_dcf(
    company_id: int,
    body: dict[str, Any],
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    """FR-RES-19..22：五年 DCF + 敏感性表（确定性计算，不是目标价）。"""
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "research")
    if not svc.get_company(org_id, company_id):
        raise HTTPException(status_code=404, detail="公司不存在")
    try:
        return run_dcf(body if isinstance(body, dict) else {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@router.get("/cases/{case_id}/report")
def export_case_report(
    case_id: int, ctx: dict[str, Any] = Depends(require_inst_user)
) -> Response:
    """FR-GLB-02/03、GAP-12：导出带演示标识的研究简报（Markdown）。"""
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "research")
    try:
        data = svc.export_research(org_id, case_id, actor_member_id=member_id)
    except Exception as exc:
        raise _handle(exc) from exc
    filename = quote(str(data["filename"]))
    return Response(
        content=str(data["content"]).encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


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


@router.get("/ai/roles")
def ai_roles(ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    """I01–I06：AI 岗位目录与可用性。"""
    _require_ws(ctx, "research")
    return {"ok": True, "items": svc.ai_role_catalog()}


@router.post("/ai/roles/{role_key}")
def ai_role_run(
    role_key: str,
    body: dict[str, Any] | None = None,
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    """执行单个 AI 岗位（只出建议，不改状态）。"""
    org_id, member_id, _ = _ctx(ctx)
    payload = body or {}
    workspace = "approvals" if role_key == "risk" else ("debate" if role_key == "debate" else "research")
    _require_ws(ctx, workspace)
    try:
        return {
            "ok": True,
            **svc.ai_role_run(
                org_id,
                role_key,
                case_id=int(payload["case_id"]) if payload.get("case_id") else None,
                proposal_id=int(payload["proposal_id"]) if payload.get("proposal_id") else None,
                actor_member_id=member_id,
            ),
        }
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


@router.get("/proposals/{proposal_id}/ai/chairman-precheck")
def chairman_precheck(
    proposal_id: int, ctx: dict[str, Any] = Depends(require_inst_user)
) -> dict[str, Any]:
    """AI Chairman 预检查：只读，返回阻断项与建议。"""
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "approvals")
    try:
        return {
            "ok": True,
            **svc.ai_chairman_precheck(org_id, proposal_id, actor_member_id=member_id),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/proposals/{proposal_id}/ai/chairman-simulate")
def chairman_simulate(
    proposal_id: int, ctx: dict[str, Any] = Depends(require_inst_user)
) -> dict[str, Any]:
    """AI 模拟批准：不写审批、不改状态，binding 恒为 false。"""
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "approvals")
    try:
        return {
            "ok": True,
            **svc.ai_chairman_simulate(org_id, proposal_id, actor_member_id=member_id),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/proposals/{proposal_id}/ai/chairman-handover")
def chairman_handover(
    proposal_id: int,
    body: dict[str, Any] | None = None,
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    """Chairman 主动移交真人流程，只写审计。"""
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "approvals")
    try:
        return svc.ai_chairman_handover(
            org_id,
            proposal_id,
            actor_member_id=member_id,
            note=str((body or {}).get("note") or "") or None,
        )
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
        direction = body.get("direction")
        target = body.get("target_weight")
        return {
            "ok": True,
            **svc.create_proposal(
                org_id,
                case_id,
                actor_member_id=member_id,
                # 方向与目标仓位的默认值由服务层按是否退出案决定（退出案默认 exit / 0）。
                direction=str(direction) if direction not in (None, "") else None,
                target_weight=float(target) if target not in (None, "") else None,
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


@router.get("/authorizations/{authorization_id}/precheck")
def authorization_precheck(
    authorization_id: int, ctx: dict[str, Any] = Depends(require_inst_user)
) -> dict[str, Any]:
    """执行前校验：授权、价格区间、现金/持仓、停牌与 ST。"""
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "execution")
    try:
        return {"ok": True, **svc.precheck_execution(org_id, authorization_id)}
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/authorizations/{authorization_id}/reconcile")
def authorization_reconcile(
    authorization_id: int, ctx: dict[str, Any] = Depends(require_inst_user)
) -> dict[str, Any]:
    """成交对账：订单/成交/持仓/现金一致性。"""
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "execution")
    try:
        return {
            "ok": True,
            **svc.reconcile_authorization(
                org_id, authorization_id, actor_member_id=member_id
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/execution/exceptions")
def execution_exceptions(
    status: str | None = None, ctx: dict[str, Any] = Depends(require_inst_user)
) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "execution")
    return {"ok": True, "items": svc.list_execution_exceptions(org_id, status=status)}


@router.post("/execution/exceptions/{exception_id}/resolve")
def resolve_execution_exception(
    exception_id: int,
    body: dict[str, Any],
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "execution")
    try:
        return {
            "ok": True,
            **svc.resolve_execution_exception(
                org_id,
                exception_id,
                status=str(body.get("status") or "resolved"),
                resolution=str(body.get("resolution") or "") or None,
                actor_member_id=member_id,
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


@router.get("/theses")
def list_theses(
    status: str | None = None, ctx: dict[str, Any] = Depends(require_inst_user)
) -> dict[str, Any]:
    org_id, _, _ = _ctx(ctx)
    _require_ws(ctx, "monitor")
    return {"ok": True, "items": svc.list_theses(org_id, status=status)}


@router.post("/theses")
def create_thesis(body: dict[str, Any], ctx: dict[str, Any] = Depends(require_inst_user)) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "monitor")
    try:
        return {
            "ok": True,
            **svc.create_thesis(
                org_id,
                company_id=int(body.get("company_id") or 0),
                thesis=str(body.get("thesis") or ""),
                proposal_id=int(body["proposal_id"]) if body.get("proposal_id") else None,
                key_assumptions=body.get("key_assumptions"),
                kpis=body.get("kpis"),
                falsifiers=body.get("falsifiers"),
                review_due=str(body.get("review_due") or "") or None,
                actor_member_id=member_id,
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/theses/{ledger_id}/review")
def review_thesis(
    ledger_id: int,
    body: dict[str, Any],
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "monitor")
    try:
        return {
            "ok": True,
            **svc.review_thesis(
                org_id,
                ledger_id,
                kpi_status=str(body.get("kpi_status") or "on_track"),
                conclusion=str(body.get("conclusion") or "hold"),
                note=str(body.get("note") or "") or None,
                actor_member_id=member_id,
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/monitor/exits/{exit_case_id}/review")
def review_exit(
    exit_case_id: int,
    body: dict[str, Any],
    ctx: dict[str, Any] = Depends(require_inst_user),
) -> dict[str, Any]:
    org_id, member_id, _ = _ctx(ctx)
    _require_ws(ctx, "monitor")
    try:
        price = body.get("realized_return")
        days = body.get("holding_days")
        return {
            "ok": True,
            **svc.review_exit(
                org_id,
                exit_case_id,
                thesis_verdict=str(body.get("thesis_verdict") or "mixed"),
                realized_return=float(price) if price is not None else None,
                holding_days=int(days) if days is not None else None,
                lessons=str(body.get("lessons") or "") or None,
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
