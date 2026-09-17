"""SVQuant FastAPI 唯一正式入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.logging import configure_logging
from app.services.factor_backtest_batch.task_registry import FactorBacktestBatchTaskRegistry
from app.services.experiment.manager import ExperimentManager
from app.services.data.engine import DataEngine, default_market_data_dir


@asynccontextmanager
async def lifespan(application: FastAPI):
    """由 FastAPI 统一拥有 DataEngine、Manager 与批量任务的生命周期。"""

    configure_logging()
    manager: ExperimentManager = application.state.experiment_manager
    task_registry: FactorBacktestBatchTaskRegistry = (
        application.state.factor_backtest_batch_task_registry
    )
    data_engine: DataEngine = application.state.data_engine
    # 只装载数据来源；字段在因子任务按 spec 日期请求时读取，不做全量预热。
    data_engine.load_parquet(default_market_data_dir())
    manager.start()
    try:
        yield
    finally:
        # 协调线程可能正在等待 Manager 的因子 worker；必须先等它退出。
        task_registry.shutdown(wait=True)
        manager.shutdown()
        data_engine.close()


def create_app() -> FastAPI:
    application = FastAPI(
        title="SVQuant Research API",
        version="2.0.0",
        description="因子/策略回测与已发布市场数据查询 API。",
        lifespan=lifespan,
    )
    data_engine = DataEngine()
    DataEngine.configure_instance(data_engine)
    manager = ExperimentManager(max_workers=2)
    application.state.data_engine = data_engine
    application.state.experiment_manager = manager
    application.state.factor_backtest_batch_task_registry = FactorBacktestBatchTaskRegistry()
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
