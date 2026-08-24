"""按职责拆分的 ResearchEngine HTTP 路由集合。"""

from fastapi import APIRouter

from app.api.routes import ai, batch, catalog, factor, health, strategy


router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(catalog.router)
router.include_router(ai.router)
router.include_router(factor.router)
router.include_router(strategy.router)
router.include_router(batch.router)

_builtin_factors = catalog._builtin_factors

__all__ = ["router", "_builtin_factors"]
