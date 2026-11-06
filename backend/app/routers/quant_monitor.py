from fastapi import APIRouter, Depends

from app.deps import require_quant_researcher
from app.routers.inst_quant import _quant_uid
from services import quant_monitor as svc

router = APIRouter(prefix="/api/inst/quant/monitor", tags=["quant-monitor"])


@router.get("/overview")
def overview(ctx=Depends(require_quant_researcher)):
    return svc.overview(_quant_uid(ctx), int(ctx["org"]["id"]))
