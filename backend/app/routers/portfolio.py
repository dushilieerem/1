from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.deps import require_quant_researcher
from app.routers.inst_quant import _quant_uid
from services import portfolio_simulation as svc

router = APIRouter(prefix="/api/inst/quant/portfolio", tags=["quant-portfolio"])


def identity(ctx):
    return _quant_uid(ctx), int(ctx["org"]["id"])


def invoke(fn, *args):
    try:
        return fn(*args)
    except KeyError:
        raise HTTPException(404, "组合不存在或无权访问") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


class Weight(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy_branch_id: str = Field(min_length=1, max_length=100)
    weight: float = Field(gt=0, le=100)


class PlanBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    capital: float = Field(gt=0)
    weights: list[Weight] = Field(min_length=1, max_length=2)
    single_limit: float = Field(default=0.1, gt=0, le=1)
    industry_limit: float = Field(default=0.3, gt=0, le=1)
    valid_from: str | None = Field(default=None, max_length=10)
    valid_to: str | None = Field(default=None, max_length=10)
    note: str = Field(default="", max_length=2000)


class ReviseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weights: list[Weight] | None = None
    name: str | None = Field(default=None, max_length=200)
    capital: float | None = Field(default=None, gt=0)
    single_limit: float | None = Field(default=None, gt=0, le=1)
    industry_limit: float | None = Field(default=None, gt=0, le=1)
    valid_from: str | None = None
    valid_to: str | None = None
    note: str = Field(default="", max_length=2000)


@router.get("/plans")
def plans(ctx=Depends(require_quant_researcher)):
    return {"plans": invoke(svc.list_plans, *identity(ctx))}


@router.post("/plans")
def plan_create(body: PlanBody, ctx=Depends(require_quant_researcher)):
    return invoke(svc.create, *identity(ctx), body.model_dump())


@router.get("/plans/{pid}")
def plan_read(pid: str, ctx=Depends(require_quant_researcher)):
    return invoke(svc.read, *identity(ctx), pid)


@router.get("/plans/{pid}/risk")
def plan_risk(pid: str, ctx=Depends(require_quant_researcher)):
    return invoke(svc.risk, *identity(ctx), pid)


@router.post("/plans/{pid}/revise")
def plan_revise(pid: str, body: ReviseBody, ctx=Depends(require_quant_researcher)):
    return invoke(svc.revise, *identity(ctx), pid, body.model_dump())


@router.post("/plans/{pid}/submit")
def plan_submit(pid: str, ctx=Depends(require_quant_researcher)):
    return invoke(svc.submit, *identity(ctx), pid)


@router.post("/plans/{pid}/approve")
def plan_approve(pid: str, ctx=Depends(require_quant_researcher)):
    return invoke(svc.approve, *identity(ctx), pid)


@router.post("/plans/{pid}/stop")
def plan_stop(pid: str, ctx=Depends(require_quant_researcher)):
    return invoke(svc.stop, *identity(ctx), pid)


@router.post("/plans/{pid}/simulate")
def plan_simulate(pid: str, ctx=Depends(require_quant_researcher)):
    return invoke(svc.simulate, *identity(ctx), pid)
