from fastapi import APIRouter, Depends

from app.routers.inst_quant import _quant_uid
from app.deps import require_quant_researcher
from services import quant_agents as svc

router = APIRouter(prefix="/api/inst/quant/agents", tags=["quant-agents"])


@router.get("/overview")
def overview(ctx=Depends(require_quant_researcher)):
    return svc.overview(_quant_uid(ctx), int(ctx["org"]["id"]))
