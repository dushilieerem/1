"""健康检查路由。"""

from fastapi import APIRouter

from app.schemas.backtest import HealthResponse


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version="2.0.0", engines=["native"])


__all__ = ["router"]
