from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.deps import require_quant_researcher
from app.routers.inst_quant import _quant_uid
from services.quant_factor.policy import WorkflowError
from services import strategy_research as svc

router = APIRouter(prefix="/api/inst/quant/strategy-research", tags=["strategy-research"])


def identity(ctx):
    return _quant_uid(ctx), int(ctx["org"]["id"])


def invoke(fn, *args):
    try:
        return fn(*args)
    except KeyError:
        raise HTTPException(404, "记录不存在或无权访问") from None
    except (ValueError, WorkflowError) as exc:
        raise HTTPException(409, str(exc)) from exc


class TopicBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    objective: str = Field(default="", max_length=3000)
    universe: str = Field(default="CSI300", max_length=50)
    benchmark: str = Field(default="CSI300", max_length=50)
    development_start: str = Field(min_length=10, max_length=10)
    development_end: str = Field(min_length=10, max_length=10)
    validation_start: str = Field(min_length=10, max_length=10)
    validation_end: str = Field(min_length=10, max_length=10)
    cost_bps: float = Field(default=10, ge=0, le=1000)
    policy_version: str = Field(default="strategy-v5-p0", min_length=1, max_length=100)
    max_trials: int = Field(ge=1, le=1000, strict=True)


class BranchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_id: str | None = Field(default=None, max_length=100)
    source: str = Field(default="manual", pattern="^(agent|manual)$")
    hypothesis: str = Field(min_length=1, max_length=3000)
    factors: list[dict] = Field(min_length=1, max_length=3)
    top_n: int = Field(ge=5, le=300, strict=True)
    rebalance_days: int = Field(ge=1, le=60, strict=True)
    buffer: float = Field(default=0, ge=0, le=1)


@router.get("/topics")
def topics(ctx=Depends(require_quant_researcher)):
    return {"topics": invoke(svc.list_topics, *identity(ctx))}


@router.post("/topics")
def topic_create(body: TopicBody, ctx=Depends(require_quant_researcher)):
    return invoke(svc.create_topic, *identity(ctx), body.model_dump())


@router.get("/topics/{tid}/ledger")
def topic_ledger(tid: str, ctx=Depends(require_quant_researcher)):
    return invoke(svc.ledger, *identity(ctx), tid)


@router.post("/topics/{tid}/branches")
def branch_create(tid: str, body: BranchBody, ctx=Depends(require_quant_researcher)):
    return invoke(svc.create_branch, *identity(ctx), tid, body.model_dump(), ("manual",))
