"""SVQuant FastAPI 唯一正式入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.services.daily_factor_backtest import DailyFactorBacktestCoordinator
from app.services.experiment.manager import ExperimentManager


@asynccontextmanager
async def lifespan(application: FastAPI):
    """由 FastAPI 统一拥有 Manager 与每日批量协调器的生命周期。"""

    manager: ExperimentManager = application.state.experiment_manager
    manager.start()
    try:
        yield
    finally:
        manager.shutdown()


def create_app() -> FastAPI:
    application = FastAPI(
        title="SVQuant Research API",
        version="2.0.0",
        description="因子/策略回测与已发布市场数据查询 API。",
        lifespan=lifespan,
    )
    manager = ExperimentManager(max_workers=2)
    application.state.experiment_manager = manager
    application.state.daily_factor_backtest = DailyFactorBacktestCoordinator(manager)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    application.include_router(router)
    return application


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=9527, workers=1, reload=False)


if __name__ == "__main__":
    main()
