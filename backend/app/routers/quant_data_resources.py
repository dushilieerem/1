from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.deps import require_quant_manager, require_quant_researcher
from app.routers.inst_quant import _quant_uid
from services import quant_data_resources as svc

router = APIRouter(prefix="/api/inst/quant/data-resources", tags=["quant-data-resources"])


def identity(ctx):
    return _quant_uid(ctx), int(ctx["org"]["id"])


def invoke(fn, *args):
    try:
        return fn(*args)
    except KeyError:
        raise HTTPException(404, "数据集或记录不存在") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except FileNotFoundError:
        raise HTTPException(503, "数据平台目录文件不可用") from None


class RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=300)
    purpose: str = Field(default="", max_length=100)
    period: str = Field(default="", max_length=200)
    frequency: str = Field(default="", max_length=100)
    fields: str = Field(default="", max_length=2000)
    related_type: str = Field(default="", max_length=50)
    related_id: str = Field(default="", max_length=100)


class RequestUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern="^(in_progress|delivered|unsupported)$")
    note: str = Field(default="", max_length=2000)
    delivered_view: str = Field(default="", max_length=100)


@router.get("/catalog")
def catalog(ctx=Depends(require_quant_researcher)):
    return invoke(svc.catalogue, *identity(ctx))


@router.get("/catalog/{name}")
def dataset(name: str, ctx=Depends(require_quant_researcher)):
    return invoke(svc.dataset, *identity(ctx), name)


@router.get("/views")
def views(ctx=Depends(require_quant_researcher)):
    return invoke(svc.views, *identity(ctx))


@router.get("/requests")
def requests(ctx=Depends(require_quant_researcher)):
    return {"requests": invoke(svc.list_requests, *identity(ctx), bool(ctx.get("can_manage")))}


@router.post("/requests")
def request_create(body: RequestBody, ctx=Depends(require_quant_researcher)):
    return invoke(svc.submit_request, *identity(ctx), body.model_dump())


@router.patch("/requests/{req_id}")
def request_update(req_id: str, body: RequestUpdateBody, ctx=Depends(require_quant_manager)):
    return invoke(svc.update_request, *identity(ctx), req_id, body.model_dump())
